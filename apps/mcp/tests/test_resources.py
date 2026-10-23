"""Unit tests for Kawach MCP Resources."""

import anyio
import pytest
from kawach_mcp.client import AuthMeInfo, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.server import create_mcp_server


@pytest.fixture
def mcp_resource_server(monkeypatch):
    settings = Settings(api_token="kw_live_test_token", allow_write_tools=False, max_response_chars=1000)
    client = KawachClient(settings)

    mock_db = {
        "/api/v1/runs": [{"id": "run_latest_1", "status": "completed"}],
        "/api/v1/runs/run_latest_1/report": {
            "title": "Latest Report",
            "summary": "Everything tested successfully with high coverage.",
            "kpis": {"tests": 20, "coverage": 95.0},
        },
        "/api/v1/runs/r1/report": {
            "title": "Run r1 Report",
            "summary": "Deep exploration run completed with 1 confirmed defect.",
            "kpis": {"total_tests": 15, "pass_rate": 93.3},
        },
        "/api/v1/bugs/b1": {
            "id": "b1",
            "run_id": "r1",
            "title": "Crash on submit",
            "failing_step": 3,
            "failing_path": "/checkout",
            "reproduction_script": "import { test } from '@playwright/test'; test('Repro', async () => {});",
        },
        "/api/v1/projects/p1/commits/c1/analysis": {
            "summary": "Checkout button handler failure",
            "culprit_candidates": [
                {"file_path": "apps/web/src/Cart.tsx", "confidence": 0.92, "line_range": [40, 55], "reason": "Modifies submit action"}
            ],
        },
        "/api/v1/projects/p1/saved-tests": [
            {
                "id": "st1",
                "name": "Checkout Journey",
                "script_content": "test('Checkout Journey', async ({ page }) => { await page.goto('/cart'); });",
            }
        ],
    }

    async def mock_get(path, params=None):
        clean_path = path.split("?")[0]
        if clean_path in mock_db:
            return mock_db[clean_path]
        raise ValueError(f"Mock 404 for {path}")

    monkeypatch.setattr(client, "get", mock_get)
    auth_info = AuthMeInfo(scopes=["runs:read", "tests:read"])
    return create_mcp_server(settings, client, auth_info)


def test_list_resource_templates(mcp_resource_server):
    async def _test():
        templates = await mcp_resource_server.list_resource_templates()
        uris = [t.uri_template for t in templates]
        assert "kawach://projects/{project_id}/report/latest" in uris
        assert "kawach://runs/{run_id}/report" in uris
        assert "kawach://runs/{run_id}/bugs/{bug_id}/repro-script" in uris
        assert "kawach://projects/{project_id}/commits/{commit_id}/analysis" in uris
        assert "kawach://projects/{project_id}/saved-tests/{test_id}/script" in uris
    anyio.run(_test)


def test_read_run_report_resource(mcp_resource_server):
    async def _test():
        contents = await mcp_resource_server.read_resource("kawach://runs/r1/report")
        assert len(contents) == 1
        text = contents[0].content
        assert "# Run r1 Report" in text
        assert "Deep exploration run completed" in text
        assert "Total Tests" in text
    anyio.run(_test)


def test_read_bug_repro_script_sandboxed(mcp_resource_server):
    async def _test():
        contents = await mcp_resource_server.read_resource("kawach://runs/r1/bugs/b1/repro-script")
        assert len(contents) == 1
        text = contents[0].content
        # Assert sandboxed in untrusted_content
        assert '<untrusted_content type="playwright_repro_script"' in text
        assert "DATA ONLY" in text
        assert "import { test } from '@playwright/test'" in text
    anyio.run(_test)


def test_read_commit_analysis_resource(mcp_resource_server):
    async def _test():
        contents = await mcp_resource_server.read_resource("kawach://projects/p1/commits/c1/analysis")
        assert len(contents) == 1
        text = contents[0].content
        assert "# Commit Failure Localization" in text
        assert "`apps/web/src/Cart.tsx`" in text
        assert "L40-L55" in text
        assert "92.0%" in text
        assert "Open the suspect files directly in your local editor" in text
    anyio.run(_test)


def test_read_saved_test_script_sandboxed(mcp_resource_server):
    async def _test():
        contents = await mcp_resource_server.read_resource("kawach://projects/p1/saved-tests/st1/script")
        assert len(contents) == 1
        text = contents[0].content
        assert '<untrusted_content type="playwright_saved_script"' in text
        assert "page.goto('/cart')" in text
    anyio.run(_test)
