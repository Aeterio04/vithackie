"""Generate machine-readable coverage.json mapping every endpoint and agentic capability to frontend UI."""

import json
from pathlib import Path

REPO_ROOT = Path("c:/projects/aiqa")
INVENTORY_PATH = REPO_ROOT / "docs" / "frontend-audit" / "endpoint_inventory.json"
OUTPUT_PATH = REPO_ROOT / "docs" / "frontend-audit" / "coverage.json"

with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
    endpoints = json.load(f)

# Comprehensive mapping rules based on frontend source inspection
# Statuses: COMPLETE, PARTIAL, MOCKED, STUB-ONLY, MISSING, N/A-BACKEND-NOT-READY

coverage_records = []

for ep in endpoints:
    method = ep["method"]
    path = ep["path"]
    status_code = ep.get("status_code")
    backend_status = "501" if status_code == 501 else ("real" if status_code and status_code < 500 else f"HTTP_{status_code}")
    
    frontend_status = "MISSING"
    frontend_files = []
    missing_details = ""
    priority = "P1"

    # 1. Auth endpoints
    if path == "/api/v1/auth/login":
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/features/auth/components/LoginForm.tsx", "apps/web/src/features/auth/api.ts"]
        missing_details = "None. Login form handles loading, error, success, and sets session cookies."
        priority = "P0"
    elif path == "/api/v1/auth/register":
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/features/auth/components/RegisterForm.tsx", "apps/web/src/features/auth/api.ts"]
        missing_details = "None. Registration form handles validation, loading, error, and redirect."
        priority = "P0"
    elif path == "/api/v1/auth/logout":
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/shared/lib/api/config.ts", "apps/web/src/shared/layout/Navbar.tsx"]
        missing_details = "Navbar clears local state and cookies, but does not explicitly trigger POST /api/v1/auth/logout."
        priority = "P1"
    elif path == "/api/v1/auth/me":
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/shared/lib/api/hooks.ts:43", "apps/web/src/shared/lib/api/config.ts:13"]
        missing_details = "None. Hook useAuthMe queries endpoint and populates user session store."
        priority = "P0"
    elif path == "/api/v1/auth/refresh":
        frontend_status = "MISSING"
        frontend_files = []
        missing_details = "Client has no silent token refresh interceptor. 401 triggers hard redirect to /login."
        priority = "P1"
    elif path.startswith("/api/v1/auth/tokens"):
        frontend_status = "MISSING"
        frontend_files = []
        missing_details = "No UI exists to create, list, view prefix, or revoke API tokens (kw_...)."
        priority = "P1"

    # 2. System & Config
    elif path == "/api/v1/health":
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/shared/lib/api/hooks.ts:17", "apps/web/src/features/runs/components/StartTestForm.tsx"]
        missing_details = "Queried during preflight in StartTestForm, but no dedicated system health indicator or cockpit telemetry status badge."
        priority = "P2"
    elif path == "/api/v1/config/defaults":
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/shared/lib/api/hooks.ts:13", "apps/web/src/features/runs/components/StartTestForm.tsx"]
        missing_details = "None. StartTestForm loads default budgets and mode."
        priority = "P1"
    elif path == "/api/v1/stats":
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/shared/lib/api/config.ts:18"]
        missing_details = "Endpoint configured in API_ENDPOINTS, but no component queries or displays global system stats."
        priority = "P2"
    elif path == "/api/v1/targets/check":
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/shared/lib/api/hooks.ts:15", "apps/web/src/features/runs/components/StartTestForm.tsx"]
        missing_details = "None. Interactive preflight validation check against targetUrl."
        priority = "P0"

    # 3. Projects
    elif path == "/api/v1/projects" and method == "GET":
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/features/projects/components/ProjectList.tsx", "apps/web/src/features/projects/api.ts:35"]
        missing_details = "None. ProjectList renders projects cards with loading and empty states."
        priority = "P0"
    elif path == "/api/v1/projects" and method == "POST":
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/features/projects/components/NewProjectForm.tsx", "apps/web/src/features/projects/api.ts:43"]
        missing_details = "None. NewProjectForm creates project with name, targetUrl, and budgets."
        priority = "P0"
    elif path == "/api/v1/projects/{project_id}" and method == "GET":
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/app/(app)/projects/[projectId]/page.tsx", "apps/web/src/features/projects/api.ts:39"]
        missing_details = "Loads project overview, but falls back to hardcoded demo data when endpoint fails. Links to non-existent /projects/:id/runs/:runId routes."
        priority = "P0"
    elif path == "/api/v1/projects/{project_id}" and method == "PUT":
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/features/projects/components/ProjectSettings.tsx", "apps/web/src/features/projects/api.ts:51"]
        missing_details = "Form exists in ProjectSettings, but backend returns 500 (AttributeError on ProjectRepository)."
        priority = "P0"
    elif path == "/api/v1/projects/{project_id}" and method == "DELETE":
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/features/projects/components/ProjectSettings.tsx", "apps/web/src/features/projects/api.ts:47"]
        missing_details = "Archive project action wired in settings UI, but backend returns 500."
        priority = "P1"
    elif path == "/api/v1/projects/{project_id}/credentials":
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/features/projects/components/ProjectSettings.tsx"]
        missing_details = "UI form fields for credentials exist in ProjectSettings, but are combined into a single submit and password cannot be read."
        priority = "P1"

    # 4. Saved Tests
    elif "/saved-tests" in path:
        if method == "GET":
            frontend_status = "STUB-ONLY"
            frontend_files = ["apps/web/src/app/(app)/projects/[projectId]/tests/page.tsx", "apps/web/src/features/library/components/SavedTestEmptyState.tsx"]
            missing_details = "Renders SavedTestEmptyState placeholder. No real list, filtering, or inspection of saved test library."
            priority = "P0"
        elif method == "POST":
            frontend_status = "MISSING"
            frontend_files = []
            missing_details = "No 'Save to Library' button or modal in ResultsView or ReportView to save verified test scripts."
            priority = "P0"
        elif method == "DELETE":
            frontend_status = "MISSING"
            frontend_files = []
            missing_details = "No delete action in frontend for saved tests."
            priority = "P1"

    # 5. Commits & Auto-Fix Loop
    elif "/commits" in path:
        if method == "GET" and "{commit_id}" not in path:
            frontend_status = "STUB-ONLY"
            frontend_files = ["apps/web/src/app/(app)/projects/[projectId]/commits/page.tsx", "apps/web/src/features/commits/components/CommitEmptyState.tsx"]
            missing_details = "Renders CommitEmptyState placeholder. No commit list, diff view, or regression run history."
            priority = "P0"
        elif method == "POST" and "{commit_id}" not in path:
            frontend_status = "MISSING"
            frontend_files = []
            missing_details = "No manual 'Simulate Commit' or 'Trigger Regression' button or form in frontend."
            priority = "P0"
        elif "analysis" in path:
            frontend_status = "MISSING"
            frontend_files = []
            missing_details = "No failure localization panel showing suspect files, line ranges, confidence scores, or AST correlation."
            priority = "P0"
        elif "suggest-fix" in path:
            frontend_status = "MISSING"
            frontend_files = []
            missing_details = "No unified diff patch viewer showing proposed code fix."
            priority = "P0"
        elif "auto-fix" in path:
            frontend_status = "MISSING"
            frontend_files = []
            missing_details = "No 'Create Pull Request' or 'Auto-Fix PR' action button or status tracker in UI."
            priority = "P0"

    # 6. Webhooks
    elif path == "/api/v1/webhooks/github":
        frontend_status = "MISSING"
        frontend_files = ["apps/web/src/features/projects/components/ProjectSettings.tsx"]
        missing_details = "ProjectSettings displays static webhook URL and secret copy box, but has no webhook delivery log or event monitor."
        priority = "P1"

    # 7. Runs, Catalog, Execution, Bugs, Reports
    elif path == "/api/v1/runs" and method == "GET":
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/shared/lib/api/hooks.ts:11", "apps/web/src/app/(app)/projects/[projectId]/page.tsx"]
        missing_details = "Queried by useRuns, displays recent run cards with mode, stage, and bug counts."
        priority = "P0"
    elif path == "/runs" and method == "POST":
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/features/runs/components/StartTestForm.tsx", "apps/web/src/shared/lib/api/hooks.ts:27"]
        missing_details = "Start form triggers run with spec, URL, budgets, and mode."
        priority = "P0"
    elif "/app-map" in path:
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/features/catalog/components/CatalogView.tsx:603"]
        missing_details = "BROKEN: CatalogView expects appMap.root_node (legacy tree). Backend returns states, edges, journeys, frontier. Renders empty state permanently."
        priority = "P0"
    elif "/catalog" in path:
        if method == "GET":
            frontend_status = "PARTIAL"
            frontend_files = ["apps/web/src/features/catalog/components/CatalogView.tsx"]
            missing_details = "Displays table, but expects legacy fields (expected_result, priority, spec_item_ids). Completely ignores depth, edgeTags, riskScore, and coverageRef."
            priority = "P0"
        elif method in ("POST", "PUT", "PATCH"):
            frontend_status = "PARTIAL"
            frontend_files = ["apps/web/src/features/catalog/components/CatalogView.tsx:618"]
            missing_details = "Supports approve selected / approve all, but edit drawer saves to legacy structure."
            priority = "P0"
    elif "/review" in path:
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/features/catalog/components/CatalogView.tsx:238", "apps/web/src/shared/lib/api/hooks.ts:46"]
        missing_details = "None. Submits ReviewDecision list to advance run from awaiting_review to executing."
        priority = "P0"
    elif "/execution" in path or (path.endswith("/runs/{run_id}") and method == "GET"):
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/features/runs/components/ExecutionCockpit.tsx"]
        missing_details = "Displays workers, budget meter, and log stream, but lacks per-step assertions, checkpoint failure tags, and depth progression."
        priority = "P0"
    elif "/stream" in path:
        frontend_status = "PARTIAL"
        frontend_files = ["apps/web/src/shared/lib/api/config.ts:35", "apps/web/hooks/useRunStream.ts"]
        missing_details = "BROKEN SSE URL: config.ts requests /api/runs/:id/stream which returns 404. Falls back to polling /events."
        priority = "P0"
    elif "/bugs" in path:
        if method == "GET" and "{bug_id}" not in path:
            frontend_status = "COMPLETE"
            frontend_files = ["apps/web/src/features/results/components/ResultsView.tsx"]
            missing_details = "Displays bug list filtered by confirmed, flaky, not reproduced, and suspected."
            priority = "P0"
        elif "{bug_id}" in path:
            frontend_status = "PARTIAL"
            frontend_files = ["apps/web/src/features/results/components/BugDetailView.tsx"]
            missing_details = "Renders 3x replay pips and details, but uses fallback synthetic script instead of backend reproductionScript, and lacks failingPath depth."
            priority = "P0"
    elif "/report" in path:
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/features/reports/components/ReportView.tsx"]
        missing_details = "Renders executive KPI summary, verified defects, not reproduced reference list, and export buttons."
        priority = "P0"
    elif "/export" in path:
        frontend_status = "COMPLETE"
        frontend_files = ["apps/web/src/features/reports/components/ReportView.tsx:23", "apps/web/src/shared/lib/api/config.ts:60"]
        missing_details = "Triggers file download for standalone Playwright zip and report formats (json/html/csv)."
        priority = "P1"
    else:
        # Legacy routes and remaining helpers
        frontend_status = "PARTIAL" if "runs" in path else "MISSING"
        frontend_files = ["apps/web/src/shared/lib/api/config.ts"]
        missing_details = "Auxiliary or legacy duplicate route."
        priority = "P2"

    record = {
        "method": method,
        "path": path,
        "operationId": ep.get("operationId"),
        "tags": ep.get("tags", []),
        "backend_status": backend_status,
        "status_code": status_code,
        "frontend_status": frontend_status,
        "frontend_files": frontend_files,
        "missing_details": missing_details,
        "priority": priority,
    }
    coverage_records.append(record)

