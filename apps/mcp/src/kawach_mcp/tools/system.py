"""Core system tools for Kawach MCP server."""

from __future__ import annotations

from typing import List, Optional
import mcp.types as types
from pydantic import BaseModel, Field

from kawach_mcp.client import KawachAPIError, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.security import redact_secrets
from kawach_mcp.tools.registry import register_tool


class ServerStatusResponse(BaseModel):
    """Status report of the Kawach MCP adapter and connected backend."""
    status: str = Field(description="Connection status (e.g. 'connected')")
    backend_url: str = Field(description="Normalized Kawach HTTP API URL")
    client_type: str = Field(description="Client type recorded in backend audit logs ('mcp')")
    granted_scopes: List[str] = Field(description="List of OAuth/API token scopes granted to this session")
    write_tools_enabled: bool = Field(description="Whether mutating write tools are enabled in configuration")
    default_project: Optional[str] = Field(default=None, description="Configured default project ID")


@register_tool(
    name="get_server_status",
    description="Check connectivity to the Kawach backend API and inspect granted token scopes and configuration.",
    required_scope=None,  # Available to any valid token
    is_write=False,
    annotations=types.ToolAnnotations(read_only_hint=True),
)
def make_get_server_status(client: KawachClient, settings: Settings):
    async def get_server_status() -> ServerStatusResponse:
        try:
            info = await client.introspect_token()
            return ServerStatusResponse(
                status="connected",
                backend_url=redact_secrets(settings.clean_api_url),
                client_type=info.client_type,
                granted_scopes=info.scopes,
                write_tools_enabled=settings.allow_write_tools,
                default_project=settings.default_project,
            )
        except KawachAPIError as exc:
            return types.CallToolResult(
                is_error=True,
                content=[types.TextContent(type="text", text=exc.to_user_message())],
            )
    return get_server_status
