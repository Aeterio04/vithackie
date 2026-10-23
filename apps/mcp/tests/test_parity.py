"""Parity verification tests between MCP Tool Registry, OpenAPI 3.1.0 schema, and Use Cases."""

import json
from pathlib import Path
from kawach_mcp.tools import TOOL_REGISTRY

OPENAPI_PATH = Path("packages/contracts/openapi.json")
USE_CASES_PATH = Path("docs/USE_CASES.md")

# Canonical parity mapping:
# tool_name -> (http_method, openapi_path, required_scope, use_case_id)
CANONICAL_TOOL_PARITY_MAP = {
    "get_server_status": ("GET", "/api/v1/auth/me", None, "UC-11"),
    "list_projects": ("GET", "/api/v1/projects", "runs:read", "UC-01"),
    "get_project": ("GET", "/api/v1/projects/{project_id}", "runs:read", "UC-01"),
    "list_runs": ("GET", "/api/v1/runs", "runs:read", "UC-01"),
    "get_run_status": ("GET", "/api/v1/runs/{run_id}", "runs:read", "UC-02"),
    "get_catalog": ("GET", "/api/v1/runs/{run_id}/catalog", "runs:read", "UC-03"),
    "get_app_map_summary": ("GET", "/api/v1/runs/{run_id}/app-map", "runs:read", "UC-01"),
    "get_results": ("GET", "/api/v1/runs/{run_id}/results", "runs:read", "UC-02"),
    "list_failures": ("GET", "/api/v1/runs/{run_id}/bugs", "runs:read", "UC-02"),
    "get_bug": ("GET", "/api/v1/bugs/{bug_id}", "runs:read", "UC-02"),
    "list_saved_tests": ("GET", "/api/v1/projects/{project_id}/saved-tests", "tests:read", "UC-06"),
    "list_commits": ("GET", "/api/v1/projects/{project_id}/commits", "tests:read", "UC-04"),
    "get_failure_analysis": ("GET", "/api/v1/projects/{project_id}/commits/{commit_id}/analysis", "tests:read", "UC-08"),
    "get_fix_suggestion": ("GET", "/api/v1/projects/{project_id}/commits/{commit_id}/suggest-fix", "runs:read", "UC-09"),
    "get_report": ("GET", "/api/v1/runs/{run_id}/report", "runs:read", "UC-02"),
    "get_coverage_matrix": ("GET", "/api/v1/runs/{run_id}/catalog", "runs:read", "UC-03"),
    "start_run": ("POST", "/api/v1/runs", "runs:write", "UC-01"),
    "approve_catalog": ("POST", "/api/v1/runs/{run_id}/execute", "runs:write", "UC-03"),
    "run_regression": ("POST", "/api/v1/projects/{project_id}/regression-runs", "runs:write", "UC-04"),
    "wait_for_run": ("GET", "/api/v1/runs/{run_id}", "runs:read", "UC-02"),
    "save_test": ("POST", "/api/v1/projects/{project_id}/saved-tests", "tests:write", "UC-05"),
    "request_fix_suggestion": ("POST", "/api/v1/projects/{project_id}/commits/{commit_id}/suggest-fix", "fixes:apply", "UC-09"),
    "apply_fix_as_pr": ("POST", "/api/v1/projects/{project_id}/commits/{commit_id}/auto-fix", "fixes:apply", "UC-10"),
}


def test_tool_registry_complete_parity_with_openapi():
    """Verify that every tool in TOOL_REGISTRY maps to an exact route and method in openapi.json."""
    assert OPENAPI_PATH.is_file(), f"OpenAPI contract missing at {OPENAPI_PATH}"
    openapi = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = openapi.get("paths", {})

    registered_tool_names = {t.name for t in TOOL_REGISTRY}
    mapped_tool_names = set(CANONICAL_TOOL_PARITY_MAP.keys())

    # 1. Parity check: all registered tools are mapped
    assert registered_tool_names == mapped_tool_names, (
        f"Mismatch between registered tools and parity map: {registered_tool_names ^ mapped_tool_names}"
    )

    # 2. Check each tool's path, method, and scope against OpenAPI
    for tool in TOOL_REGISTRY:
        method, path, scope, use_case_id = CANONICAL_TOOL_PARITY_MAP[tool.name]

        # Assert route exists in OpenAPI
        assert path in paths, f"Tool '{tool.name}' targets OpenAPI route '{path}' which does not exist in openapi.json!"

        # Assert HTTP method exists on that path
        assert method.lower() in paths[path], f"Tool '{tool.name}' targets {method} on '{path}', but method is missing in OpenAPI!"

        # Assert scope matches
        assert tool.required_scope == scope, (
            f"Scope mismatch for tool '{tool.name}': TOOL_REGISTRY has '{tool.required_scope}', parity requires '{scope}'"
        )


def test_all_tools_map_to_canonical_use_cases():
    """Verify that every tool's mapped use-case ID is documented in docs/USE_CASES.md."""
    assert USE_CASES_PATH.is_file(), f"USE_CASES.md missing at {USE_CASES_PATH}"
    use_cases_text = USE_CASES_PATH.read_text(encoding="utf-8")

    for tool_name, (_, _, _, use_case_id) in CANONICAL_TOOL_PARITY_MAP.items():
        assert use_case_id in use_cases_text, (
            f"Tool '{tool_name}' maps to use case '{use_case_id}', but '{use_case_id}' is not documented in {USE_CASES_PATH}!"
        )
