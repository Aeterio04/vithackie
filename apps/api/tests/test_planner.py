"""Unit tests for Test Planner agent."""

import json
from unittest.mock import MagicMock
import pytest

from app.agents import planner
from app.config import settings
from app.models import AppMap, Budgets, Catalog, Run, RunInput, SpecItem
from app import storage


DEMO_SPEC_ITEMS = [
    SpecItem(id="S1", text="Signing up with a valid email and a password of at least 8 characters creates the account."),
    SpecItem(id="S2", text="Signing up with an invalid email address is rejected with the message 'Enter a valid email address'."),
    SpecItem(id="S3", text="Signing up with a password shorter than 8 characters is rejected with 'Password must be at least 8 characters'."),
    SpecItem(id="S4", text="Logging in with a correct email and password lands the user on the dashboard."),
    SpecItem(id="S5", text="Logging in with a wrong password shows the message 'Invalid email or password'."),
    SpecItem(id="S6", text="Logging in is case-insensitive for the email address."),
    SpecItem(id="S7", text="On the dashboard, adding an item with a non-empty title shows that item in the list."),
    SpecItem(id="S8", text="On the dashboard, adding an item with an empty title is rejected with 'Title is required'."),
    SpecItem(id="S9", text="With several items in the list, clicking Delete on an item removes only that item."),
    SpecItem(id="S10", text="On the settings page, saving a display name shows 'Settings saved'."),
    SpecItem(id="S11", text="Logging out returns the user to the login page, and Back button does not show dashboard."),
]


@pytest.fixture
def run_fixture(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")

    run_id = "test-plan-run-001"
    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        targetUrl="http://localhost:4000",
        prompt="Testing TaskBoard to-do application",
        specRaw="S1: ...\nS2: ...",
        spec=DEMO_SPEC_ITEMS,
        username="qa.tester@example.com",
        mode="manual",
        budgets=Budgets(maxTests=12),
    )
    storage.save_model(run_id, "input.json", run_input)

    run_obj = Run(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        updatedAt="2026-10-18T00:00:00Z",
        stage="created",
        mode="manual",
        targetUrl="http://localhost:4000",
    )
    storage.save_model(run_id, "run.json", run_obj)

    # Load sample app map from packages/contracts/samples/app_map.sample.json
    sample_path = settings.repo_root / "packages" / "contracts" / "samples" / "app_map.sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        map_data = json.load(f)
    storage.write_json(run_id, "app_map.json", map_data)

    return run_id


def test_plan_catalog_with_fake_llm(run_fixture):
    run_id = run_fixture
    catalog = planner.plan_catalog(run_id)

    assert isinstance(catalog, Catalog)
    assert len(catalog.tests) == 11

    # Check ID assignment T01..T11
    expected_ids = [f"T{i:02d}" for i in range(1, 12)]
    assert [t.id for t in catalog.tests] == expected_ids

    # Check all statuses and origins
    for t in catalog.tests:
        assert t.status == "proposed"
        assert t.origin == "planner"
        assert t.script is None
        assert t.scriptStatus == "pending"
        assert len(t.steps) > 0

    # Check full spec coverage S1..S11
    all_covered = set()
    for t in catalog.tests:
        all_covered.update(t.specRef)
    assert all_covered == {f"S{i}" for i in range(1, 12)}

    # Verify stage transition
    run = storage.get_run(run_id)
    assert run.stage == "planning"


def test_plan_catalog_retry_and_fallback(run_fixture, monkeypatch):
    run_id = run_fixture
    llm = planner.get_llm()

    # Case A: First call missing S7 and S9, retry covers all
    first_call_tests = [
        {"title": f"Test {i}", "description": "desc", "specRef": [f"S{i}"], "priority": "medium", "steps": [{"action": "a", "expected": "e"}]}
        for i in range(1, 12) if i not in (7, 9)
    ]
    all_call_tests = [
        {"title": f"Test {i}", "description": "desc", "specRef": [f"S{i}"], "priority": "medium", "steps": [{"action": "a", "expected": "e"}]}
        for i in range(1, 12)
    ]

    mock_llm = MagicMock(side_effect=[{"tests": first_call_tests}, {"tests": all_call_tests}])
    monkeypatch.setattr(llm, "complete_json", mock_llm)

    catalog = planner.plan_catalog(run_id)
    assert mock_llm.call_count == 2
    assert len(catalog.tests) == 11

    # Case B: LLM never covers S7 even on retry -> generates fallback test
    never_s7_tests = [
        {"title": f"Test {i}", "description": "desc", "specRef": [f"S{i}"], "priority": "medium", "steps": [{"action": "a", "expected": "e"}]}
        for i in range(1, 12) if i != 7
    ]
    mock_llm_fallback = MagicMock(side_effect=[{"tests": never_s7_tests}, {"tests": never_s7_tests}])
    monkeypatch.setattr(llm, "complete_json", mock_llm_fallback)

    catalog_fallback = planner.plan_catalog(run_id)
    s7_test = next((t for t in catalog_fallback.tests if "S7" in t.specRef), None)
    assert s7_test is not None
    assert s7_test.origin == "fallback"
    assert s7_test.title.startswith("Verify: ")


def test_plan_catalog_clamped_without_losing_coverage(run_fixture, monkeypatch):
    run_id = run_fixture
    llm = planner.get_llm()

    # Create 15 tests: S1..S11 plus 4 duplicate/extra low-priority tests covering S1, S2, S3, S4
    fifteen_tests = [
        {"title": f"Test S{i}", "description": "desc", "specRef": [f"S{i}"], "priority": "high", "steps": [{"action": "a", "expected": "e"}]}
        for i in range(1, 12)
    ]
    extra_tests = [
        {"title": f"Extra S{i}", "description": "desc", "specRef": [f"S{i}"], "priority": "low", "steps": [{"action": "a", "expected": "e"}]}
        for i in range(1, 5)
    ]
    all_15 = fifteen_tests + extra_tests  # 15 tests total

    monkeypatch.setattr(llm, "complete_json", MagicMock(return_value={"tests": all_15}))

    catalog = planner.plan_catalog(run_id)
    assert len(catalog.tests) == 12  # Clamped to maxTests=12

    # Verify all S1..S11 are still covered
    covered = set()
    for t in catalog.tests:
        covered.update(t.specRef)
    assert covered == {f"S{i}" for i in range(1, 12)}


def test_plan_single_test_appends_and_assigns_ids(run_fixture):
    run_id = run_fixture
    # First plan catalog (creates T01..T11)
    planner.plan_catalog(run_id)

    # Add single test 1
    t1 = planner.plan_single_test(run_id, "Check that dashboard shows an error if title is over 100 characters")
    assert t1.id == "T12"
    assert t1.origin == "human"
    assert t1.status == "proposed"

    # Add single test 2
    t2 = planner.plan_single_test(run_id, "Check that login form has autofocus on email input")
    assert t2.id == "T13"
    assert t2.origin == "human"

    # Verify both are written to disk in catalog.json
    disk_cat = storage.load_model(run_id, "catalog.json", Catalog)
    assert len(disk_cat.tests) == 13
    assert disk_cat.tests[-2].id == "T12"
    assert disk_cat.tests[-1].id == "T13"


def test_plan_single_test_rejects_invalid_prompt(run_fixture):
    run_id = run_fixture
    planner.plan_catalog(run_id)

    with pytest.raises(ValueError):
        planner.plan_single_test(run_id, "")

    with pytest.raises(ValueError):
        planner.plan_single_test(run_id, "   ")

    with pytest.raises(ValueError):
        planner.plan_single_test(run_id, "a" * 501)
