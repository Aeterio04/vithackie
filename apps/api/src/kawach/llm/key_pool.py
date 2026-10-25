"""Strict round-robin multi-key pool for Groq LLM provider.

Implements:
- Strict round-robin across N keys (call 1 -> K1, call 2 -> K2, call 3 -> K3, call 4 -> K1)
- Immediate rollover on HTTP 429 without sleeping when an alternate key is available
- Bounded wait with jitter when all keys are cooling down (max 6 passes, 120s cap)
- Auth failure (401/403) auto-disabling with masked ID logging
- Network/5xx backoff with key rotation
- Header-based rate limit synchronization and proactive throttling
- Per-run metrics and protected pool status inspection
- Absolute privacy: keys are NEVER logged, printed, or returned in status endpoints
"""

import json
import logging
import os
import random
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("kawach.llm.key_pool")


class LLMError(Exception):
    """Base exception for LLM operations."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when all LLM keys are cooling down and wait caps are exceeded."""
    pass


def parse_reset_duration(val: Union[str, float, int, None]) -> Optional[float]:
    """Parse duration strings like '250ms', '1m30s', '2.5s', '60' into seconds."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return max(0.0, float(val))

    s = str(val).strip()
    if not s:
        return None

    # Plain float/int string
    try:
        return max(0.0, float(s))
    except ValueError:
        pass

    total_seconds = 0.0
    matched = False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(ms|h|m|s)", s, re.IGNORECASE):
        matched = True
        v = float(num)
        u = unit.lower()
        if u == "h":
            total_seconds += v * 3600.0
        elif u == "m":
            total_seconds += v * 60.0
        elif u == "s":
            total_seconds += v
        elif u == "ms":
            total_seconds += v / 1000.0

    return total_seconds if matched else None


def is_daily_limit_message(msg: str) -> bool:
    """Detect if an error message refers to a daily quota (TPD / RPD)."""
    m = msg.lower()
    return any(
        term in m
        for term in (
            "per day",
            "daily limit",
            "tpd",
            "rpd",
            "tokens per day",
            "requests per day",
            "day limit",
        )
    )


def mask_key(index: int, key: str) -> str:
    """Format key into masked identifier 'key#k ...last4'. Never shows key secret."""
    clean = key.strip() if key else ""
    suffix = clean[-4:] if len(clean) >= 4 else "xxxx"
    return f"key#{index + 1} ...{suffix}"


class KeyEntry:
    """Represents a single Groq API key and its runtime health state."""

    def __init__(self, index: int, key: str, client_factory: Optional[Callable[[str], Any]] = None):
        self.index: int = index
        self.key: str = key.strip()
        self.masked_id: str = mask_key(index, self.key)
        self.client_factory = client_factory or self._default_client_factory
        self._client: Optional[Any] = None

        # Health & Rotation state
        self.cooldown_until: float = 0.0
        self.consecutive_failures: int = 0
        self.disabled: bool = False
        self.disable_reason: Optional[str] = None

        # Counters & telemetry
        self.requests: int = 0
        self.rate_limits_429: int = 0
        self.tokens_used: int = 0
        self.last_used: float = 0.0
        self.remaining_tokens: Optional[int] = None
        self.remaining_requests: Optional[int] = None

    @staticmethod
    def _default_client_factory(api_key: str) -> Any:
        import openai
        return openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self.client_factory(self.key)
        return self._client

    def is_available(self, now: float) -> bool:
        return not self.disabled and self.cooldown_until <= now

    def seconds_until_ready(self, now: float) -> float:
        if self.disabled:
            return 0.0
        return max(0.0, round(self.cooldown_until - now, 2))

    def get_state(self, now: float) -> str:
        if self.disabled:
            return "disabled"
        if self.cooldown_until > now:
            return "cooling"
        return "ready"


class KeyPool:
    """Multi-key pool managing strict round-robin rotation, 429 failover, and rate limiting."""

    def __init__(
        self,
        keys: Optional[List[str]] = None,
        client_factory: Optional[Callable[[str], Any]] = None,
        state_file: Optional[str] = None,
    ):
        self._lock = threading.Lock()
        self._client_factory = client_factory
        self.state_file = state_file

        raw_keys = keys if keys is not None else self._discover_keys()
        # De-duplicate preserving order, drop empties
        deduped: List[str] = []
        for k in raw_keys:
            clean = k.strip() if k else ""
            if clean and clean not in deduped:
                deduped.append(clean)

        self.keys: List[KeyEntry] = [
            KeyEntry(idx, k, client_factory=client_factory)
            for idx, k in enumerate(deduped)
        ]
        self._rotation_counter: int = 0

        logger.info("LLM key pool ready: %d keys", len(self.keys))

    @staticmethod
    def _discover_keys() -> List[str]:
        """Discover Groq API keys in priority order:
        1. GROQ_API_KEYS (comma-separated)
        2. GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3...
        3. GROQ_API_KEY (legacy)
        """
        from kawach.core.config import settings

        raw_keys: List[str] = []

        # 1. Comma-separated list from env or settings
        env_list = os.environ.get("GROQ_API_KEYS", "").strip() or getattr(settings, "GROQ_API_KEYS", "").strip()
        if env_list:
            raw_keys.extend([k.strip() for k in env_list.split(",") if k.strip()])

        # 2. Numbered keys GROQ_API_KEY_1..N from settings and env
        if not raw_keys:
            numbered: List[Tuple[int, str]] = []
            for i in range(1, 10):
                val = getattr(settings, f"GROQ_API_KEY_{i}", "")
                if val and val.strip():
                    numbered.append((i, val.strip()))
            for env_k, env_v in os.environ.items():
                m = re.match(r"^GROQ_API_KEY_(\d+)$", env_k)
                if m and env_v and env_v.strip():
                    idx = int(m.group(1))
                    if not any(n[0] == idx for n in numbered):
                        numbered.append((idx, env_v.strip()))
            numbered.sort(key=lambda x: x[0])
            raw_keys.extend([k for _, k in numbered])

        # 3. Legacy single key
        if not raw_keys:
            legacy = (
                getattr(settings, "GROQ_API_KEY", "").strip()
                or os.environ.get("GROQ_API_KEY", "").strip()
                or os.environ.get("OPENAI_API_KEY", "").strip()
            )
            if legacy:
                raw_keys.append(legacy)

        return raw_keys

    def size(self) -> int:
        return len(self.keys)

    def get_pool_status(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Return safe telemetry on all keys in the pool without revealing secrets."""
        current = now if now is not None else time.time()
        with self._lock:
            key_statuses = [
                {
                    "masked_id": k.masked_id,
                    "state": k.get_state(current),
                    "seconds_until_ready": k.seconds_until_ready(current),
                    "requests": k.requests,
                    "rate_limits_429": k.rate_limits_429,
                }
                for k in self.keys
            ]
            return {
                "total_keys": len(self.keys),
                "keys": key_statuses,
            }

    def _select_next_key(self, now: float) -> Tuple[Optional[KeyEntry], Optional[float]]:
        """Atomically pick the next available key in strict round-robin order.

        Returns (key, earliest_cooldown_duration). If no key is ready, returns
        (None, seconds_until_earliest_ready).
        """
        if not self.keys:
            return None, None

        n = len(self.keys)
        start_idx = self._rotation_counter % n

        # Check for any available key starting from start_idx
        for offset in range(n):
            cand_idx = (start_idx + offset) % n
            cand = self.keys[cand_idx]
            if cand.is_available(now):
                # Strict round-robin: advance pointer to start next call AFTER this one
                self._rotation_counter = (cand_idx + 1) % n
                return cand, None

        # All keys are cooling down or disabled
        enabled_keys = [k for k in self.keys if not k.disabled]
        if not enabled_keys:
            return None, None

        earliest_cd = min(k.cooldown_until for k in enabled_keys)
        wait_seconds = max(0.0, earliest_cd - now)
        return None, wait_seconds

    def handle_rate_limit(
        self,
        key: KeyEntry,
        exc: Exception,
        now: float,
    ) -> float:
        """Handle 429 / quota error on key, setting cooldown and updating counters."""
        key.rate_limits_429 += 1
        key.consecutive_failures += 1

        err_str = str(exc)
        cooldown_duration = 25.0  # Default 25s bounded cooldown

        # Check response headers if present
        headers = {}
        if hasattr(exc, "response") and exc.response is not None:
            headers = getattr(exc.response, "headers", {})

        get_h = headers.get if hasattr(headers, "get") else lambda k, d=None: getattr(headers, k, d)
        retry_after = get_h("retry-after")
        reset_reqs = get_h("x-ratelimit-reset-requests")
        reset_tokens = get_h("x-ratelimit-reset-tokens")

        parsed_h = (
            parse_reset_duration(retry_after)
            or parse_reset_duration(reset_tokens)
            or parse_reset_duration(reset_reqs)
        )
        if parsed_h is not None and parsed_h > 0:
            cooldown_duration = parsed_h
        else:
            # Check message body: "try again in 22.4s"
            m = re.search(r"try again in ([\d\.]+)s", err_str, re.IGNORECASE)
            if m:
                try:
                    cooldown_duration = float(m.group(1))
                except ValueError:
                    pass

        # Check if daily limit
        if is_daily_limit_message(err_str):
            cooldown_duration = max(600.0, cooldown_duration)  # At least 10 minutes
            cooldown_duration = min(86400.0, cooldown_duration)
            logger.warning(
                "Key %s hit daily rate/quota limit. Cooldown set to %.1fs.",
                key.masked_id,
                cooldown_duration,
            )
        else:
            # Standard TPM/RPM limit: cap at 5 minutes
            cooldown_duration = min(300.0, max(0.01, cooldown_duration))
            logger.info(
                "Key %s rate limited (429). Cooldown set to %.1fs. Failing over immediately.",
                key.masked_id,
                cooldown_duration,
            )

        key.cooldown_until = now + cooldown_duration
        return cooldown_duration

    def handle_auth_failure(self, key: KeyEntry, exc: Exception) -> None:
        """Disable a key permanently upon 401/403 authorization error."""
        key.disabled = True
        key.disable_reason = "auth_failure"
        logger.info("key #%d disabled (auth) (%s)", key.index + 1, key.masked_id)

    def record_success(self, key: KeyEntry, in_tok: int, out_tok: int, headers: Any = None) -> None:
        """Record successful invocation and evaluate proactive throttling headers."""
        key.requests += 1
        key.consecutive_failures = 0
        key.tokens_used += (in_tok + out_tok)
        key.last_used = time.time()

        if headers:
            get_h = headers.get if hasattr(headers, "get") else lambda k, d=None: getattr(headers, k, d)
            rem_tok = get_h("x-ratelimit-remaining-tokens")
            rem_req = get_h("x-ratelimit-remaining-requests")
            reset_tok = get_h("x-ratelimit-reset-tokens")

            try:
                if rem_tok is not None:
                    key.remaining_tokens = int(rem_tok)
                if rem_req is not None:
                    key.remaining_requests = int(rem_req)
            except (ValueError, TypeError):
                pass

            # Proactive throttling: if tokens or requests almost exhausted, set short cooldown
            reset_s = parse_reset_duration(reset_tok) or 2.0
            if (key.remaining_tokens is not None and key.remaining_tokens < 200) or (
                key.remaining_requests is not None and key.remaining_requests <= 1
            ):
                short_cd = max(1.0, min(reset_s, 10.0))
                key.cooldown_until = time.time() + short_cd
                logger.debug(
                    "Proactive throttling on %s: remaining tokens=%s, requests=%s. Cooldown=%.1fs",
                    key.masked_id,
                    key.remaining_tokens,
                    key.remaining_requests,
                    short_cd,
                )


