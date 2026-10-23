"""Backwards compatibility shim for reviewer agent forwarding to kawach.agents.reviewer."""

from kawach.agents.reviewer.agent import review_catalog

__all__ = ["review_catalog"]
