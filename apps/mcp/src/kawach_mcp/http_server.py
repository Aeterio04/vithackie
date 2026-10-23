"""Streamable HTTP transport application for Kawach MCP Server with per-caller authentication and isolation."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer
import mcp.types as types
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from kawach_mcp.auth_cache import scope_cache
from kawach_mcp.client import AuthMeInfo, KawachAPIError, KawachClient
from kawach_mcp.config import Settings, get_settings
from kawach_mcp.context import CallerContext, get_current_caller, reset_current_caller, set_current_caller
from kawach_mcp.prompts import register_prompts
from kawach_mcp.resources import register_resources
from kawach_mcp.tools import TOOL_REGISTRY


class RemoteAuthMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing per-request Bearer token authentication, scope verification, isolation, and access logging."""

    def __init__(
        self,
        app: Any,
        settings: Settings,
        client: KawachClient,
        active_concurrency: Dict[str, int],
        concurrency_lock: asyncio.Lock,
    ):
        super().__init__(app)
        self.settings = settings
        self.client = client
        self.active_concurrency = active_concurrency
        self.concurrency_lock = concurrency_lock

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start_time = time.perf_counter()
        tool_name = "unknown"
        token_hash_prefix = "none"

        # 1. Unauthenticated endpoints
        if request.url.path == "/healthz":
            response = await call_next(request)
            response.headers["X-Request-Id"] = req_id
            return response

        # 2. Origin validation
        allowed_origins = self.settings.get_allowed_origins
        origin = request.headers.get("origin")
        if allowed_origins and origin:
            if origin not in allowed_origins:
                return JSONResponse(
                    {"error": "Forbidden: Origin header not in allowed origins"},
                    status_code=403,
                    headers={"X-Request-Id": req_id},
                )

        # 3. Request body size limit
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.settings.max_request_body_size:
                    return JSONResponse(
                        {"error": "Payload Too Large: Request body exceeds maximum allowed size"},
                        status_code=413,
                        headers={"X-Request-Id": req_id},
                    )
            except ValueError:
                pass

        # 4. Bearer token extraction and format validation
        auth_header = request.headers.get("authorization", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Unauthorized: Missing Bearer token in Authorization header"},
                status_code=401,
                headers={"X-Request-Id": req_id},
            )

        raw_token = auth_header[7:].strip()
        if not raw_token.startswith("kw_live_"):
            return JSONResponse(
                {"error": "Unauthorized: Malformed token. Must start with 'kw_live_'"},
                status_code=401,
                headers={"X-Request-Id": req_id},
            )

        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        token_hash_prefix = token_hash[:8]

        # 5. Scope introspection and caching (TTL <= 60s)
        auth_info = scope_cache.get(token_hash)
        if auth_info is None:
            try:
                auth_info = await self.client.introspect_token_with_token(raw_token)
                scope_cache.set(token_hash, auth_info)
            except KawachAPIError as exc:
                return JSONResponse(
                    {"error": f"Unauthorized: {exc.message}"},
                    status_code=401,
                    headers={"X-Request-Id": req_id},
                )
            except Exception as exc:
                return JSONResponse(
                    {"error": f"Authentication check failed: {type(exc).__name__}"},
                    status_code=502,
                    headers={"X-Request-Id": req_id},
                )

        # 6. Concurrency limiting per caller
        async with self.concurrency_lock:
            current_active = self.active_concurrency.get(token_hash, 0)
            if current_active >= self.settings.per_caller_concurrency_limit:
                return JSONResponse(
                    {"error": "Too Many Requests: Concurrency limit exceeded for caller"},
                    status_code=429,
                    headers={"X-Request-Id": req_id},
                )
            self.active_concurrency[token_hash] = current_active + 1

        # 7. Inspect method/tool from body for access logging (without consuming stream)
        try:
            body_bytes = await request.body()
            if body_bytes:
                data = json.loads(body_bytes.decode("utf-8"))
                rpc_method = data.get("method")
                if rpc_method == "tools/call":
                    tool_name = data.get("params", {}).get("name", "tool_call")
                elif rpc_method:
                    tool_name = rpc_method
        except Exception:
            pass

        # 8. Dispatch request under caller context with timeout
        ctx = CallerContext(
            token=raw_token,
            token_hash=token_hash,
            auth_info=auth_info,
            request_id=req_id,
        )
        ctx_token = set_current_caller(ctx)
        try:
            async with asyncio.timeout(self.settings.per_request_timeout_seconds):
                response = await call_next(request)
        except TimeoutError:
            response = JSONResponse(
                {"error": f"Gateway Timeout: Request exceeded {self.settings.per_request_timeout_seconds}s limit"},
                status_code=504,
            )
        except Exception as exc:
            response = JSONResponse(
                {"error": f"Internal Server Error: {type(exc).__name__}"},
                status_code=500,
            )
        finally:
            reset_current_caller(ctx_token)
            async with self.concurrency_lock:
                self.active_concurrency[token_hash] = max(
                    0, self.active_concurrency.get(token_hash, 1) - 1
                )

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        response.headers["X-Request-Id"] = req_id

        # Sanitized access log: NEVER prints Authorization header, raw token, or payloads
        sys.stderr.write(
            f"[MCP-HTTP-ACCESS] request_id={req_id} "
            f"token_hash_prefix={token_hash_prefix} "
            f"tool={tool_name} "
            f"status={response.status_code} "
            f"duration_ms={duration_ms:.2f}\n"
        )
        return response


