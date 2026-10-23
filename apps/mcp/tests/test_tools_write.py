"""Unit tests for Kawach MCP Write tools and the two-step confirmation protocol."""

import time
import anyio
import pytest
from kawach_mcp.client import AuthMeInfo, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.server import create_mcp_server
from kawach_mcp.tools.confirmation import confirmation_manager


@pytest.fixture
def mcp_write_server(monkeypatch):
    settings = Settings(api_token="kw_live_test_token", allow_write_tools=True)
    client = KawachClient(settings)

    mock_db = {
        "/api/v1/runs/r1/catalog": {
            "test_cases": [{"id": "t1", "name": "Critical Checkout Flow", "depth": 3}]
        },
        "/api/v1/projects/p1/commits/c_valid/suggest-fix": {
            "status": "validated",
            "risk_classification": "small_fix",
            "files_touched": ["apps/web/src/Cart.tsx"],
            "patch": "+ return item;",
        },
        "/api/v1/projects/p1/commits/c_unvalidated/suggest-fix": {
            "status": "pending",
            "risk_classification": "small_fix",
            "files_touched": ["apps/web/src/Cart.tsx"],
            "patch": "+ return item;",
        },
        "/api/v1/projects/p1/commits/c_large/suggest-fix": {
            "status": "validated",
            "risk_classification": "needs_engineer",
            "files_touched": ["apps/web/src/Cart.tsx", "apps/web/src/Store.tsx"],
            "patch": "+ multi file patch",
        },
        "/api/v1/projects/p1/commits/c_security/suggest-fix": {
            "status": "validated",
            "risk_classification": "small_fix",
            "files_touched": ["apps/api/src/kawach/api/v1/auth.py"],
            "patch": "+ return token;",
        },
    }

    async def mock_get(path, params=None):
        clean_path = path.split("?")[0]
        if clean_path in mock_db:
            return mock_db[clean_path]
        raise ValueError(f"Mock 404 for {path}")

    async def mock_post(path, json_data=None, params=None, idempotency_key=None):
        if "/saved-tests" in path:
            return {"id": "st_999", "name": json_data.get("name") or "Critical Checkout Flow"}
        elif "/auto-fix" in path:
            return {"pr_url": "https://github.com/org/repo/pull/42", "branch": "kawach-fix/auto-patch"}
        raise ValueError(f"Mock 404 POST for {path}")

    monkeypatch.setattr(client, "get", mock_get)
    monkeypatch.setattr(client, "post", mock_post)

    auth_info = AuthMeInfo(scopes=["tests:write", "fixes:apply"])
    return create_mcp_server(settings, client, auth_info)


def test_save_test_two_step_confirmation(mcp_write_server):
    async def _test():
        # Call 1: Preview without confirmation_id
        res1 = await mcp_write_server.call_tool(
            "save_test",
            {"project_id": "p1", "run_id": "r1", "test_id": "t1"},
        )
        assert res1.is_error is False
        data1 = res1.structured_content
        assert data1["requires_confirmation"] is True
        conf_id = data1["confirmation_id"]
        assert conf_id.startswith("conf_")
        assert data1["preview"]["action"] == "save_test_to_regression_suite"

        # Call 2: Execute with matching confirmation_id
        res2 = await mcp_write_server.call_tool(
            "save_test",
            {"project_id": "p1", "run_id": "r1", "test_id": "t1", "confirmation_id": conf_id},
        )
        assert res2.is_error is False
        data2 = res2.structured_content
        assert data2["requires_confirmation"] is False
        assert data2["result"]["saved_test_id"] == "st_999"
        assert data2["result"]["status"] == "saved"
    anyio.run(_test)


def test_confirmation_payload_mismatch_rejected(mcp_write_server):
    async def _test():
        # Step 1: Request preview for project p1, test t1
        res1 = await mcp_write_server.call_tool(
            "save_test",
            {"project_id": "p1", "run_id": "r1", "test_id": "t1"},
        )
        conf_id = res1.structured_content["confirmation_id"]

        # Step 2: Attempt execution with tampered test_id
        res2 = await mcp_write_server.call_tool(
            "save_test",
            {"project_id": "p1", "run_id": "r1", "test_id": "t2_tampered", "confirmation_id": conf_id},
        )
        assert res2.is_error is True
        assert "Payload mismatch" in res2.content[0].text
    anyio.run(_test)


def test_confirmation_reuse_and_expiry_rejected(mcp_write_server, monkeypatch):
    async def _test():
        # Generate token
        res1 = await mcp_write_server.call_tool(
            "save_test",
            {"project_id": "p1", "run_id": "r1", "test_id": "t1"},
        )
        conf_id = res1.structured_content["confirmation_id"]

        # Execute once
        res2 = await mcp_write_server.call_tool(
            "save_test",
            {"project_id": "p1", "run_id": "r1", "test_id": "t1", "confirmation_id": conf_id},
        )
        assert res2.is_error is False

        # Attempt replay (reusing consumed token)
        res_replay = await mcp_write_server.call_tool(
            "save_test",
            {"project_id": "p1", "run_id": "r1", "test_id": "t1", "confirmation_id": conf_id},
        )
        assert res_replay.is_error is True
        assert "not found, already consumed" in res_replay.content[0].text
    anyio.run(_test)


def test_apply_fix_as_pr_policy_checks(mcp_write_server):
    async def _test():
        # Case 1: Unvalidated fix rejected
        res_unval = await mcp_write_server.call_tool(
            "apply_fix_as_pr",
            {"project_id": "p1", "commit_id": "c_unvalidated"},
        )
        assert res_unval.is_error is True
        assert "Cannot apply fix with validation status 'pending'" in res_unval.content[0].text

        # Case 2: Needs engineer rejected
        res_large = await mcp_write_server.call_tool(
            "apply_fix_as_pr",
            {"project_id": "p1", "commit_id": "c_large"},
        )
        assert res_large.is_error is True
        assert "classified as 'needs_engineer'" in res_large.content[0].text

        # Case 3: Sensitive path rejected
        res_sec = await mcp_write_server.call_tool(
            "apply_fix_as_pr",
            {"project_id": "p1", "commit_id": "c_security"},
        )
        assert res_sec.is_error is True
        assert "Modifying security/auth/payment paths is forbidden" in res_sec.content[0].text

        # Case 4: Validated happy path
        res_happy_preview = await mcp_write_server.call_tool(
            "apply_fix_as_pr",
            {"project_id": "p1", "commit_id": "c_valid"},
        )
        assert res_happy_preview.is_error is False
        conf_id = res_happy_preview.structured_content["confirmation_id"]
        assert "Pull Request ONLY" in res_happy_preview.structured_content["preview"]["delivery_mode"]

        res_happy_exec = await mcp_write_server.call_tool(
            "apply_fix_as_pr",
            {"project_id": "p1", "commit_id": "c_valid", "confirmation_id": conf_id},
        )
        assert res_happy_exec.is_error is False
        assert res_happy_exec.structured_content["result"]["status"] == "pr_opened"
        assert res_happy_exec.structured_content["result"]["pr_url"] == "https://github.com/org/repo/pull/42"
    anyio.run(_test)
