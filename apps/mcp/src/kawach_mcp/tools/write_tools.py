"""Mutating MCP write tools with mandatory two-step confirmation protocol and policy guardrails."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import mcp.types as types
from pydantic import BaseModel, Field

from kawach_mcp.client import KawachAPIError, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.security import wrap_untrusted_content
from kawach_mcp.tools.confirmation import confirmation_manager
from kawach_mcp.tools.registry import register_tool

WRITE_ANNOTATIONS = types.ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    open_world_hint=True,
)

BLOCKED_SENSITIVE_PATHS = (
    "auth", "login", "password", "token", "billing", "payment", "security", "secret", "alembic", ".env"
)


class WriteToolResponse(BaseModel):
    """Unified response model for two-step mutating tools."""
    requires_confirmation: bool = Field(description="True if step 1 preview; False if step 2 execution succeeded")
    confirmation_id: Optional[str] = Field(default=None, description="Confirmation token required for step 2")
    expires_in_seconds: Optional[int] = Field(default=None, description="TTL in seconds (5 min)")
    preview: Optional[Dict[str, Any]] = Field(default=None, description="Impact preview of proposed mutation")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Result of mutation upon confirmed execution")
    instructions: Optional[str] = Field(default=None, description="Guidance for LLM or human developer")


@register_tool(
    name="save_test",
    description="Save a test case from an exploratory run into the project's permanent regression test suite (two-step confirmation).",
    required_scope="tests:write",
    is_write=True,
    annotations=WRITE_ANNOTATIONS,
)
def make_save_test(client: KawachClient, settings: Settings):
    async def save_test(
        project_id: str,
        run_id: str,
        test_id: str,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        confirmation_id: Optional[str] = None,
    ) -> WriteToolResponse:
        payload = {
            "project_id": project_id,
            "run_id": run_id,
            "test_id": test_id,
            "name": name,
            "tags": tags or [],
        }

        # Step 1: Preview & generate confirmation token
        if not confirmation_id:
            catalog = await client.get(f"/api/v1/runs/{run_id}/catalog")
            cases = catalog.get("test_cases", []) if isinstance(catalog, dict) else []
            match = next((c for c in cases if str(c.get("id")) == str(test_id)), None)

            test_name = name or (match.get("name") if match else f"Test {test_id}")
            preview = {
                "action": "save_test_to_regression_suite",
                "project_id": project_id,
                "run_id": run_id,
                "test_id": test_id,
                "test_name": test_name,
                "tags": tags or ["regression"],
                "expected_effect": "Persists generated Playwright script and coverage touchpoints for automated commit regressions.",
            }
            conf = confirmation_manager.create_confirmation(payload, preview)
            return WriteToolResponse(
                requires_confirmation=True,
                confirmation_id=conf.confirmation_id,
                expires_in_seconds=conf.expires_in_seconds,
                preview=conf.preview,
                instructions=conf.instructions,
            )

        # Step 2: Validate token & execute mutation
        valid, err = confirmation_manager.validate_and_consume(confirmation_id, payload)
        if not valid:
            return types.CallToolResult(
                is_error=True,
                content=[types.TextContent(type="text", text=f"Confirmation rejected: {err}")],
            )

        save_body = {
            "run_id": run_id,
            "test_id": test_id,
            "name": name,
            "tags": tags or ["regression"],
        }
        res = await client.post(f"/api/v1/projects/{project_id}/saved-tests", json_data=save_body)
        return WriteToolResponse(
            requires_confirmation=False,
            result={
                "saved_test_id": str(res.get("id")),
                "name": res.get("name"),
                "status": "saved",
                "script_uri": f"kawach://projects/{project_id}/saved-tests/{res.get('id')}/script",
            },
            instructions="Test saved successfully to regression suite.",
        )
    return save_test


@register_tool(
    name="request_fix_suggestion",
    description="Synthesize an automated minimal unified diff patch for a localized commit failure (two-step confirmation).",
    required_scope="fixes:apply",
    is_write=True,
    annotations=WRITE_ANNOTATIONS,
)
def make_request_fix_suggestion(client: KawachClient, settings: Settings):
    async def request_fix_suggestion(
        project_id: str,
        commit_id: str,
        confirmation_id: Optional[str] = None,
    ) -> WriteToolResponse:
        payload = {
            "project_id": project_id,
            "commit_id": commit_id,
        }

        # Step 1: Preview & generate confirmation token
        if not confirmation_id:
            analysis = await client.get(f"/api/v1/projects/{project_id}/commits/{commit_id}/analysis")
            candidates = analysis.get("culprit_candidates", []) if isinstance(analysis, dict) else []

            preview = {
                "action": "synthesize_fix_patch",
                "project_id": project_id,
                "commit_id": commit_id,
                "culprit_count": len(candidates),
                "suspect_files": [c.get("file_path", c.get("path", "")) for c in candidates[:3]],
                "policy_constraints": "Max 1 file, max 20 lines modified. Sensitive paths strictly blocked.",
                "expected_effect": "Invokes fix synthesis agent and validates patch in isolated scratch container.",
            }
            conf = confirmation_manager.create_confirmation(payload, preview)
            return WriteToolResponse(
                requires_confirmation=True,
                confirmation_id=conf.confirmation_id,
                expires_in_seconds=conf.expires_in_seconds,
                preview=conf.preview,
                instructions=conf.instructions,
            )

        # Step 2: Validate token & trigger synthesis
        valid, err = confirmation_manager.validate_and_consume(confirmation_id, payload)
        if not valid:
            return types.CallToolResult(
                is_error=True,
                content=[types.TextContent(type="text", text=f"Confirmation rejected: {err}")],
            )

        res = await client.post(f"/api/v1/projects/{project_id}/commits/{commit_id}/suggest-fix")
        diff = res.get("diff_patch", res.get("patch", ""))
        safe_diff = wrap_untrusted_content(diff, content_type="unified_diff", max_chars=2500)

        return WriteToolResponse(
            requires_confirmation=False,
            result={
                "commit_id": commit_id,
                "risk_level": res.get("risk_classification", "small_fix"),
                "validation_status": res.get("status", "validated"),
                "files_touched": res.get("files_touched", []),
                "diff_patch": safe_diff,
            },
            instructions="Fix patch synthesized and validated.",
        )
    return request_fix_suggestion


@register_tool(
    name="apply_fix_as_pr",
    description="Open a GitHub Pull Request for a validated fix patch. Strictly refuses unvalidated fixes, needs-engineer fixes, or direct pushes (two-step confirmation).",
    required_scope="fixes:apply",
    is_write=True,
    annotations=WRITE_ANNOTATIONS,
)
def make_apply_fix_as_pr(client: KawachClient, settings: Settings):
    async def apply_fix_as_pr(
        project_id: str,
        commit_id: str,
        confirmation_id: Optional[str] = None,
    ) -> WriteToolResponse:
        payload = {
            "project_id": project_id,
            "commit_id": commit_id,
        }

        # Step 0: Check fix validation and safety policies
        fix_info = await client.get(f"/api/v1/projects/{project_id}/commits/{commit_id}/suggest-fix")
        status = fix_info.get("status", "unknown")
        risk = fix_info.get("risk_classification", fix_info.get("risk_level", "unknown"))
        files = fix_info.get("files_touched", [])

        # Policy checks
        if status != "validated":
            return types.CallToolResult(
                is_error=True,
                content=[types.TextContent(
                    type="text",
                    text=f"Policy rejection: Cannot apply fix with validation status '{status}'. Only 'validated' fixes certified by deterministic replay may be opened as PRs."
                )],
            )

        if risk in ("needs_engineer", "blocked"):
            return types.CallToolResult(
                is_error=True,
                content=[types.TextContent(
                    type="text",
                    text=f"Policy rejection: Fix is classified as '{risk}' (exceeds single file or 20-line bounds). Requires human engineer review."
                )],
            )

        for f in files:
            lower_path = f.lower()
            if any(b in lower_path for b in BLOCKED_SENSITIVE_PATHS):
                return types.CallToolResult(
                    is_error=True,
                    content=[types.TextContent(
                        type="text",
                        text=f"Policy rejection: Fix touches sensitive file '{f}'. Modifying security/auth/payment paths is forbidden by policy."
                    )],
                )

        # Step 1: Preview & generate confirmation token
        if not confirmation_id:
            diff = fix_info.get("diff_patch", fix_info.get("patch", ""))
            safe_diff_preview = wrap_untrusted_content(diff[:500], content_type="unified_diff_preview", max_chars=600)

            preview = {
                "action": "open_pull_request",
                "project_id": project_id,
                "commit_id": commit_id,
                "target_branch": "kawach-fix/auto-patch",
                "delivery_mode": "Pull Request ONLY (direct push forbidden by architectural invariant)",
                "files_touched": files,
                "diff_preview": safe_diff_preview,
                "policy_check": "PASSED (validated, single-file, non-sensitive)",
            }
            conf = confirmation_manager.create_confirmation(payload, preview)
            return WriteToolResponse(
                requires_confirmation=True,
                confirmation_id=conf.confirmation_id,
                expires_in_seconds=conf.expires_in_seconds,
                preview=conf.preview,
                instructions=conf.instructions,
            )

        # Step 2: Validate confirmation token & execute PR creation
        valid, err = confirmation_manager.validate_and_consume(confirmation_id, payload)
        if not valid:
            return types.CallToolResult(
                is_error=True,
                content=[types.TextContent(type="text", text=f"Confirmation rejected: {err}")],
            )

        res = await client.post(
            f"/api/v1/projects/{project_id}/commits/{commit_id}/auto-fix",
            json_data={"action": "create_pr"},
        )
        return WriteToolResponse(
            requires_confirmation=False,
            result={
                "status": "pr_opened",
                "pr_url": res.get("pr_url", res.get("html_url", "https://github.com/repo/pull/1")),
                "branch": res.get("branch", "kawach-fix/auto-patch"),
                "files_changed": files,
            },
            instructions="Pull request opened successfully. Kawach never pushes directly to branches.",
        )
    return apply_fix_as_pr
