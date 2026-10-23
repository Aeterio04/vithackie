"""Tests for Phase 5 Scaffolding: Webhooks, Policies, 501 routes, and Regression Graph."""

import json
import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient


from kawach.core.config import settings
from kawach.db.base import Base
from kawach.db.models.commit_loop import CommitEvent
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.db.session import engine, sessionmaker
from kawach.domain.policies import classify_fix_risk, is_small_fix
from kawach.integrations.github.policy import ALLOW_DIRECT_PUSH, AUTO_FIX_TARGET, can_push_directly
from kawach.integrations.github.webhook_signature import (
    compute_github_signature,
    is_delivery_processed,
    verify_github_signature,
)
from kawach.main import create_app
from kawach.services.auth_service import AuthService
from kawach.services.fix_service import FixService
from kawach.services.localization_service import LocalizationService
from kawach.services.regression_service import RegressionService
from kawach.workflows.regression import build_regression_graph, regression_graph


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    # Keep DB for other test runs or clean up


def test_domain_policies_small_fix():
    """Verify objective classification of 'small fix' vs escalation."""
    # 1 file, 20 lines -> Small
    assert is_small_fix(["src/components/Button.tsx"], 20) is True
    assert classify_fix_risk(["src/components/Button.tsx"], 20) == "small"

    # 2 files (> max_files=1) -> Large
    assert is_small_fix(["src/components/Button.tsx", "src/styles.css"], 20) is False
    assert classify_fix_risk(["src/components/Button.tsx", "src/styles.css"], 20) == "large"

    # 1 file, 21 lines (> max_lines=20) -> Large
    assert is_small_fix(["src/components/Button.tsx"], 21) is False
    assert classify_fix_risk(["src/components/Button.tsx"], 21) == "large"

    # Forbidden paths: auth, login, payment, migrations -> Large regardless of size
    assert is_small_fix(["src/auth/jwt_handler.py"], 5) is False
    assert is_small_fix(["src/payment/stripe_checkout.py"], 5) is False
    assert is_small_fix(["alembic/versions/001_initial.py"], 5) is False
    assert is_small_fix(["src/security/crypto.py"], 5) is False

    # Zero files -> False
    assert is_small_fix([], 0) is False

    # GitHub policy constants
    assert ALLOW_DIRECT_PUSH is False
    assert can_push_directly("main") is False
    assert AUTO_FIX_TARGET == "pull_request"


def test_webhook_signature_verification_and_idempotency():
    """Test HMAC-SHA256 signature verification and delivery ID tracking."""
    secret = "test-secret-12345"
    payload = b'{"ref": "refs/heads/main", "after": "abc123"}'

    valid_sig = compute_github_signature(payload, secret)
    assert valid_sig.startswith("sha256=")
    assert verify_github_signature(payload, secret, valid_sig) is True

    # Bad signature
    assert verify_github_signature(payload, secret, "sha256=badhex0000000000") is False

    # Wrong secret
    assert verify_github_signature(payload, "wrong-secret", valid_sig) is False

    # Missing / malformed prefix
    assert verify_github_signature(payload, secret, valid_sig.replace("sha256=", "")) is False
    assert verify_github_signature(payload, secret, None) is False
    assert verify_github_signature(payload, "", valid_sig) is False

    # Test idempotency helper with DB session
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        uid = uuid.uuid4().hex[:8]
        user = User(email=f"commit_user_{uid}@example.com", password_hash="hash")
        db.add(user)
        db.commit()

        project = Project(
            name=f"Commit Webhook Project {uid}",
            slug=f"commit-webhook-proj-{uid}",
            owner_id=user.id,
            target_url="http://localhost:4000",
        )
        db.add(project)
        db.commit()

        delivery_id = f"delivery-uuid-{uid}"
        assert is_delivery_processed(delivery_id, db) is False

        event = CommitEvent(
            project_id=project.id,
            sha="1234567890123456789012345678901234567890",
            branch="main",
            webhook_delivery_id=delivery_id,
            pushed_at=datetime.now(timezone.utc),
            status="pending",
        )
        db.add(event)
        db.commit()

        # Re-check -> now True
        assert is_delivery_processed(delivery_id, db) is True


