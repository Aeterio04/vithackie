import asyncio

import httpx
import pytest

from kawach_mcp.errors import KawachError
from conftest import API, BASE


def login_route(api, tokens=("jwt-1", "jwt-2", "jwt-3")):
    it = iter(tokens)
    return api.post(API + "/auth/login").mock(
        side_effect=lambda req: httpx.Response(200, json={"token": next(it), "id": "u1"}))


async def test_login_once_and_bearer_reused(api, logged_in):
    login = login_route(api)
    ok = api.get(API + "/projects").respond(200, json=[])
    await asyncio.gather(*[logged_in.get("/projects") for _ in range(6)])
    assert login.call_count == 1
    assert ok.call_count == 6
    assert all(c.request.headers["authorization"] == "Bearer jwt-1" for c in ok.calls)


async def test_401_triggers_exactly_one_relogin_and_retry(api, logged_in):
    login = login_route(api)
    seq = iter([401, 200])
    route = api.get(API + "/runs").mock(side_effect=lambda r: httpx.Response(next(seq), json=[]))
    assert await logged_in.get("/runs") == []
    assert login.call_count == 2
    assert route.calls[1].request.headers["authorization"] == "Bearer jwt-2"


async def test_second_401_raises_auth_error(api, logged_in):
    login = login_route(api)
    api.get(API + "/runs").respond(401, json={"detail": "expired"})
    with pytest.raises(KawachError, match="Authentication failed"):
        await logged_in.get("/runs")
    assert login.call_count == 2


async def test_failed_login_is_auth_error(api, logged_in):
    api.post(API + "/auth/login").respond(401, json={"detail": "Invalid credentials"})
    with pytest.raises(KawachError, match="Authentication failed"):
        await logged_in.get("/projects")


async def test_token_mode_sends_bearer_and_never_logs_in(api, use_client):
    from pydantic import SecretStr
    c = use_client(token=SecretStr("kw_live_abc123"))
    login = api.post(API + "/auth/login").respond(200, json={})
    route = api.get(API + "/health").respond(200, json={})
    await c.get("/health")
    assert route.calls[0].request.headers["authorization"] == "Bearer kw_live_abc123"
    assert login.call_count == 0


async def test_guest_mode_sends_no_auth(api, guest):
    route = api.get(API + "/health").respond(200, json={})
    await guest.get("/health")
    assert "authorization" not in route.calls[0].request.headers


async def test_redirect_to_other_host_refused(api, guest):
    api.get(API + "/health").respond(302, headers={"location": "http://evil.test/x"})
    with pytest.raises(KawachError, match="different host"):
        await guest.get("/health")


async def test_same_host_redirect_followed(api, guest):
    api.get(API + "/old").respond(302, headers={"location": BASE + "/api/v1/new"})
    api.get(API + "/new").respond(200, json={"ok": True})
    assert await guest.get("/old") == {"ok": True}


async def test_oversized_response_rejected(api, guest):
    api.get(API + "/big").respond(200, content=b"x" * (5 * 1024 * 1024 + 10))
    with pytest.raises(KawachError, match="too large"):
        await guest.get("/big")


async def test_empty_body_is_empty_dict(api, guest):
    api.delete(API + "/projects/p1").respond(204)
    assert await guest.delete("/projects/p1") == {}


async def test_absolute_url_and_download(api, guest, tmp_path):
    assert guest.absolute_url("/api/v1/runs/r1/files/a.png") == BASE + "/api/v1/runs/r1/files/a.png"
    assert guest.absolute_url("http://x.test/a") == "http://x.test/a"
    api.get(API + "/runs/r1/export").respond(200, content=b"zipdata", headers={"content-type": "application/zip"})
    path, size, ctype = await guest.download("/runs/r1/export", tmp_path / "sub" / "r1.zip")
    assert size == 7 and ctype == "application/zip" and path.read_bytes() == b"zipdata"


# ---------------- JWT flow against the real auth contract ----------------

import base64
import time


def fake_jwt(expires_in):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{enc({'alg': 'HS256'})}.{enc({'sub': 'u1', 'exp': time.time() + expires_in})}.sig"


import json


async def test_relogin_before_the_jwt_expires(api, logged_in):
    tokens = iter([fake_jwt(30), fake_jwt(3600), fake_jwt(3600)])  # first token has < 60 s left
    login = api.post(API + "/auth/login").mock(side_effect=lambda r: httpx.Response(200, json={"token": next(tokens)}))
    ok = api.get(API + "/projects").respond(200, json=[])
    await logged_in.get("/projects")  # logs in, receives the nearly-expired token
    await logged_in.get("/projects")  # notices the expiry and logs in again BEFORE sending
    await logged_in.get("/projects")  # fresh token: no more logins
    assert login.call_count == 2 and ok.call_count == 3
    assert ok.calls[0].request.headers["authorization"] != ok.calls[1].request.headers["authorization"]


async def test_login_sends_email_and_password_and_keeps_no_cookies(api, logged_in):
    login = api.post(API + "/auth/login").mock(return_value=httpx.Response(
        200, json={"token": fake_jwt(3600), "user": {"email": "qa@example.com"}},
        headers={"set-cookie": "auth_token=cookie-value; HttpOnly; Path=/"}))
    route = api.get(API + "/projects").respond(200, json=[])
    await logged_in.get("/projects")
    body = json.loads(login.calls[0].request.content)
    assert body["email"] == "qa@example.com" and set(body) == {"email", "password"}
    assert len(logged_in.http.cookies) == 0 and "cookie" not in route.calls[0].request.headers
    assert route.calls[0].request.headers["authorization"].startswith("Bearer ")


async def test_login_rate_limit_is_reported_not_as_bad_credentials(api, logged_in):
    api.post(API + "/auth/login").respond(429, json={"detail": "Too many failed sign-in attempts. Try again in 40 seconds."})
    with pytest.raises(KawachError, match="Rate limited"):
        await logged_in.get("/projects")


async def test_login_without_token_in_response_is_an_error(api, logged_in):
    api.post(API + "/auth/login").respond(200, json={"id": "u1"})
    with pytest.raises(KawachError, match="no token"):
        await logged_in.get("/projects")
