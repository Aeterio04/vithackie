"""Tests for MCP contract gaps, scope introspection, regression-runs trigger, and pagination."""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient


from app.main import app
from kawach.core.config import settings
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.db.models.commit_loop import CommitEvent, FailureAnalysis, FixSuggestion
from kawach.db.models.saved_tests import SavedTest
from kawach.db.session import SessionLocal
from kawach.repositories.base import Scope
from kawach.services.token_service import ApiTokenService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def setup_users_and_tokens(db_session):
    """Create test users and API tokens with different scopes."""
    token_svc = ApiTokenService(db_session)

    # 1. Primary test user
    user = db_session.query(User).filter_by(email="mcp_test_user@example.com").first()
    if not user:
        user = User(
            email="mcp_test_user@example.com",
            password_hash="test_hash",
            display_name="MCP Test User",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    # 2. Foreign user
    foreign_user = db_session.query(User).filter_by(email="foreign_mcp_user@example.com").first()
    if not foreign_user:
        foreign_user = User(
            email="foreign_mcp_user@example.com",
            password_hash="test_hash",
            display_name="Foreign User",
            is_active=True,
        )
        db_session.add(foreign_user)
        db_session.commit()
        db_session.refresh(foreign_user)

    # 3. Create projects
    project = db_session.query(Project).filter_by(owner_id=user.id, name="MCP Project").first()
    if not project:
        project = Project(
            owner_id=user.id,
            name="MCP Project",
            slug="mcp-project",
            target_url="http://localhost:4000",
        )
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)

    foreign_project = db_session.query(Project).filter_by(owner_id=foreign_user.id, name="Foreign Project").first()
    if not foreign_project:
        foreign_project = Project(
            owner_id=foreign_user.id,
            name="Foreign Project",
            slug="foreign-project",
            target_url="http://localhost:4000",
        )
        db_session.add(foreign_project)
        db_session.commit()
        db_session.refresh(foreign_project)

    # 4. Mint tokens with specific scopes
    read_only_created = token_svc.create_token(
        scope=Scope(user_id=user.id),
        name="Read Only Token",
        scopes=["runs:read", "tests:read"],
    )

    write_created = token_svc.create_token(
        scope=Scope(user_id=user.id),
        name="Write Token",
        scopes=["runs:read", "runs:write", "tests:read", "tests:write", "fixes:apply"],
    )

    return {
        "user": user,
        "foreign_user": foreign_user,
        "project": project,
        "foreign_project": foreign_project,
        "read_token": read_only_created.token_secret,
        "write_token": write_created.token_secret,
    }


