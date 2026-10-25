"""Unit tests for Phase 3 persistence: SecretStore, ArtifactStore, EventBus, and Scoped Repositories."""

import pytest
import tempfile
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kawach.core.events import EventBus
from kawach.core.security import SecretStore, constant_time_compare, hash_password, mask_token, verify_password
from kawach.db.base import Base
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.repositories.base import Scope
from kawach.repositories.user_repo import UserRepository
from kawach.repositories.project_repo import ProjectRepository
from kawach.repositories.run_repo import RunRepository
from kawach.repositories.artifact_repo import ArtifactRepository
from kawach.storage.artifact_store import ArtifactStore


@pytest.fixture
def db_session():
    """In-memory SQLite database session isolated per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_secret_store():
    """Test Fernet-based symmetric encryption and decryption."""
    store = SecretStore()
    secret = "SuperSecretPassword123!"
    ciphertext = store.encrypt(secret)
    assert ciphertext != secret
    assert store.decrypt(ciphertext) == secret

    # Invalid ciphertext raises ValueError
    with pytest.raises(ValueError, match="Decryption failed"):
        store.decrypt("invalid-token-here")


def test_password_and_token_helpers():
    """Test password hashing, verification, constant time compare, and masking."""
    pwd = "MySecurePassword2026"
    pwd_hash = hash_password(pwd)
    assert pwd_hash != pwd
    assert verify_password(pwd, pwd_hash) is True
    assert verify_password("WrongPassword", pwd_hash) is False

    assert constant_time_compare("abc", "abc") is True
    assert constant_time_compare("abc", "abd") is False

    assert mask_token("ghp_1234567890abcdef1234") == "...1234"
    assert mask_token("pass") == "****"


def test_artifact_store_operations(tmp_path):
    """Test ArtifactStore save_bytes, copy_file, and path traversal prevention."""
    store = ArtifactStore(root_dir=tmp_path)

    # 1. Save bytes
    data = b"Hello, KAWACH artifact!"
    art_id, rel_uri, size, sha = store.save_bytes(
        data=data,
        project_id="proj-123",
        kind="screenshot",
        filename="login.png",
        run_id="run-001",
    )
    assert size == len(data)
    assert "proj-123" in rel_uri
    assert "login.png" in rel_uri
    assert (tmp_path / rel_uri).read_bytes() == data

    # 2. Copy file
    src = tmp_path / "original.txt"
    src.write_text("Original file content", encoding="utf-8")
    copy_id, copy_uri, copy_size, copy_sha = store.copy_file(
        src_path=src,
        project_id="proj-123",
        kind="report",
        run_id="run-001",
    )
    assert copy_size == len("Original file content")
    assert (tmp_path / copy_uri).read_text(encoding="utf-8") == "Original file content"

    # 3. Path traversal attack blocked
    with pytest.raises(ValueError, match="Path traversal detected"):
        store._safe_path("../../etc/passwd")


def test_event_bus():
    """Test sync subscription and event publishing."""
    bus = EventBus()
    received = []

    def on_run_stage(data):
        received.append(data)

    bus.subscribe("run.stage", on_run_stage)
    bus.publish("run.stage", {"run_id": "r1", "stage": "planning"})

    assert len(received) == 1
    assert received[0]["stage"] == "planning"


def test_scoped_repositories(db_session):
    """Test multi-tenant Scope isolation between User A and User B."""
    user_repo = UserRepository(db_session)
    proj_repo = ProjectRepository(db_session)
    run_repo = RunRepository(db_session)

    # Create users
    user_a = user_repo.create_user("user.a@example.com", "hash_a", "User A")
    user_b = user_repo.create_user("user.b@example.com", "hash_b", "User B")
    assert user_a.id != user_b.id

    # User A creates a project
    scope_a = Scope(user_id=user_a.id)
    proj_a = proj_repo.create_project(
        scope=scope_a,
        name="Project Alpha",
        slug="proj-alpha",
        target_url="http://localhost:4000",
    )
    assert proj_a.owner_id == user_a.id

    # User B cannot see or access Project A
    scope_b = Scope(user_id=user_b.id)
    assert proj_repo.get_project(scope_b, proj_a.id) is None
    assert len(proj_repo.list_projects(scope_b)) == 0

    # User A can access Project A
    assert proj_repo.get_project(scope_a, proj_a.id) is not None
    assert len(proj_repo.list_projects(scope_a)) == 1

    # System scope can access Project A
    scope_sys = Scope(is_system=True)
    assert proj_repo.get_project(scope_sys, proj_a.id) is not None

    # Test RunRepository under Project A
    run_a = run_repo.create_run(
        scope=scope_a,
        project_id=proj_a.id,
        run_id="run-alpha-1",
        mode="autonomous",
    )
    assert run_a.id == "run-alpha-1"

    # User B cannot see Run A
    assert run_repo.get_run(scope_b, "run-alpha-1") is None
    # User A and System can see Run A
    assert run_repo.get_run(scope_a, "run-alpha-1") is not None
    assert run_repo.get_run(scope_sys, "run-alpha-1") is not None


def test_project_slug_deduplication_and_url_normalization(db_session):
    """Test that creating projects with identical names or colliding slugs auto-disambiguates cleanly."""
    user_repo = UserRepository(db_session)
    proj_repo = ProjectRepository(db_session)

    user = user_repo.create_user("owner@example.com", "hash", "Owner")
    scope = Scope(user_id=user.id)

    # First project with default name 'localhost App'
    p1 = proj_repo.create_project(scope=scope, name="localhost App", target_url="http://localhost:4000")
    assert p1.slug == "localhost-app"

    # Second project with identical name 'localhost App' (different port or target)
    p2 = proj_repo.create_project(scope=scope, name="localhost App", target_url="http://localhost:5173")
    assert p2.slug == "localhost-app-2"
    assert p2.id != p1.id

    # Third project with identical name 'localhost App'
    p3 = proj_repo.create_project(scope=scope, name="localhost App", target_url="http://localhost:8080")
    assert p3.slug == "localhost-app-3"

    # Test URL normalization
    assert ProjectRepository.normalize_url("http://localhost:5173/") == "http://localhost:5173"
    assert ProjectRepository.normalize_url("HTTP://LOCALHOST:5173///") == "http://localhost:5173"

