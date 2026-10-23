"""Tests for Task A3: Multi-Level Planner and Edge-Case Engine."""

import json
from unittest.mock import MagicMock
import pytest

from kawach.agents.planner.agent import plan_catalog, plan_single_test
from kawach.agents.planner.edge_library import EDGE_LIBRARY, compute_risk_score
from kawach.agents.reviewer.agent import review_catalog
from kawach.core.config import settings
from kawach.schemas import (
    AppMap,
    Budgets,
    Catalog,
    CoverageMatrix,
    Journey,
    ReviewDecision,
    ReviewLog,
    Run,
    RunInput,
    SpecItem,
    Step,
    TestCase,
)
from kawach.storage import artifacts as storage


@pytest.fixture
def multi_level_run_fixture(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")

    run_id = "test-plan-ml-001"
    spec_items = [
        SpecItem(id="S1", text="User registration with email and password"),
        SpecItem(id="S2", text="User authentication and dashboard landing"),
        SpecItem(id="S3", text="Create new item with title and description"),
        SpecItem(id="S4", text="Item configuration wizard with permissions"),
        SpecItem(id="S5", text="Delete item with confirmation dialog"),
    ]

    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-23T00:00:00Z",
        targetUrl="http://localhost:5055",
        prompt="Testing multi-level application",
        specRaw="S1: User registration\nS2: User auth\nS3: Create item\nS4: Item wizard\nS5: Delete item",
        spec=spec_items,
        username="tester@test.com",
        mode="autonomous",
        budgets=Budgets(maxTests=10),
    )
    storage.save_model(run_id, "input.json", run_input)

    run_obj = Run(
        runId=run_id,
        createdAt="2026-10-23T00:00:00Z",
        updatedAt="2026-10-23T00:00:00Z",
        stage="created",
        mode="autonomous",
        targetUrl="http://localhost:5055",
    )
    storage.save_model(run_id, "run.json", run_obj)

    # AppMap with journeys and deep states
    app_map = AppMap(
        baseUrl="http://localhost:5055",
        generatedAt="2026-10-23T00:00:00Z",
        pages=[],
        journeys=[
            Journey(
                journeyId="journey_1",
                title="Dashboard -> Create Item -> Configure Settings -> Save",
                depth=3,
                steps=[
                    "Navigate to /dashboard",
                    "Click 'New Item'",
                    "Fill 'Title' with 'Task A'",
                    "Click 'Configure Permissions'",
                ],
            )
        ],
    )
    storage.save_model(run_id, "app_map.json", app_map)

    return run_id


def test_edge_library_definitions():
    """Verify all 14 data-driven edge cases exist with severity and templates."""
    required_tags = [
        "empty_whitespace",
        "very_long_input",
        "unicode_emoji_rtl",
        "html_script_escaping",
        "boundary_negative_numbers",
        "duplicate_submission",
        "rapid_repeat_submit",
        "back_forward_refresh",
        "interrupted_flow",
        "expired_session",
        "order_permutations",
        "keyboard_only",
        "viewport_changes",
        "network_failure",
    ]

    for tag in required_tags:
        assert tag in EDGE_LIBRARY, f"Missing edge case: {tag}"
        edge_def = EDGE_LIBRARY[tag]
        assert edge_def.severity >= 1.0
        assert len(edge_def.title_template) > 0
        assert len(edge_def.action_template) > 0
        assert len(edge_def.assertion_template) > 0


def test_risk_score_computation():
    """Verify riskScore = spec criticality x depth x edge severity."""
    # Critical spec (3.0) x depth 3 x edge severity 3.0 = 27.0
    score = compute_risk_score(priority="critical", depth=3, severity=3.0)
    assert score == 27.0

    # High spec (2.5) x depth 2 x standard edge 1.0 = 5.0
    score_standard = compute_risk_score(priority="high", depth=2, severity=1.0)
    assert score_standard == 5.0

    # Low spec (1.0) x depth 1 x severity 2.0 = 2.0
    score_low = compute_risk_score(priority="low", depth=1, severity=2.0)
    assert score_low == 2.0