def test_auth_me_scope_introspection(client, setup_users_and_tokens):
    """Test that GET /api/v1/auth/me returns scopes, client_type, and token identity."""
    read_token = setup_users_and_tokens["read_token"]

    # 1. Programmatic API token
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {read_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "mcp_test_user@example.com"
    assert data["client_type"] == "mcp"
    assert data["is_session"] is False
    assert set(data["scopes"]) == {"runs:read", "tests:read"}
    assert data["token_id"] is not None

    # 2. Write token introspection
    write_token = setup_users_and_tokens["write_token"]
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {write_token}"})
    assert res.status_code == 200
    data = res.json()
    assert "runs:write" in data["scopes"]
    assert "fixes:apply" in data["scopes"]


def test_regression_runs_endpoint_scopes_and_idempotency(client, setup_users_and_tokens):
    """Test POST /projects/{id}/regression-runs authorization, execution, and idempotency."""
    project = setup_users_and_tokens["project"]
    read_token = setup_users_and_tokens["read_token"]
    write_token = setup_users_and_tokens["write_token"]

    # 1. Read-only token receives 403 Forbidden
    res = client.post(
        f"/api/v1/projects/{project.id}/regression-runs",
        headers={"Authorization": f"Bearer {read_token}"},
        json={"commit_sha": "abc1234"},
    )
    assert res.status_code == 403
    assert "Insufficient permissions" in res.json()["detail"]

    # 2. Foreign project returns 404 Not Found (not 403)
    foreign_project = setup_users_and_tokens["foreign_project"]
    res = client.post(
        f"/api/v1/projects/{foreign_project.id}/regression-runs",
        headers={"Authorization": f"Bearer {write_token}"},
        json={"commit_sha": "abc1234"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Project not found"

    # 3. Authorized runs:write token succeeds and returns run handle
    idempotency_key = "idemp-reg-test-12345"
    payload = {
        "commit_sha": "abc1234",
        "files_changed": ["src/App.tsx"],
        "message": "Manual MCP regression run",
    }
    res = client.post(
        f"/api/v1/projects/{project.id}/regression-runs",
        headers={
            "Authorization": f"Bearer {write_token}",
            "Idempotency-Key": idempotency_key,
        },
        json=payload,
    )
    assert res.status_code == 201
    data = res.json()
    assert "run_id" in data
    assert data["project_id"] == project.id
    assert data["status"] == "running"
    first_run_id = data["run_id"]

    # 4. Repeated request with same Idempotency-Key returns cached response
    res_repeat = client.post(
        f"/api/v1/projects/{project.id}/regression-runs",
        headers={
            "Authorization": f"Bearer {write_token}",
            "Idempotency-Key": idempotency_key,
        },
        json=payload,
    )
    assert res_repeat.status_code == 201
    assert res_repeat.json()["run_id"] == first_run_id


def test_suggest_fix_read_write_split(client, setup_users_and_tokens, db_session):
    """Test that GET suggest-fix is read-only (runs:read) while POST requires fixes:apply."""
    project = setup_users_and_tokens["project"]
    read_token = setup_users_and_tokens["read_token"]
    write_token = setup_users_and_tokens["write_token"]

    # Seed CommitEvent, FailureAnalysis, and FixSuggestion with unique keys
    import uuid
    uniq = uuid.uuid4().hex[:8]
    test_sha = f"commit_split_{uniq}"
    commit_evt = CommitEvent(
        project_id=project.id,
        provider="github",
        sha=test_sha,
        branch="main",
        message="Test commit",
        status="completed",
        pushed_at=datetime.now(timezone.utc),
        webhook_delivery_id=f"deliv_{uniq}",
    )
    db_session.add(commit_evt)
    db_session.commit()
    db_session.refresh(commit_evt)

    analysis = FailureAnalysis(
        run_id=f"run_split_{uniq}",
        test_result_id=f"res_split_{uniq}",
        commit_event_id=commit_evt.id,
        summary="Analysis for split test",
        status="completed",
    )
    db_session.add(analysis)
    db_session.commit()
    db_session.refresh(analysis)

    suggestion = FixSuggestion(
        analysis_id=analysis.id,
        risk_class="small",
        files_changed=1,
        lines_changed=2,
        status="proposed",
    )
    db_session.add(suggestion)
    db_session.commit()

    # 1. GET suggest-fix with read-only token succeeds
    res_get = client.get(
        f"/api/v1/projects/{project.id}/commits/{commit_evt.sha}/suggest-fix",
        headers={"Authorization": f"Bearer {read_token}"},
    )
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["risk_class"] == "small"
    assert data["status"] == "proposed"

    # 2. POST suggest-fix with read-only token is rejected with 403 Forbidden
    res_post_read = client.post(
        f"/api/v1/projects/{project.id}/commits/{commit_evt.sha}/suggest-fix",
        headers={"Authorization": f"Bearer {read_token}"},
    )
    assert res_post_read.status_code == 403

    # 3. POST suggest-fix with fixes:apply token succeeds
    res_post_write = client.post(
        f"/api/v1/projects/{project.id}/commits/{commit_evt.sha}/suggest-fix",
        headers={"Authorization": f"Bearer {write_token}"},
    )
    assert res_post_write.status_code == 200



def test_list_endpoints_pagination(client, setup_users_and_tokens):
    """Test pagination parameters on list endpoints."""
    read_token = setup_users_and_tokens["read_token"]
    project = setup_users_and_tokens["project"]

    # Projects pagination
    res = client.get(
        "/api/v1/projects?limit=1&offset=0",
        headers={"Authorization": f"Bearer {read_token}"},
    )
    assert res.status_code == 200
    assert len(res.json()) <= 1

    # Commits pagination
    res = client.get(
        f"/api/v1/projects/{project.id}/commits?limit=1&offset=0",
        headers={"Authorization": f"Bearer {read_token}"},
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # Saved tests pagination
    res = client.get(
        f"/api/v1/projects/{project.id}/saved-tests?limit=1&offset=0",
        headers={"Authorization": f"Bearer {read_token}"},
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)
