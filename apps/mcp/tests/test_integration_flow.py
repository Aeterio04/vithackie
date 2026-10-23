"""End-to-End integration test for Kawach MCP Server over real OS stdio transport."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class MockBackendHandler(BaseHTTPRequestHandler):
    """Minimal mock HTTP backend responding to the demo flow."""

    def log_message(self, format, *args):
        pass  # Suppress console logging

    def do_GET(self):
        clean_path = self.path.split("?")[0]
        if clean_path == "/api/v1/auth/me":
            self._send_json(200, {
                "client_type": "mcp",
                "scopes": ["runs:read", "runs:write", "tests:read", "tests:write", "fixes:apply"],
                "is_session": False,
                "token_id": "tok_demo_123",
            })
        elif clean_path == "/api/v1/runs/demo_run_1":
            self._send_json(200, {
                "id": "demo_run_1",
                "status": "completed",
                "stage": "done",
                "current_progress": 100.0,
                "confirmed_bugs": 1,
                "flaky_bugs": 0,
            })
        elif clean_path == "/api/v1/runs/demo_run_1/bugs":
            self._send_json(200, [
                {
                    "id": "bug_demo_1",
                    "title": "500 Error on submit",
                    "verification_status": "confirmed",
                    "replay_count": 3,
                    "depth": 2,
                    "failing_step": 3,
                    "error_message": "Crash on button submit: checkout_state is undefined",
                }
            ])
        elif "/analysis" in clean_path:
            self._send_json(200, {
                "summary": "Culprit candidate localized to checkout payment handler.",
                "culprit_candidates": [
                    {
                        "file_path": "apps/web/src/Checkout.tsx",
                        "confidence": 0.95,
                        "line_range": [42, 50],
                        "reason": "Unchecked null pointer on payment processing response",
                    }
                ],
            })
        elif "/suggest-fix" in clean_path:
            self._send_json(200, {
                "status": "validated",
                "risk_classification": "small_fix",
                "diff_patch": "--- a/Checkout.tsx\n+++ b/Checkout.tsx\n@@ -42,1 +42,1 @@\n- return payment.process();\n+ return payment ? payment.process() : null;",
                "files_touched": ["apps/web/src/Checkout.tsx"],
                "lines_touched": 2,
            })
        else:
            self._send_json(404, {"detail": "Not found"})

    def do_POST(self):
        clean_path = self.path.split("?")[0]
        if clean_path == "/api/v1/runs":
            self._send_json(201, {
                "id": "demo_run_1",
                "status": "running",
                "stage": "exploring",
            })
        elif "/regression-runs" in clean_path:
            self._send_json(201, {
                "run_id": "reg_run_demo_100",
                "status": "running",
                "selected_test_ids": ["test_checkout_flow"],
            })
        else:
            self._send_json(404, {"detail": "Not found"})

    def _send_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


@pytest.fixture(scope="module")
def mock_backend_server():
    """Start an ephemeral HTTP backend for real stdio integration testing."""
    server = HTTPServer(("127.0.0.1", 0), MockBackendHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_mcp_stdio_demo_flow(mock_backend_server):
    """Execute the complete demo flow over real OS stdio transport with ClientSession:
    
    start_run -> wait_for_run -> list_failures -> run_regression -> get_failure_analysis -> get_fix_suggestion
    """
    server_env = dict(os.environ)
    server_env["KAWACH_API_URL"] = mock_backend_server
    server_env["KAWACH_API_TOKEN"] = "kw_live_demo_integration_token_777"
    server_env["KAWACH_ALLOW_WRITE_TOOLS"] = "true"
    server_env["PYTHONPATH"] = "apps/mcp/src;apps/api/src"

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "kawach_mcp.server"],
        env=server_env,
    )

    async def _run_demo():
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 1. Initialize MCP protocol handshake
                init_res = await session.initialize()
                assert init_res.server_info.name == "kawach"

                # 2. Check registered tools (must have all 23 tools since all scopes granted)
                tools_res = await session.list_tools()
                tool_names = {t.name for t in tools_res.tools}
                assert "start_run" in tool_names
                assert "wait_for_run" in tool_names
                assert "list_failures" in tool_names
                assert "run_regression" in tool_names
                assert "get_failure_analysis" in tool_names
                assert "get_fix_suggestion" in tool_names

                # Step 1: Start Run
                start_call = await session.call_tool(
                    "start_run",
                    {"target_url": "http://localhost:4000", "mode": "autonomous"},
                )
                assert start_call.is_error is False
                start_data = start_call.structured_content or json.loads(start_call.content[0].text)
                run_id = start_data["run_id"]
                assert run_id == "demo_run_1"

                # Step 2: Wait for Run (poll progress until terminal state)
                wait_call = await session.call_tool(
                    "wait_for_run",
                    {"run_id": run_id, "timeout_seconds": 10, "poll_interval_seconds": 1},
                )
                wait_data = wait_call.structured_content or json.loads(wait_call.content[0].text)
                assert wait_data["completed"] is True
                assert wait_data["status"] == "completed"
                assert wait_data["confirmed_bugs"] == 1

                # Step 3: List Failures
                fail_call = await session.call_tool("list_failures", {"run_id": run_id})
                fail_data = fail_call.structured_content or json.loads(fail_call.content[0].text)
                bugs = fail_data["bugs"]
                assert len(bugs) == 1
                assert bugs[0]["id"] == "bug_demo_1"
                assert "<untrusted_content type=\"bug_assertion\"" in bugs[0]["assertion_snippet"]

                # Step 4: Run Regression on simulated bad commit
                reg_call = await session.call_tool(
                    "run_regression",
                    {"project_id": "demo_proj", "commit_sha": "bad_commit_sha_123"},
                )
                reg_data = reg_call.structured_content or json.loads(reg_call.content[0].text)
                reg_run_id = reg_data["run_id"]
                assert reg_run_id == "reg_run_demo_100"

                # Step 5: Get Failure Analysis
                analysis_call = await session.call_tool(
                    "get_failure_analysis",
                    {"project_id": "demo_proj", "commit_id": "bad_commit_sha_123"},
                )
                analysis_data = analysis_call.structured_content or json.loads(analysis_call.content[0].text)
                candidates = analysis_data["culprit_candidates"]
                assert len(candidates) == 1
                assert candidates[0]["repo_relative_path"] == "apps/web/src/Checkout.tsx"
                assert candidates[0]["confidence_pct"] == 95.0
                assert candidates[0]["line_range"] == [42, 50]

                # Step 6: Get Fix Suggestion
                fix_call = await session.call_tool(
                    "get_fix_suggestion",
                    {"project_id": "demo_proj", "commit_id": "bad_commit_sha_123"},
                )
                fix_data = fix_call.structured_content or json.loads(fix_call.content[0].text)
                assert fix_data["risk_level"] == "small_fix"
                assert fix_data["validation_status"] == "validated"
                assert "<untrusted_content type=\"unified_diff\"" in fix_data["diff_patch"]
                assert "payment ? payment.process() : null" in fix_data["diff_patch"]

    anyio.run(_run_demo)
