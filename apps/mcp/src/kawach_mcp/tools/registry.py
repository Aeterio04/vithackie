"""Tool registry and definition metadata for dynamic scope gating."""

from __future__ import annotations

from typing import Any, Callable, List, NamedTuple, Optional
import mcp.types as types
from kawach_mcp.client import KawachClient
from kawach_mcp.config import Settings


class ToolSpec(NamedTuple):
    """Specification for an MCP tool including security and scope requirements."""
    name: str
    description: str
    required_scope: Optional[str]
    is_write: bool
    handler_factory: Callable[[KawachClient, Settings], Callable[..., Any]]
    annotations: Optional[types.ToolAnnotations] = None


TOOL_REGISTRY: List[ToolSpec] = []


def register_tool(
    name: str,
    description: str,
    required_scope: Optional[str] = None,
    is_write: bool = False,
    annotations: Optional[types.ToolAnnotations] = None,
) -> Callable[[Callable[[KawachClient, Settings], Callable[..., Any]]], Callable[[KawachClient, Settings], Callable[..., Any]]]:
    """Decorator to register a tool factory in the global TOOL_REGISTRY."""
    def decorator(
        factory: Callable[[KawachClient, Settings], Callable[..., Any]]
    ) -> Callable[[KawachClient, Settings], Callable[..., Any]]:
        spec = ToolSpec(
            name=name,
            description=description,
            required_scope=required_scope,
            is_write=is_write,
            handler_factory=factory,
            annotations=annotations,
        )
        TOOL_REGISTRY.append(spec)
        return factory
    return decorator
