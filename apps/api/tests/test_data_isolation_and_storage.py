"""Comprehensive verification of multi-tenant data isolation and local file storage.

Verifies:
1. Complete isolation between User A and User B:
   - User B cannot see, access, or modify User A's projects, runs, saved tests, bugs, artifacts, or files.
   - All unauthorized cross-tenant requests return 404 (not 403) to prevent existence leakage.
   - Listing endpoints return only caller-owned resources.
2. Local file storage:
   - Files are stored on local disk under storage/users/<user_id>/tests/<test_id>/<uuid>.<ext>.
   - Database stores only metadata (id, user_id, test_id, type, relative_path, size, mime_type, created_at).
   - Absolute filesystem paths are never exposed.
   - Path traversal attempts (..) are rejected.
   - Range requests (HTTP 206) allow video players to seek.
   - Deleting a test cleans up all files from disk and removes DB records.
   - Deleting an artifact cleans up disk file and DB record.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kawach.api.deps import get_db
from kawach.core.config import settings
from kawach.db.base import Base
from kawach.db.models.artifacts import Artifact
from kawach.db.models.bugs import Bug
from kawach.db.models.project import Project
from kawach.db.models.runs import Run
from kawach.main import app
from kawach.storage.file_storage import get_file_path


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    """Setup isolated test environment with temporary database and storage directory."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Point storage to tmp_path
    storage_root = tmp_path / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "storage_dir", storage_root)
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path / "artifacts")
    monkeypatch.setattr(settings, "runs_dir", tmp_path / "runs")

    with TestClient(app) as client:
        yield client, TestingSession, storage_root

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_data_isolation_and_file_storage_lifecycle(test_env):
    client, SessionMaker, storage_root = test_env

    # 1. Register User A and User B
    res_a = client.post(
        "/api/v1/auth/register",
        json={"email": "usera@example.com", "password": "UserAPassword123!", "displayName": "User A"},
    )
    assert res_a.status_code == 200, res_a.text
    token_a = res_a.json()["token"]
    user_a_id = res_a.json()["id"]

    res_b = client.post(
        "/api/v1/auth/register",
        json={"email": "userb@example.com", "password": "UserBPassword123!", "displayName": "User B"},
    )
    assert res_b.status_code == 200, res_b.text
    token_b = res_b.json()["token"]
    user_b_id = res_b.json()["id"]

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 2. User A creates Project A
    res_proj = client.post(
        "/api/v1/projects",
        headers=headers_a,
        json={"name": "Project A", "targetUrl": "http://localhost:3000"},
    )
    assert res_proj.status_code == 201
    proj_a = res_proj.json()
    proj_a_id = proj_a["id"]
    assert proj_a["ownerId"] == user_a_id

    # 3. User A has a saved test in Project A
    test_a_id = "test-alice-smoke-001"
    with SessionMaker() as db:
        from kawach.db.models.saved_tests import SavedTest
        saved_test = SavedTest(
            id=test_a_id,
            project_id=proj_a_id,
            kind="journey",
            title="User A Login Test",
            tags=["smoke"],
            is_active=True,
            created_by=user_a_id,
        )
        db.add(saved_test)
        db.commit()

    # 4. User A uploads a screenshot and a video file via storage API
    screenshot_bytes = b"\x89PNG\r\n\x1a\nfake_screenshot_content_1234567890"
    res_upload_img = client.post(
        "/api/v1/storage/upload",
        headers=headers_a,
        data={"test_id": test_a_id, "file_type": "screenshot", "project_id": proj_a_id},
        files={"file": ("screenshot.png", screenshot_bytes, "image/png")},
    )
    assert res_upload_img.status_code == 201, res_upload_img.text
    img_meta = res_upload_img.json()
    img_id = img_meta["id"]
    img_rel_path = img_meta["relative_path"]

    # Verify upload response contains only metadata, no raw absolute path
    assert img_meta["user_id"] == user_a_id
    assert img_meta["test_id"] == test_a_id
    assert img_meta["type"] == "screenshot"
    assert img_meta["size"] == len(screenshot_bytes)
    assert img_meta["mime_type"] == "image/png"
    assert "C:" not in img_rel_path and "\\" not in img_rel_path
    assert img_rel_path.startswith(f"users/{user_a_id}/tests/{test_a_id}/")

    # Verify screenshot exists on local disk at expected path: storage/users/<user_id>/tests/<test_id>/<uuid>.<ext>
    expected_img_path = storage_root / "users" / user_a_id / "tests" / test_a_id / f"{img_id}.png"
    assert expected_img_path.exists()
    assert expected_img_path.read_bytes() == screenshot_bytes

    # User A uploads a video file (for testing range requests)
    video_bytes = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_VIDEO_TEST_STREAM"
    res_upload_vid = client.post(
        "/api/v1/storage/upload",
        headers=headers_a,
        data={"test_id": test_a_id, "file_type": "screen_recording", "project_id": proj_a_id},
        files={"file": ("recording.webm", video_bytes, "video/webm")},
    )
    assert res_upload_vid.status_code == 201
    vid_meta = res_upload_vid.json()
    vid_id = vid_meta["id"]
    vid_rel_path = vid_meta["relative_path"]

    expected_vid_path = storage_root / "users" / user_a_id / "tests" / test_a_id / f"{vid_id}.webm"
    assert expected_vid_path.exists()
    assert expected_vid_path.read_bytes() == video_bytes

    # 5. Add Run A and Bug A under Project A in DB
    run_a_id = "run-alice-qa-001"
    bug_a_id = "bug-alice-qa-001"
    with SessionMaker() as db:
        run_a = Run(
            id=run_a_id,
            project_id=proj_a_id,
            created_by=user_a_id,
            mode="manual",
            stage="completed",
        )
        db.add(run_a)
        bug_a = Bug(
            id=bug_a_id,
            project_id=proj_a_id,
            run_id=run_a_id,
            key="BUG-101",
            title="Alice Button Broken",
            category="functional",
            severity="medium",
            status="confirmed",
            fingerprint="fp_alice_defect_101",
        )
        db.add(bug_a)
        db.commit()

    # =========================================================================
    # STEP 2 VERIFICATION: User B attempts to access User A's resources
    # ALL MUST RETURN 404 (or empty list for listing endpoints)
    # =========================================================================

    # B lists projects -> empty (does not see Project A)
    res_b_projs = client.get("/api/v1/projects", headers=headers_b)
    assert res_b_projs.status_code == 200
    assert len(res_b_projs.json()) == 0

    # B gets Project A -> 404
    assert client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_b).status_code == 404

    # B updates Project A -> 404
    assert client.put(f"/api/v1/projects/{proj_a_id}", headers=headers_b, json={"name": "Hacked"}).status_code == 404

    # B deletes Project A -> 404
    assert client.delete(f"/api/v1/projects/{proj_a_id}", headers=headers_b).status_code == 404

    # B lists saved tests in Project A -> 404
    assert client.get(f"/api/v1/projects/{proj_a_id}/saved-tests", headers=headers_b).status_code == 404

    # B deletes User A's test -> 404
    assert client.delete(f"/api/v1/projects/{proj_a_id}/saved-tests/{test_a_id}", headers=headers_b).status_code == 404

    # B lists runs -> empty list (does not see Run A)
    res_b_runs = client.get("/api/v1/runs", headers=headers_b)
    assert res_b_runs.status_code == 200
    assert len(res_b_runs.json()) == 0

    # B gets Run A -> 404
    assert client.get(f"/api/v1/runs/{run_a_id}", headers=headers_b).status_code == 404

    # B gets Run A files -> 404
    assert client.get(f"/api/v1/runs/{run_a_id}/files/screenshot.png", headers=headers_b).status_code == 404

    # B gets Run A app-map -> 404
    assert client.get(f"/api/v1/runs/{run_a_id}/app-map", headers=headers_b).status_code == 404

    # B gets Run A bugs -> 404
    assert client.get(f"/api/v1/runs/{run_a_id}/bugs", headers=headers_b).status_code == 404

    # B gets single Bug A -> 404
    assert client.get(f"/api/v1/bugs/{bug_a_id}", headers=headers_b).status_code == 404

    # B cancels Run A -> 404
    assert client.post(f"/api/v1/runs/{run_a_id}/cancel", headers=headers_b).status_code == 404

    # B retries Run A -> 404
    assert client.post(f"/api/v1/runs/{run_a_id}/retry", headers=headers_b).status_code == 404

    # B deletes Run A -> 404
    assert client.delete(f"/api/v1/runs/{run_a_id}", headers=headers_b).status_code == 404

    # B downloads User A's artifact by ID -> 404
    assert client.get(f"/api/v1/artifacts/{img_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/storage/files/{img_id}", headers=headers_b).status_code == 404

    # B downloads User A's artifact by path -> 404
    assert client.get(f"/api/v1/storage/files/by-path/{img_rel_path}", headers=headers_b).status_code == 404

    # B deletes User A's artifact -> 404
    assert client.delete(f"/api/v1/artifacts/{img_id}", headers=headers_b).status_code == 404
    assert client.delete(f"/api/v1/storage/files/{img_id}", headers=headers_b).status_code == 404

    # =========================================================================
    # STEP 3 VERIFICATION: Authorized access and video range requests for User A
    # =========================================================================

    # User A downloads screenshot by ID -> 200 OK
    res_dl = client.get(f"/api/v1/storage/files/{img_id}", headers=headers_a)
    assert res_dl.status_code == 200
    assert res_dl.content == screenshot_bytes
    assert res_dl.headers.get("accept-ranges") == "bytes"

    # User A streams video with Range request (e.g. video seeking: bytes 0-15)
    res_range = client.get(
        f"/api/v1/storage/files/{vid_id}",
        headers={**headers_a, "Range": "bytes=0-15"},
    )
    assert res_range.status_code == 206  # HTTP 206 Partial Content
    assert res_range.content == video_bytes[0:16]
    assert res_range.headers.get("accept-ranges") == "bytes"
    assert res_range.headers.get("content-range") == f"bytes 0-15/{len(video_bytes)}"
    assert res_range.headers.get("content-length") == "16"

    # User A seeks middle of video (bytes 20-35)
    res_range_mid = client.get(
        f"/api/v1/storage/files/{vid_id}",
        headers={**headers_a, "Range": "bytes=20-35"},
    )
    assert res_range_mid.status_code == 206
    assert res_range_mid.content == video_bytes[20:36]

    # Verify path traversal rejection
    res_traversal = client.get("/api/v1/storage/files/by-path/../secret.txt", headers=headers_a)
    assert res_traversal.status_code in (400, 403, 404)

    # =========================================================================
    # STEP 4 VERIFICATION: Cleanup when test or artifact is deleted
    # =========================================================================

    # User A deletes video artifact -> verify removed from disk and DB
    res_del_vid = client.delete(f"/api/v1/storage/files/{vid_id}", headers=headers_a)
    assert res_del_vid.status_code == 200
    assert not expected_vid_path.exists()
    with SessionMaker() as db:
        assert db.get(Artifact, vid_id) is None

    # User A deletes test -> verify all remaining test files removed from disk & DB
    assert expected_img_path.exists()  # screenshot was still there
    res_del_test = client.delete(f"/api/v1/projects/{proj_a_id}/saved-tests/{test_a_id}", headers=headers_a)
    assert res_del_test.status_code == 204

    # File on disk must be deleted!
    assert not expected_img_path.exists()
    test_folder = storage_root / "users" / user_a_id / "tests" / test_a_id
    assert not test_folder.exists()

    # DB record must be gone!
    with SessionMaker() as db:
        assert db.get(Artifact, img_id) is None
