"""Unit tests for Kawach HTTP client, header generation, retry logic, and error mapping."""

import uuid
import httpx
import pytest
from kawach_mcp.client import KawachAPIError, KawachClient
from kawach_mcp.config import Settings


@pytest.fixture
def test_settings():
    return Settings(
        api_url="http://test-server:8000",
        api_token="kw_live_test_client_token_123",
        request_timeout_seconds=5.0,
        max_retries=2,
    )


def test_build_headers_standard(test_settings):
    """Verify headers include client_type, request_id, and Authorization."""
    client = KawachClient(test_settings)
    headers = client._build_headers(idempotency_key="idemp-key-xyz")

    assert headers["X-Client-Type"] == "mcp"
    assert headers["Authorization"] == "Bearer kw_live_test_client_token_123"
    assert headers["Idempotency-Key"] == "idemp-key-xyz"
    # Verify request-id is a valid UUID
    uuid.UUID(headers["X-Request-ID"])


def test_map_http_error_401(test_settings):
    """Verify 401 produces actionable authentication message."""
    client = KawachClient(test_settings)
    resp = httpx.Response(401, request=httpx.Request("GET", "http://test-server/api"))
    err = client._map_http_error(resp)
    assert err.status_code == 401
    assert "KAWACH_API_TOKEN is invalid or expired" in err.message


def test_map_http_error_404_foreign_indistinguishable(test_settings):
    """Verify 404 error message does not distinguish between foreign vs nonexistent resources."""
    client = KawachClient(test_settings)
    resp = httpx.Response(404, request=httpx.Request("GET", "http://test-server/api"))
    err = client._map_http_error(resp)
    assert err.status_code == 404
    assert "Resource not found" in err.message
    assert "or you do not have permission" in err.message


def test_map_http_error_422_formatting(test_settings):
    """Verify 422 validation errors are cleanly extracted without raw traceback dumps."""
    client = KawachClient(test_settings)
    body = {
        "detail": [
            {"loc": ["body", "project_id"], "msg": "Field required", "type": "missing"},
            {"loc": ["body", "depth"], "msg": "Must be greater than 0", "type": "value_error"},
        ]
    }
    resp = httpx.Response(422, json=body, request=httpx.Request("POST", "http://test-server/api"))
    err = client._map_http_error(resp)
    assert err.status_code == 422
    assert "Validation failed: 'project_id': Field required; 'depth': Must be greater than 0" in err.message


def test_map_http_error_redacts_secrets_in_backend_body(test_settings):
    """Verify that if backend accidentally echoes a secret, error mapping redacts it."""
    client = KawachClient(test_settings)
    body = {"detail": "Failed connecting with token kw_live_backend_leaked_key_999"}
    resp = httpx.Response(500, json=body, request=httpx.Request("GET", "http://test-server/api"))
    err = client._map_http_error(resp)
    assert "kw_live_" not in err.to_user_message()


def test_client_retry_on_429(monkeypatch, test_settings):
    """Verify client retries on 429 rate limit errors."""
    import anyio

    async def _test():
        client = KawachClient(test_settings)
        call_count = 0

        async def mock_send(request, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return httpx.Response(429, request=request)
            return httpx.Response(200, json={"ok": True}, request=request)

        async_client = await client.get_client()
        monkeypatch.setattr(async_client, "send", mock_send)

        async def _noop_sleep(*args, **kwargs):
            return None

        monkeypatch.setattr("asyncio.sleep", _noop_sleep)

        resp_data = await client.get("/api/v1/test")
        assert resp_data == {"ok": True}
        assert call_count == 2

    anyio.run(_test)
