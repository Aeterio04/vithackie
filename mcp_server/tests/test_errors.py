import httpx
import pytest

from kawach_mcp.errors import KawachError, map_status
from conftest import API, BASE


async def test_connection_refused(api, guest):
    api.get(API + "/projects").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(KawachError) as ei:
        await guest.get("/projects")
    assert str(ei.value) == f"Cannot reach the KAWACH backend at {BASE}. Is it running? (start it, then retry)"
    assert ei.value.kind == "unreachable"


async def test_timeout_is_unreachable(api, guest):
    api.get(API + "/projects").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(KawachError, match="Cannot reach") as ei:
        await guest.get("/projects")
    assert ei.value.kind == "timeout"  # distinguishable from a refused connection


@pytest.mark.parametrize("status,body,expected", [
    (401, {"detail": "x"}, "Authentication failed. Check KAWACH_EMAIL"),
    (403, {"detail": "Insufficient permissions: requires one of ['runs:write']"}, "Not allowed to do that. Insufficient"),
    (404, {"detail": "Run not found"}, "Not found (it may not exist or may belong to another account)."),
    (409, {"detail": "run is not awaiting review"}, "run is not awaiting review"),
    (429, {}, "Rate limited, retry shortly."),
])
def test_simple_mappings(status, body, expected):
    e = map_status(status, body)
    assert str(e).startswith(expected)
    assert e.status_code == status


def test_422_includes_field_detail():
    body = {"detail": [{"loc": ["body", "target_url"], "msg": "field required", "type": "missing"},
                       {"loc": ["body", "budgets", "max_pages"], "msg": "too big", "type": "x"}]}
    msg = str(map_status(422, body))
    assert msg.startswith("Invalid input:")
    assert "target_url: field required" in msg and "budgets.max_pages: too big" in msg


def test_500_truncates_body():
    msg = str(map_status(500, None, "E" * 1000))
    assert msg.startswith("Backend error (500): ") and len(msg) == len("Backend error (500): ") + 300


@pytest.mark.parametrize("status", [401, 404, 409, 422, 500])
async def test_http_errors_propagate_through_client(api, guest, status):
    api.get(API + "/runs/r1").respond(status, json={"detail": "boom"})
    with pytest.raises(KawachError) as ei:
        await guest.get("/runs/r1")
    assert ei.value.status_code == status
