"""LLM client, cache, and cost tracking with multi-provider support.

Supported providers: groq, openai, anthropic, gemini, fake.
"""

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from kawach.core.config import settings
from kawach.schemas.metrics import LlmUsage
from kawach.llm.cache import check_cache, compute_cache_key, write_cache
from kawach.llm.usage import record_usage, usage

_singleton_lock = threading.Lock()
_groq_pace_lock = threading.Lock()
_groq_last_call_time = 0.0
_llm_instance: Optional["LLM"] = None


class LLMError(Exception):
    """Base exception for all LLM client errors."""
    pass


class LLM:
    """LLM client supporting Groq, OpenAI, Anthropic, Gemini, and offline Fake providers."""

    def __init__(self) -> None:
        self.cache_dir: Path = settings.repo_root / "apps" / "api" / ".llm_cache"
        if settings.LLM_CACHE in ("on", "readonly"):
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._provider = settings.LLM_PROVIDER.lower()
        self._openai_client = None
        self._groq_client = None
        self._groq_handler = None
        self._anthropic_client = None
        self._gemini_client = None

    def _get_groq_client(self):
        if self._groq_client is None:
            try:
                import openai
            except ImportError:
                raise LLMError("openai package is required for groq provider. Install openai>=1.0.0")

            api_key = (
                os.getenv("GROQ_API_KEY")
                or getattr(settings, "GROQ_API_KEY", "")
                or os.getenv("OPENAI_API_KEY")
                or settings.OPENAI_API_KEY
            )
            if not api_key:
                raise LLMError("Missing or invalid API key for provider groq (GROQ_API_KEY not set)")
            self._groq_client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        return self._groq_client

    def _get_groq_handler(self):
        if self._groq_handler is None:
            from kawach.llm.groq_handler import GroqHandler
            self._groq_handler = GroqHandler(self._get_groq_client)
        return self._groq_handler

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

    def _get_gemini_client(self):
        if self._gemini_client is None:
            try:
                import google.generativeai as genai
            except ImportError:
                raise LLMError("google-generativeai package is required for gemini provider. Install google-generativeai")

            api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                raise LLMError("Missing or invalid API key for provider gemini (GEMINI_API_KEY not set)")
            genai.configure(api_key=api_key)
            self._gemini_client = genai
        return self._gemini_client

    def _resolve_fake_file(self, schema_name: str, ext: str) -> Path:
        """Resolve fake response file from co-located or fallback directory."""
        fake_path = Path(__file__).resolve().parent / "fake_responses" / f"{schema_name}.{ext}"
        if fake_path.exists():
            return fake_path
        legacy_path = settings.repo_root / "apps" / "api" / "app" / "fake_llm" / f"{schema_name}.{ext}"
        if legacy_path.exists():
            return legacy_path
        return fake_path

    def _call_provider(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        is_json: bool,
        schema_name: str = "text",
        run_id: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        provider = self._provider
        model = settings.LLM_MODEL
        max_attempts = 5
        last_err: Optional[Exception] = None

        if provider == "groq":
            handler = self._get_groq_handler()
            return handler.complete(
                system=system,
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                is_json=is_json,
                schema_name=schema_name,
                run_id=run_id,
                max_attempts=max_attempts,
            )

        for attempt in range(max_attempts):
            try:
                if provider == "openai":
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

                elif provider == "gemini":
                    genai = self._get_gemini_client()
                    model_name = settings.GEMINI_DEFAULT_MODEL or "gemini-3.8-flash"
                    client = genai.GenerativeModel(model_name)
                    
                    # Combine system and user prompt for Gemini
                    full_prompt = f"{system}\n\n{prompt}"
                    
                    resp = client.generate_content(
                        full_prompt,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=max_tokens,
                            temperature=temperature,
                        ),
                    )
                    text = resp.text or ""
                    in_tok = len(prompt) // 4
                    out_tok = len(text) // 4
                    return (text, in_tok, out_tok)

                else:
                    raise LLMError(f"Unsupported provider: {provider}")

            except LLMError:
                raise
            except Exception as e:
                err_msg = str(e).lower()
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

                    m_limit = re.search(r"limit\s+(\d+),\s*requested\s+(\d+)", str(e), re.IGNORECASE)
                    if m_limit:
                        try:
                            allowed_lim = int(m_limit.group(1))
                            max_tokens = max(150, allowed_lim - 50)
                            wait_seconds = max(2.0, min(wait_seconds, 6.0))
                        except Exception:
                            pass

                    logging.getLogger("llm").warning(
                        f"[Rate Limit] 429 hit. Waiting {wait_seconds:.1f}s before retry (attempt {attempt + 1}/{max_attempts})..."
                    )
                    time.sleep(wait_seconds)
                    continue

                backoffs = [1, 3, 8]
                if attempt < len(backoffs):
                    time.sleep(backoffs[attempt])
                else:
                    break

        raise LLMError(f"Provider {provider} failed after {max_attempts} retries: {last_err}")

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
        if self._provider == "fake":
            fake_path = self._resolve_fake_file(schema_name, "txt")
            if not fake_path.exists():
                raise LLMError(f"no fake response for {schema_name}")
            text = fake_path.read_text(encoding="utf-8")
            in_tok = len(prompt) // 4
            out_tok = len(text) // 4
            record_usage(run_id, in_tok, out_tok, is_cache_hit=False)
            return text

        if self._provider == "groq":
            from kawach.llm.groq_handler import get_budgeted_max_tokens
            max_tokens = get_budgeted_max_tokens(schema_name, max_tokens)

        cache_k = compute_cache_key(
            provider=self._provider,
            model=settings.LLM_MODEL,
            system=system,
            prompt=prompt,
            schema_name=schema_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        cached = check_cache(self.cache_dir, cache_k)
        if cached is not None:
            raw_text, in_tok, out_tok = cached
            record_usage(run_id, in_tok, out_tok, is_cache_hit=True)
            return raw_text

        raw_text, in_tok, out_tok = self._call_provider(
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            is_json=False,
            schema_name=schema_name,
            run_id=run_id,
        )

        write_cache(self.cache_dir, cache_k, raw_text, in_tok, out_tok)
        record_usage(run_id, in_tok, out_tok, is_cache_hit=False)
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
        if self._provider == "fake":
            fake_path = self._resolve_fake_file(schema_name, "json")
            if not fake_path.exists():
                raise LLMError(f"no fake response for {schema_name}")
            try:
                with open(fake_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                raise LLMError(f"Invalid JSON in fake file {schema_name}.json: {e}")
            in_tok = len(prompt) // 4
            out_tok = len(json.dumps(data)) // 4
            record_usage(run_id, in_tok, out_tok, is_cache_hit=False)
            return data

        if self._provider == "groq":
            from kawach.llm.groq_handler import get_budgeted_max_tokens
            max_tokens = get_budgeted_max_tokens(schema_name, max_tokens)

        cache_k = compute_cache_key(
            provider=self._provider,
            model=settings.LLM_MODEL,
            system=system,
            prompt=prompt,
            schema_name=schema_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        cached = check_cache(self.cache_dir, cache_k)
        if cached is not None:
            raw_text, in_tok, out_tok = cached
            record_usage(run_id, in_tok, out_tok, is_cache_hit=True)
            return self._parse_json_defensive(
                raw_text=raw_text,
                system=system,
                schema_name=schema_name,
                run_id=run_id,
                temperature=temperature,
                max_tokens=max_tokens,
                allow_repair=False,
            )

        raw_text, in_tok, out_tok = self._call_provider(
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            is_json=True,
            schema_name=schema_name,
            run_id=run_id,
        )

        data = self._parse_json_defensive(
            raw_text=raw_text,
            system=system,
            schema_name=schema_name,
            run_id=run_id,
            temperature=temperature,
            max_tokens=max_tokens,
            allow_repair=True,
        )

        write_cache(self.cache_dir, cache_k, raw_text, in_tok, out_tok)
        record_usage(run_id, in_tok, out_tok, is_cache_hit=False)
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
        cleaned = raw_text.strip()

        if cleaned.startswith("```"):
            fence_match = re.search(r"^```(?:json)?\s*([\s\S]*?)\s*```$", cleaned, re.IGNORECASE)
            if fence_match:
                cleaned = fence_match.group(1).strip()

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
                schema_name=f"{schema_name}_repair",
                run_id=run_id,
            )
            record_usage(run_id, rep_in, rep_out, is_cache_hit=False)

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