# Global singleton instance
_global_pool: Optional[KeyPool] = None
_pool_lock = threading.Lock()


def get_key_pool() -> KeyPool:
    """Return process-wide KeyPool singleton."""
    global _global_pool
    if _global_pool is None:
        with _pool_lock:
            if _global_pool is None:
                _global_pool = KeyPool()
    return _global_pool


def set_global_key_pool(pool: KeyPool) -> None:
    """Set process-wide KeyPool (useful for tests and dependency injection)."""
    global _global_pool
    with _pool_lock:
        _global_pool = pool


def complete_with_pool(
    *,
    system: str = "",
    prompt: str = "",
    messages: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    max_tokens: int = 1000,
    temperature: float = 0.2,
    is_json: bool = False,
    response_format: Optional[Dict[str, Any]] = None,
    schema_name: str = "text",
    run_id: Optional[str] = None,
    stream: bool = False,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Any] = None,
    pool: Optional[KeyPool] = None,
    time_fn: Callable[[], float] = time.time,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Union[Tuple[str, int, int], Any]:
    """Single central wrapper for all Groq LLM calls.

    Strict round-robin with immediate rollover on 429, retry limits, and observability.
    Returns (text, in_tokens, out_tokens) when stream=False, or stream response object.
    """
    key_pool = pool or get_key_pool()
    if key_pool.size() == 0:
        raise LLMError("Missing or invalid API key for provider groq (GROQ_API_KEY not set)")

    # Prepare message payload
    if messages is not None:
        call_messages = list(messages)
    else:
        call_messages = []
        if system:
            call_messages.append({"role": "system", "content": system})
        if prompt:
            call_messages.append({"role": "user", "content": prompt})

    # Prepare model
    from kawach.core.config import settings
    active_model = model or getattr(settings, "LLM_MODEL", None) or getattr(settings, "GROQ_DEFAULT_MODEL", "qwen/qwen3.8-27b")
    if not active_model or "claude" in active_model.lower() or "gpt" in active_model.lower():
        active_model = getattr(settings, "LLM_MODEL", None) or getattr(settings, "GROQ_DEFAULT_MODEL", "qwen/qwen3.8-27b")

    # Prepare kwargs
    base_kwargs: Dict[str, Any] = {
        "model": active_model,
        "messages": call_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if is_json:
        base_kwargs["response_format"] = {"type": "json_object"}
    elif response_format:
        base_kwargs["response_format"] = response_format

    if tools:
        base_kwargs["tools"] = tools
    if tool_choice:
        base_kwargs["tool_choice"] = tool_choice
    if stream:
        base_kwargs["stream"] = True

    # Pacing / retry bounds
    max_passes = 6
    total_wait_cap = 120.0
    accumulated_wait = 0.0
    passes_completed = 0
    keys_tried_this_pass = 0
    total_keys = key_pool.size()

    while True:
        now = time_fn()

        with key_pool._lock:
            selected_key, wait_seconds = key_pool._select_next_key(now)

        if selected_key is None:
            # Check if all keys disabled
            all_disabled = all(k.disabled for k in key_pool.keys)
            if all_disabled:
                raise LLMError("All Groq API keys are disabled due to authentication errors.")

            # All keys cooling down: bounded sleep until earliest
            wait = wait_seconds if wait_seconds is not None else 1.0
            jitter = random.uniform(0.5, 1.5) if wait >= 1.0 else (wait * 0.1)
            sleep_duration = wait + jitter

            accumulated_wait += sleep_duration
            passes_completed += 1

            if passes_completed > max_passes or accumulated_wait > total_wait_cap:
                raise LLMRateLimitError(
                    f"All {total_keys} Groq API keys are rate-limited. "
                    f"Earliest key ready in {wait:.1f}s. "
                    f"Exceeded wait cap ({total_wait_cap}s) or max passes ({max_passes})."
                )

            logger.info(
                "All %d Groq keys cooling down. Waiting %.2fs (earliest cooldown in %.2fs)...",
                total_keys,
                sleep_duration,
                wait,
            )
            # Record wait duration in run metrics if applicable
            _record_key_wait(run_id, sleep_duration)
            sleep_fn(sleep_duration)
            keys_tried_this_pass = 0
            continue

        # Execute call with selected key
        logger.debug(
            "Calling Groq LLM with %s for schema '%s' (model=%s, max_tokens=%d)",
            selected_key.masked_id,
            schema_name,
            active_model,
            max_tokens,
        )

        try:
            client = selected_key.client
            try:
                resp = client.chat.completions.create(**base_kwargs)
            except Exception as param_err:
                # Handle provider param difference if max_completion_tokens is enforced
                if "max_completion_tokens" in str(param_err).lower():
                    kwargs_copy = dict(base_kwargs)
                    tok = kwargs_copy.pop("max_tokens", max_tokens)
                    kwargs_copy["max_completion_tokens"] = tok
                    resp = client.chat.completions.create(**kwargs_copy)
                else:
                    raise param_err

            # Handle streaming
            if stream:
                key_pool.record_success(selected_key, 0, 0)
                _record_key_call(run_id, selected_key.masked_id)
                return resp

            text = resp.choices[0].message.content or ""
            in_tok = resp.usage.prompt_tokens if hasattr(resp, "usage") and resp.usage else (len(str(call_messages)) // 4)
            out_tok = resp.usage.completion_tokens if hasattr(resp, "usage") and resp.usage else (len(text) // 4)

            raw_headers = getattr(resp, "_raw_response", None)
            headers = getattr(raw_headers, "headers", None) if raw_headers else None

            key_pool.record_success(selected_key, in_tok, out_tok, headers)
            _record_key_call(run_id, selected_key.masked_id)

            return text, in_tok, out_tok

        except Exception as exc:
            err_msg = str(exc).lower()
            status_code = getattr(exc, "status_code", None)
            if status_code is None and hasattr(exc, "response") and exc.response is not None:
                status_code = getattr(exc.response, "status_code", None)

            # 1. Auth failure (401/403)
            if status_code in (401, 403) or "unauthorized" in err_msg or "invalid api key" in err_msg or "authentication" in err_msg:
                with key_pool._lock:
                    key_pool.handle_auth_failure(selected_key, exc)
                # Continue immediately to next key
                continue

            # 2. Bad Request (400, 422) - NOT retried
            if status_code in (400, 422) and "rate limit" not in err_msg:
                raise LLMError(f"Groq API bad request ({status_code}): {exc}")

            # 3. Rate Limit / Quota (429)
            is_429 = (
                status_code == 429
                or "429" in err_msg
                or "rate limit" in err_msg
                or "tokens per minute" in err_msg
                or "tpm" in err_msg
                or "too many requests" in err_msg
                or is_daily_limit_message(err_msg)
            )
            if is_429:
                with key_pool._lock:
                    key_pool.handle_rate_limit(selected_key, exc, time_fn())
                _record_key_429(run_id)
                keys_tried_this_pass += 1
                if keys_tried_this_pass >= total_keys:
                    passes_completed += 1
                    keys_tried_this_pass = 0
                if passes_completed >= 2:
                    fallback_model = getattr(settings, "GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
                    if fallback_model and base_kwargs["model"] != fallback_model:
                        base_kwargs["model"] = fallback_model
                # Immediate rollover to next key (no sleep!)
                continue

            # 4. Network timeout / 5xx
            is_transient = (
                (status_code is not None and status_code >= 500)
                or "timeout" in err_msg
                or "connection" in err_msg
                or "temporarily unavailable" in err_msg
            )
            if is_transient:
                selected_key.consecutive_failures += 1
                if selected_key.consecutive_failures <= 3:
                    backoff = (2 ** selected_key.consecutive_failures) * 0.25 + random.uniform(0.1, 0.4)
                    sleep_fn(backoff)
                    continue

            # Unhandled error
            raise LLMError(f"Groq API error on key {selected_key.masked_id}: {exc}")


def _record_key_call(run_id: Optional[str], masked_id: str) -> None:
    """Record a key call in the run's llm_usage.json."""
    if not run_id:
        return
    try:
        from kawach.storage.artifacts import run_dir
        usage_file = run_dir(run_id) / "llm_usage.json"
        if not usage_file.exists():
            return
        with open(usage_file, "r+", encoding="utf-8") as f:
            data = json.load(f)
            key_calls = data.setdefault("keyCalls", {})
            key_calls[masked_id] = key_calls.get(masked_id, 0) + 1
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
    except Exception:
        pass


def _record_key_429(run_id: Optional[str]) -> None:
    """Increment the 429 count in the run's llm_usage.json."""
    if not run_id:
        return
    try:
        from kawach.storage.artifacts import run_dir
        usage_file = run_dir(run_id) / "llm_usage.json"
        if not usage_file.exists():
            return
        with open(usage_file, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["rateLimits429"] = data.get("rateLimits429", 0) + 1
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
    except Exception:
        pass


def _record_key_wait(run_id: Optional[str], wait_seconds: float) -> None:
    """Record rate limit wait seconds in the run's llm_usage.json."""
    if not run_id:
        return
    try:
        from kawach.storage.artifacts import run_dir
        usage_file = run_dir(run_id) / "llm_usage.json"
        if not usage_file.exists():
            return
        with open(usage_file, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["rateLimitWaitSeconds"] = round(data.get("rateLimitWaitSeconds", 0.0) + wait_seconds, 2)
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
    except Exception:
        pass
