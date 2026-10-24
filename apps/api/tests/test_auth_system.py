"""Registration / login / JWT behaviour and per-user data isolation.

Runs against an in-memory database and temporary run storage, never the real data/kawach.db.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kawach.api.deps import get_db
from kawach.api.v1.auth import reset_login_limits
from kawach.core.config import LEGACY_DEV_SECRET, Settings, settings
from kawach.core.security import hash_password, verify_password
from kawach.db.base import Base
from kawach.db.models.identity import User
from kawach.db.models.runs import Run
from kawach.main import app
from kawach.schemas import Run as RunModel, StageTime
from kawach.storage import artifacts as storage

PW = "CorrectHorse-Battery9"
INVALID = "Invalid email or password"


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(settings, "runs_dir", tmp_path / "runs")
    monkeypatch.setattr("kawach.storage.artifact_store.settings.artifacts_dir", tmp_path / "artifacts")
    reset_login_limits()
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, Session=Session, tmp=tmp_path)
    app.dependency_overrides.pop(get_db, None)
    reset_login_limits()


def register(client, email="alice@example.com", password=PW, **extra):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password, **extra})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def make_user(env, email):
    res = register(env.client, email)
    assert res.status_code == 200, res.text
    return res.json()["id"], bearer(res.json()["token"])


def seed_run(env, user_id, project_id, run_id):
    """A run both in the DB (ownership) and on disk (content), like a real one."""
    with env.Session() as db:
        db.add(Run(id=run_id, project_id=project_id, created_by=user_id, stage="done", mode="manual", progress={}))
        db.commit()
    now = "2026-10-24T10:00:00Z"
    storage.save_model(run_id, "run.json", RunModel(
        runId=run_id, createdAt=now, updatedAt=now, stage="done", mode="manual", targetUrl="http://localhost:4000",
        stageTimes={"done": StageTime(startedAt=now, endedAt=now)}, golden=False))
    (storage.run_dir(run_id) / "report.md").write_text("# Alice private report", encoding="utf-8")


# ---------------------------------------------------------------- registration

def test_register_success_returns_user_and_token_and_cookie(env):
    res = register(env.client, "  Alice@Example.COM ", name="Alice A")
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "alice@example.com" and body["user"]["email"] == "alice@example.com"
    assert body["displayName"] == "Alice A" and body["token"] and body["access_token"] == body["token"]
    assert body["token_type"] == "bearer"
    assert "password" not in str(body).lower().replace("password_", "") or PW not in str(body)
    assert PW not in res.text and "argon2" not in res.text and "password_hash" not in res.text
    set_cookie = res.headers.get_list("set-cookie")
    session_cookie = next(c for c in set_cookie if c.startswith("auth_token="))
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie
    with env.Session() as db:
        user = db.scalar(select(User).where(User.email == "alice@example.com"))
        assert user.password_hash.startswith("$argon2id$") and PW not in user.password_hash


@pytest.mark.parametrize("second", ["alice@example.com", "ALICE@example.com", "  Alice@Example.com  "])
def test_duplicate_email_is_409_any_case(env, second):
    assert register(env.client, "alice@example.com").status_code == 200
    res = register(env.client, second, password="AnotherPass123")
    assert res.status_code == 409
    assert res.json()["detail"] == "An account with this email already exists"


@pytest.mark.parametrize("email,password,fragment", [
    ("alice@example.com", "short", "at least 8"),
    ("alice@example.com", "", "at least 8"),
    ("not-an-email", PW, "valid email"),
    ("a@b", PW, "valid email"),
    ("", PW, "valid email"),
    ("evil@kawach.local", PW, "reserved"),
])
def test_invalid_registration_rejected(env, email, password, fragment):
    res = register(env.client, email, password)
    assert res.status_code == 422 and fragment in res.json()["detail"]


# ---------------------------------------------------------------- login

def test_login_success_case_insensitive_and_whitespace(env):
    register(env.client, "alice@example.com")
    for email in ("alice@example.com", "ALICE@EXAMPLE.COM", "  alice@example.com "):
        res = env.client.post("/api/v1/auth/login", json={"email": email, "password": PW})
        assert res.status_code == 200 and res.json()["email"] == "alice@example.com"
        assert res.json()["token"]


def test_wrong_password_and_unknown_email_are_indistinguishable(env):
    register(env.client, "alice@example.com")
    wrong_pw = env.client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "nope-nope-nope"})
    unknown = env.client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json() == {"detail": INVALID}


def test_disabled_account_gets_the_same_error(env):
    register(env.client, "alice@example.com")
    with env.Session() as db:
        db.scalar(select(User).where(User.email == "alice@example.com")).is_active = False
        db.commit()
    res = env.client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PW})
    assert res.status_code == 401 and res.json()["detail"] == INVALID


def test_login_lockout_after_five_failures_then_recovers(env, monkeypatch):
    register(env.client, "alice@example.com")
    for _ in range(5):
        assert env.client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong-wrong"}).status_code == 401
    locked = env.client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PW})
    assert locked.status_code == 429 and "Retry-After" in locked.headers and "Too many" in locked.json()["detail"]
    # another email is not locked
    register(env.client, "bob@example.com")
    assert env.client.post("/api/v1/auth/login", json={"email": "bob@example.com", "password": PW}).status_code == 200
    reset_login_limits()
    assert env.client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PW}).status_code == 200


def test_legacy_pbkdf2_hash_still_logs_in_and_is_upgraded(env):
    import hashlib, os
    salt = os.urandom(16)
    legacy = f"{salt.hex()}:{hashlib.pbkdf2_hmac('sha256', PW.encode(), salt, 100_000).hex()}"
    with env.Session() as db:
        db.add(User(email="old@example.com", password_hash=legacy, display_name="Old", is_active=True))
        db.commit()
    assert verify_password(PW, legacy) and not verify_password("wrong", legacy)
    assert env.client.post("/api/v1/auth/login", json={"email": "old@example.com", "password": PW}).status_code == 200
    with env.Session() as db:
        assert db.scalar(select(User).where(User.email == "old@example.com")).password_hash.startswith("$argon2id$")


def test_hashes_are_salted_argon2():
    a, b = hash_password(PW), hash_password(PW)
    assert a != b and a.startswith("$argon2id$") and verify_password(PW, a) and not verify_password(PW + "x", a)


# ---------------------------------------------------------------- old hard-coded / shared accounts

@pytest.mark.parametrize("email,password", [
    ("tester@example.com", "password"), ("tester@example.com", "tester123"), ("admin", "admin"), ("admin@example.com", "admin"),
    ("system@kawach.local", "system_demo_hash"), ("system@kawach.local", "password"), ("demo@example.com", "demo1234"),
])
def test_no_default_or_hardcoded_credentials_work(env, email, password):
    res = env.client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 401


def test_system_account_cannot_log_in_even_with_its_real_password(env):
    with env.Session() as db:
        db.add(User(email="system@kawach.local", password_hash=hash_password(PW), display_name="System", is_active=True))
        db.commit()
    assert env.client.post("/api/v1/auth/login", json={"email": "system@kawach.local", "password": PW}).status_code == 401


def test_system_user_token_has_no_superpowers(env):
    """Even a validly signed token for system@kawach.local only sees that user's own data (no is_system scope)."""
    alice_id, alice_h = make_user(env, "alice@example.com")
    proj = env.client.post("/api/v1/projects", headers=alice_h, json={"name": "A", "targetUrl": "http://localhost:4000"}).json()
    seed_run(env, alice_id, proj["id"], "run-alice-1")
    with env.Session() as db:
        sysu = User(email="system@kawach.local", password_hash="x", display_name="System", is_active=True)
        db.add(sysu)
        db.commit()
        from kawach.services.auth_service import AuthService
        token = AuthService(db).create_access_token(sysu.id, sysu.email)
    h = bearer(token)
    assert env.client.get("/api/v1/projects", headers=h).json() == []
    assert env.client.get("/api/v1/runs", headers=h).json() == []
    assert env.client.get("/api/v1/runs/run-alice-1", headers=h).status_code == 404
    assert env.client.get(f"/api/v1/projects/{proj['id']}", headers=h).status_code == 404


