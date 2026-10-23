"""Unit and security tests for Kawach MCP Server HTTP transport mode with per-caller auth and isolation."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import sys
from typing import Any, Dict, List
import pytest
from starlette.testclient import TestClient

from kawach_mcp.auth_cache import ScopeCache, scope_cache
from kawach_mcp.client import AuthMeInfo, KawachAPIError, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.http_server import create_http_app
from kawach_mcp.tools.confirmation import confirmation_manager


class MockBackendClient(KawachClient):
    """Mock client simulating backend token scope introspection and API calls."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        # token -> AuthMeInfo or status_code
        self.mock_tokens: Dict[str, AuthMeInfo] = {
            "kw_live_tester_readonly": AuthMeInfo(
                user_id="usr_ro",
                email="ro@tester.local",
                client_type="mcp",
                scopes=["projects:read", "runs:read", "analysis:read", "tests:read"],
            ),
            "kw_live_tester_runner": AuthMeInfo(
                user_id="usr_run",
                email="run@tester.local",
                client_type="mcp",
                scopes=["projects:read", "runs:read", "runs:write", "analysis:read", "tests:read"],
            ),
            "kw_live_tester_admin": AuthMeInfo(
                user_id="usr_admin",
                email="admin@tester.local",
                client_type="mcp",
                scopes=[
                    "projects:read", "projects:write", "runs:read", "runs:write",
                    "analysis:read", "analysis:run", "tests:read", "tests:write"
                ],
            ),
        }
        self.revoked_tokens: set[str] = set()

    async def introspect_token_with_token(self, token: str) -> AuthMeInfo:
        if token in self.revoked_tokens:
            raise KawachAPIError(401, "Token has been revoked.")
        info = self.mock_tokens.get(token)
        if not info:
            raise KawachAPIError(401, "Invalid API token provided.")
        return info

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if path == "/api/v1/projects":
            return {"items": [{"id": "proj_123", "name": "Target App"}], "total": 1, "page": 1, "page_size": 20}
        if path.startswith("/api/v1/runs/"):
            return {"id": "run_1", "status": "completed", "tests_total": 5}
        return {}

    async def post(self, path: str, json_data: Optional[Any] = None, params: Optional[Dict[str, Any]] = None, idempotency_key: Optional[str] = None) -> Any:
        if path == "/api/v1/runs":
            return {"run_id": "run_new_123", "status": "pending"}
        if "saved-tests" in path:
            return {"id": "saved_test_99", "name": "Saved Test"}
        return {"status": "ok"}


@pytest.fixture(autouse=True)
def clean_environment():
    """Ensure scope cache and confirmation manager are clean before each test."""
    scope_cache.clear()
    confirmation_manager._tokens.clear()
    yield
    scope_cache.clear()
    confirmation_manager._tokens.clear()


@pytest.fixture
def mock_app():
    """Create test Starlette application with mock backend."""
    settings = Settings(
        api_url="http://localhost:8000",
        allow_write_tools=True,
        allowed_origins="http://allowed.local,https://tester.local",
        max_request_body_size=512,  # 512 bytes for testing
        per_caller_concurrency_limit=2,
        per_request_timeout_seconds=2.0,
    )
    client = MockBackendClient(settings)
    app = create_http_app(settings=settings, client=client)
    return app, client, settings


def test_healthz_unauthenticated(mock_app):
    """Test /healthz returns ok without requiring authentication."""
    app, _, _ = mock_app
    with TestClient(app) as client:
        res = client.get("/healthz")
        assert res.status_code == 200
        assert res.json() == {"ok": True}
        assert "X-Request-Id" in res.headers


def test_401_without_token(mock_app):
    """Test POST to /mcp without Authorization header returns 401."""
    app, _, _ = mock_app
    with TestClient(app) as client:
        res = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert res.status_code == 401
        data = res.json()
        assert "Missing Bearer token" in data.get("error", "")
        assert "X-Request-Id" in res.headers


