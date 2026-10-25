"""LLM package re-exporting client, cache, usage, and prompt loading utilities."""

from kawach.llm.client import LLM, LLMError, get_llm
from kawach.llm.key_pool import (
    KeyEntry,
    KeyPool,
    LLMRateLimitError,
    complete_with_pool,
    get_key_pool,
)
from kawach.llm.groq_handler import (
    GroqHandler,
    GroqRateLimiter,
    get_budgeted_max_tokens,
    get_groq_rate_limiter,
)
from kawach.llm.prompting import guard, load_prompt, untrusted
from kawach.llm.usage import record_usage, usage

__all__ = [
    "LLM",
    "LLMError",
    "LLMRateLimitError",
    "KeyEntry",
    "KeyPool",
    "get_key_pool",
    "complete_with_pool",
    "get_llm",
    "GroqHandler",
    "GroqRateLimiter",
    "get_groq_rate_limiter",
    "get_budgeted_max_tokens",
    "usage",
    "record_usage",
    "load_prompt",
    "untrusted",
    "guard",
]