# ---------------------------------------------------------------- tokens & sessions

PROTECTED = ["/api/v1/auth/me", "/api/v1/projects", "/api/v1/runs", "/api/v1/stats", "/api/v1/bugs/b1",
             "/api/v1/runs/r1", "/api/v1/runs/r1/catalog", "/api/v1/runs/r1/bugs", "/api/v1/runs/r1/logs",
             "/api/v1/runs/r1/events", "/api/v1/runs/r1/stream", "/api/v1/runs/r1/app-map", "/api/v1/runs/r1/report",
             "/api/v1/runs/r1/export", "/api/v1/runs/r1/files/report.md", "/api/v1/artifacts/a1",
             "/api/v1/projects/p1/saved-tests", "/api/v1/projects/p1/commits",
             "/runs", "/runs/r1", "/runs/r1/report", "/runs/r1/files/report.md", "/runs/r1/export", "/runs/r1/stream"]


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_routes_need_authentication(env, path):
    res = env.client.get(path)
    assert res.status_code == 401, (path, res.status_code)


def test_unauthenticated_writes_are_401(env):
    for method, path in [("post", "/api/v1/runs"), ("post", "/api/v1/projects"), ("post", "/api/v1/specs/upload"),
                         ("post", "/api/v1/targets/check"), ("post", "/runs"), ("put", "/api/v1/projects/p1")]:
        assert getattr(env.client, method)(path, json={}).status_code == 401, path


