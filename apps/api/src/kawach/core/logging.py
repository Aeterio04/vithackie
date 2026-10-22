"""Logging configuration, sensitive data masking, and ANSI regex utilities."""

import logging
import re
from typing import Optional

logger = logging.getLogger("kawach")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ANSI terminal escape sequence regex
ANSI_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def get_logger(name: str) -> logging.Logger:
    """Return a logger child of the root kawach logger."""
    return logging.getLogger(f"kawach.{name}")


def mask_sensitive(text: str, secret: Optional[str]) -> str:
    """Mask occurrences of secret in text."""
    if not secret:
        return text
    return text.replace(secret, "***")


__all__ = ["logger", "ANSI_REGEX", "get_logger", "mask_sensitive"]
