"""Unit tests for Explorer agent."""

import json
from unittest.mock import MagicMock, patch
import pytest

from app.agents import explorer
from app.config import settings
from app.models import AppMap, Budgets, Run, RunInput
from app import storage


@pytest.fixture
def run_fixture(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")

    run_id = "test-explore-run-001"
    # Create input.json, run.json, secrets.json
    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        targetUrl="http://localhost:5055",
        prompt="Testing fixture web application",
        specRaw="S1: Login works\nS2: Items works",
        username="admin@test.com",
        mode="manual",
        budgets=Budgets(maxPages=5, exploreSeconds=30),
    )
    storage.save_model(run_id, "input.json", run_input)
    storage.write_json(run_id, "secrets.json", {"password": "test_pass_123"})

    run_obj = Run(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        updatedAt="2026-10-18T00:00:00Z",
        stage="created",
        mode="manual",
        targetUrl="http://localhost:5055",
    )
    storage.save_model(run_id, "run.json", run_obj)

    return run_id


def test_run_explorer_with_mocked_subprocess(run_fixture, monkeypatch):
    run_id = run_fixture

    # Write a pre-cooked explore_raw.json to simulate crawler finishing
    raw_data = {
        "baseUrl": "http://localhost:5055",
        "generatedAt": "2026-10-18T00:00:00Z",
        "login": {"attempted": True, "success": True, "url": "http://localhost:5055/login", "note": "OK"},
        "pages": [
            {
                "url": "http://localhost:5055/login",
                "path": "/login",
                "title": "Login",
                "status": 200,
                "requiresAuth": False,
                "headings": [{"level": 1, "text": "Sign In"}],
                "links": [],
                "buttons": [{"text": "Log In"}],
                "forms": [],
                "consoleErrors": [],
            },
            {
                "url": "http://localhost:5055/home",
                "path": "/home",
                "title": "Dashboard",
                "status": 200,
                "requiresAuth": True,
                "headings": [{"level": 1, "text": "Welcome Home"}],
                "links": [],
                "buttons": [],
                "forms": [],
                "consoleErrors": [],
            },
        ],
        "summary": "",
        "features": [],
        "stats": {"pagesVisited": 2, "durationSeconds": 1.5, "budgetHit": None},
        "error": None,
    }

    # Mock subprocess.Popen so we don't need real Chromium in this unit test
    class MockProc:
        def __init__(self):
            self.stdout = MagicMock()
            self.stdout.readline = MagicMock(side_effect=["PAGE 1/5 /login\n", "PAGE 2/5 /home\n", ""])
        def communicate(self, timeout=None):
            # Save raw data on communicate
            storage.write_json(run_id, "explore_raw.json", raw_data)
            return ("", "")

    monkeypatch.setattr(explorer.subprocess, "Popen", lambda *args, **kwargs: MockProc())

    app_map = explorer.run_explorer(run_id)

    assert isinstance(app_map, AppMap)
    assert len(app_map.pages) == 2
    assert app_map.pages[0].path == "/login"
    assert app_map.pages[1].path == "/home"
    assert app_map.summary != ""  # Filled by fake LLM
    assert len(app_map.features) > 0  # Filled by fake LLM

    # Verify stage and progress
    run = storage.get_run(run_id)
    assert run.stage == "exploring"
    assert run.progress is not None
    assert run.progress.total == 5


def test_run_explorer_handles_subprocess_failure_softly(run_fixture, monkeypatch):
    run_id = run_fixture

    # Simulate subprocess crash / no output file
    class FailingProc:
        def __init__(self):
            self.stdout = MagicMock()
            self.stdout.readline = MagicMock(return_value="")
        def communicate(self, timeout=None):
            return ("", "Fatal browser launch crash")

    monkeypatch.setattr(explorer.subprocess, "Popen", lambda *args, **kwargs: FailingProc())

    app_map = explorer.run_explorer(run_id)

    assert isinstance(app_map, AppMap)
    assert app_map.pages == []
    assert "Explorer produced no output" in str(app_map.error)