def test_health_and_defaults_stay_public(env):
    assert env.client.get("/api/v1/health").status_code == 200
    assert env.client.get("/api/v1/config/defaults").status_code == 200


def test_token_works_via_bearer_and_via_cookie(env):
    res = register(env.client, "alice@example.com")
    token = res.json()["token"]
    anon = TestClient(app)
    assert anon.get("/api/v1/auth/me", headers=bearer(token)).json()["email"] == "alice@example.com"
    cookie_client = TestClient(app, cookies={"auth_token": token})
    assert cookie_client.get("/api/v1/auth/me").json()["email"] == "alice@example.com"
    # the website session (cookie set by login) works without any header
    env.client.headers.pop("Authorization", None)
    login = env.client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PW})
    assert login.status_code == 200 and env.client.get("/api/v1/auth/me").json()["email"] == "alice@example.com"


def test_query_string_token_is_not_accepted(env):
    token = register(env.client, "alice@example.com").json()["token"]
    anon = TestClient(app)
    assert anon.get(f"/api/v1/auth/me?token={token}").status_code == 401


def _forge(sub, exp_delta, secret=None, **extra):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "email": "x@example.com", "iss": "kawach", "iat": now, "exp": now + exp_delta, **extra},
                      secret or settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def test_expired_wrong_secret_and_garbage_tokens_rejected(env):
    uid, headers = make_user(env, "alice@example.com")
    assert env.client.get("/api/v1/auth/me", headers=bearer(_forge(uid, timedelta(hours=1)))).status_code == 200
    assert env.client.get("/api/v1/auth/me", headers=bearer(_forge(uid, timedelta(seconds=-5)))).status_code == 401
    assert env.client.get("/api/v1/auth/me", headers=bearer(_forge(uid, timedelta(hours=1), secret="x" * 40))).status_code == 401
    assert env.client.get("/api/v1/auth/me", headers=bearer(_forge(uid, timedelta(hours=1), secret=LEGACY_DEV_SECRET))).status_code == 401
    assert env.client.get("/api/v1/auth/me", headers=bearer("not.a.jwt")).status_code == 401
    assert env.client.get("/api/v1/auth/me", headers=bearer(_forge("no-such-user", timedelta(hours=1)))).status_code == 401


def test_logout_clears_cookies_and_me_reports_account(env):
    register(env.client, "alice@example.com")
    me = env.client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "alice@example.com" and "password" not in me.text.lower()
    out = env.client.post("/api/v1/auth/logout")
    assert out.status_code == 200
    assert any("auth_token=" in c and ("Max-Age=0" in c or "expires" in c.lower()) for c in out.headers.get_list("set-cookie"))


