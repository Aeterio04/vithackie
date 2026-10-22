"""Backwards compatibility shim forwarding to kawach.core.config."""

from kawach.core.config import Settings, settings

__all__ = ["Settings", "settings"]
