"""Comprehensive tests for Task A2: Deep Explorer state-graph exploration."""

import json
from unittest.mock import MagicMock
import pytest

from kawach.agents.explorer.agent import run_explorer, _extract_journeys_from_edges
import kawach.agents.explorer.agent as explorer_agent
from kawach.core.config import settings
from kawach.schemas import ActionEdge, AppMap, Budgets, FrontierState, Journey, Run, RunInput, StateNode
from kawach.storage import artifacts as storage


@pytest.fixture
def deep_run_fixture(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")

    run_id = "test-deep-explore-001"
    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-23T00:00:00Z",
        targetUrl="http://localhost:5055",
        prompt="Deep exploratory test run",
        specRaw="S1: Navigation works\nS2: Deep flows work",
        username="qa@test.com",
        mode="manual",
        budgets=Budgets(maxPages=10, exploreSeconds=60),
    )
    storage.save_model(run_id, "input.json", run_input)
    storage.write_json(run_id, "secrets.json", {"password": "test_pass_deep"})

    run_obj = Run(
        runId=run_id,
        createdAt="2026-10-23T00:00:00Z",
        updatedAt="2026-10-23T00:00:00Z",
        stage="created",
        mode="manual",
        targetUrl="http://localhost:5055",
    )
    storage.save_model(run_id, "run.json", run_obj)
    return run_id


def test_journey_extraction_depth_gte_3():
    """Verify that _extract_journeys_from_edges only extracts paths with depth >= 3."""
    states = [
        StateNode(stateId="s0", url="http://localhost:5055/", depth=0, domSignature="sig0", uiState={}, signals={}),
        StateNode(stateId="s1", url="http://localhost:5055/products", depth=1, domSignature="sig1", uiState={}, signals={}),
        StateNode(stateId="s2", url="http://localhost:5055/products/42", depth=2, domSignature="sig2", uiState={"openModal": False}, signals={}),
        StateNode(stateId="s3", url="http://localhost:5055/products/42", depth=3, domSignature="sig3", uiState={"openModal": True}, signals={}),
        StateNode(stateId="s4", url="http://localhost:5055/cart", depth=4, domSignature="sig4", uiState={}, signals={}),
    ]

    edges = [
        ActionEdge(edgeId="e1", fromState="s0", toState="s1", action="click", locator="role=link[name='Products']", depth=1),
        ActionEdge(edgeId="e2", fromState="s1", toState="s2", action="click", locator="role=button[name='View']", depth=2),
        ActionEdge(edgeId="e3", fromState="s2", toState="s3", action="click", locator="role=button[name='Quick View']", depth=3),
        ActionEdge(edgeId="e4", fromState="s3", toState="s4", action="click", locator="role=button[name='Add To Cart']", depth=4),
    ]

    journeys = _extract_journeys_from_edges(edges, states)
    assert len(journeys) >= 1
    # Check that every extracted journey has depth >= 3
    for j in journeys:
        assert j.depth >= 3
        assert len(j.steps) >= 3
        assert j.journeyId.startswith("journey_")
        assert len(j.title) > 0


