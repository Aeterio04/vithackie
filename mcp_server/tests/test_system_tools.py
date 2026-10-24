import httpx
import pytest

from kawach_mcp.errors import KawachError
from kawach_mcp.tools import system
from conftest import API, PASSWORD


async def test_health_ok(api, guest):
    api.get(API + "/health").respond(200, json={"status": "active", "workers_up": 2, "queue_depth": 0, "message": "ok"})
    r = await system.health_check()
    assert r["status"] == "active" and r["workers_up"] == 2 and r["backend_url"]


async def test_health_unreachable_does_not_raise(api, guest):
    api.get(API + "/health").mock(side_effect=httpx.ConnectError("refused"))
    r = await system.health_check()
    assert r["status"] == "unreachable"
    assert "Start the KAWACH backend" in r["next_step_hint"]


async def test_health_other_errors_still_raise(api, guest):
    api.get(API + "/health").respond(500, text="kaput")
    with pytest.raises(KawachError, match="Backend error"):
        await system.health_check()


@pytest.mark.parametrize("backend,verdict", [
    ({"allowed": True, "reachable": True, "status_code": 200, "reason": None}, "OK to test"),
    ({"allowed": False, "reachable": True, "status_code": 403, "reason": "Host not in ALLOWED_HOSTS"}, "Blocked by SSRF policy"),
    ({"allowed": True, "reachable": False, "status_code": None, "reason": "down"}, "Unreachable, is the app running?"),
])
async def test_check_target_verdicts(api, guest, backend, verdict):
    api.post(API + "/targets/check").respond(200, json=backend)
    r = await system.check_target("http://example.org:3000/app")
    assert r["verdict"] == verdict
    assert r["host"] == "example.org"
    assert r["allowed"] == backend["allowed"]


async def test_check_target_rejects_bad_url(guest):
    with pytest.raises(KawachError, match="Invalid target_url"):
        await system.check_target("not a url")


async def test_upload_spec_rejects_missing_file(api, guest, defaults_route, tmp_path):
    with pytest.raises(KawachError, match="not found"):
        await system.upload_spec(str(tmp_path / "nope.md"))


async def test_upload_spec_rejects_bad_extension(api, guest, defaults_route, tmp_path):
    f = tmp_path / "spec.exe"
    f.write_text("x")
    with pytest.raises(KawachError, match="Unsupported spec extension"):
        await system.upload_spec(str(f))


async def test_upload_spec_rejects_oversize(api, guest, defaults_route, tmp_path):
    f = tmp_path / "big.md"
    f.write_bytes(b"a" * (1024 * 1024 + 1))  # limit in test defaults is 1 MB
    with pytest.raises(KawachError, match="the limit is 1 MB"):
        await system.upload_spec(str(f))


async def test_upload_spec_ok_sends_multipart(api, guest, defaults_route, tmp_path):
    f = tmp_path / "spec.md"
    f.write_text("S1: login works\nS2: logout works\n", encoding="utf-8")
    route = api.post(API + "/specs/upload").respond(
        200, json={"spec_id": "spec_ab12", "filename": "spec.md", "file_size_bytes": 33, "item_count": 2})
    r = await system.upload_spec(str(f))
    assert r["spec_id"] == "spec_ab12" and r["items_count"] == 2
    assert r["preview"].startswith("S1: login works")
    req = route.calls[0].request
    assert req.headers["content-type"].startswith("multipart/form-data")
    assert b'filename="spec.md"' in req.content and b"S2: logout works" in req.content


async def test_whoami_guest_unauthenticated(api, guest):
    api.get(API + "/auth/me").respond(401, json={"detail": "Authentication required"})
    r = await system.whoami()
    assert r["auth_mode"] == "guest" and r["authenticated"] is False
    assert "KAWACH_EMAIL" in r["note"] and r["email"] is None


async def test_whoami_logged_in_has_no_secrets(api, logged_in):
    api.post(API + "/auth/login").respond(200, json={"token": "jwt-secret-token"})
    api.get(API + "/auth/me").respond(200, json={"id": "u1", "email": "qa@example.com", "displayName": "QA", "role": "qa_engineer"})
    r = await system.whoami()
    text = str(r)
    assert r["authenticated"] and r["user"]["email"] == "qa@example.com" and r["email"] == "qa@example.com"
    assert PASSWORD not in text and "jwt-secret-token" not in text


async def test_health_timeout_is_unreachable_status(api, guest):
    api.get(API + "/health").mock(side_effect=httpx.ReadTimeout("slow"))
    assert (await system.health_check())["status"] == "unreachable"


async def test_health_check_needs_no_login_even_with_wrong_credentials(api, logged_in):
    """Live finding: --check crashed with a traceback on a wrong password because /health triggered a login."""
    login = api.post(API + "/auth/login").respond(401, json={"detail": "Invalid email or password"})
    route = api.get(API + "/health").respond(200, json={"status": "active", "workers_up": 2})
    r = await system.health_check()
    assert r["status"] == "active" and login.call_count == 0
    assert "authorization" not in route.calls[0].request.headers
