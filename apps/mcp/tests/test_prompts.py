"""Unit tests for Kawach MCP Prompts."""

import anyio
import pytest
from kawach_mcp.client import AuthMeInfo, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.server import create_mcp_server


@pytest.fixture
def mcp_prompt_server():
    settings = Settings(api_token="kw_live_test_token", allow_write_tools=False)
    client = KawachClient(settings)
    auth_info = AuthMeInfo(scopes=["runs:read", "tests:read"])
    return create_mcp_server(settings, client, auth_info)


def test_list_prompts(mcp_prompt_server):
    async def _test():
        prompts = await mcp_prompt_server.list_prompts()
        names = [p.name for p in prompts]
        assert "triage_failing_commit" in names
        assert "explain_bug" in names
        assert "run_regression_for_my_changes" in names
        assert "review_fix_before_apply" in names
    anyio.run(_test)


def test_get_triage_failing_commit_prompt(mcp_prompt_server):
    async def _test():
        res = await mcp_prompt_server.get_prompt(
            "triage_failing_commit",
            {"project_id": "p_test", "commit_id": "sha_xyz123"},
        )
        assert len(res.messages) == 1
        msg = res.messages[0].content.text
        assert "commit `sha_xyz123`" in msg
        assert "get_failure_analysis" in msg
        assert "Inspect the culprit files locally in this workspace" in msg
        assert "get_fix_suggestion" in msg
    anyio.run(_test)


def test_get_explain_bug_prompt(mcp_prompt_server):
    async def _test():
        res = await mcp_prompt_server.get_prompt("explain_bug", {"bug_id": "bug_456"})
        assert len(res.messages) == 1
        msg = res.messages[0].content.text
        assert "defect `bug_456`" in msg
        assert "get_bug" in msg
        assert "repro-script" in msg
    anyio.run(_test)


def test_get_review_fix_before_apply_prompt(mcp_prompt_server):
    async def _test():
        res = await mcp_prompt_server.get_prompt(
            "review_fix_before_apply",
            {"project_id": "p_test", "commit_id": "sha_xyz123"},
        )
        assert len(res.messages) == 1
        msg = res.messages[0].content.text
        assert "3x deterministic replay" in msg
        assert "small_fix" in msg
        assert "<= 1 file and <= 20 lines" in msg
        assert "blocked sensitive categories" in msg
        assert "apply_fix_as_pr" in msg
    anyio.run(_test)
