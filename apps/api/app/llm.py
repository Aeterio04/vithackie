"""LLM client, cache, and cost tracking with multi-provider support.

Supported providers: groq, openai, anthropic, fake.
Implemented by Track B.
"""

import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from app.config import settings
from app.models import LlmUsage
from app.storage import run_dir

_usage_lock = threading.RLock()
_singleton_lock = threading.Lock()
_groq_pace_lock = threading.Lock()
_groq_last_call_time = 0.0
_llm_instance: Optional["LLM"] = None


class LLMError(Exception):
    """Base exception for all LLM client errors."""
    pass


class LLM:
    """LLM client supporting Groq, OpenAI, Anthropic, and offline Fake providers."""

    def __init__(self) -> None:
        self.cache_dir: Path = settings.repo_root / "apps" / "api" / ".llm_cache"
        if settings.LLM_CACHE in ("on", "readonly"):
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._provider = settings.LLM_PROVIDER.lower()
        self._openai_client = None
        self._groq_client = None
        self._anthropic_client = None

    def _get_groq_client(self):
        if self._groq_client is None:
            try:
                import openai
            except ImportError:
                raise LLMError("openai package is required for groq provider. Install openai>=1.0.0")

            api_key = os.getenv("GROQ_API_KEY") or settings.OPENAI_API_KEY
            if not api_key:
                raise LLMError("Missing or invalid API key for provider groq (GROQ_API_KEY not set)")
            self._groq_client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        return self._groq_client

    def _get_openai_client(self):
        if self._openai_client is None:
            try:
                import openai
            except ImportError:
                raise LLMError("openai package is required for openai provider. Install openai>=1.0.0")

            api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                raise LLMError("Missing or invalid API key for provider openai")
            self._openai_client = openai.OpenAI(api_key=api_key)
        return self._openai_client

    def _get_anthropic_client(self):
        if self._anthropic_client is None:
            try:
                import anthropic
            except ImportError:
                raise LLMError("anthropic package is required for anthropic provider.")

            api_key = settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise LLMError("Missing or invalid API key for provider anthropic")
            self._anthropic_client = anthropic.Anthropic(api_key=api_key)
        return self._anthropic_client

    # --- Cache helpers ---

    def _cache_key(
        self,
        *,
        provider: str,
        model: str,
        system: str,
        prompt: str,
        schema_name: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        payload = {
            "max_tokens": max_tokens,
            "model": model,
            "prompt": prompt,
            "provider": provider,
            "schema_name": schema_name,
            "system": system,
            "temperature": temperature,
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _check_cache(self, key: str) -> Optional[Tuple[str, int, int]]:
        if settings.LLM_CACHE not in ("on", "readonly"):
            return None
        cache_file = self.cache_dir / f"{key}.json"
        if not cache_file.exists():
            return None
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return (data["text"], data.get("inputTokens", 0), data.get("outputTokens", 0))
        except Exception:
            return None

    def _write_cache(self, key: str, text: str, input_tokens: int, output_tokens: int) -> None:
        if settings.LLM_CACHE != "on":
            return
        cache_file = self.cache_dir / f"{key}.json"
        temp_file = cache_file.with_suffix(f".tmp.{secrets.token_hex(4)}")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "text": text,
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                    },
                    f,
                    ensure_ascii=False,
                )
                f.flush()
                os.fsync(f.fileno())
            
            replaced = False
            for attempt in range(8):
                try:
                    os.replace(temp_file, cache_file)
                    replaced = True
                    break
                except (PermissionError, OSError):
                    time.sleep(0.03 * (attempt + 1))
            if not replaced:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "text": text,
                                "inputTokens": input_tokens,
                                "outputTokens": output_tokens,
                            },
                            f,
                            ensure_ascii=False,
                        )
                except Exception:
                    pass
        except Exception:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    # --- Usage tracking ---

    def _record_usage(
        self,
        run_id: Optional[str],
        input_tokens: int,
        output_tokens: int,
        is_cache_hit: bool,
    ) -> None:
        if not run_id:
            return

        with _usage_lock:
            usage_file = run_dir(run_id) / "llm_usage.json"
            cur_usage = {
                "calls": 0,
                "cacheHits": 0,
                "inputTokens": 0,
                "outputTokens": 0,
                "costUsd": 0.0,
            }

            if usage_file.exists():
                try:
                    with open(usage_file, "r", encoding="utf-8") as f:
                        cur_usage = json.load(f)
                except Exception:
                    pass

            cur_usage["calls"] += 1
            if is_cache_hit:
                cur_usage["cacheHits"] += 1

            # A cache hit still counts its ORIGINAL tokens and cost
            cur_usage["inputTokens"] += input_tokens
            cur_usage["outputTokens"] += output_tokens

            cost = (input_tokens * settings.LLM_PRICE_IN_PER_MTOK / 1e6) + (
                output_tokens * settings.LLM_PRICE_OUT_PER_MTOK / 1e6
            )
            cur_usage["costUsd"] = round(cur_usage.get("costUsd", 0.0) + cost, 6)

            # Atomic write
            temp_file = usage_file.with_suffix(f".tmp.{secrets.token_hex(4)}")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(cur_usage, f, indent=2)
                f.flush()
            replaced = False
            for attempt in range(8):
                try:
                    os.replace(temp_file, usage_file)
                    replaced = True
                    break
                except (PermissionError, OSError):
                    time.sleep(0.03 * (attempt + 1))
            if not replaced:
                try:
                    with open(usage_file, "w", encoding="utf-8") as f:
                        json.dump(cur_usage, f, indent=2)
                except Exception:
                    pass
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass

    # --- Low-level provider invocation ---

    def _call_provider(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        is_json: bool,
    ) -> Tuple[str, int, int]:
        provider = self._provider
        model = settings.LLM_MODEL

        # Extended retry logic: up to 5 attempts for rate limits, 3 for general errors
        max_attempts = 5
        last_err: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                if provider == "groq":
                    # Proactive rate-budgeting / pacing for Groq free-tier
                    global _groq_last_call_time
                    with _groq_pace_lock:
                        now = time.time()
                        elapsed_since_last = now - _groq_last_call_time
                        if elapsed_since_last < 1.8:
                            time.sleep(1.8 - elapsed_since_last)
                        _groq_last_call_time = time.time()

                    client = self._get_groq_client()
                    kwargs = {
                        "model": model or "qwen/qwen3.8-27b",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    if is_json:
                        kwargs["response_format"] = {"type": "json_object"}

                    resp = client.chat.completions.create(**kwargs)
                    text = resp.choices[0].message.content or ""
                    in_tok = resp.usage.prompt_tokens if resp.usage else len(prompt) // 4
                    out_tok = resp.usage.completion_tokens if resp.usage else len(text) // 4
                    return (text, in_tok, out_tok)

                elif provider == "openai":
                    client = self._get_openai_client()
                    kwargs = {
                        "model": model or "gpt-4o",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": temperature,
                    }
                    if is_json:
                        kwargs["response_format"] = {"type": "json_object"}

                    try:
                        resp = client.chat.completions.create(max_tokens=max_tokens, **kwargs)
                    except Exception as e:
                        if "max_completion_tokens" in str(e).lower() or "unsupported parameter" in str(e).lower():
                            resp = client.chat.completions.create(max_completion_tokens=max_tokens, **kwargs)
                        else:
                            raise e

                    text = resp.choices[0].message.content or ""
                    in_tok = resp.usage.prompt_tokens if resp.usage else len(prompt) // 4
                    out_tok = resp.usage.completion_tokens if resp.usage else len(text) // 4
                    return (text, in_tok, out_tok)

                elif provider == "anthropic":
                    client = self._get_anthropic_client()
                    resp = client.messages.create(
                        model=model or "claude-3-5-sonnet-20241022",
                        system=system,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    text = "".join([b.text for b in resp.content if hasattr(b, "text")])
                    in_tok = resp.usage.input_tokens if resp.usage else len(prompt) // 4
                    out_tok = resp.usage.output_tokens if resp.usage else len(text) // 4
                    return (text, in_tok, out_tok)

                else:
                    raise LLMError(f"Unsupported provider: {provider}")

            except LLMError:
                raise
            except Exception as e:
                err_msg = str(e).lower()
                # Fast fail without retrying for authentication or fatal client errors
                if (
                    "authentication" in err_msg
                    or "invalid api key" in err_msg
                    or "unauthorized" in err_msg
                    or "401" in err_msg
                    or ("400" in err_msg and "bad request" in err_msg)
                ):
                    raise LLMError(f"Missing or invalid API key or bad request for provider {provider}: {e}")

                last_err = e
                is_rate_limit = (
                    "429" in err_msg
                    or "rate limit" in err_msg
                    or "tpm" in err_msg
                    or "tokens per minute" in err_msg
                    or "too many requests" in err_msg
                )

                if is_rate_limit and attempt < max_attempts - 1:
                    wait_seconds = 12.0
                    m = re.search(r"try again in ([\d\.]+)s", str(e), re.IGNORECASE)
                    if m:
                        try:
                            wait_seconds = float(m.group(1)) + 1.5
                        except ValueError:
                            pass
                    elif hasattr(e, "response") and e.response and "retry-after" in getattr(e.response, "headers", {}):
                        try:
                            wait_seconds = float(e.response.headers.get("retry-after", 12)) + 1.0
                        except ValueError:
                            pass
                    else:
                        wait_seconds = [6.0, 12.0, 20.0, 30.0, 45.0][min(attempt, 4)]

                    # If error was specifically an OTPM limit rejection (e.g. Limit 1000, Requested 1200)
                    m_limit = re.search(r"limit\s+(\d+),\s*requested\s+(\d+)", str(e), re.IGNORECASE)
                    if m_limit:
                        try:
                            allowed_lim = int(m_limit.group(1))
                            max_tokens = max(150, allowed_lim - 50)
                            wait_seconds = max(2.0, min(wait_seconds, 6.0))
                        except Exception:
                            pass

                    import logging
                    logging.getLogger("llm").warning(
                        f"[Groq Rate Limit] 429 hit (clamped max_tokens={max_tokens}). Waiting {wait_seconds:.1f}s before retry (attempt {attempt + 1}/{max_attempts})..."
                    )
                    time.sleep(wait_seconds)
                    continue

                # Standard backoff for non-rate-limit errors (only 3 attempts)
                backoffs = [1, 3, 8]
                if attempt < len(backoffs):
                    time.sleep(backoffs[attempt])
                else:
                    break

        raise LLMError(f"Provider {provider} failed after {max_attempts} retries: {last_err}")

    # --- Public completion methods ---

    def complete_text(
        self,
        *,
        system: str,
        prompt: str,
        schema_name: str = "text",
        run_id: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> str:
        """Complete prompt and return text response."""
        # 1. Fake provider
        if self._provider == "fake":
            fake_path = settings.repo_root / "apps" / "api" / "app" / "fake_llm" / f"{schema_name}.txt"
            if not fake_path.exists():
                raise LLMError(f"no fake response for {schema_name}")
            text = fake_path.read_text(encoding="utf-8")
            in_tok = len(prompt) // 4
            out_tok = len(text) // 4
            self._record_usage(run_id, in_tok, out_tok, is_cache_hit=False)
            return text

        # 2. Check disk cache
        cache_k = self._cache_key(
            provider=self._provider,
            model=settings.LLM_MODEL,
            system=system,
            prompt=prompt,
            schema_name=schema_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        cached = self._check_cache(cache_k)
        if cached is not None:
            raw_text, in_tok, out_tok = cached
            self._record_usage(run_id, in_tok, out_tok, is_cache_hit=True)
            return raw_text

        # 3. Call Provider
        raw_text, in_tok, out_tok = self._call_provider(
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            is_json=False,
        )

        # 4. Write cache & record usage
        self._write_cache(cache_k, raw_text, in_tok, out_tok)
        self._record_usage(run_id, in_tok, out_tok, is_cache_hit=False)
        return raw_text

    def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        schema_name: str,
        run_id: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> Union[Dict[str, Any], List[Any]]:
        """Complete prompt and return validated JSON data."""
        # 1. Fake provider
        if self._provider == "fake":
            fake_path = settings.repo_root / "apps" / "api" / "app" / "fake_llm" / f"{schema_name}.json"
            if not fake_path.exists():
                raise LLMError(f"no fake response for {schema_name}")
            try:
                with open(fake_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                raise LLMError(f"Invalid JSON in fake file {schema_name}.json: {e}")
            in_tok = len(prompt) // 4
            out_tok = len(json.dumps(data)) // 4
            self._record_usage(run_id, in_tok, out_tok, is_cache_hit=False)
            return data

        # 2. Check disk cache
        cache_k = self._cache_key(
            provider=self._provider,
            model=settings.LLM_MODEL,
            system=system,
            prompt=prompt,
            schema_name=schema_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        cached = self._check_cache(cache_k)
        if cached is not None:
            raw_text, in_tok, out_tok = cached
            self._record_usage(run_id, in_tok, out_tok, is_cache_hit=True)
            return self._parse_json_defensive(
                raw_text=raw_text,
                system=system,
                schema_name=schema_name,
                run_id=run_id,
                temperature=temperature,
                max_tokens=max_tokens,
                allow_repair=False,  # Already cached, should be valid
            )

        # 3. Call Provider
        raw_text, in_tok, out_tok = self._call_provider(
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            is_json=True,
        )

        # 4. Parse defensively with 1-shot repair if needed
        data = self._parse_json_defensive(
            raw_text=raw_text,
            system=system,
            schema_name=schema_name,
            run_id=run_id,
            temperature=temperature,
            max_tokens=max_tokens,
            allow_repair=True,
        )

        # 5. Write raw reply to cache & record usage
        self._write_cache(cache_k, raw_text, in_tok, out_tok)
        self._record_usage(run_id, in_tok, out_tok, is_cache_hit=False)
        return data

    def _parse_json_defensive(
        self,
        *,
        raw_text: str,
        system: str,
        schema_name: str,
        run_id: Optional[str],
        temperature: float,
        max_tokens: int,
        allow_repair: bool,
    ) -> Union[Dict[str, Any], List[Any]]:
        """Parse JSON defensively, stripping fences and running 1 repair call on failure."""
        cleaned = raw_text.strip()

        # Strip markdown fences if present
        if cleaned.startswith("```"):
            fence_match = re.search(r"^```(?:json)?\s*([\s\S]*?)\s*```$", cleaned, re.IGNORECASE)
            if fence_match:
                cleaned = fence_match.group(1).strip()

        # Find first { or [ to last } or ]
        first_brace = cleaned.find("{")
        first_bracket = cleaned.find("[")

        start = -1
        if first_brace != -1 and first_bracket != -1:
            start = min(first_brace, first_bracket)
        elif first_brace != -1:
            start = first_brace
        elif first_bracket != -1:
            start = first_bracket

        last_brace = cleaned.rfind("}")
        last_bracket = cleaned.rfind("]")
        end = max(last_brace, last_bracket)

        if start != -1 and end != -1 and end >= start:
            candidate = cleaned[start : end + 1]
            try:
                return json.loads(candidate)
            except Exception as parse_err:
                first_err = parse_err
        else:
            first_err = Exception("No JSON object or array found in response")

        # Repair path: 1 repair attempt
        if allow_repair:
            repair_prompt = (
                f"Your previous reply was not valid JSON ({first_err}). "
                "Reply again with ONLY the valid JSON, no explanations, no code fences."
            )
            repair_text, rep_in, rep_out = self._call_provider(
                system=system,
                prompt=repair_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                is_json=True,
            )
            self._record_usage(run_id, rep_in, rep_out, is_cache_hit=False)

            # Clean repair reply
            rep_clean = repair_text.strip()
            if rep_clean.startswith("```"):
                rep_match = re.search(r"^```(?:json)?\s*([\s\S]*?)\s*```$", rep_clean, re.IGNORECASE)
                if rep_match:
                    rep_clean = rep_match.group(1).strip()

            r_start = min(
                [i for i in (rep_clean.find("{"), rep_clean.find("[")) if i != -1] or [-1]
            )
            r_end = max(rep_clean.rfind("}"), rep_clean.rfind("]"))

            if r_start != -1 and r_end != -1 and r_end >= r_start:
                try:
                    return json.loads(rep_clean[r_start : r_end + 1])
                except Exception:
                    pass

        raise LLMError(f"Failed to parse JSON reply: {raw_text[:300]}")


def get_llm() -> LLM:
    """Return the process-wide LLM singleton."""
    global _llm_instance
    if _llm_instance is None:
        with _singleton_lock:
            if _llm_instance is None:
                _llm_instance = LLM()
    return _llm_instance


def usage(run_id: str) -> LlmUsage:
    """Return token usage and estimated cost for a run, or zeros if missing."""
    usage_file = run_dir(run_id) / "llm_usage.json"
    if not usage_file.exists():
        return LlmUsage()
    try:
        with open(usage_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return LlmUsage(**data)
    except Exception:
        return LlmUsage()
