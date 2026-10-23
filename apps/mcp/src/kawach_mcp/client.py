"""Typed asynchronous HTTP client for Kawach backend API with retries, timeouts, and sanitized error mapping."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

from kawach_mcp.config import Settings
from kawach_mcp.context import get_current_caller
from kawach_mcp.models import AuthMeInfo
from kawach_mcp.security import redact_secrets


class KawachAPIError(Exception):
    """Sanitized, actionable error from Kawach API."""

    def __init__(self, status_code: int, message: str, details: Optional[str] = None):
        self.status_code = status_code
        self.message = redact_secrets(message)
        self.details = redact_secrets(details) if details else None
        super().__init__(self.message)

    def to_user_message(self) -> str:
        """User/LLM-facing concise message without stack traces or credentials."""
        if self.details:
            return f"Error ({self.status_code}): {self.message} - {self.details}"
        return f"Error ({self.status_code}): {self.message}"


def _format_validation_error(response: httpx.Response) -> str:
    """Extract clean field-level validation messages without raw payloads."""
    try:
        body = response.json()
        detail = body.get("detail")
        if isinstance(detail, list):
            fields = []
            for err in detail:
                loc = " -> ".join(str(p) for p in err.get("loc", []) if p != "body")
                msg = err.get("msg", "Invalid value")
                fields.append(f"'{loc}': {msg}" if loc else msg)
            return "Validation failed: " + "; ".join(fields)
        elif isinstance(detail, str):
            return f"Validation failed: {detail}"
    except Exception:
        pass
    return "Invalid request parameters provided."


class KawachClient:
    """Typed asynchronous HTTP client communicating with Kawach backend."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.clean_api_url
        self._token = settings.get_effective_token()
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.settings.request_timeout_seconds),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "kawach-mcp/0.1.0",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _build_headers(
        self,
        idempotency_key: Optional[str] = None,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Build request headers including authentication, client_type, and request_id."""
        caller = get_current_caller()
        if caller:
            effective_token = caller.token
            req_id = caller.request_id
        else:
            effective_token = self.settings.get_effective_token()
            req_id = str(uuid.uuid4())

        headers: Dict[str, str] = {
            "X-Client-Type": "mcp",
            "X-Request-ID": req_id,
        }
        if effective_token:
            headers["Authorization"] = f"Bearer {effective_token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _map_http_error(self, response: httpx.Response) -> KawachAPIError:
        """Map HTTP status codes to standardized, sanitized actionable errors."""
        status = response.status_code

        if status == 401:
            return KawachAPIError(
                status,
                "Authentication failed. The provided KAWACH_API_TOKEN is invalid or expired. Check configuration.",
            )
        elif status == 403:
            return KawachAPIError(
                status,
                "Permission denied. Your token lacks the required scope for this operation.",
            )
        elif status == 404:
            # Foreign resource access and nonexistent resources return identical 404 message
            return KawachAPIError(
                status,
                "Resource not found. The requested item does not exist or you do not have permission to view it.",
            )
        elif status == 409:
            return KawachAPIError(
                status,
                "Resource conflict. The operation cannot be completed because the resource is in an incompatible state.",
            )
        elif status == 422:
            return KawachAPIError(status, _format_validation_error(response))
        elif status == 429:
            return KawachAPIError(
                status,
                "Rate limit exceeded. The server is currently throttled; please wait before retrying.",
            )
        elif status == 501:
            return KawachAPIError(status, "This capability is not yet implemented or enabled on the backend.")
        elif status >= 500:
            return KawachAPIError(
                status,
                f"Kawach backend service error (HTTP {status}). Check backend health logs.",
            )
        return KawachAPIError(status, f"Unexpected HTTP status {status} received.")

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        idempotency_key: Optional[str] = None,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Execute HTTP request with exponential backoff retries for transient errors."""
        client = await self.get_client()
        headers = self._build_headers(idempotency_key=idempotency_key, custom_headers=custom_headers)

        last_error: Optional[Exception] = None
        max_retries = self.settings.max_retries

        for attempt in range(max_retries + 1):
            try:
                resp = await client.request(
                    method=method,
                    url=path,
                    params=params,
                    json=json_data,
                    headers=headers,
                )

                if resp.is_success:
                    if resp.status_code == 204 or not resp.content:
                        return None
                    return resp.json()

                # Check if error is transient and retryable (429 or 502/503/504)
                if resp.status_code in (429, 502, 503, 504) and attempt < max_retries:
                    backoff = 0.5 * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue

                # Non-transient or final attempt: map to sanitized KawachAPIError
                raise self._map_http_error(resp)

            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_error = exc
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                raise KawachAPIError(
                    503,
                    f"Unable to connect to Kawach backend at {self.base_url}. Ensure the backend service is running.",
                ) from None
            except httpx.ReadTimeout as exc:
                last_error = exc
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                raise KawachAPIError(
                    504,
                    f"Request to Kawach backend timed out after {self.settings.request_timeout_seconds}s.",
                ) from None

        if last_error:
            raise KawachAPIError(500, f"HTTP request failed: {type(last_error).__name__}")

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(
        self,
        path: str,
        json_data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Any:
        return await self.request("POST", path, params=params, json_data=json_data, idempotency_key=idempotency_key)

    async def put(self, path: str, json_data: Optional[Any] = None) -> Any:
        return await self.request("PUT", path, json_data=json_data)

    async def delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return await self.request("DELETE", path, params=params)

    async def introspect_token(self) -> AuthMeInfo:
        """Call GET /api/v1/auth/me to verify token validity and retrieve granted scopes."""
        data = await self.get("/api/v1/auth/me")
        if not data or not isinstance(data, dict):
            raise KawachAPIError(500, "Unexpected token introspection response from backend.")
        return AuthMeInfo(**data)

    async def introspect_token_with_token(self, token: str) -> AuthMeInfo:
        """Call GET /api/v1/auth/me using a specific caller token."""
        custom_headers = {"Authorization": f"Bearer {token}"}
        data = await self.request("GET", "/api/v1/auth/me", custom_headers=custom_headers)
        if not data or not isinstance(data, dict):
            raise KawachAPIError(500, "Unexpected token introspection response from backend.")
        return AuthMeInfo(**data)
