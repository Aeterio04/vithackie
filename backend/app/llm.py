"""LLM client, cache, and cost tracking.

Implemented by Track B.
"""

from typing import Any, Dict, Optional
from app.models import LlmUsage


class LLM:
    """LLM completion interface for text and JSON."""

    def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        schema_name: str,
        run_id: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Complete prompt and return validated JSON dictionary.

        Implemented by Track B.
        """
        raise NotImplementedError("Track B implements complete_json")

    def complete_text(
        self,
        *,
        system: str,
        prompt: str,
        run_id: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> str:
        """Complete prompt and return text response.

        Implemented by Track B.
        """
        raise NotImplementedError("Track B implements complete_text")


def get_llm() -> LLM:
    """Return the configured LLM instance.

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements get_llm")


def usage(run_id: str) -> LlmUsage:
    """Return token usage and estimated cost for a run.

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements usage")
