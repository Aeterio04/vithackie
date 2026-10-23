"""Comprehensive tests for Task A5: Commit Regression Loop, Saved Tests, and Webhooks."""

from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from kawach.core.config import settings
from kawach.db.models.commit_loop import CommitEvent, FailureAnalysis, FailureCandidate, FixSuggestion
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.db.models.runs import Run as DbRun
from kawach.db.models.saved_tests import SavedTest, SavedTestCoverage
from kawach.db.session import engine
from kawach.integrations.github.client import GitHubClient
from kawach.integrations.github.webhook_signature import compute_github_signature
from kawach.schemas.commit_loop import CommitEventCreate, FixSuggestionActionRequest
from kawach.schemas.saved_tests import SavedTestCreate
from kawach.services.auth_service import AuthService
from kawach.services.regression_service import RegressionService
from kawach.services.saved_test_service import SavedTestService
from kawach.workflows.regression import RegressionState, regression_graph


@pytest.fixture
def test_setup():
    """Setup project, user, and db session."""
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        uid = uuid.uuid4().hex[:8]
        auth_svc = AuthService(db)
        user = auth_svc.register_user(f"commit_loop_{uid}@example.com", "Password123!")
        token = auth_svc.create_access_token(user.id, user.email)

        project = Project(
            name=f"Commit Loop Project {uid}",
            slug=f"commit-loop-proj-{uid}",
            owner_id=user.id,
            target_url="http://localhost:4000",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        yield {
            "db": db,
            "user": user,
            "token": token,
            "project": project,
            "project_id": project.id,
        }


def test_saved_test_service_save_list_delete(test_setup, tmp_path):
    """Verify SavedTestService creates SHA-256 script artifacts, coverage touchpoints, and lists/deletes."""
    db = test_setup["db"]
    project_id = test_setup["project_id"]

    svc = SavedTestService(db)

    # 1. Save test
    payload = SavedTestCreate(
        run_id="run_alpha_01",
        test_id="T01",
        name="Checkout Flow Journey",
        tags=["checkout", "payment", "p0"],
    )

    saved = svc.save_test(project_id, payload, user_id=test_setup["user"].id)

    assert saved.id is not None
    assert saved.project_id == project_id
    assert saved.name == "Checkout Flow Journey"
    assert "checkout" in saved.tags
    assert Path(saved.script_path).exists()

    # 2. Verify coverage touchpoints in DB
    cov_items = db.scalars(
        select(SavedTestCoverage).where(SavedTestCoverage.saved_test_id == saved.id)
    ).all()
    assert len(cov_items) >= 1
    refs = [c.ref for c in cov_items]
    assert "checkout" in refs or "/" in refs

    # 3. List saved tests
    all_tests = svc.list_saved_tests(project_id)
    assert len(all_tests) == 1
    assert all_tests[0].id == saved.id

    # Filter by tag
    checkout_tests = svc.list_saved_tests(project_id, tag="checkout")
    assert len(checkout_tests) == 1
    unrelated_tests = svc.list_saved_tests(project_id, tag="nonexistent_tag")
    assert len(unrelated_tests) == 0

    # 4. Delete saved test
    del_ok = svc.delete_saved_test(project_id, saved.id)
    assert del_ok is True
    assert len(svc.list_saved_tests(project_id)) == 0


def test_diff_aware_test_selection(test_setup):
    """Verify smart test selection maps changed files to affected tests only."""
    db = test_setup["db"]
    project_id = test_setup["project_id"]

    # Create 3 saved tests touching different areas
    svc = SavedTestService(db)

    t1 = svc.save_test(
        project_id,
        SavedTestCreate(run_id="r1", test_id="T01", name="Checkout Test", tags=["checkout.tsx"]),
    )
    t2 = svc.save_test(
        project_id,
        SavedTestCreate(run_id="r1", test_id="T02", name="Auth Test", tags=["auth_modal.tsx"]),
    )
    t3 = svc.save_test(
        project_id,
        SavedTestCreate(run_id="r1", test_id="T03", name="Navbar Test", tags=["navbar.tsx"]),
    )

    reg_svc = RegressionService(db)

    # 1. Modify Checkout component -> should select only Checkout test (T01)
    selected_1 = reg_svc.select_tests_for_diff(
        project_id,
        files_changed=["src/components/Checkout.tsx"],
    )
    assert t1.id in selected_1
    assert t2.id not in selected_1

    # 2. Modify AuthModal component -> should select only Auth test (T02)
    selected_2 = reg_svc.select_tests_for_diff(
        project_id,
        files_changed=["src/modals/Auth_Modal.tsx"],
    )
    assert t2.id in selected_2
    assert t1.id not in selected_2

    # 3. Modify unrelated file -> fallback to all tests to prevent silent regressions
    selected_3 = reg_svc.select_tests_for_diff(
        project_id,
        files_changed=["README.md"],
    )
    assert len(selected_3) == 3

    # 4. Force full run -> selects all 3
    selected_4 = reg_svc.select_tests_for_diff(
        project_id,
        files_changed=["src/components/Checkout.tsx"],
        force_full=True,
    )
    assert len(selected_4) == 3


def test_webhook_ingestion_creates_commit_and_run(test_setup):
    """Test webhook ingestion verifies HMAC-SHA256, records CommitEvent, and triggers run."""
    from fastapi.testclient import TestClient
    from kawach.main import create_app

    app = create_app()
    client = TestClient(app)

    db = test_setup["db"]
    project_id = test_setup["project_id"]
    secret = settings.GITHUB_WEBHOOK_SECRET or "dev-webhook-secret"

    payload_data = {
        "ref": "refs/heads/feature-branch",
        "after": "c1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0",
        "head_commit": {
            "id": "c1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0",
            "message": "Fix checkout pricing bug",
            "author": {"name": "QA Engineer"},
            "modified": ["src/components/Checkout.tsx"],
        },
        "commits": [
            {
                "id": "c1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0",
                "modified": ["src/components/Checkout.tsx"],
            }
        ],
    }
    raw_payload = json.dumps(payload_data).encode("utf-8")
    sig = compute_github_signature(raw_payload, secret)
    delivery_id = f"hook_{uuid.uuid4().hex[:8]}"

    res = client.post(
        f"/api/v1/webhooks/github?project_id={project_id}",
        content=raw_payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "push",
        },
    )

    assert res.status_code == 202
    body = res.json()
    assert body["ok"] is True
    assert body["sha"] == "c1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0"
    assert body["branch"] == "feature-branch"
    assert "run_id" in body

    # Verify CommitEvent recorded in DB
    event = db.scalar(
        select(CommitEvent).where(CommitEvent.webhook_delivery_id == delivery_id)
    )
    assert event is not None
    assert event.sha == "c1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0"
    assert event.author == "QA Engineer"
    assert "src/components/Checkout.tsx" in event.files_changed

    # Duplicate delivery must be rejected with 409
    res_dup = client.post(
        f"/api/v1/webhooks/github?project_id={project_id}",
        content=raw_payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-GitHub-Delivery": delivery_id,
        },
    )
    assert res_dup.status_code == 409


