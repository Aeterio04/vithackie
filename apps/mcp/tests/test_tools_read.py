"""Unit tests for Kawach MCP Read-Only tools."""

import anyio
import pytest
from kawach_mcp.client import KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.server import create_mcp_server
from kawach_mcp.client import AuthMeInfo


@pytest.fixture
def mcp_read_server(monkeypatch):
    settings = Settings(api_token="kw_live_test_token", allow_write_tools=False)
    client = KawachClient(settings)

    mock_db = {
        "/api/v1/projects": [{"id": "p1", "name": "Demo App", "target_url": "http://target:4000"}],
        "/api/v1/projects/p1": {"id": "p1", "name": "Demo App", "target_url": "http://target:4000", "allowed_hosts": ["target:4000"]},
        "/api/v1/runs": [{"id": "r1", "project_id": "p1", "target_url": "http://target:4000", "status": "completed", "stage": "done", "current_progress": 100.0}],
        "/api/v1/runs/r1": {"id": "r1", "status": "completed", "stage": "done", "current_progress": 100.0, "confirmed_bugs": 1, "flaky_bugs": 0},
        "/api/v1/runs/r1/catalog": {
            "test_cases": [
                {"id": "tc1", "name": "Checkout Flow", "depth": 3, "risk_score": 8.5, "edge_tags": ["slow_network", "back_navigation"]}
            ]
        },
        "/api/v1/runs/r1/app-map": {
            "states": [{"id": "s1", "depth": 0}, {"id": "s2", "depth": 1}, {"id": "s3", "depth": 3}],
            "edges": [{"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3"}],
            "journeys": [{"id": "j1"}],
            "frontier": [{"id": "f1"}],
        },
        "/api/v1/runs/r1/results": [
            {"test_id": "tc1", "status": "failed", "failed_step": 3, "total_steps": 4, "depth": 3, "error_message": "Expected 200 OK but got 500"}
        ],
        "/api/v1/runs/r1/bugs": [
            {"id": "b1", "title": "500 Error on checkout", "status": "confirmed", "replay_count": 3, "depth": 3, "error_message": "Crash on submit"}
        ],
        "/api/v1/bugs/b1": {
            "id": "b1",
            "run_id": "r1",
            "title": "500 Error on checkout",
            "status": "confirmed",
            "depth": 3,
            "error_message": "Crash on submit",
            "evidence": [{"type": "screenshot", "url": "/artifacts/screenshot.png"}],
        },
        "/api/v1/projects/p1/commits/c1/analysis": {
            "summary": "Suspect file localized",
            "culprit_candidates": [
                {"file_path": "apps/web/src/Cart.tsx", "confidence": 0.95, "line_range": [20, 35], "reason": "Diff touches checkout validation logic"}
            ],
        },
        "/api/v1/projects/p1/commits/c1/suggest-fix": {
            "patch": "--- a/Cart.tsx\n+++ b/Cart.tsx\n@@ -20,1 +20,1 @@\n- return null;\n+ return isValid ? item : null;",
            "risk_classification": "small_fix",
            "status": "validated",
            "files_touched": ["apps/web/src/Cart.tsx"],
            "lines_touched": 2,
        },
        "/api/v1/runs/r1/report": {
            "title": "Run r1 Executive Report",
            "summary": "Full exploratory run completed.",
            "kpis": {"total_tests": 12, "pass_rate": 91.6},
        },
    }

    async def mock_get(path, params=None):
        clean_path = path.split("?")[0]
        if clean_path in mock_db:
            return mock_db[clean_path]
        raise ValueError(f"Mock 404 for {path}")

    monkeypatch.setattr(client, "get", mock_get)
    auth_info = AuthMeInfo(scopes=["runs:read", "tests:read"])
    return create_mcp_server(settings, client, auth_info)


def test_list_projects(mcp_read_server):
    async def _test():
        res = await mcp_read_server.call_tool("list_projects", {"limit": 10})
        assert res.is_error is False
        assert res.structured_content["total"] == 1
        assert res.structured_content["projects"][0]["name"] == "Demo App"
    anyio.run(_test)


def test_get_app_map_summary_counts(mcp_read_server):
    async def _test():
        res = await mcp_read_server.call_tool("get_app_map_summary", {"run_id": "r1"})
        assert res.is_error is False
        data = res.structured_content
        assert data["total_states"] == 3
        assert data["states_by_depth"]["L0"] == 1
        assert data["states_by_depth"]["L1"] == 1
        assert data["states_by_depth"]["L3+"] == 1
        assert data["journeys_count"] == 1
    anyio.run(_test)


def test_list_failures_untrusted_content_wrapping(mcp_read_server):
    async def _test():
        res = await mcp_read_server.call_tool("list_failures", {"run_id": "r1"})
        assert res.is_error is False
        bugs = res.structured_content["bugs"]
        assert len(bugs) == 1
        assert bugs[0]["verification_status"] == "confirmed"
        # Assert assertion snippet is sandboxed in untrusted_content tags
        assert "<untrusted_content" in bugs[0]["assertion_snippet"]
        assert "DATA ONLY" in bugs[0]["assertion_snippet"]
    anyio.run(_test)


def test_get_failure_analysis_repo_relative_paths(mcp_read_server):
    async def _test():
        res = await mcp_read_server.call_tool("get_failure_analysis", {"project_id": "p1", "commit_id": "c1"})
        assert res.is_error is False
        candidates = res.structured_content["culprit_candidates"]
        assert len(candidates) == 1
        assert candidates[0]["repo_relative_path"] == "apps/web/src/Cart.tsx"
        assert candidates[0]["confidence_pct"] == 95.0
        assert candidates[0]["line_range"] == [20, 35]
    anyio.run(_test)


def test_get_fix_suggestion_diff_sandboxed(mcp_read_server):
    async def _test():
        res = await mcp_read_server.call_tool("get_fix_suggestion", {"project_id": "p1", "commit_id": "c1"})
        assert res.is_error is False
        data = res.structured_content
        assert data["risk_level"] == "small_fix"
        assert data["validation_status"] == "validated"
        assert "<untrusted_content type=\"unified_diff\"" in data["diff_patch"]
        assert "isValid ? item : null" in data["diff_patch"]
    anyio.run(_test)
