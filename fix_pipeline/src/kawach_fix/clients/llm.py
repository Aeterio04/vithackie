"""LLM client protocol and HTTP implementations for Groq/Gemini/OpenAI."""

import os
from typing import Optional, Protocol, runtime_checkable
import httpx


class LLMClientError(Exception):
    """Exception raised when LLM generation fails."""
    pass


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM generation required by FixLLMAgent."""

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        """Generate text completion from system and user instructions."""
        ...


GROQ_CANDIDATE_MODELS = [
    "qwen/qwen3.8-27b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
]


class HttpxGroqClient:
    """Production Groq LLM client using httpx with automatic model discovery and fallback."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        if not api_key and not os.environ.get("GROQ_API_KEY"):
            try:
                from dotenv import load_dotenv
                from pathlib import Path
                for candidate in [
                    Path.cwd() / ".env",
                    Path.cwd() / "apps" / "api" / ".env",
                    Path(__file__).resolve().parents[4] / ".env",
                    Path(__file__).resolve().parents[4] / "apps" / "api" / ".env",
                ]:
                    if candidate.exists():
                        load_dotenv(candidate, override=False)
            except Exception:
                pass

        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = (
            model
            or os.environ.get("LLM_MODEL")
            or os.environ.get("GROQ_MODEL")
            or os.environ.get("GROQ_DEFAULT_MODEL")
            or "qwen/qwen3.8-27b"
        )
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        if not self.api_key:
            raise LLMClientError("GROQ_API_KEY is not set.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (KAWACH-Fix-Pipeline)",
        }

        # Build list of candidate models with preferred model first
        models_to_try = [self.model] + [m for m in GROQ_CANDIDATE_MODELS if m != self.model]

        last_error = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for candidate in models_to_try:
                payload = {
                    "model": candidate,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                }
                try:
                    res = await client.post(self.base_url, headers=headers, json=payload)
                    if res.status_code == 404 and "model_not_found" in res.text:
                        last_error = f"Model '{candidate}' not accessible on this Groq key, trying fallback..."
                        continue
                    if res.is_error:
                        raise LLMClientError(f"Groq API error ({res.status_code}): {res.text}")
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
                except LLMClientError:
                    raise
                except Exception as e:
                    last_error = str(e)
                    continue

        raise LLMClientError(f"Failed to communicate with Groq: {last_error}")


class HttpxGeminiClient:
    """Production Gemini LLM client using httpx."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        if not self.api_key:
            raise LLMClientError("GEMINI_API_KEY is not set.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {"parts": [{"text": user_prompt}]}
            ],
            "generationConfig": {
                "temperature": temperature,
                "response_mime_type": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                res = await client.post(url, json=payload)
                if res.is_error:
                    raise LLMClientError(f"Gemini API error ({res.status_code}): {res.text}")
                data = res.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    raise LLMClientError(f"No response candidate returned by Gemini: {data}")
                return candidates[0]["content"]["parts"][0]["text"]
            except Exception as e:
                if isinstance(e, LLMClientError):
                    raise
                raise LLMClientError(f"Failed to communicate with Gemini: {str(e)}")


def get_default_llm_client() -> LLMClient:
    """Factory creating an LLM client based on available environment variables."""
    if not os.environ.get("GROQ_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            for candidate in [
                Path.cwd() / ".env",
                Path.cwd() / "apps" / "api" / ".env",
                Path(__file__).resolve().parents[4] / ".env",
                Path(__file__).resolve().parents[4] / "apps" / "api" / ".env",
            ]:
                if candidate.exists():
                    load_dotenv(candidate, override=False)
        except Exception:
            pass

    if os.environ.get("GROQ_API_KEY"):
        return HttpxGroqClient()
    if os.environ.get("GEMINI_API_KEY"):
        return HttpxGeminiClient()
    raise LLMClientError("No LLM API key detected. Set GROQ_API_KEY or GEMINI_API_KEY.")
