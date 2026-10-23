"""MCP Prompts implementation for IDE developer workflows."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from kawach_mcp.client import KawachClient
from kawach_mcp.config import Settings


def register_prompts(server: MCPServer, client: KawachClient, settings: Settings) -> None:
    """Register all 4 pre-configured developer workflow prompts on the MCP server."""

    @server.prompt(
        "triage_failing_commit",
        description="Triage a failing commit: inspect localized suspect files, view the suggested patch, and review evidence.",
    )
    def prompt_triage_failing_commit(project_id: str, commit_id: str) -> str:
        return (
            f"You are triaging a test failure detected on commit `{commit_id}` in project `{project_id}`.\n\n"
            f"Please perform the following workflow:\n"
            f"1. Call `get_failure_analysis(project_id='{project_id}', commit_id='{commit_id}')` to retrieve the ranked suspect files and line ranges.\n"
            f"2. Inspect the culprit files locally in this workspace using your editor tools. Focus on the reported line ranges.\n"
            f"3. Call `get_fix_suggestion(project_id='{project_id}', commit_id='{commit_id}')` to view the synthesized fix patch and validation status.\n"
            f"4. Compare the suggested diff with your local codebase and explain to the developer whether the fix correctly addresses the root cause.\n"
            f"5. If the fix is verified and the developer approves, you can run `apply_fix_as_pr` to open a Pull Request.\n"
        )

    @server.prompt(
        "explain_bug",
        description="Diagnose a verified defect: inspect checkpoint steps, assertions, and explain why the test failed.",
    )
    def prompt_explain_bug(bug_id: str) -> str:
        return (
            f"You are investigating verified defect `{bug_id}`.\n\n"
            f"Please follow these steps:\n"
            f"1. Call `get_bug(bug_id='{bug_id}')` to fetch defect metadata, failing step index, and error messages.\n"
            f"2. Read the reproduction script using the resource URI `kawach://runs/{{run_id}}/bugs/{bug_id}/repro-script`.\n"
            f"3. Analyze the error message and DOM checkpoint state to explain in plain English:\n"
            f"   - What action triggered the failure\n"
            f"   - What assertion failed and the expected vs actual UI behavior\n"
            f"   - Potential code components responsible for the regression\n"
        )

    @server.prompt(
        "run_regression_for_my_changes",
        description="Run diff-aware regression testing for modified local files and summarize results.",
    )
    def prompt_run_regression_for_my_changes(project_id: str, files_changed: str) -> str:
        return (
            f"You are triggering a diff-aware regression run for project `{project_id}` based on recent local modifications.\n\n"
            f"Files changed: {files_changed}\n\n"
            f"Workflow:\n"
            f"1. Call `run_regression(project_id='{project_id}', files_changed={files_changed.split(',')})`.\n"
            f"2. Take the returned `run_id` and call `wait_for_run(run_id=...)` to monitor execution.\n"
            f"3. When finished, if any bugs are found, call `list_failures(run_id=...)` to summarize defects.\n"
            f"4. If all tests pass, confirm to the developer that their local changes are regression-free.\n"
        )

    @server.prompt(
        "review_fix_before_apply",
        description="Verify policy compliance and replay certification for a proposed fix before opening a Pull Request.",
    )
    def prompt_review_fix_before_apply(project_id: str, commit_id: str) -> str:
        return (
            f"You are conducting a pre-apply policy review for the fix patch on commit `{commit_id}` in project `{project_id}`.\n\n"
            f"Verification Checklist:\n"
            f"1. Call `get_fix_suggestion(project_id='{project_id}', commit_id='{commit_id}')`.\n"
            f"2. Verify that `validation_status` is 'validated' (certified by 3x deterministic replay).\n"
            f"3. Verify that `risk_level` is 'small_fix' (touches <= 1 file and <= 20 lines).\n"
            f"4. Confirm that none of the touched files belong to blocked sensitive categories (auth, billing, security, migrations).\n"
            f"5. Present your verdict to the user. If approved, call `apply_fix_as_pr` to create a GitHub Pull Request.\n"
        )
