"""Groq LLM provider handler, rate limit manager, and schema token budgeter.

Groq enforces rate limits across four distinct sliding windows simultaneously:
1. RPM (Requests Per Minute): typically 30 RPM (min 2.0s interval)
2. RPD (Requests Per Day): typically 14,400 RPD
3. TPM (Tokens Per Minute): typically 6,000 TPM (70B) to 20,000 TPM (8B)
4. TPD (Tokens Per Day): typically 500k-1M TPD

CRITICAL GROQ BEHAVIOR:
Groq reserves (prompt_tokens + max_tokens) against the rolling 60s TPM ceiling upfront.
If (used_tokens + prompt_tokens + max_tokens > tpm_limit), Groq immediately returns 429.
This module provides:
- Schema token budgeting: prevents sending blind 2000-4000 max_tokens
- Proactive sliding window limiter: prevents 429s by tracking tokens and requests over 60s
- Authoritative header tracking: synchronizes with x-ratelimit-* and retry-after headers
- Reactive 429 recovery: extracts exact wait times, shrinks max_tokens, and applies jittered backoff
- High-throughput fallback model: switches from 70B to 8B if TPM ceiling is persistently saturated
"""

from collections import deque
import logging
import random
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from kawach.core.config import settings

logger = logging.getLogger("kawach.llm.groq")

# Calibrated max_tokens budgets per agent schema to avoid upfront TPM reservation exhaustion
SCHEMA_TOKEN_BUDGETS: Dict[str, int] = {
    "explore_summary": 600,
    "planner": 1500,
    "planner_single": 800,
    "script_writer": 900,
    "bug_reporter": 800,
    "reviewer": 600,
    "self_healing": 750,
    "text": 1000,
}


def get_budgeted_max_tokens(schema_name: str, requested_max: Optional[int] = None) -> int:
    """Return calibrated max_tokens for the given schema to prevent upfront TPM blowouts."""
    calibrated = SCHEMA_TOKEN_BUDGETS.get(schema_name, 1000)
    if requested_max and requested_max > 0:
        return min(calibrated, requested_max)
    return calibrated


