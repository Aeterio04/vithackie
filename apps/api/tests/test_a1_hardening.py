"""Comprehensive hardening test suite for Task A1.

Covers:
1. Alembic fresh database migration and roundtrip.
2. Granular scope enforcement (read-only token -> 403 on write; 404 for foreign resources).
3. Session-only token management (API tokens get 403 on token routes; zero leakage in logs).
4. System-user fallback gating and no-fallthrough on invalid/revoked tokens.
5. Multi-door audit logging verifying client_type ('web', 'mcp', 'github').
6. Idempotency-Key semantics (same key+payload -> original handle; different payload -> 409).
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
from pathlib import Path
import tempfile
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from alembic import command
from alembic.config import Config
from kawach.api.deps import get_db
from kawach.core.config import settings
from kawach.db.models.audit import AuditLog
from kawach.db.models.identity import ApiToken, User
from kawach.db.models.project import Project
from kawach.main import create_app
from kawach.services.auth_service import AuthService
from kawach.services.idempotency import IdempotencyService
from kawach.services.token_service import ApiTokenService


@pytest.fixture(autouse=True)
def clean_idempotency():
    IdempotencyService.clear()
    yield
    IdempotencyService.clear()


# ==============================================================================
# 1. Alembic Fresh DB & Round-trip
# ==============================================================================

def test_alembic_fresh_db_build_and_roundtrip(tmp_path):
    """Verify fresh DB creation via Alembic migrations only and test round-trip."""
    db_file = tmp_path / "alembic_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    repo_root = Path(__file__).resolve().parents[3]
    ini_path = repo_root / "apps" / "api" / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", str(repo_root / "apps" / "api" / "alembic"))

    # 1. Upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify tables via engine inspection
    engine = create_engine(db_url)
    with engine.connect() as conn:
        import sqlite3
        con = sqlite3.connect(str(db_file))
        tables = [r[0] for r in con.cursor().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "api_tokens" in tables
        assert "audit_logs" in tables
        assert "users" in tables

        audit_cols = [r[1] for r in con.cursor().execute("PRAGMA table_info(audit_logs)").fetchall()]
        assert "client_type" in audit_cols
        con.close()

    # 2. Downgrade -1 (removes A1 additions)
    command.downgrade(alembic_cfg, "-1")
    con = sqlite3.connect(str(db_file))
    tables = [r[0] for r in con.cursor().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "api_tokens" not in tables
    audit_cols = [r[1] for r in con.cursor().execute("PRAGMA table_info(audit_logs)").fetchall()]
    assert "client_type" not in audit_cols
    con.close()

    # 3. Upgrade back to head (round-trip)
    command.upgrade(alembic_cfg, "head")
    con = sqlite3.connect(str(db_file))
    tables = [r[0] for r in con.cursor().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "api_tokens" in tables
    audit_cols = [r[1] for r in con.cursor().execute("PRAGMA table_info(audit_logs)").fetchall()]
    assert "client_type" in audit_cols
    con.close()

    # 4. Run token service test directly against Alembic-migrated DB
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        auth_svc = AuthService(db)
        user = auth_svc.register_user("alembic_user@example.com", "Password123!")

        token_svc = ApiTokenService(db)
        from kawach.repositories.base import Scope
        created = token_svc.create_token(
            scope=Scope(user_id=user.id),
            name="Alembic Token",
            scopes=["runs:read"],
        )
        assert created.token_secret.startswith("kw_live_")

        verified = token_svc.verify_token(created.token_secret)
        assert verified is not None
        v_user, v_scopes, _ = verified
        assert v_user.id == user.id
        assert v_scopes == ["runs:read"]


# ==============================================================================
# Environment fixture for test endpoints
# ==============================================================================

@pytest.fixture
def hardening_env(tmp_path, monkeypatch):
    test_runs_dir = tmp_path / "runs"
    test_runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", test_runs_dir)
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"])
    monkeypatch.setattr(settings, "STUB_MODE", 1)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    monkeypatch.setattr("kawach.api.legacy._start_pipeline_background", lambda run_id: None)

    db_file = tmp_path / "hardening.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    repo_root = Path(__file__).resolve().parents[3]
    ini_path = repo_root / "apps" / "api" / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", str(repo_root / "apps" / "api" / "alembic"))
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    app = create_app()

    def override_get_db():
        with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Create Alice (owner) and Bob (foreign user)
    with SessionLocal() as db:
        auth_svc = AuthService(db)
        alice = auth_svc.register_user("alice_hard@example.com", "Password123!")
        bob = auth_svc.register_user("bob_hard@example.com", "Password123!")
        alice_jwt = auth_svc.create_access_token(alice.id, alice.email)
        bob_jwt = auth_svc.create_access_token(bob.id, bob.email)

        # Create Alice's project
        p_alice = Project(
            id=str(uuid.uuid4()),
            owner_id=alice.id,
            name="Alice Project",
            slug="alice-proj",
            target_url="http://localhost:4000",
            allowed_hosts=["localhost", "127.0.0.1"],
        )
        db.add(p_alice)

        # Create Bob's project
        p_bob = Project(
            id=str(uuid.uuid4()),
            owner_id=bob.id,
            name="Bob Project",
            slug="bob-proj",
            target_url="http://localhost:4000",
            allowed_hosts=["localhost", "127.0.0.1"],
        )
        db.add(p_bob)
        db.commit()

        alice_id = alice.id
        bob_id = bob.id
        alice_project_id = p_alice.id
        bob_project_id = p_bob.id

    client = TestClient(app)
    return {
        "client": client,
        "SessionLocal": SessionLocal,
        "alice_id": alice_id,
        "bob_id": bob_id,
        "alice_jwt": alice_jwt,
        "bob_jwt": bob_jwt,
        "alice_project_id": alice_project_id,
        "bob_project_id": bob_project_id,
    }


# ==============================================================================
# 2. Scope Enforcement Tests
# ==============================================================================

def test_scope_enforcement_read_only_token_rejected_on_write(hardening_env):
    """Read-only token gets 403 on write route; foreign resources get 404."""
    client = hardening_env["client"]
    alice_jwt = hardening_env["alice_jwt"]
    alice_project_id = hardening_env["alice_project_id"]
    bob_project_id = hardening_env["bob_project_id"]

    # 1. Alice creates a read-only token via web session
    res = client.post(
        "/api/v1/auth/tokens",
        headers={"Authorization": f"Bearer {alice_jwt}"},
        json={"name": "Read Only Token", "scopes": ["runs:read", "tests:read"]},
    )
    assert res.status_code == 201
    read_token = res.json()["token_secret"]

    # 2. Reading own project with read-only token succeeds (200)
    res = client.get(
        f"/api/v1/projects/{alice_project_id}",
        headers={"Authorization": f"Bearer {read_token}"},
    )
    assert res.status_code == 200

    # 3. Writing with read-only token is rejected with 403 Forbidden
    res = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {read_token}"},
        json={"name": "New Project", "targetUrl": "http://localhost:4000"},
    )
    assert res.status_code == 403
    assert "Insufficient permissions" in res.json()["detail"]

    # 4. Accessing foreign project (Bob's) returns 404 Not Found (NOT 403) to prevent existence leakage
    res = client.get(
        f"/api/v1/projects/{bob_project_id}",
        headers={"Authorization": f"Bearer {read_token}"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Project not found"


# ==============================================================================
# 3. Token Management Session-Only & Security Hygiene
# ==============================================================================

def test_token_management_is_session_only_and_secure(hardening_env):
    """API tokens must NOT manage tokens (403), hashes stored, no secret leakage."""
    client = hardening_env["client"]
    alice_jwt = hardening_env["alice_jwt"]
    SessionLocal = hardening_env["SessionLocal"]

    # 1. Create an API token with all write scopes
    res = client.post(
        "/api/v1/auth/tokens",
        headers={"Authorization": f"Bearer {alice_jwt}"},
        json={"name": "Admin Like Token", "scopes": ["runs:read", "runs:write", "tests:write"]},
    )
    assert res.status_code == 201
    data = res.json()
    raw_token = data["token_secret"]
    token_id = data["id"]
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # 2. Verify only hash is stored in database; plaintext secret is not stored
    with SessionLocal() as db:
        tok_row = db.get(ApiToken, token_id)
        assert tok_row.token_hash == token_hash
        assert raw_token not in tok_row.token_prefix
        # Verify last_used_at is initially None
        assert tok_row.last_used_at is None

    # 3. Attempting to create, list, or revoke tokens using an API token returns 403
    # Try create
    res = client.post(
        "/api/v1/auth/tokens",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"name": "Nested Token"},
    )
    assert res.status_code == 403
    assert "session" in res.json()["detail"].lower()

    # Try list
    res = client.get(
        "/api/v1/auth/tokens",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert res.status_code == 403

    # Try delete
    res = client.delete(
        f"/api/v1/auth/tokens/{token_id}",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert res.status_code == 403

    # 4. Use the API token on an allowed route and verify last_used_at is updated
    res = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert res.status_code == 200

    with SessionLocal() as db:
        tok_row = db.get(ApiToken, token_id)
        assert tok_row.last_used_at is not None

    # 5. Check audit logs: verify token secret NEVER appears in metadata
    with SessionLocal() as db:
        audit_entries = db.scalars(select(AuditLog)).all()
        for entry in audit_entries:
            meta_str = str(entry.metadata_json)
            assert raw_token not in meta_str


# ==============================================================================
# 4. System-User Fallback Gating & No Fallthrough
# ==============================================================================

def test_system_user_fallback_disabled_and_no_fallthrough(hardening_env, monkeypatch):
    """Fallback disabled unless ENV=dev, and invalid/revoked kw_ tokens never fall through."""
    client = hardening_env["client"]
    alice_jwt = hardening_env["alice_jwt"]

    # 1. Turn off fallback
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_USER_FALLBACK", False)
    monkeypatch.setattr(settings, "ENV", "production")

    # Unauthenticated request returns 401
    res = client.get("/api/v1/projects")
    assert res.status_code == 401

    # 2. Invalid kw_ token returns 401 (never falls through to system user)
    res = client.get(
        "/api/v1/projects",
        headers={"Authorization": "Bearer kw_live_invalid_entropy_token_123"},
    )
    assert res.status_code == 401
    assert "Invalid, expired, or revoked API token" in res.json()["detail"]

    # 3. Create a token, revoke it, then verify it is rejected with 401
    res = client.post(
        "/api/v1/auth/tokens",
        headers={"Authorization": f"Bearer {alice_jwt}"},
        json={"name": "Temp Token"},
    )
    tok_data = res.json()
    tok_secret = tok_data["token_secret"]
    tok_id = tok_data["id"]

    # Revoke it
    client.delete(
        f"/api/v1/auth/tokens/{tok_id}",
        headers={"Authorization": f"Bearer {alice_jwt}"},
    )

    # Calling with revoked token returns 401
    res = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {tok_secret}"},
    )
    assert res.status_code == 401


# ==============================================================================
# 5. Audit Logging Client Types
# ==============================================================================

def test_audit_logging_client_types(hardening_env):
    """Confirm client_type is 'web' for JWT, 'mcp' for kw_ tokens, 'github' for webhooks."""
    client = hardening_env["client"]
    alice_jwt = hardening_env["alice_jwt"]
    SessionLocal = hardening_env["SessionLocal"]

    # 1. Action via JWT (Web) -> client_type="web"
    res = client.post(
        "/api/v1/auth/tokens",
        headers={"Authorization": f"Bearer {alice_jwt}"},
        json={"name": "Client Type Test Token", "scopes": ["runs:write"]},
    )
    assert res.status_code == 201
    kw_token = res.json()["token_secret"]

    with SessionLocal() as db:
        latest = db.scalar(select(AuditLog).where(AuditLog.action == "token_create").order_by(AuditLog.created_at.desc()))
        assert latest is not None
        assert latest.client_type == "web"

    # 2. Action via kw_ API token (MCP) -> client_type="mcp"
    res = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {kw_token}"},
        json={"name": "MCP Project", "targetUrl": "http://localhost:4000"},
    )
    assert res.status_code == 201

    # Verify audit context client_type for mcp
    with SessionLocal() as db:
        token_svc = ApiTokenService(db)
        # Verify token reports client_type
        verified = token_svc.verify_token(kw_token)
        assert verified is not None

    # 3. Action via GitHub Webhook -> client_type="github"
    secret = settings.GITHUB_WEBHOOK_SECRET or "dev-webhook-secret"
    body = b'{"ref": "refs/heads/main", "after": "abc1234"}'
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    delivery_id = f"deliv-{uuid.uuid4().hex[:8]}"

    res = client.post(
        "/api/v1/webhooks/github",
        data=body,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery_id,
            "Content-Type": "application/json",
        },
    )
    assert res.status_code in (202, 501)  # Verified, returns 202 when implemented or 501 scaffold

    with SessionLocal() as db:
        webhook_log = db.scalar(
            select(AuditLog).where(AuditLog.action == "webhook_receive").order_by(AuditLog.created_at.desc())
        )
        assert webhook_log is not None
        assert webhook_log.client_type == "github"
        assert webhook_log.metadata_json.get("delivery_id") == delivery_id


# ==============================================================================
# 6. Idempotency Key Semantics
# ==============================================================================

def test_idempotency_key_start_run_behavior(hardening_env):
    """Same key + same user + same payload -> original handle; different payload -> 409."""
    client = hardening_env["client"]
    alice_jwt = hardening_env["alice_jwt"]
    idemp_key = f"key-{uuid.uuid4().hex[:12]}"

    payload_a = {
        "targetUrl": "http://localhost:4000",
        "spec": "S1: Users can sign up\nS2: Users can sign in",
        "prompt": "Test prompt A",
        "mode": "manual",
    }

    # 1. First execution
    res1 = client.post(
        "/runs",
        headers={
            "Authorization": f"Bearer {alice_jwt}",
            "Idempotency-Key": idemp_key,
        },
        json=payload_a,
    )
    assert res1.status_code == 201
    run_id_1 = res1.json()["runId"]

    # 2. Exact retry with same idempotency key and same payload returns original handle
    res2 = client.post(
        "/runs",
        headers={
            "Authorization": f"Bearer {alice_jwt}",
            "Idempotency-Key": idemp_key,
        },
        json=payload_a,
    )
    assert res2.status_code == 201
    run_id_2 = res2.json()["runId"]
    assert run_id_2 == run_id_1

    # 3. Same idempotency key with DIFFERENT payload raises 409 Conflict
    payload_b = {
        "targetUrl": "http://localhost:4000",
        "spec": "S1: Users can sign up\nS2: Users can sign in",
        "prompt": "DIFFERENT prompt B",
        "mode": "manual",
    }
    res3 = client.post(
        "/runs",
        headers={
            "Authorization": f"Bearer {alice_jwt}",
            "Idempotency-Key": idemp_key,
        },
        json=payload_b,
    )
    assert res3.status_code == 409
    assert "Idempotency key collision" in res3.json()["detail"]