# ---------------------------------------------------------------- JWT secret policy

def test_jwt_secret_required_outside_dev_and_generated_in_dev(monkeypatch, tmp_path):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "")
    with pytest.raises(ValueError, match="JWT_SECRET is required"):
        Settings(_env_file=None)
    monkeypatch.setenv("JWT_SECRET", LEGACY_DEV_SECRET)  # the old public default is not acceptable either
    with pytest.raises(ValueError, match="JWT_SECRET is required"):
        Settings(_env_file=None)
    monkeypatch.setenv("JWT_SECRET", "s" * 48)
    assert Settings(_env_file=None).JWT_SECRET == "s" * 48
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "")
    dev = Settings(_env_file=None)
    assert len(dev.JWT_SECRET) >= 32 and dev.JWT_SECRET != LEGACY_DEV_SECRET
    # the credential vault keeps deriving from the legacy basis when no explicit secret was configured
    assert dev.secret_store_basis == LEGACY_DEV_SECRET


# ---------------------------------------------------------------- isolation

def test_user_b_cannot_touch_user_a_anything(env):
    a_id, a = make_user(env, "alice@example.com")
    b_id, b = make_user(env, "bob@example.com")
    proj = env.client.post("/api/v1/projects", headers=a, json={"name": "Alice App", "targetUrl": "http://localhost:4000"}).json()
    pid = proj["id"]
    seed_run(env, a_id, pid, "run-alice-1")

    # positive control: Alice sees her own things
    assert [p["id"] for p in env.client.get("/api/v1/projects", headers=a).json()] == [pid]
    assert [r["id"] for r in env.client.get("/api/v1/runs", headers=a).json()] == ["run-alice-1"]
    assert env.client.get("/api/v1/runs/run-alice-1/files/report.md", headers=a).status_code == 200

    # Bob's lists are empty
    assert env.client.get("/api/v1/projects", headers=b).json() == []
    assert env.client.get("/api/v1/runs", headers=b).json() == []
    assert env.client.get("/runs", headers=b).json() == []
    assert env.client.get("/api/v1/stats", headers=b).json()["total_runs"] == 0
    assert env.client.get("/api/v1/stats", headers=a).json()["total_runs"] == 1

    not_found = [
        ("get", f"/api/v1/projects/{pid}"), ("put", f"/api/v1/projects/{pid}"), ("delete", f"/api/v1/projects/{pid}"),
        ("get", f"/api/v1/projects/{pid}/credentials"), ("put", f"/api/v1/projects/{pid}/credentials"),
        ("get", f"/api/v1/projects/{pid}/runs"), ("get", f"/api/v1/projects/{pid}/saved-tests"),
        ("post", f"/api/v1/projects/{pid}/saved-tests/run-all"), ("get", f"/api/v1/projects/{pid}/commits"),
        ("get", "/api/v1/runs/run-alice-1"), ("delete", "/api/v1/runs/run-alice-1"),
        ("post", "/api/v1/runs/run-alice-1/cancel"), ("post", "/api/v1/runs/run-alice-1/start"),
        ("post", "/api/v1/runs/run-alice-1/resume"), ("post", "/api/v1/runs/run-alice-1/retry"),
        ("get", "/api/v1/runs/run-alice-1/catalog"), ("post", "/api/v1/runs/run-alice-1/review"),
        ("get", "/api/v1/runs/run-alice-1/review-log"), ("get", "/api/v1/runs/run-alice-1/bugs"),
        ("get", "/api/v1/runs/run-alice-1/logs"), ("get", "/api/v1/runs/run-alice-1/events"),
        ("get", "/api/v1/runs/run-alice-1/execution"), ("get", "/api/v1/runs/run-alice-1/tests"),
        ("get", "/api/v1/runs/run-alice-1/app-map"), ("get", "/api/v1/runs/run-alice-1/report"),
        ("get", "/api/v1/runs/run-alice-1/results"), ("get", "/api/v1/runs/run-alice-1/metrics"),
        ("get", "/api/v1/runs/run-alice-1/export"), ("get", "/api/v1/runs/run-alice-1/export/scripts"),
        ("get", "/api/v1/runs/run-alice-1/stream"), ("get", "/api/v1/runs/run-alice-1/files/report.md"),
        ("get", "/runs/run-alice-1"), ("get", "/runs/run-alice-1/report"), ("get", "/runs/run-alice-1/files/report.md"),
        ("get", "/runs/run-alice-1/export"), ("post", "/runs/run-alice-1/execute"), ("get", "/runs/run-alice-1/stream"),
    ]
    for method, path in not_found:
        res = getattr(env.client, method)(path, headers=b, **({"json": {"username": "u", "password": "p", "test_ids": [], "decision": "approved"}} if method in ("post", "put") else {}))
        assert res.status_code == 404, (method, path, res.status_code, res.text[:120])


