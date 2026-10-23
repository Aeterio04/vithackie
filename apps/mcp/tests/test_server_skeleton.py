"""Unit tests for Kawach MCP Server skeleton, scope introspection, and tool gating."""

from typing import List
import pytest
from pydantic import BaseModel
import mcp.types as types

from kawach_mcp.client import AuthMeInfo, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.server import create_mcp_server
from kawach_mcp.tools.registry import TOOL_REGISTRY, ToolSpec, register_tool


class DummyOutput(BaseModel):
    ok: bool = True


@pytest.fixture(autouse=True)
def clean_registry():
    """Backup and restore tool registry between test runs."""
    original = list(TOOL_REGISTRY)
    yield
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY.extend(original)


def test_scope_gated_tool_registration():
    """Verify tools are registered only if their required scope is present."""
    # Register test tools with distinct scopes
    @register_tool("tool_read_proj", "Read project", required_scope="projects:read")
    def factory_read(c, s):
        async def h() -> DummyOutput:
            return DummyOutput()
        return h

    @register_tool("tool_write_run", "Write run", required_scope="runs:write")
    def factory_write(c, s):
        async def h() -> DummyOutput:
            return DummyOutput()
        return h

    settings = Settings(api_token="kw_live_dummy", allow_write_tools=True)
    client = KawachClient(settings)

    # Scenario 1: Token only has projects:read
    auth_info = AuthMeInfo(scopes=["projects:read"])
    server = create_mcp_server(settings, client, auth_info)

    # Inspect registered tools via low-level server tool manager
    registered_names = list(server._tool_manager._tools.keys())
    assert "tool_read_proj" in registered_names
    assert "tool_write_run" not in registered_names

    # Scenario 2: Token has both scopes
    auth_info_both = AuthMeInfo(scopes=["projects:read", "runs:write"])
    server_both = create_mcp_server(settings, client, auth_info_both)
    registered_both = list(server_both._tool_manager._tools.keys())
    assert "tool_read_proj" in registered_both
    assert "tool_write_run" in registered_both


def test_write_tools_gated_by_config():
    """Verify write tools are withheld when allow_write_tools is False, even if scope granted."""
    @register_tool("mutating_action", "Mutating action", required_scope="runs:write", is_write=True)
    def factory_mutate(c, s):
        async def h() -> DummyOutput:
            return DummyOutput()
        return h

    # Token HAS runs:write, but server setting has allow_write_tools=False
    settings_blocked = Settings(api_token="kw_live_dummy", allow_write_tools=False)
    client = KawachClient(settings_blocked)
    auth_info = AuthMeInfo(scopes=["runs:write"])

    server = create_mcp_server(settings_blocked, client, auth_info)
    registered = list(server._tool_manager._tools.keys())
    assert "mutating_action" not in registered

    # Now enable allow_write_tools=True
    settings_allowed = Settings(api_token="kw_live_dummy", allow_write_tools=True)
    server_allowed = create_mcp_server(settings_allowed, client, auth_info)
    registered_allowed = list(server_allowed._tool_manager._tools.keys())
    assert "mutating_action" in registered_allowed


def test_get_server_status_tool(monkeypatch):
    """Verify get_server_status tool executes and returns sanitized configuration."""
    import anyio

    async def _test():
        settings = Settings(
            api_url="http://test-server:8000",
            api_token="kw_live_dummy_token_123",
            allow_write_tools=False,
        )
        client = KawachClient(settings)

        async def mock_introspect():
            return AuthMeInfo(
                client_type="mcp",
                scopes=["projects:read", "runs:read"],
                email="test@kawach.ai",
            )

        monkeypatch.setattr(client, "introspect_token", mock_introspect)

        auth_info = await client.introspect_token()
        server = create_mcp_server(settings, client, auth_info)

        res = await server.call_tool("get_server_status", {})
        assert res.is_error is False
        assert res.structured_content["status"] == "connected"
        assert res.structured_content["client_type"] == "mcp"
        assert "projects:read" in res.structured_content["granted_scopes"]
        assert res.structured_content["write_tools_enabled"] is False

    anyio.run(_test)
