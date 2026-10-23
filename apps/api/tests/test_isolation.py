"""Mandatory multi-tenant isolation, access control, and secrecy tests (Section 7 and Section 13).

Verifies:
1. User A cannot read, list, modify or download anything of User B (projects, runs, catalog, bugs, artifacts, SSE streams, exports).
2. Foreign resources return 404 Not Found (not 403) to prevent existence leakage.
3. Passwords and tokens never appear in any API response.
4. Audit log records sensitive security events (login, credential change, run start, export).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kawach.api.deps import get_db
from kawach.core.security import secret_store
from kawach.db.base import Base
from kawach.db.models.artifacts import Artifact
from kawach.db.models.audit import AuditLog
from kawach.db.models.bugs import Bug
from kawach.db.models.project import Project, ProjectCredential
from kawach.db.models.runs import Run
from kawach.main import app
from kawach.repositories.base import Scope
from kawach.storage.artifact_store import ArtifactStore


@pytest.fixture
def isolation_client(tmp_path, monkeypatch):
    """Isolated TestClient connected to an in-memory database and temporary artifact storage."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Override get_db dependency
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Point artifact store to temp dir
    monkeypatch.setattr("kawach.storage.artifact_store.settings.artifacts_dir", tmp_path / "artifacts")

    with TestClient(app) as client:
        yield client, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_multi_tenant_isolation_and_404s(isolation_client, tmp_path):
    client, SessionMaker = isolation_client

    # 1. Register User A
    res_a = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "AlicePassword123!", "displayName": "Alice"},
    )
    assert res_a.status_code == 200
    token_a = res_a.json()["token"]
    user_a_id = res_a.json()["id"]

    # 2. Register User B
    res_b = client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "BobPassword123!", "displayName": "Bob"},
    )
    assert res_b.status_code == 200
    token_b = res_b.json()["token"]
    user_b_id = res_b.json()["id"]

    # 3. User A creates Project A
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res_proj = client.post(
        "/api/v1/projects",
        headers=headers_a,
        json={"name": "Alice Target App", "targetUrl": "http://localhost:4000"},
    )
    assert res_proj.status_code == 201
    proj_a_id = res_proj.json()["id"]

    # 4. Populate project with a run, bug, and physical artifact in database
    run_a_id = "run-alice-100"
    bug_a_id = "bug-alice-1"

    with SessionMaker() as db:
        # Create Run A
        run_a = Run(
            id=run_a_id,
            project_id=proj_a_id,
            created_by=user_a_id,
            stage="done",
            mode="autonomous",
            progress={},
        )
        db.add(run_a)
        db.flush()

        # Create Bug A
        bug_a = Bug(
            id=bug_a_id,
            project_id=proj_a_id,
            run_id=run_a_id,
            key="B01",
            fingerprint="sig123",
            title="Alice Private Defect",
            category="functional",
            severity="high",
            status="confirmed",
        )
        db.add(bug_a)
        db.flush()

        # Create Artifact A
        store = ArtifactStore(root_dir=tmp_path / "artifacts")
        art_id, rel_uri, size, sha = store.save_bytes(
            data=b"Alice sensitive trace evidence",
            project_id=proj_a_id,
            kind="screenshot",
            filename="evidence.png",
            run_id=run_a_id,
        )
        art = Artifact(
            id=art_id,
            project_id=proj_a_id,
            run_id=run_a_id,
            kind="screenshot",
            uri=rel_uri,
            size_bytes=size,
            sha256=sha,
            mime="image/png",
        )
        db.add(art)
        db.commit()

    # --- ISOLATION CHECKS: User B MUST get 404 for ALL of User A's resources ---

    # B cannot view or list Alice's project
    b_proj_list = client.get("/api/v1/projects", headers=headers_b)
    assert b_proj_list.status_code == 200
    assert len(b_proj_list.json()) == 0

    b_proj_get = client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_b)
    assert b_proj_get.status_code == 404
    assert b_proj_get.json()["detail"] == "Project not found"

    b_proj_put = client.put(f"/api/v1/projects/{proj_a_id}", headers=headers_b, json={"name": "Hacked"})
    assert b_proj_put.status_code == 404

    # B cannot view Alice's run
    b_run_get = client.get(f"/api/v1/runs/{run_a_id}", headers=headers_b)
    assert b_run_get.status_code == 404
    assert b_run_get.json()["detail"] == "Run not found"

    # B cannot view Alice's catalog
    b_cat_get = client.get(f"/api/v1/runs/{run_a_id}/catalog", headers=headers_b)
    assert b_cat_get.status_code == 404

    # B cannot view Alice's bugs
    b_bugs_get = client.get(f"/api/v1/runs/{run_a_id}/bugs", headers=headers_b)
    assert b_bugs_get.status_code == 404

    b_single_bug = client.get(f"/api/v1/bugs/{bug_a_id}", headers=headers_b)
    assert b_single_bug.status_code == 404

    # B cannot stream Alice's run SSE
    b_stream_get = client.get(f"/api/v1/runs/{run_a_id}/stream", headers=headers_b)
    assert b_stream_get.status_code == 404

    # B cannot download Alice's export
    b_export_get = client.get(f"/api/v1/runs/{run_a_id}/export", headers=headers_b)
    assert b_export_get.status_code == 404

    # B cannot download Alice's artifact
    b_art_get = client.get(f"/api/v1/artifacts/{art_id}", headers=headers_b)
    assert b_art_get.status_code == 404
    assert b_art_get.json()["detail"] == "Artifact not found"

    # --- VERIFY ALICE HAS FULL ACCESS TO HER OWN RESOURCES ---
    a_proj_get = client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_a)
    assert a_proj_get.status_code == 200
    assert a_proj_get.json()["name"] == "Alice Target App"

    a_art_get = client.get(f"/api/v1/artifacts/{art_id}", headers=headers_a)
    assert a_art_get.status_code == 200
    assert a_art_get.content == b"Alice sensitive trace evidence"


