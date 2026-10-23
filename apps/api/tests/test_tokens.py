"""Unit and integration tests for ApiToken lifecycle and authentication."""

import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kawach.api.deps import get_db
from kawach.core.config import settings
from kawach.db.base import Base
from kawach.db.models import ApiToken, AuditLog, User
from kawach.main import create_app
from kawach.repositories.base import Scope
from kawach.services.auth_service import AuthService
from kawach.services.token_service import ApiTokenService


@pytest.fixture
def token_test_env(tmp_path, monkeypatch):
    """Isolated environment with in-memory DB and test client."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    app = create_app()

    def override_get_db():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Create test user
    uid = uuid.uuid4().hex[:8]
    email = f"alice_{uid}@example.com"
    with TestingSession() as session:
        auth_svc = AuthService(session)
        user = auth_svc.register_user(email, "Password123!", display_name="Alice")
        jwt_token = auth_svc.create_access_token(user.id, user.email)
        user_id = user.id

    client = TestClient(app)
    yield {
        "client": client,
        "jwt_token": jwt_token,
        "user_id": user_id,
        "email": email,
        "session_maker": TestingSession,
    }


def test_create_and_list_api_tokens(token_test_env):
    """Verify creating a token returns plaintext secret once and hashes at rest."""
    client = token_test_env["client"]
    jwt_token = token_test_env["jwt_token"]
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # 1. Create Token
    create_res = client.post(
        "/api/v1/auth/tokens",
        headers=headers,
        json={"name": "Cursor IDE Token", "scopes": ["read", "write"], "expires_in_days": 14},
    )
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["name"] == "Cursor IDE Token"
    assert created_data["token_prefix"].startswith("kw_live_")
    token_secret = created_data["token_secret"]
    assert token_secret.startswith("kw_live_")
    token_id = created_data["id"]

    # 2. Check Database: hash stored, plaintext NOT stored
    with token_test_env["session_maker"]() as session:
        db_token = session.get(ApiToken, token_id)
        assert db_token is not None
        assert db_token.token_hash != token_secret
        assert len(db_token.token_hash) == 64  # SHA-256

        # Audit log verification with client_type
        audit = session.query(AuditLog).filter_by(action="token_create").first()
        assert audit is not None
        assert audit.client_type in ("web", "mcp")

    # 3. List Tokens
    list_res = client.get("/api/v1/auth/tokens", headers=headers)
    assert list_res.status_code == 200
    tokens_list = list_res.json()
    assert len(tokens_list) >= 1
    assert any(t["id"] == token_id for t in tokens_list)
    # Ensure plaintext secret is NEVER returned in list responses
    assert "token_secret" not in tokens_list[0]


def test_api_token_bearer_authentication(token_test_env):
    """Verify MCP / CLI clients can authenticate using the kw_live_ API token."""
    client = token_test_env["client"]
    jwt_token = token_test_env["jwt_token"]
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # Create Token
    create_res = client.post(
        "/api/v1/auth/tokens",
        headers=headers,
        json={"name": "MCP Server Token", "scopes": ["read", "write"]},
    )
    assert create_res.status_code == 201
    token_secret = create_res.json()["token_secret"]
    token_id = create_res.json()["id"]

    # Authenticate to /api/v1/auth/me using API token instead of JWT
    mcp_headers = {"Authorization": f"Bearer {token_secret}"}
    me_res = client.get("/api/v1/auth/me", headers=mcp_headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == token_test_env["email"]

    # Verify last_used_at was updated
    with token_test_env["session_maker"]() as session:
        tok = session.get(ApiToken, token_id)
        assert tok.last_used_at is not None


def test_revoked_api_token_rejected(token_test_env):
    """Verify revoked API tokens are immediately rejected with 401."""
    client = token_test_env["client"]
    jwt_token = token_test_env["jwt_token"]
    headers = {"Authorization": f"Bearer {jwt_token}"}

    create_res = client.post(
        "/api/v1/auth/tokens",
        headers=headers,
        json={"name": "Temporary Token", "scopes": ["read"]},
    )
    token_data = create_res.json()
    token_secret = token_data["token_secret"]
    token_id = token_data["id"]

    # Revoke
    del_res = client.delete(f"/api/v1/auth/tokens/{token_id}", headers=headers)
    assert del_res.status_code == 200

    # Attempt auth with revoked token -> 401
    mcp_headers = {"Authorization": f"Bearer {token_secret}"}
    fail_res = client.get("/api/v1/auth/me", headers=mcp_headers)
    assert fail_res.status_code == 401
    assert "Invalid, expired, or revoked API token" in fail_res.text