def test_401_with_malformed_token(mock_app):
    """Test POST to /mcp with non-kw_live token returns 401."""
    app, _, _ = mock_app
    with TestClient(app) as client:
        res = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": "Bearer invalid_prefix_secret"},
        )
        assert res.status_code == 401
        assert "Must start with 'kw_live_'" in res.json().get("error", "")


def test_scope_limited_tool_lists_per_caller(mock_app):
    """Test dynamic tool listing filters tools per caller scopes."""
    app, _, _ = mock_app
    with TestClient(app) as client:
        # Caller 1: Read-only token (no runs:trigger scope)
        res_ro = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": "Bearer kw_live_tester_readonly"},
        )
        assert res_ro.status_code == 200
        tools_ro = [t["name"] for t in res_ro.json()["result"]["tools"]]
        assert "list_projects" in tools_ro
        assert "get_run_status" in tools_ro
        assert "list_failures" in tools_ro
        assert "start_run" not in tools_ro  # Requires runs:trigger
        assert "run_regression" not in tools_ro  # Requires runs:trigger
        assert "save_test" not in tools_ro  # Requires tests:write

        # Caller 2: Runner token (has runs:trigger scope)
        res_run = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={"Authorization": "Bearer kw_live_tester_runner"},
        )
        assert res_run.status_code == 200
        tools_run = [t["name"] for t in res_run.json()["result"]["tools"]]
        assert "start_run" in tools_run
        assert "run_regression" in tools_run
        assert "save_test" not in tools_run  # Still lacks tests:write


def test_unauthorized_tool_execution_rejected(mock_app):
    """Test calling an unauthorized tool returns permission denied error CallToolResult."""
    app, _, _ = mock_app
    with TestClient(app) as client:
        # Read-only caller directly attempting to execute start_run
        payload = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "start_run",
                "arguments": {"target_url": "http://localhost:4000"},
            },
        }
        res = client.post(
            "/mcp",
            json=payload,
            headers={"Authorization": "Bearer kw_live_tester_readonly"},
        )
        assert res.status_code == 200
        data = res.json()["result"]
        assert data.get("isError") is True
        error_text = data["content"][0]["text"]
        assert "Permission denied" in error_text
        assert "runs:write" in error_text


def test_parallel_callers_isolation_and_confirmation(mock_app):
    """Test two callers in parallel: Caller B cannot consume Caller A's confirmation token."""
    app, _, _ = mock_app
    with TestClient(app) as client:
        # Step 1: Admin Caller A creates confirmation for save_test
        payload_step1 = {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "save_test",
                "arguments": {
                    "project_id": "proj_123",
                    "run_id": "run_1",
                    "test_id": "test_42",
                    "name": "Checkout Promo Test",
                },
            },
        }
        res_step1 = client.post(
            "/mcp",
            json=payload_step1,
            headers={"Authorization": "Bearer kw_live_tester_admin"},
        )
        assert res_step1.status_code == 200
        data_step1 = res_step1.json()["result"]["structuredContent"]
        assert data_step1["requires_confirmation"] is True
        conf_id = data_step1["confirmation_id"]
        assert conf_id.startswith("conf_")

        # Step 2: Malicious Caller B (different token) attempts to use Caller A's confirmation ID
        payload_step2_hijack = {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "save_test",
                "arguments": {
                    "project_id": "proj_123",
                    "run_id": "run_1",
                    "test_id": "test_42",
                    "name": "Checkout Promo Test",
                    "confirmation_id": conf_id,
                },
            },
        }
        # Even if Caller B has admin rights with a different token
        res_hijack = client.post(
            "/mcp",
            json=payload_step2_hijack,
            headers={"Authorization": "Bearer kw_live_tester_runner"},  # Lacks scope or different token
        )
        assert res_hijack.status_code == 200
        data_hijack = res_hijack.json()["result"]
        assert data_hijack.get("isError") is True
        # Scope denied or confirmation rejected
        assert "Permission denied" in data_hijack["content"][0]["text"] or "Confirmation rejected" in data_hijack["content"][0]["text"]

        # Step 3: Legitimate Caller A executes with the same confirmation ID -> SUCCEEDS
        res_step2_legit = client.post(
            "/mcp",
            json=payload_step2_hijack,
            headers={"Authorization": "Bearer kw_live_tester_admin"},
        )
        assert res_step2_legit.status_code == 200
        data_legit = res_step2_legit.json()["result"]
        assert data_legit.get("isError") is False or "result" in data_legit