def test_user_b_cannot_use_a_project_run_spec_or_files(env):
    a_id, a = make_user(env, "alice@example.com")
    b_id, b = make_user(env, "bob@example.com")
    pid = env.client.post("/api/v1/projects", headers=a, json={"name": "Alice App", "targetUrl": "http://localhost:4000"}).json()["id"]
    seed_run(env, a_id, pid, "run-alice-1")

    # cannot start a run inside Alice's project
    res = env.client.post("/api/v1/runs", headers=b, json={"target_url": "http://localhost:4000", "project_id": pid})
    assert res.status_code == 404 and res.json()["detail"] == "Project not found"
    # cannot copy Alice's test script into his own library
    bp = env.client.post("/api/v1/projects", headers=b, json={"name": "Bob App", "targetUrl": "http://localhost:4000"}).json()["id"]
    res = env.client.post(f"/api/v1/projects/{bp}/saved-tests", headers=b, json={"run_id": "run-alice-1", "test_id": "T01"})
    assert res.status_code == 404
    # cannot use Alice's uploaded spec
    up = env.client.post("/api/v1/specs/upload", headers=a, data={"spec_text": "S1: alice secret requirement"})
    assert up.status_code == 200
    res = env.client.post("/api/v1/runs", headers=b, json={"target_url": "http://localhost:4000", "spec_id": up.json()["spec_id"]})
    assert res.status_code == 404
    # cannot read Alice's storage folder by path, but can only reach his own
    assert env.client.get(f"/api/v1/storage/files/by-path/users/{a_id}/anything.png", headers=b).status_code == 404
    assert env.client.get("/api/v1/storage/files/by-path/runs/x.json", headers=b).status_code == 404


def test_unclaimed_disk_run_is_not_auto_claimed(env):
    """A run that exists on disk without an owner must stay invisible; it is never handed to the first caller."""
    a_id, a = make_user(env, "alice@example.com")
    now = "2026-10-24T10:00:00Z"
    storage.save_model("orphan-run", "run.json", RunModel(
        runId="orphan-run", createdAt=now, updatedAt=now, stage="done", mode="manual", targetUrl="http://localhost:4000",
        stageTimes={"done": StageTime(startedAt=now, endedAt=now)}, golden=False))
    assert env.client.get("/api/v1/runs/orphan-run", headers=a).status_code == 404
    assert env.client.get("/runs/orphan-run", headers=a).status_code == 404
    assert env.client.get("/api/v1/runs", headers=a).json() == []
    with env.Session() as db:
        assert db.get(Run, "orphan-run") is None


def test_legacy_start_run_records_ownership(env):
    a_id, a = make_user(env, "alice@example.com")
    b_id, b = make_user(env, "bob@example.com")
    import kawach.api.legacy as legacy
    legacy._start_pipeline_background = lambda run_id: None  # no pipeline needed to test ownership
    res = env.client.post("/runs", headers=a, json={"targetUrl": "http://localhost:4000", "spec": "S1: login works", "mode": "manual"})
    assert res.status_code == 201, res.text
    rid = res.json()["runId"]
    assert env.client.get(f"/runs/{rid}", headers=a).status_code == 200
    assert env.client.get(f"/runs/{rid}", headers=b).status_code == 404
    assert [r["runId"] for r in env.client.get("/runs", headers=a).json()] == [rid]
    assert env.client.get("/runs", headers=b).json() == []
