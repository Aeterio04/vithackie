"""Authenticated async HTTP client for the KAWACH backend."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, AsyncIterator, Optional
from urllib.parse import urljoin, urlparse

import httpx

from . import __version__
from .config import Settings, get_settings
from .errors import KawachError, add_secret, map_status, unreachable

log = logging.getLogger("kawach_mcp.client")

API_PREFIX = "/api/v1"
MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
_NET_ERRORS = (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError)
EXPIRY_MARGIN_SECONDS = 60  # log in again when the JWT has less than this left


def jwt_expiry(token: str) -> Optional[float]:
    """The `exp` claim of a JWT (unverified, only used to know when to log in again)."""
    try:
        payload = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(data["exp"])
    except Exception:
        return None


class KawachClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.base_url.rstrip("/")
        self._http: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        self._bearer: Optional[str] = None
        self._logged_in = False
        self._expires_at: Optional[float] = None  # JWT expiry, login mode only; token is kept in memory only
        self._generation = 0
        self._defaults: Optional[dict] = None
        if self.settings.token:
            self._bearer = self.settings.token.get_secret_value()
            add_secret(self._bearer)
        if self.settings.password:
            add_secret(self.settings.password.get_secret_value())

    # ----- plumbing -----
    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=self.settings.timeout_seconds,
                follow_redirects=False,  # redirects are followed manually, same host only
                headers={"User-Agent": f"kawach-mcp/{__version__}", "Accept": "application/json"},
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def absolute_url(self, path_or_url: Optional[str]) -> Optional[str]:
        if not path_or_url:
            return path_or_url
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return urljoin(self.base_url + "/", path_or_url.lstrip("/"))

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if path.startswith(API_PREFIX + "/"):
            return self.base_url + path
        return f"{self.base_url}{API_PREFIX}/{path.lstrip('/')}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._bearer}"} if self._bearer else {}

    def _same_host(self, url: str) -> bool:
        return urlparse(url).netloc == urlparse(self.base_url).netloc

    # ----- auth -----
    async def _login(self) -> None:
        email = self.settings.email
        pw = self.settings.password.get_secret_value() if self.settings.password else ""
        try:
            resp = await self.http.post(self._url("/auth/login"), json={"email": email, "password": pw})
        except _NET_ERRORS as e:
            raise unreachable(self.base_url) from e
        if resp.status_code != 200:
            code = 401 if resp.status_code in (400, 401) else resp.status_code
            raise map_status(code, _loads(resp.text), resp.text)
        tok = (_loads(resp.text) or {}).get("token")
        if not tok:
            raise KawachError("Login succeeded but the backend returned no token.")
        self._bearer = tok
        self._expires_at = jwt_expiry(tok)
        add_secret(tok)
        self.http.cookies.clear()  # authenticate with the Bearer header only; keep no session cookies
        self._logged_in = True
        log.info("logged in to the KAWACH backend")

    async def _ensure_auth(self) -> int:
        if self.settings.auth_mode != "login":
            return self._generation
        async with self._lock:
            if self._logged_in and self._expires_at and time.time() > self._expires_at - EXPIRY_MARGIN_SECONDS:
                self._logged_in, self._bearer = False, None  # about to expire: log in again before the request
            if not self._logged_in:
                await self._login()
                self._generation += 1
            return self._generation

    async def _relogin(self, seen_generation: int) -> None:
        async with self._lock:
            if self._generation != seen_generation:
                return  # another task already refreshed the session
            self._logged_in = False
            self._bearer = None
            self.http.cookies.clear()
            await self._login()
            self._generation += 1

    # ----- requests -----
    async def _send(self, method: str, url: str, auth: bool = True, **kw: Any) -> tuple[httpx.Response, bytes]:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with self.http.stream(method, url, headers=self._headers() if auth else {}, **kw) as resp:
                    log.debug("%s %s -> %s", method, urlparse(url).path, resp.status_code)
                    if resp.is_redirect:
                        loc = urljoin(url, resp.headers.get("location", ""))
                        if not self._same_host(loc):
                            raise KawachError("Refusing to follow a redirect to a different host.")
                        url = loc
                        continue
                    buf = bytearray()
                    async for chunk in resp.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) > MAX_JSON_BYTES:
                            raise KawachError("Backend response is too large to read (over 5 MB).")
                    return resp, bytes(buf)
            except httpx.TimeoutException as e:
                raise unreachable(self.base_url, kind="timeout") from e
            except _NET_ERRORS as e:
                raise unreachable(self.base_url) from e
        raise KawachError("Too many redirects.")

    async def request(self, method: str, path: str, *, params: Optional[dict] = None,
                      json_body: Any = None, data: Optional[dict] = None,
                      files: Optional[dict] = None, raw: bool = False,
                      timeout: Optional[float] = None, auth: bool = True) -> Any:
        kw: dict = {}
        if timeout is not None:
            kw["timeout"] = timeout
        if params:
            kw["params"] = {k: v for k, v in params.items() if v is not None}
        if json_body is not None:
            kw["json"] = json_body
        if data is not None:
            kw["data"] = data
        if files is not None:
            kw["files"] = files
        url = self._url(path)
        gen = await self._ensure_auth() if auth else self._generation
        resp, body = await self._send(method, url, auth=auth, **kw)
        if auth and resp.status_code == 401 and self.settings.auth_mode == "login":
            await self._relogin(gen)
            resp, body = await self._send(method, url, auth=auth, **kw)
        text = body.decode("utf-8", errors="replace")
        if resp.status_code >= 400:
            raise map_status(resp.status_code, _loads(text), text)
        if raw:
            return text
        if not text.strip():
            return {}
        parsed = _loads(text)
        return parsed if parsed is not None else {}

    async def get(self, path: str, params: Optional[dict] = None, auth: bool = True) -> Any:
        """GET JSON. auth=False sends no credentials and never triggers a login (for open routes such as /health)."""
        return await self.request("GET", path, params=params, auth=auth)

    async def get_text(self, path: str, params: Optional[dict] = None) -> str:
        """GET a text file (markdown, ts, json...) without JSON parsing. Capped at 5 MB."""
        return await self.request("GET", path, params=params, raw=True)

    async def post(self, path: str, json_body: Any = None, params: Optional[dict] = None) -> Any:
        return await self.request("POST", path, json_body=json_body, params=params)

    async def put(self, path: str, json_body: Any = None) -> Any:
        return await self.request("PUT", path, json_body=json_body)

    async def patch(self, path: str, json_body: Any = None) -> Any:
        return await self.request("PATCH", path, json_body=json_body)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def post_multipart(self, path: str, files: Optional[dict] = None,
                             data: Optional[dict] = None) -> Any:
        return await self.request("POST", path, files=files, data=data)

    async def download(self, path: str, dest_path: Path) -> tuple[Path, int, str]:
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        url = self._url(path)
        gen = await self._ensure_auth()
        for attempt in (0, 1):
            try:
                async with self.http.stream("GET", url, headers=self._headers()) as resp:
                    if resp.status_code == 401 and attempt == 0 and self.settings.auth_mode == "login":
                        await resp.aread()
                        await self._relogin(gen)
                        continue
                    if resp.status_code >= 400:
                        text = (await resp.aread()).decode("utf-8", errors="replace")
                        raise map_status(resp.status_code, _loads(text), text)
                    size = 0
                    with open(dest_path, "wb") as fh:
                        async for chunk in resp.aiter_bytes():
                            fh.write(chunk)
                            size += len(chunk)
                    return dest_path, size, resp.headers.get("content-type", "")
            except _NET_ERRORS as e:
                raise unreachable(self.base_url) from e
        raise map_status(401, None)

    async def stream_lines(self, path: str, params: Optional[dict] = None) -> AsyncIterator[str]:
        """Yield raw lines of a streaming (SSE) response."""
        url = self._url(path)
        await self._ensure_auth()
        try:
            async with self.http.stream("GET", url, params=params, timeout=None,
                                        headers={**self._headers(), "Accept": "text/event-stream"}) as resp:
                if resp.status_code >= 400:
                    text = (await resp.aread()).decode("utf-8", errors="replace")
                    raise map_status(resp.status_code, _loads(text), text)
                async for line in resp.aiter_lines():
                    yield line
        except (httpx.RemoteProtocolError, httpx.ReadError):
            return  # server closed the stream mid-frame: treat as a normal end
        except _NET_ERRORS as e:
            raise unreachable(self.base_url) from e

    # ----- cached helpers -----
    async def get_defaults(self) -> dict:
        if self._defaults is None:
            self._defaults = await self.get("/config/defaults")
        return self._defaults


def _loads(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


_client: Optional[KawachClient] = None


def get_client() -> KawachClient:
    global _client
    if _client is None:
        _client = KawachClient()
    return _client


def set_client(client: Optional[KawachClient]) -> None:
    global _client
    _client = client