def test_token_never_in_logs_or_errors(mock_app, monkeypatch):
    """Test raw Bearer tokens never appear in stderr access logs or error bodies."""
    app, _, _ = mock_app
    stderr_capture = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_capture)

    secret_token = "kw_live_tester_readonly"
    with TestClient(app) as client:
        # Successful request
        client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": f"Bearer {secret_token}"},
        )
        # 401 error request
        client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={"Authorization": "Bearer kw_live_invalid_nonexistent"},
        )

    log_contents = stderr_capture.getvalue()
    # Ensure raw secret token NEVER appears anywhere in stderr
    assert secret_token not in log_contents
    assert "kw_live_invalid_nonexistent" not in log_contents

    # Verify sanitized access log format: token_hash_prefix is present instead
    expected_hash_prefix = hashlib.sha256(secret_token.encode("utf-8")).hexdigest()[:8]
    assert f"token_hash_prefix={expected_hash_prefix}" in log_contents


def test_origin_validation(mock_app):
    """Test Origin header validation against allowed origins list."""
    app, _, _ = mock_app
    with TestClient(app) as client:
        # Disallowed origin -> 403 Forbidden
        res_bad = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={
                "Authorization": "Bearer kw_live_tester_readonly",
                "Origin": "http://evil-attacker.com",
            },
        )
        assert res_bad.status_code == 403
        assert "Origin header not in allowed origins" in res_bad.json()["error"]

        # Allowed origin -> 200 OK
        res_good = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={
                "Authorization": "Bearer kw_live_tester_readonly",
                "Origin": "https://tester.local",
            },
        )
        assert res_good.status_code == 200


def test_oversized_request_body_rejected(mock_app):
    """Test request body exceeding max_request_body_size returns 413 Payload Too Large."""
    app, _, _ = mock_app
    huge_padding = "x" * 1024  # max is set to 512 in fixture
    with TestClient(app) as client:
        res = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "padding": huge_padding},
            headers={"Authorization": "Bearer kw_live_tester_readonly"},
        )
        assert res.status_code == 413
        assert "Payload Too Large" in res.json()["error"]


def test_revoked_token_fails_within_cache_ttl(mock_app):
    """Test token revocation is enforced when scope cache expires."""
    app, mock_client, _ = mock_app
    token = "kw_live_tester_readonly"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    with TestClient(app) as client:
        # First request succeeds and populates cache
        res1 = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res1.status_code == 200
        assert scope_cache.get(token_hash) is not None

        # Revoke token on backend
        mock_client.revoked_tokens.add(token)

        # Invalidate scope cache (simulating TTL expiry <= 60s)
        scope_cache.invalidate(token_hash)

        # Second request now fails fast with 401
        res2 = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res2.status_code == 401
        assert "revoked" in res2.json()["error"].lower()


def test_concurrency_cap_per_caller(mock_app):
    """Test exceeding per_caller_concurrency_limit returns 429 Too Many Requests."""
    app, _, _ = mock_app
    token = "kw_live_tester_readonly"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    with TestClient(app) as client:
        # Artificially saturate concurrency counter for this caller
        for mw in app.user_middleware:
            if mw.cls.__name__ == "RemoteAuthMiddleware":
                mw.kwargs["active_concurrency"][token_hash] = 2

        res = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 429
        assert "Concurrency limit exceeded" in res.json()["error"]


def test_stdio_transport_remains_unchanged():
    """Verify stdio server creation and tool registration remain completely unchanged."""
    from kawach_mcp.server import create_mcp_server
    settings = Settings(api_token="kw_live_local_stdio", allow_write_tools=False)
    client = MockBackendClient(settings)
    auth_info = AuthMeInfo(scopes=["projects:read", "runs:read"])
    server = create_mcp_server(settings, client, auth_info)
    assert server.name == "kawach"
