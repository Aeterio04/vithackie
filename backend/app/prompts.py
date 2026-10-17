"""Prompt loaders and untrusted content wrappers.

Implemented by Track B.
"""

from typing import Any


def load_prompt(name: str, **vars: Any) -> str:
    """Read app/prompts/<name>.md and replace {{var}} placeholders.

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements load_prompt")


def untrusted(text: str, label: str) -> str:
    """Wrap untrusted text in <untrusted_content label="..."> tags with guard sentence.

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements untrusted")


def guard() -> str:
    """Return standard guard warning sentence.

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements guard")