class GroqRateLimiter:
    """Thread-safe proactive sliding-window rate limiter and token budgeter for Groq API."""

    def __init__(
        self,
        rpm_limit: Optional[int] = None,
        tpm_limit: Optional[int] = None,
        min_interval: Optional[float] = None,
        window_seconds: float = 60.0,
    ):
        self.rpm_limit = rpm_limit or getattr(settings, "GROQ_RPM_LIMIT", 30)
        self.tpm_limit = tpm_limit or getattr(settings, "GROQ_TPM_LIMIT", 6000)
        self.min_interval = min_interval or getattr(settings, "GROQ_MIN_INTERVAL", 2.0)
        self.window_seconds = window_seconds

        self._lock = threading.Lock()
        self._request_times: deque[float] = deque()
        self._token_history: deque[Tuple[float, int]] = deque()
        self._last_call_time: float = 0.0

        # Authoritative server header telemetry
        self.server_remaining_tokens: Optional[int] = None
        self.server_remaining_requests: Optional[int] = None
        self.server_reset_tokens_s: Optional[float] = None

    def _prune(self, now: float) -> None:
        """Remove request and token records older than window_seconds."""
        cutoff = now - self.window_seconds
        while self._request_times and self._request_times[0] < cutoff:
            self._request_times.popleft()
        while self._token_history and self._token_history[0][0] < cutoff:
            self._token_history.popleft()

    def get_current_window_usage(self) -> Tuple[int, int]:
        """Return (requests_in_window, tokens_in_window)."""
        with self._lock:
            now = time.time()
            self._prune(now)
            rpm = len(self._request_times)
            tpm = sum(tok for _, tok in self._token_history)
            return rpm, tpm

    def acquire(
        self,
        est_prompt_tokens: int,
        max_tokens: int,
        schema_name: str = "text",
    ) -> Tuple[int, float]:
        """Proactively throttle and clamp tokens before issuing request to Groq.

        Returns (clamped_max_tokens, seconds_waited).
        """
        waited_total = 0.0

        with self._lock:
            # 1. Enforce minimum request spacing (anti-burst pacing)
            now = time.time()
            elapsed_since_last = now - self._last_call_time
            if elapsed_since_last < self.min_interval:
                pace_sleep = self.min_interval - elapsed_since_last
                time.sleep(pace_sleep)
                waited_total += pace_sleep
                now = time.time()

            # 2. Prune old records
            self._prune(now)

            # 3. Dynamic max_tokens clamping against absolute TPM limit
            budgeted = get_budgeted_max_tokens(schema_name, max_tokens)
            effective_max_tokens = budgeted

            # If prompt + budgeted exceeds total TPM limit, clamp max_tokens to headroom
            if est_prompt_tokens + effective_max_tokens > self.tpm_limit:
                headroom = max(150, self.tpm_limit - est_prompt_tokens - 50)
                effective_max_tokens = min(effective_max_tokens, headroom)
                logger.debug(
                    f"Clamped max_tokens to {effective_max_tokens} (prompt={est_prompt_tokens}, limit={self.tpm_limit})"
                )

            # 4. Proactive sliding window RPM throttle
            if len(self._request_times) >= self.rpm_limit:
                oldest_req = self._request_times[0]
                rpm_wait = max(0.1, (oldest_req + self.window_seconds) - now + 0.1)
                logger.info(
                    f"Groq RPM quota reached ({len(self._request_times)}/{self.rpm_limit}). Proactively waiting {rpm_wait:.2f}s..."
                )
                time.sleep(rpm_wait)
                waited_total += rpm_wait
                now = time.time()
                self._prune(now)

            # 5. Proactive sliding window TPM throttle
            current_window_tokens = sum(tok for _, tok in self._token_history)
            needed_tokens = est_prompt_tokens + effective_max_tokens

            # Check if server headers report lower remaining tokens
            effective_remaining = self.tpm_limit - current_window_tokens
            if self.server_remaining_tokens is not None:
                effective_remaining = min(effective_remaining, self.server_remaining_tokens)

            if needed_tokens > effective_remaining and self._token_history:
                # Calculate how long until enough token entries expire from the window
                freed = 0
                tokens_to_free = needed_tokens - effective_remaining
                tpm_wait = 1.0

                for t_time, t_count in self._token_history:
                    freed += t_count
                    if freed >= tokens_to_free:
                        tpm_wait = max(0.1, (t_time + self.window_seconds) - now + 0.2)
                        break

                logger.info(
                    f"Groq TPM quota constrained (needed={needed_tokens}, remaining={effective_remaining}). "
                    f"Proactively waiting {tpm_wait:.2f}s..."
                )
                time.sleep(tpm_wait)
                waited_total += tpm_wait
                now = time.time()
                self._prune(now)

            # Record request reservation
            self._last_call_time = time.time()
            self._request_times.append(self._last_call_time)
            # Optimistically record estimated tokens until actual usage arrives
            self._token_history.append((self._last_call_time, needed_tokens))

            return effective_max_tokens, waited_total

    def record_actual_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Correct the latest estimated token reservation with actual observed token count."""
        with self._lock:
            total_actual = input_tokens + output_tokens
            if self._token_history:
                latest_time, _ = self._token_history.pop()
                self._token_history.append((latest_time, total_actual))

    def update_from_headers(self, headers: Any) -> None:
        """Update client telemetry directly from Groq's authoritative HTTP response headers."""
        if not headers:
            return

        with self._lock:
            # Handle dictionary or httpx.Headers
            get_h = headers.get if hasattr(headers, "get") else lambda k, d=None: getattr(headers, k, d)

            rem_tokens = get_h("x-ratelimit-remaining-tokens")
            rem_reqs = get_h("x-ratelimit-remaining-requests")
            reset_tok = get_h("x-ratelimit-reset-tokens")

            if rem_tokens is not None:
                try:
                    self.server_remaining_tokens = int(rem_tokens)
                except ValueError:
                    pass

            if rem_reqs is not None:
                try:
                    self.server_remaining_requests = int(rem_reqs)
                except ValueError:
                    pass

            if reset_tok is not None:
                try:
                    # Formats can be '5.2s' or float
                    clean_reset = str(reset_tok).rstrip("s")
                    self.server_reset_tokens_s = float(clean_reset)
                except ValueError:
                    pass


# Singleton rate limiter instance
_global_groq_limiter: Optional[GroqRateLimiter] = None
_limiter_init_lock = threading.Lock()


def get_groq_rate_limiter() -> GroqRateLimiter:
    """Return process-wide GroqRateLimiter singleton."""
    global _global_groq_limiter
    if _global_groq_limiter is None:
        with _limiter_init_lock:
            if _global_groq_limiter is None:
                _global_groq_limiter = GroqRateLimiter()
    return _global_groq_limiter


def parse_429_error(exc: Exception, prompt_len_estimate: int = 200) -> Tuple[float, Optional[int]]:
    """Parse HTTP 429 exception for wait seconds and dynamic max_tokens recommendation.

    Returns (wait_seconds, recommended_max_tokens).
    """
    err_str = str(exc)
    wait_seconds = 6.0
    recommended_max_tokens: Optional[int] = None

    # 1. Parse retry-after from exception or response headers
    if hasattr(exc, "response") and exc.response is not None:
        headers = getattr(exc.response, "headers", {})
        retry_after = headers.get("retry-after") if hasattr(headers, "get") else None
        if retry_after:
            try:
                wait_seconds = float(retry_after)
            except ValueError:
                pass

    # 2. Parse 'try again in Xs' from message
    time_match = re.search(r"try again in ([\d\.]+)s", err_str, re.IGNORECASE)
    if time_match:
        try:
            wait_seconds = float(time_match.group(1))
        except ValueError:
            pass

    # 3. Parse 'Limit X, Requested Y' to diagnose token reservation blowout
    limit_match = re.search(r"Limit\s+(\d+),\s*(?:Used\s+(\d+),\s*)?Requested\s+(\d+)", err_str, re.IGNORECASE)
    if limit_match:
        try:
            limit_val = int(limit_match.group(1))
            requested_val = int(limit_match.group(3))
            if requested_val >= limit_val:
                # The request itself was too large for the limit; shrink max_tokens
                headroom = max(150, limit_val - prompt_len_estimate - 50)
                recommended_max_tokens = headroom
                logger.warning(
                    f"Groq 429 reservation blowout: requested={requested_val} exceeds limit={limit_val}. "
                    f"Shrinking max_tokens to {recommended_max_tokens}."
                )
        except Exception:
            pass

    # Add 0.5s jitter to avoid thundering-herd collisions
    jitter = random.uniform(0.3, 0.8)
    return wait_seconds + jitter, recommended_max_tokens