# Agentic Specific Capabilities
agentic_capabilities = [
    {
        "capability": "AppMap State Graph Visualizer",
        "description": "Visual rendering of StateNode topology, ActionEdge transitions, depth levels (L0-L3+), and FrontierState priority queue.",
        "backend_status": "real",
        "frontend_status": "PARTIAL",
        "frontend_files": ["apps/web/src/features/catalog/components/CatalogView.tsx:603"],
        "missing_details": "Broken contract: UI checks appMap.root_node (legacy). Backend returns states[], edges[], journeys[], unexploredFrontier[]. Renders empty state permanently.",
        "priority": "P0"
    },
    {
        "capability": "Multi-Level Catalog with Edge Tags & Risk Scoring",
        "description": "Test catalog displaying depth, 14-category edge tags, risk score (0.0-1.0), spec requirement linkage, and per-step assertions.",
        "backend_status": "real",
        "frontend_status": "PARTIAL",
        "frontend_files": ["apps/web/src/features/catalog/components/CatalogView.tsx:258"],
        "missing_details": "Catalog table displays legacy columns (priority, expected_result). Depth, edgeTags, riskScore, and per-step assertions are omitted.",
        "priority": "P0"
    },
    {
        "capability": "Requirements Coverage Matrix",
        "description": "Interactive matrix displaying spec items (S1..Sn) x depth levels (L0-L3) x edge categories with 100% coverage indicators.",
        "backend_status": "real",
        "frontend_status": "MISSING",
        "frontend_files": [],
        "missing_details": "No UI component renders the CoverageMatrix data generated by Planner agent.",
        "priority": "P0"
    },
    {
        "capability": "Live Exploration & Execution Cockpit with Checkpoint Evidence",
        "description": "Real-time execution dashboard showing active Playwright workers, live logs, budget consumption, and checkpoint failure indicators.",
        "backend_status": "real",
        "frontend_status": "PARTIAL",
        "frontend_files": ["apps/web/src/features/runs/components/ExecutionCockpit.tsx"],
        "missing_details": "Displays worker cards and logs, but SSE live stream URL is broken (404), falling back to polling. Checkpoint failure context (failed at step k of n) is omitted.",
        "priority": "P0"
    },
    {
        "capability": "Deterministic 3x Replay Bug Prover & Replay Script Viewer",
        "description": "Detailed defect proof showing 3/3 confirmed status, minimal failing path, depth, and real standalone Playwright reproduction script.",
        "backend_status": "real",
        "frontend_status": "PARTIAL",
        "frontend_files": ["apps/web/src/features/results/components/BugDetailView.tsx"],
        "missing_details": "Renders 3x pips, but generates a fallback synthetic reproduction script instead of rendering backend reproductionScript. Omits failingPath and checkpoint.",
        "priority": "P0"
    },
    {
        "capability": "Saved Test Library Manager",
        "description": "Management interface for project regression test library, displaying SHA-256 hashes, indexed touchpoints, and filter by tags/spec.",
        "backend_status": "real",
        "frontend_status": "STUB-ONLY",
        "frontend_files": ["apps/web/src/app/(app)/projects/[projectId]/tests/page.tsx", "apps/web/src/features/library/components/SavedTestEmptyState.tsx"],
        "missing_details": "Displays SavedTestEmptyState placeholder only. No list, delete, or run trigger.",
        "priority": "P0"
    },
    {
        "capability": "Commit Regression History & Trigger",
        "description": "Tracked commit events, commit diff inspect, diff-aware test selection breakdown, and manual 'Run Regression' trigger.",
        "backend_status": "real",
        "frontend_status": "STUB-ONLY",
        "frontend_files": ["apps/web/src/app/(app)/projects/[projectId]/commits/page.tsx", "apps/web/src/features/commits/components/CommitEmptyState.tsx"],
        "missing_details": "Displays CommitEmptyState placeholder only. No commit list, diff view, or regression run history.",
        "priority": "P0"
    },
    {
        "capability": "Failure Localization Panel",
        "description": "Ranked suspect culprit files with line ranges, confidence percentage, failure evidence correlation, and explanation.",
        "backend_status": "real",
        "frontend_status": "MISSING",
        "frontend_files": [],
        "missing_details": "No UI component renders FailureAnalysisRead data.",
        "priority": "P0"
    },
    {
        "capability": "Fix Suggestion Diff Viewer & Auto-Fix PR Action",
        "description": "Unified git diff patch viewer with 'validated' badge, small-fix safety boundary label, and one-click 'Open PR' button.",
        "backend_status": "real",
        "frontend_status": "MISSING",
        "frontend_files": [],
        "missing_details": "No UI component renders FixSuggestionRead or triggers auto-fix PR creation.",
        "priority": "P0"
    },
    {
        "capability": "Personal Scoped API Token Manager",
        "description": "Interface to create, list, view token prefix, copy plaintext secret once, and revoke CLI/MCP API tokens.",
        "backend_status": "real",
        "frontend_status": "MISSING",
        "frontend_files": [],
        "missing_details": "No API token settings page exists under project or user profile settings.",
        "priority": "P1"
    },
    {
        "capability": "Audit Log Telemetry Viewer",
        "description": "Searchable audit trail tracking all actions, user identities, and client front doors (web, github, mcp).",
        "backend_status": "real",
        "frontend_status": "MISSING",
        "frontend_files": [],
        "missing_details": "No audit log view exists in the frontend.",
        "priority": "P2"
    }
]

output_data = {
    "summary": {
        "total_endpoints": len(coverage_records),
        "total_agentic_capabilities": len(agentic_capabilities),
        "frontend_classification_counts": {},
        "priority_counts": {}
    },
    "endpoints": coverage_records,
    "agentic_capabilities": agentic_capabilities,
}

for r in coverage_records:
    fs = r["frontend_status"]
    output_data["summary"]["frontend_classification_counts"][fs] = output_data["summary"]["frontend_classification_counts"].get(fs, 0) + 1
    p = r["priority"]
    output_data["summary"]["priority_counts"][p] = output_data["summary"]["priority_counts"].get(p, 0) + 1

with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
    json.dump(output_data, out, indent=2, ensure_ascii=False)

print("Coverage Data Generated Successfully:")
print("Endpoint Statuses:", output_data["summary"]["frontend_classification_counts"])
print("Priority Counts:", output_data["summary"]["priority_counts"])
