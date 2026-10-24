"""MCP resources: read-only views of projects and run artifacts, backed by the same tool logic."""

import json

from mcp.server.fastmcp import FastMCP

from .tools import bugs, catalog, observe, projects, reports


def _j(data) -> str:
    return json.dumps(data, indent=2, default=str)


def register_resources(mcp: FastMCP) -> list[str]:
    @mcp.resource("kawach://projects", name="projects", mime_type="application/json",
                  description="All projects in this account (compact).")
    async def projects_resource() -> str:
        return _j(await projects.list_projects(limit=200))

    @mcp.resource("kawach://runs/{run_id}/report", name="run_report", mime_type="text/markdown",
                  description="Markdown executive report for a run.")
    async def report_resource(run_id: str) -> str:
        return (await reports.get_report(run_id, max_chars=20000))["report"]

    @mcp.resource("kawach://runs/{run_id}/catalog", name="run_catalog", mime_type="application/json",
                  description="Test catalog for a run, with steps.")
    async def catalog_resource(run_id: str) -> str:
        return _j(await catalog.get_catalog(run_id, include_steps=True))

    @mcp.resource("kawach://runs/{run_id}/bugs", name="run_bugs", mime_type="application/json",
                  description="Bugs for a run, confirmed first, each with its verification result.")
    async def bugs_resource(run_id: str) -> str:
        return _j(await bugs.list_bugs(run_id))

    @mcp.resource("kawach://runs/{run_id}/app-map", name="run_app_map", mime_type="application/json",
                  description="Summary of the app map discovered during exploration.")
    async def app_map_resource(run_id: str) -> str:
        return _j(await observe.get_app_map(run_id))

    return ["kawach://projects", "kawach://runs/{run_id}/report", "kawach://runs/{run_id}/catalog",
            "kawach://runs/{run_id}/bugs", "kawach://runs/{run_id}/app-map"]