def test_deep_explorer_state_graph_and_signals(deep_run_fixture, monkeypatch):
    """Verify full AppMap graph structure with nodes, edges, journeys, unexplored frontier, and per-state signals."""
    run_id = deep_run_fixture

    mock_raw_appmap = {
        "baseUrl": "http://localhost:5055",
        "generatedAt": "2026-10-23T12:00:00Z",
        "login": {"attempted": True, "success": True, "url": "http://localhost:5055/login", "note": "OK"},
        "pages": [
            {
                "url": "http://localhost:5055/login",
                "path": "/login",
                "title": "Sign In",
                "status": 200,
                "requiresAuth": False,
                "headings": [{"level": 1, "text": "Login"}],
                "links": [],
                "buttons": [{"text": "Submit"}],
                "forms": [],
                "consoleErrors": [],
            },
            {
                "url": "http://localhost:5055/dashboard",
                "path": "/dashboard",
                "title": "Dashboard",
                "status": 200,
                "requiresAuth": True,
                "headings": [{"level": 1, "text": "Dashboard"}],
                "links": [],
                "buttons": [{"text": "Create Project"}],
                "forms": [],
                "consoleErrors": [],
            },
        ],
        "summary": "",
        "features": [],
        "stats": {
            "pagesVisited": 2,
            "durationSeconds": 8.5,
            "budgetHit": "discovery_rate",
            "statesDiscovered": 4,
            "transitionsExecuted": 5,
        },
        "states": [
            {
                "stateId": "s_root",
                "url": "http://localhost:5055/",
                "depth": 0,
                "domSignature": "dom_sig_0",
                "uiState": {"openModal": False, "activeTabs": [], "formValuesHash": "fv0"},
                "signals": {
                    "consoleErrors": [],
                    "httpErrors": [],
                    "failedRequests": [],
                    "accessibilityViolations": [
                        {"rule": "image-alt", "selector": "img#hero", "impact": "critical", "message": "Missing alt attribute"}
                    ],
                    "brokenLinks": [],
                },
            },
            {
                "stateId": "s_dash",
                "url": "http://localhost:5055/dashboard",
                "depth": 1,
                "domSignature": "dom_sig_1",
                "uiState": {"openModal": False, "activeTabs": ["Overview"], "formValuesHash": "fv1"},
                "signals": {
                    "consoleErrors": ["Warning: DevTools connected"],
                    "httpErrors": [],
                    "failedRequests": [],
                    "accessibilityViolations": [],
                    "brokenLinks": [],
                },
            },
            {
                "stateId": "s_modal",
                "url": "http://localhost:5055/dashboard",
                "depth": 2,
                "domSignature": "dom_sig_2",
                "uiState": {"openModal": True, "modalTitle": "New Project", "activeTabs": [], "formValuesHash": "fv2"},
                "signals": {
                    "consoleErrors": [],
                    "httpErrors": [],
                    "failedRequests": [],
                    "accessibilityViolations": [
                        {"rule": "label", "selector": "input#proj_name", "impact": "serious", "message": "Missing label"}
                    ],
                    "brokenLinks": [],
                },
            },
            {
                "stateId": "s_wizard_step2",
                "url": "http://localhost:5055/dashboard",
                "depth": 3,
                "domSignature": "dom_sig_3",
                "uiState": {"openModal": True, "modalTitle": "Configure Settings", "activeTabs": ["Permissions"], "formValuesHash": "fv3"},
                "signals": {
                    "consoleErrors": [],
                    "httpErrors": [{"status": 404, "url": "http://localhost:5055/api/missing-asset", "method": "GET"}],
                    "failedRequests": [],
                    "accessibilityViolations": [],
                    "brokenLinks": [],
                },
            },
        ],
        "edges": [
            {"edgeId": "e0", "fromState": "s_root", "toState": "s_dash", "action": "click", "locator": "role=link[name='Dashboard']", "value": None, "depth": 1},
            {"edgeId": "e1", "fromState": "s_dash", "toState": "s_modal", "action": "click", "locator": "role=button[name='Create Project']", "value": None, "depth": 2},
            {"edgeId": "e2", "fromState": "s_modal", "toState": "s_wizard_step2", "action": "click", "locator": "role=button[name='Next Step']", "value": None, "depth": 3},
        ],
        "journeys": [
            {
                "journeyId": "journey_1",
                "title": "http://localhost:5055/ -> click -> click -> click",
                "depth": 3,
                "steps": [
                    "click [role=link[name='Dashboard']]",
                    "click [role=button[name='Create Project']]",
                    "click [role=button[name='Next Step']]",
                ],
            }
        ],
        "unexploredFrontier": [
            {
                "stateId": "s_dash",
                "url": "http://localhost:5055/dashboard",
                "depth": 2,
                "reason": "discovery_rate_threshold",
            },
            {
                "stateId": "s_modal",
                "url": "http://localhost:5055/dashboard",
                "depth": 3,
                "reason": "stuck_loop_detected",
            },
        ],
        "error": None,
    }

    class MockDeepProc:
        def __init__(self):
            self.stdout = MagicMock()
            self.stdout.readline = MagicMock(
                side_effect=[
                    "STATE s_root depth=0 http://localhost:5055/\n",
                    "PAGE 1/10 /login\n",
                    "ACTION [L1] click on role=link[name='Dashboard']\n",
                    "STATE s_dash depth=1 http://localhost:5055/dashboard\n",
                    "PAGE 2/10 /dashboard\n",
                    "ACTION [L2] click on role=button[name='Create Project']\n",
                    "STATE s_modal depth=2 http://localhost:5055/dashboard\n",
                    "ACTION [L3] click on role=button[name='Next Step']\n",
                    "STATE s_wizard_step2 depth=3 http://localhost:5055/dashboard\n",
                    "",
                ]
            )

        def communicate(self, timeout=None):
            storage.write_json(run_id, "explore_raw.json", mock_raw_appmap)
            return ("", "")

    monkeypatch.setattr(explorer_agent.subprocess, "Popen", lambda *args, **kwargs: MockDeepProc())

    app_map = run_explorer(run_id)

    # 1. Verify schema model validation
    assert isinstance(app_map, AppMap)
    assert app_map.stats.budgetHit == "discovery_rate"
    assert app_map.stats.statesDiscovered == 4
    assert app_map.stats.transitionsExecuted == 5

    # 2. Verify State Nodes and Depth Tracking (L0, L1, L2, L3)
    assert len(app_map.states) == 4
    depths = [s.depth for s in app_map.states]
    assert depths == [0, 1, 2, 3]

    # Verify State Fingerprints and UI State
    modal_state = next(s for s in app_map.states if s.stateId == "s_modal")
    assert modal_state.uiState.get("openModal") is True
    assert modal_state.uiState.get("modalTitle") == "New Project"

    # 3. Verify Per-State Signals (a11y, consoleErrors, httpErrors)
    root_state = next(s for s in app_map.states if s.stateId == "s_root")
    assert len(root_state.signals.get("accessibilityViolations", [])) == 1
    assert root_state.signals["accessibilityViolations"][0]["rule"] == "image-alt"

    step2_state = next(s for s in app_map.states if s.stateId == "s_wizard_step2")
    assert len(step2_state.signals.get("httpErrors", [])) == 1
    assert step2_state.signals["httpErrors"][0]["status"] == 404

    # 4. Verify Action Edges with locators and depth
    assert len(app_map.edges) == 3
    assert app_map.edges[0].action == "click"
    assert app_map.edges[0].depth == 1
    assert app_map.edges[2].depth == 3

    # 5. Verify Deep Journeys (depth >= 3)
    assert len(app_map.journeys) == 1
    journey = app_map.journeys[0]
    assert journey.depth == 3
    assert len(journey.steps) == 3
    assert "role=button[name='Next Step']" in journey.steps[2]

    # 6. Verify Unexplored Frontier with reasons
    assert len(app_map.unexploredFrontier) == 2
    frontier_reasons = {f.reason for f in app_map.unexploredFrontier}
    assert "discovery_rate_threshold" in frontier_reasons
    assert "stuck_loop_detected" in frontier_reasons


def test_fixed_action_set_validation():
    """Verify that only the fixed action set is permitted on ActionEdge."""
    valid_actions = ["click", "fill", "select", "press", "navigate", "back", "refresh", "wait"]
    for act in valid_actions:
        edge = ActionEdge(
            edgeId=f"e_{act}",
            fromState="s0",
            toState="s1",
            action=act,
            locator="role=button",
            depth=1,
        )
        assert edge.action == act
