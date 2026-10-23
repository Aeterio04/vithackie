"""Unit tests for Kawach MCP Action tools (start_run, approve_catalog, run_regression, wait_for_run)."""

import anyio
import pytest
from kawach_mcp.client import AuthMeInfo, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.server import create_mcp_server


@pytest.fixture
def mcp_action_server(monkeypatch):
    settings = Settings(api_token="kw_live_test_token", allow_write_tools=False)
    client = KawachClient(settings)

    captured_posts = []

    async def mock_post(path, json_data=None, params=None, idempotency_key=None):
        captured_posts.append({"path": path, "json": json_data, "idempotency_key": idempotency_key})
        if path == "/api/v1/runs":
            return {"id": "run_new_123", "status": "running", "stage": "init"}
        elif "/execute" in path:
            return {"id": "run_new_123", "status": "running", "stage": "executing", "target_url": "http://target"}
        elif "/regression-runs" in path:
            return {"run_id": "reg_run_456", "status": "running", "selected_test_ids": ["t1", "t2"]}
        raise ValueError(f"Unknown POST path {path}")

    poll_count = 0

    async def mock_get(path, params=None):
        nonlocal poll_count
        if "/api/v1/runs/run_poll" in path:
            poll_count += 1
            if poll_count < 2:
                return {"id": "run_poll", "status": "running", "stage": "executing", "current_progress": 45.0}
            return {"id": "run_poll", "status": "completed", "stage": "done", "current_progress": 100.0, "confirmed_bugs": 2}
        raise ValueError(f"Unknown GET path {path}")

    monkeypatch.setattr(client, "post", mock_post)
    monkeypatch.setattr(client, "get", mock_get)

    auth_info = AuthMeInfo(scopes=["runs:read", "runs:write"])
    server = create_mcp_server(settings, client, auth_info)
    return server, captured_posts


def test_start_run_action(mcp_action_server):
    server, captured = mcp_action_server

    async def _test():
        res = await server.call_tool(
            "start_run",
            {"target_url": "http://target:4000", "mode": "autonomous", "idempotency_key": "idemp-1"},
        )
        assert res.is_error is False
        assert res.structured_content["run_id"] == "run_new_123"
        assert res.structured_content["status"] == "running"
        assert captured[0]["idempotency_key"] == "idemp-1"
        assert captured[0]["json"]["target_url"] == "http://target:4000"
    anyio.run(_test)


def test_run_regression_action(mcp_action_server):
    server, captured = mcp_action_server

    async def _test():
        res = await server.call_tool(
            "run_regression",
            {"project_id": "proj_abc", "commit_sha": "a1b2c3d4", "idempotency_key": "reg-idemp-2"},
        )
        assert res.is_error is False
        assert res.structured_content["run_id"] == "reg_run_456"
        assert res.structured_content["selected_tests_count"] == 2
        assert captured[-1]["idempotency_key"] == "reg-idemp-2"
    anyio.run(_test)


def test_wait_for_run_bounded_poll(mcp_action_server, monkeypatch):
    server, _ = mcp_action_server

    async def _test():
        async def _fast_sleep(*args):
            pass
        monkeypatch.setattr("asyncio.sleep", _fast_sleep)

        res = await server.call_tool("wait_for_run", {"run_id": "run_poll", "timeout_seconds": 10, "poll_interval_seconds": 1})
        assert res.is_error is False
        assert res.structured_content["completed"] is True
        assert res.structured_content["status"] == "completed"
        assert res.structured_content["confirmed_bugs"] == 2
    anyio.run(_test)
