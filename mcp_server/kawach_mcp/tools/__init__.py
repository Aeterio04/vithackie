"""Tool plumbing: uniform error handling, output shaping and annotation presets."""

from __future__ import annotations

import functools
import logging
import types
from typing import Any, Callable

from mcp.types import ToolAnnotations

from ..client import get_client
from ..errors import KawachError, redact
from ..formatting import MAX_OUTPUT_CHARS, trim

log = logging.getLogger("kawach_mcp.tools")

READ = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
IDEMPOTENT_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                   openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True,
                              openWorldHint=False)

CONFIRM_MESSAGE = {
    "done": False,
    "message": "This is destructive. Ask the user to confirm, then call again with confirm=true.",
}


def _absolutize(obj: Any) -> Any:
    """Turn relative backend URLs (keys ending in url) into absolute ones."""
    client = get_client()
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, str) and v.startswith("/") and k.lower().endswith("url"):
                out[k] = client.absolute_url(v)
            else:
                out[k] = _absolutize(v)
        return out
    if isinstance(obj, list):
        return [_absolutize(v) for v in obj]
    return obj


def _shrink(obj: Any, budget: int = 4000) -> Any:
    if isinstance(obj, str):
        return trim(obj, budget)
    if isinstance(obj, dict):
        return {k: _shrink(v, budget) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_shrink(v, budget) for v in obj[:200]]
    return obj


def shape_output(result: Any) -> Any:
    """Absolutize URLs and keep the payload under MAX_OUTPUT_CHARS."""
    import json

    result = _absolutize(result)
    if len(json.dumps(result, default=str)) > MAX_OUTPUT_CHARS:
        result = _shrink(result, 1500)
    return result


def tool(annotations: ToolAnnotations) -> Callable:
    """Mark an async function as an MCP tool and guard it uniformly."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return shape_output(await fn(*args, **kwargs))
            except KawachError:
                raise
            except Exception as e:  # never crash the server process
                log.error("tool %s failed with %s", fn.__name__, type(e).__name__, exc_info=True)  # stderr only
                raise KawachError(f"Unexpected error in {fn.__name__}: {type(e).__name__}") from e

        wrapper._mcp_annotations = annotations  # type: ignore[attr-defined]
        return wrapper

    return deco


def register_module(mcp: Any, module: types.ModuleType) -> list[str]:
    names = []
    for name, obj in vars(module).items():
        ann = getattr(obj, "_mcp_annotations", None)
        if ann is not None and callable(obj) and getattr(obj, "__module__", None) == module.__name__:
            mcp.add_tool(obj, name=name, annotations=ann)
            names.append(name)
    return names