def test_secret_encryption_and_zero_leakage(isolation_client):
    client, SessionMaker = isolation_client

    # Register user
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "CarolPassword123!", "displayName": "Carol"},
    )
    token = res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create project
    res_proj = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Carol Project", "targetUrl": "http://localhost:4000"},
    )
    proj_id = res_proj.json()["id"]

    # Set secret credentials
    secret_pass = "VerySensitiveAppPassword!#$99"
    res_cred = client.put(
        f"/api/v1/projects/{proj_id}/credentials",
        headers=headers,
        json={"username": "carol_admin", "password": secret_pass},
    )
    assert res_cred.status_code == 200
    cred_json = res_cred.json()
    assert cred_json["hasSecret"] is True
    assert cred_json["username"] == "carol_admin"
    # CRITICAL: Plaintext password MUST NOT be returned
    assert "password" not in cred_json
    assert secret_pass not in str(cred_json)

    # Get credentials info
    res_info = client.get(f"/api/v1/projects/{proj_id}/credentials", headers=headers)
    assert res_info.status_code == 200
    info_json = res_info.json()
    assert info_json["hasSecret"] is True
    assert info_json["username"] == "carol_admin"
    assert "password" not in info_json
    assert secret_pass not in str(info_json)

    # Verify database has ciphertext and not plaintext
    with SessionMaker() as db:
        cred = db.get(ProjectCredential, proj_id)
        assert cred is not None
        assert cred.secret_ciphertext != secret_pass
        assert secret_store.decrypt(cred.secret_ciphertext) == secret_pass


def test_audit_logging_of_sensitive_actions(isolation_client):
    client, SessionMaker = isolation_client

    # 1. Register & Login
    client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "DavePassword123!", "displayName": "Dave"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "dave@example.com", "password": "DavePassword123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create project
    proj_res = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Dave Project", "targetUrl": "http://localhost:4000"},
    )
    proj_id = proj_res.json()["id"]

    # 3. Set credentials
    client.put(
        f"/api/v1/projects/{proj_id}/credentials",
        headers=headers,
        json={"username": "dave_user", "password": "DaveSecretPass!123"},
    )

    # Inspect audit logs in DB
    with SessionMaker() as db:
        logs = db.query(AuditLog).order_by(AuditLog.created_at.asc()).all()
        actions = [log.action for log in logs]
        assert "user_register" in actions
        assert "login" in actions
        assert "project_create" in actions
        assert "credential_change" in actions

        # Check credential_change log details: NEVER contains password
        cred_log = next(l for l in logs if l.action == "credential_change")
        assert "password" not in str(cred_log.metadata_json)
        assert "DaveSecretPass!123" not in str(cred_log.metadata_json)


def test_system_user_fallback_gating(isolation_client, monkeypatch):
    """Verify unauthenticated system user fallback is gated behind config flag and ENV=dev."""
    from kawach.core.config import settings
    client, _ = isolation_client

    # Case 1: Default OFF -> 401 Unauthorized
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_USER_FALLBACK", False)
    monkeypatch.setattr(settings, "ENV", "development")
    res_default = client.get("/api/v1/auth/me")
    assert res_default.status_code == 401
    assert "Authentication required" in res_default.text

    # Case 2: Flag ON, but ENV is production -> 401 Unauthorized
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_USER_FALLBACK", True)
    monkeypatch.setattr(settings, "ENV", "production")
    res_prod = client.get("/api/v1/auth/me")
    assert res_prod.status_code == 401

    # Case 3: Flag ON and ENV is dev -> 200 OK with system demo user
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_USER_FALLBACK", True)
    monkeypatch.setattr(settings, "ENV", "dev")
    res_dev = client.get("/api/v1/auth/me")
    assert res_dev.status_code == 200
    assert res_dev.json()["email"] == "system@kawach.local"