def test_manual_commit_trigger_and_analysis_routes(test_setup):
    """Test manual commit regression trigger, failure analysis, and auto-fix PR endpoints."""
    from fastapi.testclient import TestClient
    from kawach.main import create_app

    app = create_app()
    client = TestClient(app)
    client.cookies.set("auth_token", test_setup["token"])

    project_id = test_setup["project_id"]
    sha = "9999888877776666555544443333222211110000"

    # 1. Trigger manual commit regression
    commit_payload = {
        "sha": sha,
        "branch": "staging",
        "author": "Alice Developer",
        "message": "Update payment calculations",
        "pushed_at": datetime.now(timezone.utc).isoformat(),
        "webhook_delivery_id": f"man_{uuid.uuid4().hex[:8]}",
        "files_changed": ["src/checkout/payment.ts"],
        "diff_stats": {"additions": 5, "deletions": 2},
    }

    res_post = client.post(
        f"/api/v1/projects/{project_id}/commits",
        json=commit_payload,
    )
    assert res_post.status_code == 201
    evt_read = res_post.json()
    assert evt_read["sha"] == sha
    assert evt_read["branch"] == "staging"

    # 2. List commits
    res_list = client.get(f"/api/v1/projects/{project_id}/commits")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1
    assert any(c["sha"] == sha for c in res_list.json())

    # 3. Simulate failure analysis in DB for this commit
    db = test_setup["db"]
    analysis = FailureAnalysis(
        id=str(uuid.uuid4()),
        run_id="reg_run_01",
        test_result_id="T01",
        commit_event_id=evt_read["id"],
        summary="Payment failure on edge currency boundary",
        status="completed",
    )
    db.add(analysis)
    db.flush()

    db.add(
        FailureCandidate(
            analysis_id=analysis.id,
            rank=1,
            file_path="src/checkout/payment.ts",
            component="PaymentService",
            confidence=0.92,
            rationale="Modified directly in commit 99998888",
        )
    )
    db.commit()

    # 4. Fetch analysis
    res_ana = client.get(f"/api/v1/projects/{project_id}/commits/{sha}/analysis")
    assert res_ana.status_code == 200
    ana_data = res_ana.json()
    assert len(ana_data["candidates"]) == 1
    assert ana_data["candidates"][0]["file_path"] == "src/checkout/payment.ts"
    assert ana_data["candidates"][0]["confidence"] == 0.92

    # 5. Suggest fix
    res_sug = client.post(f"/api/v1/projects/{project_id}/commits/{sha}/suggest-fix")
    assert res_sug.status_code == 200
    sug_data = res_sug.json()
    assert sug_data["risk_class"] == "small"
    assert sug_data["files_changed"] <= 1
    assert sug_data["lines_changed"] <= 20

    # 6. Open Auto-Fix PR
    res_pr = client.post(
        f"/api/v1/projects/{project_id}/commits/{sha}/auto-fix",
        json={"action": "create_pr"},
    )
    assert res_pr.status_code == 200
    pr_data = res_pr.json()
    assert pr_data["status"] == "applied"
    assert "github.com" in pr_data["pr_url"]
    assert pr_data["pr_number"] == 42


def test_github_client_pr_comment_formatting():
    """Verify GitHubClient formats markdown summary with test counts, suspects, and diff."""
    client = GitHubClient()

    comment = client.format_pr_comment(
        sha="abcdef1234567890",
        branch="main",
        run_id="reg_abcdef12",
        selected_tests=["T01", "T02"],
        failed_tests=["T01"],
        verified_defects=["T01"],
        suspect_files=[{
            "rank": 1,
            "file_path": "src/pages/Checkout.tsx",
            "confidence": 0.88,
            "rationale": "Changed in commit abcdef12",
        }],
        diff_patch="--- a/src/pages/Checkout.tsx\n+++ b/src/pages/Checkout.tsx\n+ // fix",
        is_validated=True,
    )

    assert "Kawach Autonomous QA" in comment
    assert "abcdef12" in comment
    assert "src/pages/Checkout.tsx" in comment
    assert "88%" in comment
    assert "Replay Validated" in comment
    assert "diff" in comment
