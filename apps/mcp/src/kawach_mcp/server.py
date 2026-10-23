"""MCP Server implementation for Kawach AI QA Engineer."""

from __future__ import annotations

import sys
from typing import List, Optional
import anyio
from mcp.server.mcpserver import MCPServer

from kawach_mcp.client import AuthMeInfo, KawachAPIError, KawachClient
from kawach_mcp.config import Settings, get_settings
from kawach_mcp.tools import TOOL_REGISTRY
from kawach_mcp.resources import register_resources
from kawach_mcp.prompts import register_prompts


def create_mcp_server(
    settings: Settings,
    client: KawachClient,
    auth_info: AuthMeInfo,
) -> MCPServer:
    """Instantiate and configure MCPServer with scope-gated tool registration.
    
    Only tools whose required scope is granted in auth_info.scopes are registered.
    Write tools are further gated behind settings.allow_write_tools.
    """
    server = MCPServer("kawach")

    granted_scopes = set(auth_info.scopes)
    registered_names: List[str] = []

    for spec in TOOL_REGISTRY:
        # Check scope entitlement
        if spec.required_scope and spec.required_scope not in granted_scopes:
            continue

        # Check write tool policy gating
        if spec.is_write and not settings.allow_write_tools:
            continue

        handler = spec.handler_factory(client, settings)
        server.tool(
            name=spec.name,
            description=spec.description,
            annotations=spec.annotations,
        )(handler)
        registered_names.append(spec.name)

    # Register resources and prompts if user has read entitlement
    if "runs:read" in granted_scopes or "tests:read" in granted_scopes or not granted_scopes:
        register_resources(server, client, settings)
    register_prompts(server, client, settings)

    sys.stderr.write(
        f"[Kawach MCP] Registered {len(registered_names)} tools: {', '.join(registered_names)}\n"
    )
    return server


async def run_server(settings: Optional[Settings] = None) -> None:
    """Verify credentials, introspect scopes, and start stdio transport loop."""
    if settings is None:
        settings = get_settings()

    token = settings.get_effective_token()
    if not token:
        sys.stderr.write(
            "FATAL: Missing Kawach API token. Set KAWACH_API_TOKEN in your environment "
            "or provide a 0600-permissioned token file via KAWACH_TOKEN_FILE or ~/.kawach/token.\n"
        )
        sys.exit(1)

    client = KawachClient(settings)
    try:
        sys.stderr.write(f"[Kawach MCP] Connecting to backend at {settings.clean_api_url}...\n")
        auth_info = await client.introspect_token()
        sys.stderr.write(
            f"[Kawach MCP] Authenticated as {auth_info.email or 'API Token'} "
            f"with scopes: {auth_info.scopes}\n"
        )
    except KawachAPIError as exc:
        sys.stderr.write(f"FATAL: Backend rejected authentication: {exc.message}\n")
        sys.exit(1)
    except Exception as exc:
        sys.stderr.write(f"FATAL: Failed to connect to Kawach backend: {exc}\n")
        sys.exit(1)

    server = create_mcp_server(settings, client, auth_info)
    try:
        await server.run_stdio_async()
    finally:
        await client.close()


def main() -> None:
    """Entry point for kawach-mcp command line script supporting stdio and http transports."""
    import argparse

    parser = argparse.ArgumentParser(description="Kawach Model Context Protocol (MCP) Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=None,
        help="MCP transport protocol (default: stdio, or KAWACH_MCP_TRANSPORT)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host to bind for HTTP transport (default: 127.0.0.1 or KAWACH_MCP_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind for HTTP transport (default: 8765 or KAWACH_MCP_PORT)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Path for HTTP transport endpoint (default: /mcp or KAWACH_MCP_PATH)",
    )

    args = parser.parse_args()
    settings = get_settings()

    transport = args.transport or settings.mcp_transport or "stdio"

    if transport == "http":
        from kawach_mcp.http_server import run_http_server

        try:
            anyio.run(
                run_http_server,
                settings,
                args.host or settings.mcp_host,
                args.port or settings.mcp_port,
                args.path or settings.mcp_path,
            )
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        try:
            anyio.run(run_server, settings)
        except (KeyboardInterrupt, SystemExit):
            pass


if __name__ == "__main__":
    main()
