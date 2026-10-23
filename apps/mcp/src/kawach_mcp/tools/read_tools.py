"""Read-only MCP tools for inspecting projects, runs, AppMap, bugs, commits, and failure analysis."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import mcp.types as types
from pydantic import BaseModel, Field

from kawach_mcp.client import KawachAPIError, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.security import redact_secrets, truncate_text, wrap_untrusted_content
from kawach_mcp.tools.registry import register_tool

READ_ONLY_ANNOTATIONS = types.ToolAnnotations(read_only_hint=True, idempotent_hint=True)


# --- Pydantic Output Models ---

class ProjectSummary(BaseModel):
    id: str
    name: str
    target_url: str
    allowed_hosts: List[str] = Field(default_factory=list)


class ListProjectsResponse(BaseModel):
    projects: List[ProjectSummary]
    total: int


class ProjectDetailResponse(BaseModel):
    id: str
    name: str
    target_url: str
    allowed_hosts: List[str]
    depth_budget: int = 3
    breadth_budget: int = 50


class RunSummary(BaseModel):
    id: str
    project_id: Optional[str] = None
    target_url: str
    mode: str
    status: str
    stage: str
    current_progress: float = 0.0
    confirmed_bugs: int = 0
    flaky_bugs: int = 0


class ListRunsResponse(BaseModel):
    runs: List[RunSummary]
    total: int


class RunStatusResponse(BaseModel):
    run_id: str
    status: str
    stage: str
    current_progress: float
    confirmed_bugs: int = 0
    flaky_bugs: int = 0
    active_workers: int = 0
    checkpoint: Optional[str] = None
    sse_url: str


class TestCaseSummary(BaseModel):
    id: str
    name: str
    depth: int = 0
    risk_score: float = 0.0
    edge_tags: List[str] = Field(default_factory=list)
    archetype: Optional[str] = None


class CatalogResponse(BaseModel):
    run_id: str
    total_test_cases: int
    test_cases: List[TestCaseSummary]


class AppMapSummaryResponse(BaseModel):
    run_id: str
    total_states: int
    states_by_depth: Dict[str, int]
    total_edges: int
    journeys_count: int
    frontier_count: int


class CheckpointFailureLocation(BaseModel):
    failed_at_step: int
    total_steps: int
    depth: int
    state_fingerprint: Optional[str] = None


class TestResultSummary(BaseModel):
    test_id: str
    status: str
    duration_ms: float = 0.0
    checkpoint: Optional[CheckpointFailureLocation] = None
    error_message: Optional[str] = None


class ResultsResponse(BaseModel):
    run_id: str
    total_results: int
    passed_count: int
    failed_count: int
    results: List[TestResultSummary]


class BugSummary(BaseModel):
    id: str
    title: str
    verification_status: str  # confirmed | flaky | not_reproduced
    replay_count: int = 3
    depth: int = 0
    failing_step: Optional[int] = None
    minimal_repro_path: Optional[str] = None
    assertion_snippet: Optional[str] = None


class ListFailuresResponse(BaseModel):
    run_id: str
    total_failures: int
    bugs: List[BugSummary]


class BugDetailResponse(BaseModel):
    id: str
    title: str
    verification_status: str
    depth: int
    reproduction_script_uri: str
    error_message: Optional[str] = None
    evidence_artifacts: List[Dict[str, str]] = Field(default_factory=list)


class SavedTestSummary(BaseModel):
    id: str
    name: str
    tags: List[str] = Field(default_factory=list)
    coverage_touchpoints: List[str] = Field(default_factory=list)
    script_uri: str


class ListSavedTestsResponse(BaseModel):
    project_id: str
    saved_tests: List[SavedTestSummary]
    total: int


class CommitSummary(BaseModel):
    id: str
    commit_sha: str
    branch: Optional[str] = None
    regression_run_id: Optional[str] = None
    verified_defect_count: int = 0


class ListCommitsResponse(BaseModel):
    project_id: str
    commits: List[CommitSummary]
    total: int


class SuspectFileCandidate(BaseModel):
    path: str
    repo_relative_path: str
    component: Optional[str] = None
    confidence_pct: float
    line_range: Optional[List[int]] = None
    reason: str


class FailureAnalysisResponse(BaseModel):
    project_id: str
    commit_id: str
    culprit_candidates: List[SuspectFileCandidate]
    explanation: str


class FixSuggestionResponse(BaseModel):
    project_id: str
    commit_id: str
    risk_level: str  # small_fix | needs_engineer | blocked
    validation_status: str  # validated | failed | pending
    files_touched: List[str] = Field(default_factory=list)
    lines_touched: int = 0
    diff_patch: str


class ReportResponse(BaseModel):
    run_id: str
    title: str
    summary_markdown: str
    kpis: Dict[str, Any] = Field(default_factory=dict)
    download_url: str


class CoverageMatrixResponse(BaseModel):
    run_id: str
    edge_categories: List[str] = Field(default_factory=list)
    depth_tiers: Dict[str, int] = Field(default_factory=dict)
    coverage_score: float = 0.0


# --- Read Tools Implementations ---

@register_tool("list_projects", "List Kawach QA projects with IDs, names, and target URLs.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_list_projects(client: KawachClient, settings: Settings):
    async def list_projects(limit: int = 50, offset: int = 0) -> ListProjectsResponse:
        raw = await client.get("/api/v1/projects", params={"limit": limit, "offset": offset})
        items = raw if isinstance(raw, list) else raw.get("items", [])
        total = len(items) if isinstance(raw, list) else raw.get("total", len(items))
        projects = [
            ProjectSummary(
                id=str(p.get("id")),
                name=p.get("name", "Unnamed Project"),
                target_url=p.get("target_url", p.get("targetUrl", "")),
                allowed_hosts=p.get("allowed_hosts", p.get("allowedHosts", [])),
            )
            for p in items
        ]
        return ListProjectsResponse(projects=projects, total=total)
    return list_projects


@register_tool("get_project", "Get details and test budget configuration for a specific project.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_get_project(client: KawachClient, settings: Settings):
    async def get_project(project_id: str) -> ProjectDetailResponse:
        p = await client.get(f"/api/v1/projects/{project_id}")
        return ProjectDetailResponse(
            id=str(p.get("id")),
            name=p.get("name", "Project"),
            target_url=p.get("target_url", p.get("targetUrl", "")),
            allowed_hosts=p.get("allowed_hosts", p.get("allowedHosts", [])),
            depth_budget=p.get("depth_budget", 3),
            breadth_budget=p.get("breadth_budget", 50),
        )
    return get_project


@register_tool("list_runs", "List exploratory and regression runs filtered by project or status.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_list_runs(client: KawachClient, settings: Settings):
    async def list_runs(
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ListRunsResponse:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if project_id:
            params["project_id"] = project_id
        if status:
            params["status"] = status
        raw = await client.get("/api/v1/runs", params=params)
        items = raw if isinstance(raw, list) else raw.get("items", [])
        total = len(items) if isinstance(raw, list) else raw.get("total", len(items))
        runs = [
            RunSummary(
                id=str(r.get("id")),
                project_id=r.get("project_id"),
                target_url=r.get("target_url", r.get("targetUrl", "")),
                mode=r.get("mode", "autonomous"),
                status=r.get("status", "unknown"),
                stage=r.get("stage", "init"),
                current_progress=float(r.get("current_progress", r.get("currentProgress", 0.0))),
                confirmed_bugs=r.get("confirmed_bugs", r.get("confirmedBugs", 0)),
                flaky_bugs=r.get("flaky_bugs", r.get("flakyBugs", 0)),
            )
            for r in items
        ]
        return ListRunsResponse(runs=runs, total=total)
    return list_runs


@register_tool("get_run_status", "Poll real-time execution stage, progress percentage, and bug counts.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_get_run_status(client: KawachClient, settings: Settings):
    async def get_run_status(run_id: str) -> RunStatusResponse:
        r = await client.get(f"/api/v1/runs/{run_id}")
        return RunStatusResponse(
            run_id=str(r.get("id")),
            status=r.get("status", "unknown"),
            stage=r.get("stage", "init"),
            current_progress=float(r.get("current_progress", r.get("currentProgress", 0.0))),
            confirmed_bugs=r.get("confirmed_bugs", r.get("confirmedBugs", 0)),
            flaky_bugs=r.get("flaky_bugs", r.get("flakyBugs", 0)),
            active_workers=r.get("active_workers", 0),
            checkpoint=r.get("checkpoint"),
            sse_url=f"{settings.clean_api_url}/api/v1/runs/{run_id}/stream",
        )
    return get_run_status


@register_tool("get_catalog", "Get planned test cases for a run with risk scores and edge tags.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_get_catalog(client: KawachClient, settings: Settings):
    async def get_catalog(run_id: str) -> CatalogResponse:
        raw = await client.get(f"/api/v1/runs/{run_id}/catalog")
        items = raw.get("test_cases", raw.get("testCases", [])) if isinstance(raw, dict) else raw
        cases = [
            TestCaseSummary(
                id=str(c.get("id")),
                name=c.get("name", "Test Case"),
                depth=c.get("depth", 0),
                risk_score=float(c.get("risk_score", c.get("riskScore", 0.0))),
                edge_tags=c.get("edge_tags", c.get("edgeTags", [])),
                archetype=c.get("archetype"),
            )
            for c in items
        ]
        return CatalogResponse(run_id=run_id, total_test_cases=len(cases), test_cases=cases)
    return get_catalog


@register_tool("get_app_map_summary", "Get compact summary of explored application state graph (depth tiers, journeys, frontier).", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_get_app_map_summary(client: KawachClient, settings: Settings):
    async def get_app_map_summary(run_id: str) -> AppMapSummaryResponse:
        raw = await client.get(f"/api/v1/runs/{run_id}/app-map")
        states = raw.get("states", []) if isinstance(raw, dict) else []
        edges = raw.get("edges", []) if isinstance(raw, dict) else []
        journeys = raw.get("journeys", []) if isinstance(raw, dict) else []
        frontier = raw.get("frontier", raw.get("frontier_states", [])) if isinstance(raw, dict) else []

        by_depth: Dict[str, int] = {}
        for s in states:
            d = s.get("depth", 0)
            key = f"L{d}" if d < 3 else "L3+"
            by_depth[key] = by_depth.get(key, 0) + 1

        return AppMapSummaryResponse(
            run_id=run_id,
            total_states=len(states),
            states_by_depth=by_depth,
            total_edges=len(edges),
            journeys_count=len(journeys),
            frontier_count=len(frontier),
        )
    return get_app_map_summary


@register_tool("get_results", "Get test execution results and outcomes with checkpoint failure locations.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_get_results(client: KawachClient, settings: Settings):
    async def get_results(run_id: str) -> ResultsResponse:
        raw = await client.get(f"/api/v1/runs/{run_id}/results")
        items = raw if isinstance(raw, list) else raw.get("results", [])
        results: List[TestResultSummary] = []
        passed = 0
        failed = 0

        for r in items:
            status = r.get("status", "unknown")
            if status == "passed":
                passed += 1
            elif status in ("failed", "error"):
                failed += 1

            ckpt = None
            if r.get("failed_step") is not None or r.get("failedStep") is not None:
                step_idx = r.get("failed_step", r.get("failedStep", 0))
                total_s = r.get("total_steps", r.get("totalSteps", 1))
                d = r.get("depth", 0)
                ckpt = CheckpointFailureLocation(failed_at_step=step_idx, total_steps=total_s, depth=d)

            err_msg = r.get("error_message", r.get("errorMessage"))
            if err_msg:
                err_msg = wrap_untrusted_content(err_msg, content_type="assertion_error", max_chars=500)

            results.append(
                TestResultSummary(
                    test_id=str(r.get("test_id", r.get("testId", r.get("id")))),
                    status=status,
                    duration_ms=float(r.get("duration_ms", r.get("durationMs", 0.0))),
                    checkpoint=ckpt,
                    error_message=err_msg,
                )
            )

        return ResultsResponse(
            run_id=run_id,
            total_results=len(results),
            passed_count=passed,
            failed_count=failed,
            results=results,
        )
    return get_results


@register_tool("list_failures", "List confirmed and flaky bugs with depth and minimal repro path.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_list_failures(client: KawachClient, settings: Settings):
    async def list_failures(
        run_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> ListFailuresResponse:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        raw = await client.get(f"/api/v1/runs/{run_id}/bugs", params=params)
        items = raw if isinstance(raw, list) else raw.get("bugs", [])
        bugs: List[BugSummary] = []

        for b in items:
            assertion = b.get("assertion_message") or b.get("error_message") or b.get("errorMessage")
            if assertion:
                assertion = wrap_untrusted_content(assertion, content_type="bug_assertion", max_chars=400)

            bugs.append(
                BugSummary(
                    id=str(b.get("id")),
                    title=b.get("title", "Defect"),
                    verification_status=b.get("verification_status", b.get("status", "confirmed")),
                    replay_count=b.get("replay_count", 3),
                    depth=b.get("depth", 0),
                    failing_step=b.get("failing_step", b.get("failingStep")),
                    minimal_repro_path=b.get("failing_path", b.get("reproductionPath")),
                    assertion_snippet=assertion,
                )
            )

        return ListFailuresResponse(run_id=run_id, total_failures=len(bugs), bugs=bugs)
    return list_failures


@register_tool("get_bug", "Get defect evidence, step checkpoints, and repro script references.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_get_bug(client: KawachClient, settings: Settings):
    async def get_bug(bug_id: str) -> BugDetailResponse:
        b = await client.get(f"/api/v1/bugs/{bug_id}")
        err_msg = b.get("error_message", b.get("errorMessage"))
        if err_msg:
            err_msg = wrap_untrusted_content(err_msg, content_type="error_trace", max_chars=800)

        return BugDetailResponse(
            id=str(b.get("id")),
            title=b.get("title", "Defect"),
            verification_status=b.get("verification_status", b.get("status", "confirmed")),
            depth=b.get("depth", 0),
            reproduction_script_uri=f"kawach://runs/{b.get('run_id')}/bugs/{bug_id}/repro-script",
            error_message=err_msg,
            evidence_artifacts=b.get("evidence", []),
        )
    return get_bug


@register_tool("list_saved_tests", "List saved regression test suite for a project.", "tests:read", False, READ_ONLY_ANNOTATIONS)
def make_list_saved_tests(client: KawachClient, settings: Settings):
    async def list_saved_tests(
        project_id: str,
        tag: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ListSavedTestsResponse:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if tag:
            params["tag"] = tag
        raw = await client.get(f"/api/v1/projects/{project_id}/saved-tests", params=params)
        items = raw if isinstance(raw, list) else raw.get("items", [])
        total = len(items) if isinstance(raw, list) else raw.get("total", len(items))

        tests = [
            SavedTestSummary(
                id=str(t.get("id")),
                name=t.get("name", "Saved Test"),
                tags=t.get("tags", []),
                coverage_touchpoints=t.get("coverage_touchpoints", t.get("touchpoints", [])),
                script_uri=f"kawach://projects/{project_id}/saved-tests/{t.get('id')}/script",
            )
            for t in items
        ]
        return ListSavedTestsResponse(project_id=project_id, saved_tests=tests, total=total)
    return list_saved_tests


@register_tool("list_commits", "List tracked commit events and regression run results for a project.", "tests:read", False, READ_ONLY_ANNOTATIONS)
def make_list_commits(client: KawachClient, settings: Settings):
    async def list_commits(project_id: str, limit: int = 50, offset: int = 0) -> ListCommitsResponse:
        raw = await client.get(f"/api/v1/projects/{project_id}/commits", params={"limit": limit, "offset": offset})
        items = raw if isinstance(raw, list) else raw.get("items", [])
        total = len(items) if isinstance(raw, list) else raw.get("total", len(items))

        commits = [
            CommitSummary(
                id=str(c.get("id")),
                commit_sha=c.get("commit_sha", c.get("sha", "unknown")),
                branch=c.get("branch"),
                regression_run_id=c.get("run_id", c.get("regression_run_id")),
                verified_defect_count=c.get("verified_defects", c.get("defect_count", 0)),
            )
            for c in items
        ]
        return ListCommitsResponse(project_id=project_id, commits=commits, total=total)
    return list_commits


@register_tool("get_failure_analysis", "Get root-cause suspect candidate files with confidence, reasons, and line ranges for local IDE editing.", "tests:read", False, READ_ONLY_ANNOTATIONS)
def make_get_failure_analysis(client: KawachClient, settings: Settings):
    async def get_failure_analysis(project_id: str, commit_id: str) -> FailureAnalysisResponse:
        raw = await client.get(f"/api/v1/projects/{project_id}/commits/{commit_id}/analysis")
        candidates_raw = raw.get("culprit_candidates", raw.get("candidates", []))

        candidates = [
            SuspectFileCandidate(
                path=c.get("file_path", c.get("path", "")),
                repo_relative_path=c.get("file_path", c.get("path", "")),
                component=c.get("component"),
                confidence_pct=float(c.get("confidence", 0.0)) * (100.0 if float(c.get("confidence", 0.0)) <= 1.0 else 1.0),
                line_range=c.get("line_range"),
                reason=c.get("reason", "Suspect code path correlated with failing checkpoint"),
            )
            for c in candidates_raw
        ]

        explanation = raw.get("summary", raw.get("explanation", "Failure localized to recent commit changes."))
        return FailureAnalysisResponse(
            project_id=project_id,
            commit_id=commit_id,
            culprit_candidates=candidates,
            explanation=truncate_text(explanation, max_chars=1000),
        )
    return get_failure_analysis


@register_tool("get_fix_suggestion", "Inspect proposed fix unified diff patch, validation badge, and eligibility.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_get_fix_suggestion(client: KawachClient, settings: Settings):
    async def get_fix_suggestion(project_id: str, commit_id: str) -> FixSuggestionResponse:
        raw = await client.get(f"/api/v1/projects/{project_id}/commits/{commit_id}/suggest-fix")
        diff = raw.get("diff_patch", raw.get("patch", ""))
        safe_diff = wrap_untrusted_content(diff, content_type="unified_diff", max_chars=2500)

        return FixSuggestionResponse(
            project_id=project_id,
            commit_id=commit_id,
            risk_level=raw.get("risk_classification", raw.get("risk_level", "small_fix")),
            validation_status=raw.get("status", "validated"),
            files_touched=raw.get("files_touched", []),
            lines_touched=int(raw.get("lines_touched", len(diff.splitlines()) if diff else 0)),
            diff_patch=safe_diff,
        )
    return get_fix_suggestion


@register_tool("get_report", "Get executive report summary with coverage metrics and download links.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_get_report(client: KawachClient, settings: Settings):
    async def get_report(run_id: str) -> ReportResponse:
        raw = await client.get(f"/api/v1/runs/{run_id}/report")
        summary = raw.get("summary", raw.get("markdown", "Test run report generated."))
        return ReportResponse(
            run_id=run_id,
            title=raw.get("title", f"Run {run_id} Report"),
            summary_markdown=truncate_text(summary, max_chars=settings.max_response_chars),
            kpis=raw.get("kpis", {}),
            download_url=f"{settings.clean_api_url}/api/v1/runs/{run_id}/report",
        )
    return get_report


@register_tool("get_coverage_matrix", "Get 3D coverage matrix mapping test coverage across depth tiers and 14 edge categories.", "runs:read", False, READ_ONLY_ANNOTATIONS)
def make_get_coverage_matrix(client: KawachClient, settings: Settings):
    async def get_coverage_matrix(run_id: str) -> CoverageMatrixResponse:
        raw = await client.get(f"/api/v1/runs/{run_id}/catalog")
        cases = raw.get("test_cases", []) if isinstance(raw, dict) else []

        edges_seen = set()
        depth_counts = {"L0": 0, "L1": 0, "L2": 0, "L3+": 0}
        for c in cases:
            d = c.get("depth", 0)
            key = f"L{d}" if d < 3 else "L3+"
            depth_counts[key] = depth_counts.get(key, 0) + 1
            for tag in c.get("edge_tags", []):
                edges_seen.add(tag)

        return CoverageMatrixResponse(
            run_id=run_id,
            edge_categories=sorted(list(edges_seen)),
            depth_tiers=depth_counts,
            coverage_score=min(100.0, float(len(cases)) * 2.5),
        )
    return get_coverage_matrix