def test_planner_generates_multi_level_tests_and_coverage_matrix(multi_level_run_fixture, monkeypatch):
    """Verify generation of all 4 archetypes, riskScore sorting, and coverage matrix."""
    run_id = multi_level_run_fixture

    # Custom LLM output with 4 archetypes: single_step, journey, deep_path, edge_case
    mock_llm_tests = [
        {
            "title": "Single Step: Verify Landing Page Title",
            "description": "Verifies homepage loads and title is visible",
            "specRef": ["S1"],
            "priority": "low",
            "depth": 1,
            "category": "single_step",
            "steps": [{"action": "Navigate to /", "expected": "Page title is displayed"}],
        },
        {
            "title": "Journey: Login to Dashboard",
            "description": "Navigates to login and authenticates to dashboard",
            "specRef": ["S2"],
            "priority": "high",
            "depth": 2,
            "category": "journey",
            "steps": [
                {"action": "Navigate to /login", "expected": None},
                {"action": "Fill credentials and submit", "expected": "Dashboard is displayed"},
            ],
        },
        {
            "title": "Deep Path: Multi-step Item Configuration Wizard",
            "description": "Traverses 3 screens from creation to settings and save",
            "specRef": ["S3", "S4"],
            "priority": "critical",
            "depth": 3,
            "category": "deep_path",
            "steps": [
                {"action": "Click 'New Item'", "expected": "Modal opens"},
                {"action": "Fill 'Title' and click 'Next'", "expected": "Step 2 settings visible"},
                {"action": "Toggle permissions and click 'Finish'", "expected": "Item saved successfully"},
            ],
        },
        {
            "title": "Edge Case: Escape HTML Script Tags in Item Title",
            "description": "Verifies script injection in item title is escaped",
            "specRef": ["S3"],
            "priority": "high",
            "depth": 2,
            "category": "edge_case",
            "edgeTags": ["html_script_escaping"],
            "steps": [
                {"action": "Fill Title with '<script>alert(1)</script>'", "expected": None},
                {"action": "Submit form", "expected": "Title rendered with escaped characters"},
            ],
        },
        {
            "title": "Verify: Delete item with confirmation dialog",
            "description": "Checks item deletion",
            "specRef": ["S5"],
            "priority": "medium",
            "depth": 1,
            "category": "single_step",
            "steps": [{"action": "Click Delete", "expected": "Item removed"}],
        },
    ]

    llm = MagicMock()
    llm.complete_json.return_value = {"tests": mock_llm_tests}
    monkeypatch.setattr("kawach.agents.planner.agent.get_llm", lambda: llm)

    catalog = plan_catalog(run_id)

    assert isinstance(catalog, Catalog)
    assert len(catalog.tests) >= 5

    # 1. Verify all 4 archetypes exist
    categories = {t.category for t in catalog.tests}
    assert "single_step" in categories
    assert "journey" in categories
    assert "deep_path" in categories
    assert "edge_case" in categories

    # 2. Verify sorting by riskScore descending
    risk_scores = [t.riskScore for t in catalog.tests]
    assert risk_scores == sorted(risk_scores, reverse=True), "Catalog not sorted by riskScore descending"

    # Verify highest risk test is T01
    assert catalog.tests[0].id == "T01"
    assert catalog.tests[0].riskScore >= catalog.tests[-1].riskScore

    # 3. Verify steps have checkpoints and assertions
    deep_test = next(t for t in catalog.tests if t.category == "deep_path")
    assert deep_test.depth >= 3
    for s in deep_test.steps:
        assert s.checkpoint is not None
        assert len(s.checkpoint) > 0

    # 4. Verify CoverageMatrix
    assert catalog.coverageMatrix is not None
    matrix: CoverageMatrix = catalog.coverageMatrix
    assert set(matrix.specItems) == {"S1", "S2", "S3", "S4", "S5"}
    assert matrix.depthLevels["L1"] >= 1
    assert matrix.depthLevels["L2"] >= 1
    assert matrix.depthLevels["L3+"] >= 1
    assert matrix.edgeCategories.get("escaping_security", 0) >= 1

    # Check matrix mapping for S3
    assert "S3" in matrix.matrix
    assert len(matrix.matrix["S3"]["testIds"]) >= 1


def test_reviewer_approve_reject_powers(multi_level_run_fixture):
    """Verify Reviewer agent approves valid tests and rejects incomplete tests with logged reasons."""
    run_id = multi_level_run_fixture

    # Construct catalog with 1 valid test and 1 invalid test (empty steps)
    test_valid = TestCase(
        id="T01",
        title="Valid Journey Test",
        description="A completely valid multi-step test",
        specRef=["S1"],
        priority="high",
        depth=2,
        category="journey",
        riskScore=5.0,
        steps=[
            Step(n=1, action="Go to /login", expected=None, checkpoint="Step 1"),
            Step(n=2, action="Submit valid credentials", expected="Dashboard shown", checkpoint="Step 2"),
        ],
        status="proposed",
    )

    test_invalid = TestCase(
        id="T02",
        title="Invalid Incomplete Test",
        description="Missing steps",
        specRef=["S2"],
        priority="low",
        depth=1,
        category="single_step",
        riskScore=1.0,
        steps=[],  # Invalid: no steps!
        status="proposed",
    )

    catalog = Catalog(runId=run_id, generatedAt="2026-10-23T00:00:00Z", tests=[test_valid, test_invalid])
    storage.save_model(run_id, "catalog.json", catalog)

    review_log: ReviewLog = review_catalog(run_id)

    assert isinstance(review_log, ReviewLog)
    assert len(review_log.decisions) == 2

    decisions_by_id = {d.testId: d for d in review_log.decisions}

    # T01 should be approved
    assert decisions_by_id["T01"].decision == "approve"
    assert "Approved autonomously" in decisions_by_id["T01"].reason
    assert "journey" in decisions_by_id["T01"].reason

    # T02 should be rejected
    assert decisions_by_id["T02"].decision == "reject"
    assert "Rejected autonomously" in decisions_by_id["T02"].reason
    assert "missing steps" in decisions_by_id["T02"].reason

    # Verify catalog.json updated on disk
    updated_cat = storage.load_model(run_id, "catalog.json", Catalog)
    assert updated_cat.tests[0].status == "approved"
    assert updated_cat.tests[1].status == "rejected"