def test_webhook_endpoint_validation_and_501():
    """Test POST /api/v1/webhooks/github endpoint validation and status responses."""
    app = create_app()
    client = TestClient(app)

    webhook_secret = settings.GITHUB_WEBHOOK_SECRET or "dev-webhook-secret"
    payload = json.dumps({"zen": "Keep it logically awesome."}).encode("utf-8")
    valid_sig = compute_github_signature(payload, webhook_secret)

    # 1. Missing signature header -> 401
    res_missing = client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert res_missing.status_code == 401
    assert "Missing required" in res_missing.json()["detail"]

    # 2. Invalid signature header -> 401
    res_bad = client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=invalidhex000000",
        },
    )
    assert res_bad.status_code == 401
    assert "Invalid HMAC" in res_bad.json()["detail"]

    # 3. Valid signature, fresh delivery -> 501 Not Implemented
    fresh_id = f"delivery-fresh-{uuid.uuid4().hex[:8]}"
    res_valid = client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": valid_sig,
            "X-GitHub-Delivery": fresh_id,
        },
    )
    assert res_valid.status_code == 501
    assert "scaffolded but not implemented" in res_valid.json()["detail"]

    # 4. Duplicate delivery ID -> 409 Conflict
    dup_delivery_id = f"delivery-dup-{uuid.uuid4().hex[:8]}"
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        user = db.query(User).first()
        project = db.query(Project).filter_by(owner_id=user.id).first()
        event = CommitEvent(
            project_id=project.id,
            sha="abcdef1234567890abcdef1234567890abcdef12",
            branch="main",
            webhook_delivery_id=dup_delivery_id,
            pushed_at=datetime.now(timezone.utc),
            status="pending",
        )
        db.add(event)
        db.commit()

    res_dup = client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": valid_sig,
            "X-GitHub-Delivery": dup_delivery_id,
        },
    )
    assert res_dup.status_code == 409
    assert "Duplicate webhook delivery ID" in res_dup.json()["detail"]


def test_scaffolded_501_api_routes():
    """Verify all new-flow routes return 501 Not Implemented."""
    app = create_app()
    client = TestClient(app)

    uid = uuid.uuid4().hex[:8]
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        auth_svc = AuthService(db)
        user = auth_svc.register_user(f"scaffold_user_{uid}@example.com", "Password123!")
        token = auth_svc.create_access_token(user.id, user.email)


        project = Project(
            name=f"Scaffold Project {uid}",
            slug=f"scaffold-proj-{uid}",
            owner_id=user.id,
            target_url="http://localhost:4000",
        )
        db.add(project)
        db.commit()
        project_id = project.id

    client.cookies.set("auth_token", token)

    # 1. Saved Tests routes (501)
    res = client.get(f"/api/v1/projects/{project_id}/saved-tests")
    assert res.status_code == 501

    res = client.post(
        f"/api/v1/projects/{project_id}/saved-tests",
        json={"run_id": "r1", "test_id": "T01"},
    )
    assert res.status_code == 501

    res = client.delete(f"/api/v1/projects/{project_id}/saved-tests/t01")
    assert res.status_code == 501

    # 2. Commits routes (501)
    res = client.get(f"/api/v1/projects/{project_id}/commits")
    assert res.status_code == 501

    res = client.post(
        f"/api/v1/projects/{project_id}/commits",
        json={
            "sha": "1234567890123456789012345678901234567890",
            "branch": "main",
            "pushed_at": datetime.now(timezone.utc).isoformat(),
            "webhook_delivery_id": "d-123",
        },
    )
    assert res.status_code == 501

    res = client.get(f"/api/v1/projects/{project_id}/commits/c1/analysis")
    assert res.status_code == 501

    res = client.post(f"/api/v1/projects/{project_id}/commits/c1/suggest-fix")
    assert res.status_code == 501

    res = client.post(
        f"/api/v1/projects/{project_id}/commits/c1/auto-fix",
        json={"action": "create_pr"},
    )
    assert res.status_code == 501


def test_regression_graph_structure():
    """Verify LangGraph regression state machine compiles with all 6 named nodes."""
    graph = build_regression_graph()
    assert graph is not None

    # Inspect graph nodes
    node_keys = set(graph.get_graph().nodes.keys())
    required_nodes = {
        "select_tests",
        "run_saved",
        "verify",
        "localize",
        "suggest_fix",
        "validate_fix",
    }
    assert required_nodes.issubset(node_keys)

    # Run pass-through execution
    init_state = {
        "project_id": "p1",
        "commit_sha": "abc1234",
        "files_changed": ["src/App.tsx"],
        "selected_test_ids": [],
        "failed_test_ids": [],
        "verified_defect_ids": [],
        "analysis_id": None,
        "fix_suggestion_id": None,
        "is_validated": False,
        "status": "pending",
        "error": None,
    }
    final_state = graph.invoke(init_state)
    assert final_state["status"] == "verification_completed"


def test_service_and_agent_protocols_raise_not_implemented():
    """Verify scaffolded service and agent implementations raise NotImplementedError."""
    reg_svc = RegressionService()
    with pytest.raises(NotImplementedError):
        reg_svc.select_tests_for_diff("p1", ["src/App.tsx"])
    with pytest.raises(NotImplementedError):
        reg_svc.save_test("p1", "r1", "T01")
    with pytest.raises(NotImplementedError):
        reg_svc.run_regression_suite("p1", ["t1"])

    loc_svc = LocalizationService()
    with pytest.raises(NotImplementedError):
        loc_svc.localize_failure("r1", "res1")

    fix_svc = FixService()
    with pytest.raises(NotImplementedError):
        fix_svc.suggest_fix("a1")
    with pytest.raises(NotImplementedError):
        fix_svc.validate_fix("f1")
    with pytest.raises(NotImplementedError):
        fix_svc.create_auto_fix_pr("f1")