class GroqHandler:
    """Provider handler managing complete execution, pacing, budgeting, and 429 recovery for Groq."""

    def __init__(
        self,
        client_getter: Callable[[], Any],
        rate_limiter: Optional[GroqRateLimiter] = None,
    ):
        self.client_getter = client_getter
        self.rate_limiter = rate_limiter or get_groq_rate_limiter()

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.2,
        is_json: bool = False,
        schema_name: str = "text",
        run_id: Optional[str] = None,
        max_attempts: int = 5,
    ) -> Tuple[str, int, int]:
        active_model = model or getattr(settings, "GROQ_DEFAULT_MODEL", "qwen/qwen3.8-27b")
        # Guard against leftover model names from other providers (e.g., claude, gpt)
        if (
            not active_model
            or "claude" in active_model.lower()
            or "gpt" in active_model.lower()
            or "llama-3" in active_model.lower()
        ):
            active_model = getattr(settings, "GROQ_DEFAULT_MODEL", "qwen/qwen3.8-27b")

        fallback_model = getattr(settings, "GROQ_FALLBACK_MODEL", "qwen/qwen3.8-27b")

        est_prompt_tokens = len(system + prompt) // 4
        current_max_tokens = max_tokens
        last_exception: Optional[Exception] = None

        for attempt in range(max_attempts):
            # 1. Proactive rate limiting and token clamping
            clamped_max_tokens, _ = self.rate_limiter.acquire(
                est_prompt_tokens=est_prompt_tokens,
                max_tokens=current_max_tokens,
                schema_name=schema_name,
            )

            client = self.client_getter()
            kwargs: Dict[str, Any] = {
                "model": active_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": clamped_max_tokens,
            }
            if is_json:
                kwargs["response_format"] = {"type": "json_object"}

            try:
                # Execute completion via OpenAI-compatible Groq API
                resp = client.chat.completions.create(**kwargs)

                # Extract response text and usage
                text = resp.choices[0].message.content or ""
                in_tok = resp.usage.prompt_tokens if resp.usage else est_prompt_tokens
                out_tok = resp.usage.completion_tokens if resp.usage else (len(text) // 4)

                # Update rate limiter with actual usage and headers if accessible
                self.rate_limiter.record_actual_usage(in_tok, out_tok)
                if hasattr(resp, "_raw_response") and hasattr(resp._raw_response, "headers"):
                    self.rate_limiter.update_from_headers(resp._raw_response.headers)

                return text, in_tok, out_tok

            except Exception as exc:
                last_exception = exc
                err_msg = str(exc).lower()

                # Critical auth / bad request errors should fail immediately
                if (
                    "authentication" in err_msg
                    or "invalid api key" in err_msg
                    or "unauthorized" in err_msg
                    or "401" in err_msg
                ):
                    from kawach.llm.client import LLMError
                    raise LLMError(f"Groq API authentication failed: {exc}")

                is_rate_limit = (
                    "429" in err_msg
                    or "rate limit" in err_msg
                    or "tpm" in err_msg
                    or "tokens per minute" in err_msg
                    or "too many requests" in err_msg
                )

                if is_rate_limit and attempt < max_attempts - 1:
                    wait_s, suggested_tokens = parse_429_error(exc, est_prompt_tokens)
                    if suggested_tokens:
                        current_max_tokens = suggested_tokens

                    # If model is 70B and repeated rate limits occur, fall back to high-throughput 8B model
                    if attempt >= 1 and active_model != fallback_model and fallback_model:
                        logger.warning(
                            f"Persistent Groq 429 on {active_model}. Falling back to high-capacity model {fallback_model}."
                        )
                        active_model = fallback_model

                    logger.warning(
                        f"Groq 429 Rate Limit hit (attempt {attempt + 1}/{max_attempts}). "
                        f"Waiting {wait_s:.2f}s before retry..."
                    )
                    time.sleep(wait_s)
                    continue

                if attempt < max_attempts - 1:
                    backoff = [1.0, 2.5, 5.0, 10.0][min(attempt, 3)]
                    time.sleep(backoff)
                    continue

                break

        from kawach.llm.client import LLMError
        raise LLMError(f"Groq provider failed after {max_attempts} attempts: {last_exception}")
