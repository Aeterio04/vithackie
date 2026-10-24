import pytest
import respx
from pydantic import SecretStr

from kawach_mcp.client import KawachClient, set_client
from kawach_mcp.config import Settings

BASE = "http://kawach.test"
API = BASE + "/api/v1"
PASSWORD = "Sup3r-Secret-Pw!"

DEFAULTS = {
    "allowedHosts": ["localhost"],
    "default_budgets": {"max_pages": 20, "max_steps_per_test": 30, "max_run_minutes": 15, "parallel_workers": 2},
    "limits": {"min_pages": 1, "max_pages": 100, "min_steps": 5, "max_steps": 100,
               "min_minutes": 1, "max_minutes": 60, "min_workers": 1, "max_workers": 4},
    "accepted_spec_extensions": [".md", ".txt", ".pdf", ".json", ".yaml", ".yml"],
    "max_spec_file_size_mb": 1,
}


def make_settings(**kw) -> Settings:
    return Settings(base_url=BASE, **kw)


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    from kawach_mcp import config, server
    guest_settings = make_settings()
    monkeypatch.setattr(config, "get_settings", lambda: guest_settings)
    monkeypatch.setattr(server, "get_settings", lambda: guest_settings)


@pytest.fixture
def api():
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
async def use_client():
    made = []

    def _use(**kw) -> KawachClient:
        c = KawachClient(make_settings(**kw))
        set_client(c)
        made.append(c)
        return c

    yield _use
    for c in made:
        await c.aclose()
    set_client(None)


@pytest.fixture
async def guest(use_client):
    return use_client()


@pytest.fixture
async def logged_in(use_client):
    return use_client(email="qa@example.com", password=SecretStr(PASSWORD))


@pytest.fixture
def defaults_route(api):
    return api.get(API + "/config/defaults").respond(200, json=DEFAULTS)
