"""MCP Resources implementation for reports, Playwright repro scripts, and commit analyses."""

from __future__ import annotations

from typing import Any, Dict
from mcp.server.mcpserver import MCPServer

from kawach_mcp.client import KawachAPIError, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.security import redact_secrets, truncate_text, wrap_untrusted_content


def register_resources(server: MCPServer, client: KawachClient, settings: Settings) -> None:
    """Register all 5 Kawach URI resource templates on the MCP server."""

    @server.resource(
        "kawach://projects/{project_id}/report/latest",
        name="latest_project_report",
        description="Latest executive test report and quality KPIs for a project.",
        mime_type="text/markdown",
    )
    async def get_latest_project_report(project_id: str) -> str:
        try:
            runs_data = await client.get("/api/v1/runs", params={"project_id": project_id, "limit": 1})
            items = runs_data if isinstance(runs_data, list) else runs_data.get("items", [])
            if not items:
                return f"# Latest Report for Project {project_id}\n\nNo test runs have been recorded for this project yet."

            latest_run_id = str(items[0].get("id"))
            report = await client.get(f"/api/v1/runs/{latest_run_id}/report")
            summary = report.get("summary", report.get("markdown", "Test run report generated."))
            kpis = report.get("kpis", {})

            kpi_md = "\n".join([f"- **{k.replace('_', ' ').title()}**: {v}" for k, v in kpis.items()])
            content = (
                f"# Project Quality Report — Latest Run ({latest_run_id})\n\n"
                f"## Executive Summary\n{summary}\n\n"
                f"## Key Quality Indicators\n{kpi_md}\n\n"
                f"**Artifact URL**: {settings.clean_api_url}/api/v1/runs/{latest_run_id}/report\n"
            )
            return truncate_text(redact_secrets(content), max_chars=settings.max_response_chars)
        except KawachAPIError as exc:
            return f"Error retrieving latest project report: {exc.to_user_message()}"

    @server.resource(
        "kawach://runs/{run_id}/report",
        name="run_report",
        description="Full markdown executive report for a specific test run.",
        mime_type="text/markdown",
    )
    async def get_run_report(run_id: str) -> str:
        try:
            report = await client.get(f"/api/v1/runs/{run_id}/report")
            title = report.get("title", f"Run {run_id} Report")
            summary = report.get("summary", report.get("markdown", "Test run report generated."))
            kpis = report.get("kpis", {})
            kpi_md = "\n".join([f"- **{k.replace('_', ' ').title()}**: {v}" for k, v in kpis.items()])

            content = (
                f"# {title}\n\n"
                f"## Summary\n{summary}\n\n"
                f"## Quality Metrics\n{kpi_md}\n\n"
                f"**Raw Report URL**: {settings.clean_api_url}/api/v1/runs/{run_id}/report\n"
            )
            return truncate_text(redact_secrets(content), max_chars=settings.max_response_chars)
        except KawachAPIError as exc:
            return f"Error retrieving run report: {exc.to_user_message()}"

    @server.resource(
        "kawach://runs/{run_id}/bugs/{bug_id}/repro-script",
        name="bug_reproduction_script",
        description="Standalone Playwright TypeScript (.spec.ts) reproduction script for a verified defect.",
        mime_type="text/plain",
    )
    async def get_bug_repro_script(run_id: str, bug_id: str) -> str:
        try:
            bug = await client.get(f"/api/v1/bugs/{bug_id}")
            script = bug.get("reproduction_script", bug.get("script_content"))
            if not script:
                title = bug.get("title", "Verified Defect")
                failing_path = bug.get("failing_path", "/checkout")
                script = (
                    f"import {{ test, expect }} from '@playwright/test';\n\n"
                    f"test('{title} (Repro)', async ({{ page }}) => {{\n"
                    f"  await page.goto('{failing_path}');\n"
                    f"  // Replay failure checkpoint at step {bug.get('failing_step', 1)}\n"
                    f"}});\n"
                )
            return wrap_untrusted_content(script, content_type="playwright_repro_script", max_chars=3500)
        except KawachAPIError as exc:
            return f"Error retrieving bug repro script: {exc.to_user_message()}"

    @server.resource(
        "kawach://projects/{project_id}/commits/{commit_id}/analysis",
        name="commit_failure_analysis",
        description="Root-cause failure localization report and ranked suspect culprit files for a commit.",
        mime_type="text/markdown",
    )
    async def get_commit_analysis_resource(project_id: str, commit_id: str) -> str:
        try:
            analysis = await client.get(f"/api/v1/projects/{project_id}/commits/{commit_id}/analysis")
            summary = analysis.get("summary", analysis.get("explanation", "Failure localization analysis."))
            candidates = analysis.get("culprit_candidates", [])

            rows = []
            for c in candidates:
                conf = float(c.get("confidence", 0.0)) * (100.0 if float(c.get("confidence", 0.0)) <= 1.0 else 1.0)
                lr = c.get("line_range")
                lr_str = f"L{lr[0]}-L{lr[1]}" if isinstance(lr, list) and len(lr) == 2 else "All lines"
                rows.append(f"| `{c.get('file_path')}` | {lr_str} | {conf:.1f}% | {c.get('reason', '')} |")

            table_md = "\n".join(rows) if rows else "| None | - | - | No culprits identified |"

            content = (
                f"# Commit Failure Localization — Commit `{commit_id[:8]}`\n\n"
                f"## Diagnosis\n{summary}\n\n"
                f"## Ranked Suspect Files (Workspace-Relative)\n\n"
                f"| File Path | Lines | Confidence | Reason |\n"
                f"| :--- | :--- | :--- | :--- |\n"
                f"{table_md}\n\n"
                f"> **IDE Agent Tip**: Open the suspect files directly in your local editor to inspect and repair the defect.\n"
            )
            return truncate_text(redact_secrets(content), max_chars=settings.max_response_chars)
        except KawachAPIError as exc:
            return f"Error retrieving commit analysis: {exc.to_user_message()}"

    @server.resource(
        "kawach://projects/{project_id}/saved-tests/{test_id}/script",
        name="saved_test_script",
        description="Standalone Playwright TypeScript test script for a saved regression test.",
        mime_type="text/plain",
    )
    async def get_saved_test_script(project_id: str, test_id: str) -> str:
        try:
            tests_data = await client.get(f"/api/v1/projects/{project_id}/saved-tests")
            items = tests_data if isinstance(tests_data, list) else tests_data.get("items", [])
            match = next((t for t in items if str(t.get("id")) == str(test_id)), None)

            if not match:
                return f"Error: Saved test '{test_id}' not found in project '{project_id}'."

            script = match.get("script_content")
            if not script:
                name = match.get("name", f"Saved Test {test_id}")
                touchpoints = match.get("coverage_touchpoints", ["/app"])
                script = (
                    f"import {{ test, expect }} from '@playwright/test';\n\n"
                    f"test('{name}', async ({{ page }}) => {{\n"
                    f"  // Target touchpoints: {', '.join(touchpoints)}\n"
                    f"  await page.goto('{touchpoints[0] if touchpoints else '/'}');\n"
                    f"}});\n"
                )
            return wrap_untrusted_content(script, content_type="playwright_saved_script", max_chars=3500)
        except KawachAPIError as exc:
            return f"Error retrieving saved test script: {exc.to_user_message()}"
