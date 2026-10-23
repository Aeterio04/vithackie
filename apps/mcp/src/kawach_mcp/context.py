"""Context management for per-request caller identity and token forwarding in HTTP mode."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Optional

from kawach_mcp.models import AuthMeInfo


@dataclass(frozen=True)
class CallerContext:
    """Identity and authorization context for the current HTTP caller."""
    token: str
    token_hash: str
    auth_info: AuthMeInfo
    request_id: str


_current_caller: contextvars.ContextVar[Optional[CallerContext]] = contextvars.ContextVar(
    "current_caller", default=None
)


def get_current_caller() -> Optional[CallerContext]:
    """Retrieve the active caller context for the current async task, or None if in stdio mode."""
    return _current_caller.get()


def set_current_caller(ctx: Optional[CallerContext]) -> contextvars.Token:
    """Set the active caller context for the current async task."""
    return _current_caller.set(ctx)


def reset_current_caller(token: contextvars.Token) -> None:
    """Reset the caller context to its previous state."""
    _current_caller.reset(token)