def create_http_app(
    settings: Optional[Settings] = None,
    client: Optional[KawachClient] = None,
) -> Starlette:
    """Create and configure the Starlette application serving MCP over Streamable HTTP."""
    if settings is None:
        settings = get_settings()
    if client is None:
        client = KawachClient(settings)

    server = MCPServer("kawach")

    # Map tool specifications for lookup during dynamic tool listing and invocation
    tool_spec_by_name = {spec.name: spec for spec in TOOL_REGISTRY}

    # Register all tools with per-caller scope verification wrapped into the handler
    for spec in TOOL_REGISTRY:
        handler = spec.handler_factory(client, settings)
        required_scope = spec.required_scope
        is_write = spec.is_write

        def _make_scope_guarded_handler(orig_handler, req_scope, write_flag):
            @functools.wraps(orig_handler)
            async def guarded_handler(*args, **kwargs):
                caller = get_current_caller()
                if write_flag and not settings.allow_write_tools:
                    return types.CallToolResult(
                        is_error=True,
                        content=[types.TextContent(
                            type="text",
                            text="Permission denied: Write and mutating tools are disabled on this MCP server instance."
                        )],
                    )
                if caller and req_scope:
                    if req_scope not in caller.auth_info.scopes:
                        return types.CallToolResult(
                            is_error=True,
                            content=[types.TextContent(
                                type="text",
                                text=f"Permission denied: Your token lacks the required scope '{req_scope}' for tool execution."
                            )],
                        )
                return await orig_handler(*args, **kwargs)
            return guarded_handler

        server.tool(
            name=spec.name,
            description=spec.description,
            annotations=spec.annotations,
        )(_make_scope_guarded_handler(handler, required_scope, is_write))

    # Dynamic tool listing: filter tools per active caller's scopes
    orig_list_tools = server.list_tools

    async def dynamic_list_tools() -> List[types.Tool]:
        all_tools = await orig_list_tools()
        caller = get_current_caller()
        if caller is None:
            return all_tools

        granted_scopes = set(caller.auth_info.scopes)
        filtered: List[types.Tool] = []
        for tool_item in all_tools:
            spec = tool_spec_by_name.get(tool_item.name)
            if spec:
                if spec.required_scope and spec.required_scope not in granted_scopes:
                    continue
                if spec.is_write and not settings.allow_write_tools:
                    continue
            filtered.append(tool_item)
        return filtered

    server.list_tools = dynamic_list_tools

    # Register resources and prompts
    register_resources(server, client, settings)
    register_prompts(server, client, settings)

    # Disable strict Host header check for tunnel and loopback flexibility
    sec_settings = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    # Instantiate base Starlette streamable HTTP app in stateless mode returning plain JSON
    app = server.streamable_http_app(
        streamable_http_path=settings.mcp_path,
        json_response=True,
        stateless_http=True,
        transport_security=sec_settings,
        host=settings.mcp_host,
    )

    # Add health check route
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app.add_route("/healthz", healthz, methods=["GET"])

    # Attach RemoteAuthMiddleware
    active_concurrency: Dict[str, int] = {}
    concurrency_lock = asyncio.Lock()
    app.add_middleware(
        RemoteAuthMiddleware,
        settings=settings,
        client=client,
        active_concurrency=active_concurrency,
        concurrency_lock=concurrency_lock,
    )

    return app


async def run_http_server(
    settings: Optional[Settings] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    path: Optional[str] = None,
) -> None:
    """Run Kawach MCP Server over HTTP transport."""
    import uvicorn

    if settings is None:
        settings = get_settings()

    bind_host = host or settings.mcp_host
    bind_port = port or settings.mcp_port
    mcp_path = path or settings.mcp_path

    client = KawachClient(settings)
    app = create_http_app(settings=settings, client=client)

    sys.stderr.write(
        f"[Kawach MCP] Starting HTTP server on http://{bind_host}:{bind_port}{mcp_path} "
        f"(stateless_http=True, json_response=True)\n"
    )
    if settings.effective_public_url:
        sys.stderr.write(f"[Kawach MCP] Public URL: {settings.effective_public_url}\n")

    config = uvicorn.Config(
        app=app,
        host=bind_host,
        port=bind_port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await client.close()
