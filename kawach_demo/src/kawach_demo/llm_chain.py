"""Resilient LLM chain with Groq TPM budgeting, proactive pacing, and Gemini failover."""

import asyncio
import json
import logging
import os
import re
import time
from typing import List, Optional
import httpx
from pydantic import SecretStr

from kawach_fix.clients.llm import LLMClient, LLMClientError

logger = logging.getLogger("kawach_demo.llm_chain")


class ResilientLLMChain(LLMClient):
    """Production LLMClient implementation with proactive rate limiting and failover."""

    def __init__(
        self,
        groq_api_key: Optional[SecretStr] = None,
        gemini_api_key: Optional[SecretStr] = None,
        groq_model: Optional[str] = None,
        gemini_model: str = "gemini-2.5-flash",
        max_retries: int = 2,
        timeout_sec: float = 45.0,
        min_groq_interval_sec: float = 2.0,
    ):
        self.groq_key = (
            groq_api_key.get_secret_value()
            if groq_api_key
            else os.environ.get("GROQ_API_KEY", "")
        )
        self.gemini_key = (
            gemini_api_key.get_secret_value()
            if gemini_api_key
            else os.environ.get("GEMINI_API_KEY", "")
        )
        if self.gemini_key.startswith("AIzaxxxxx"):
            self.gemini_key = ""

        env_groq_model = os.environ.get("GROQ_MODEL", "")
        default_model = groq_model or env_groq_model or "openai/gpt-oss-120b"

        # Candidate models ordered by accuracy and token efficiency
        candidates = [default_model]
        for m in [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
            "llama-3.3-70b-versatile",
        ]:
            if m not in candidates:
                candidates.append(m)

        self.groq_candidate_models: List[str] = candidates
        self.groq_model = self.groq_candidate_models[0]
        self.gemini_model = gemini_model
        self.max_retries = max_retries
        self.timeout_sec = timeout_sec
        self.min_groq_interval_sec = min_groq_interval_sec
        self._last_groq_call_time: float = 0.0

        self.last_provider: Optional[str] = None
        self.last_model: Optional[str] = None
        self.last_latency_sec: float = 0.0

    async def _throttle_groq(self) -> None:
        """Enforce minimum interval between consecutive Groq requests to respect RPM."""
        now = time.time()
        elapsed = now - self._last_groq_call_time
        if elapsed < self.min_groq_interval_sec:
            await asyncio.sleep(self.min_groq_interval_sec - elapsed)
        self._last_groq_call_time = time.time()

    async def _call_groq(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        model: Optional[str] = None,
        max_tokens: int = 1000,
    ) -> str:
        await self._throttle_groq()
        url = "https://api.groq.com/openai/v1/chat/completions"
        target_model = model or self.groq_model
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json",
        }
        # CRITICAL: Always budget max_tokens so Groq doesn't reserve 4k+ tokens against 6k TPM ceiling
        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code == 404:
                raise LLMClientError(f"GROQ_MODEL_404: {res.text}")
            if res.status_code == 429:
                # Extract wait duration from retry-after header or body text
                wait_time = 4.0
                retry_header = res.headers.get("retry-after")
                if retry_header:
                    try:
                        wait_time = float(retry_header)
                    except ValueError:
                        pass
                else:
                    match = re.search(r"try again in (\d+\.?\d*)s", res.text)
                    if match:
                        wait_time = float(match.group(1)) + 0.5
                raise LLMClientError(f"GROQ_RATE_LIMIT_429: wait={wait_time} body={res.text}")

            if res.is_error:
                raise LLMClientError(f"Groq error ({res.status_code}): {res.text}")

            data = res.json()
            return data["choices"][0]["message"]["content"]

    async def _call_gemini(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
            f"?key={self.gemini_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 1000,
                "response_mime_type": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            res = await client.post(url, json=payload)
            if res.is_error:
                raise LLMClientError(f"Gemini error ({res.status_code}): {res.text}")
            data = res.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise LLMClientError(f"Gemini returned empty candidates: {data}")
            return candidates[0]["content"]["parts"][0]["text"]

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        start_time = asyncio.get_event_loop().time()
        last_err: Optional[Exception] = None

        # 1. Try Groq (if key configured)
        if self.groq_key:
            for model_candidate in self.groq_candidate_models:
                for attempt in range(self.max_retries + 1):
                    try:
                        resp = await self._call_groq(
                            system_prompt,
                            user_prompt,
                            temperature,
                            model=model_candidate,
                            max_tokens=900,
                        )
                        self.groq_model = model_candidate
                        self.last_provider = "Groq"
                        self.last_model = model_candidate
                        self.last_latency_sec = asyncio.get_event_loop().time() - start_time
                        return resp
                    except Exception as e:
                        last_err = e
                        err_str = str(e)
                        if "GROQ_MODEL_404" in err_str:
                            logger.info(f"Model '{model_candidate}' returned 404, switching to next...")
                            break  # Move to next candidate model immediately without retry
                        if "GROQ_RATE_LIMIT_429" in err_str:
                            # Parse suggested wait time
                            wait_s = 4.0
                            m = re.search(r"wait=(\d+\.?\d*)", err_str)
                            if m:
                                wait_s = float(m.group(1))
                            logger.warning(
                                f"Groq 429 rate limit hit on {model_candidate}. Backing off {wait_s:.1f}s (attempt {attempt + 1})..."
                            )
                            if attempt < self.max_retries:
                                await asyncio.sleep(wait_s)
                            else:
                                logger.info(f"TPM saturated on {model_candidate}, falling back to next candidate model...")
                                break
                        else:
                            logger.warning(f"Groq attempt {attempt + 1} with {model_candidate} failed: {e}")
                            if attempt < self.max_retries:
                                backoff = 1.5 * (2 ** attempt)
                                await asyncio.sleep(backoff)
                            else:
                                break
                if "GROQ_MODEL_404" not in str(last_err) and "GROQ_RATE_LIMIT_429" not in str(last_err):
                    break

        # 2. Fallback to Gemini (if valid key configured)
        if self.gemini_key:
            start_gemini = asyncio.get_event_loop().time()
            for attempt in range(self.max_retries + 1):
                try:
                    resp = await self._call_gemini(system_prompt, user_prompt, temperature)
                    self.last_provider = "Gemini"
                    self.last_model = self.gemini_model
                    self.last_latency_sec = asyncio.get_event_loop().time() - start_gemini
                    return resp
                except Exception as e:
                    last_err = e
                    logger.warning(f"Gemini attempt {attempt + 1} failed: {e}")
                    if attempt < self.max_retries:
                        backoff = 1.5 * (2 ** attempt)
                        await asyncio.sleep(backoff)

        raise LLMClientError(f"All LLM providers failed. Last error: {last_err}")
