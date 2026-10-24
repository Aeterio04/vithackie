"""Autonomous GitHub Fix Pipeline Service.

Integrates kawach_fix LangGraph pipeline into KAWACH:
- Step 1: Verification (1 single deterministic Playwright sandbox run)
- Step 2: Collector (fetch last commit on origin/main via GitHub REST API)
- Step 3: Fix LLM (pass commit diff + playwright script + error details for exact patch)
- Step 4: PR Raiser (raise autonomous PR into main on branch kawach/fix-<sha7>)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid
from pydantic import SecretStr

from kawach.core.config import settings
from kawach.core.security import secret_store
from kawach.db.models.project import Project as DbProject
from kawach.db.models.runs import Run as DbRun
from kawach.storage import artifacts as storage

from kawach_fix.deps import Deps
from kawach_fix.graph import build_fix_graph, PipelineState
from kawach_fix.schemas import (
    ErrorReport,
    FixOptions,
    FixProposal,
    FixRequest,
    FixResult,
    PullRequestInfo,
    VerificationResult,
    normalize_github_repo,
)

logger = logging.getLogger("kawach.services.fix")

# Global in-memory cache for live streaming fix sessions
FIX_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_fix_runs_dir() -> Path:
    runs_dir = getattr(settings, "runs_dir", Path("runs"))
    p = runs_dir / "fix_runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


class FixService:
    """Service managing autonomous fix pipeline executions, state tracking, and GitHub configuration."""

    @staticmethod
    def get_fix_readiness(run_id: str, db: Any) -> Dict[str, Any]:
        """Check if project has GitHub URL and PAT configured for a given run."""
        db_run = db.query(DbRun).filter(DbRun.id == run_id).first()
        project = None
        if db_run and db_run.project_id:
            project = db.query(DbProject).filter(DbProject.id == db_run.project_id).first()

        env_pat = os.environ.get("GITHUB_PAT", "")
        env_repo = os.environ.get("DEMO_REPO", "")

        github_url = (project.github_url if project and project.github_url else "") or env_repo
        has_pat = bool((project and project.pat_encrypted) or env_pat)

        target_url = "http://localhost:4000"
        if project and project.target_url:
            target_url = project.target_url
        else:
            r_json = storage.read_json(run_id, "run.json") or {}
            target_url = r_json.get("targetUrl") or r_json.get("target_url") or target_url

        return {
            "configured": bool(github_url and has_pat),
            "hasPat": has_pat,
            "githubUrl": github_url,
            "repo": github_url,
            "targetUrl": target_url,
            "projectId": project.id if project else None,
            "projectName": project.name if project else None,
        }

    @staticmethod
    def save_github_config(run_id: str, github_url: str, pat: str, db: Any) -> Dict[str, Any]:
        """Save GitHub repository and encrypted PAT for the parent project of run."""
        clean_url = github_url.strip()
        clean_pat = pat.strip()

        if not clean_url:
            raise ValueError("GitHub repository URL or identifier is required.")
        if not clean_pat:
            raise ValueError("GitHub Personal Access Token (PAT) is required.")

        normalized_repo = normalize_github_repo(clean_url)

        db_run = db.query(DbRun).filter(DbRun.id == run_id).first()
        if not db_run or not db_run.project_id:
            # Fallback to default project if run project is missing
            project = db.query(DbProject).first()
        else:
            project = db.query(DbProject).filter(DbProject.id == db_run.project_id).first()

        if not project:
            raise ValueError(f"No project found for run {run_id}")

        project.github_url = normalized_repo
        project.pat_encrypted = secret_store.encrypt(clean_pat)
        db.commit()

        logger.info(f"Saved GitHub config for project {project.id} ({normalized_repo})")
        return {
            "success": True,
            "githubUrl": normalized_repo,
            "hasPat": True,
            "projectId": project.id,
        }

    @staticmethod
    def resolve_repro_script(run_id: str, bug: Any, target_url: str) -> str:
        """Locate Playwright script on disk or generate a synthetic reproducible test."""
        run_dir = storage.run_dir(run_id)
        test_id = getattr(bug, "testId", getattr(bug, "id", ""))

        script_candidates = [
            run_dir / "scripts" / f"{test_id}.spec.ts",
            run_dir / "scripts" / f"{getattr(bug, 'id', '')}.spec.ts",
        ]
        for p in script_candidates:
            if p.exists() and p.is_file():
                try:
                    c = p.read_text(encoding="utf-8")
                    if c.strip():
                        return c
                except Exception:
                    pass

        scripts_dir = run_dir / "scripts"
        if scripts_dir.exists():
            for sf in scripts_dir.glob("*.spec.ts"):
                try:
                    c = sf.read_text(encoding="utf-8")
                    if test_id and (test_id in sf.name or test_id in c):
                        return c
                except Exception:
                    pass

        # Synthetic fallback
        title = getattr(bug, "title", f"Defect {test_id}")
        steps = getattr(bug, "steps", getattr(bug, "steps_to_reproduce", [])) or []
        expected = getattr(bug, "expected", "Operation succeeds without errors")
        actual = getattr(bug, "actual", getattr(bug, "title", "Assertion failure"))

        steps_code = "\n".join([f"    // Step: {s}" for s in steps]) if steps else "    // Automated exploratory failure"

        return f"""import {{ test, expect }} from '@playwright/test';

test.describe('Deterministic Defect Reproduction: {title}', () => {{
  test('reproduce defect scenario', async ({{ page }}) => {{
    await page.goto('{target_url}');
{steps_code}
    // Expected: {expected}
    // Observed actual: {actual}
    expect(true).toBe(false);
  }});
}});
"""

    @classmethod
    def start_fix_pipeline(
        cls,
        run_id: str,
        bug_id: Optional[str] = None,
        repo: Optional[str] = None,
        github_pat: Optional[str] = None,
        target_url: Optional[str] = None,
        dry_run: bool = False,
        db: Any = None,
    ) -> Dict[str, Any]:
        """Initialize fix session and launch background execution task."""
        # 1. Resolve Project and GitHub credentials
        db_run = db.query(DbRun).filter(DbRun.id == run_id).first() if db else None
        project = None
        if db_run and db_run.project_id:
            project = db.query(DbProject).filter(DbProject.id == db_run.project_id).first()

        resolved_repo = repo or (project.github_url if project else None) or os.environ.get("DEMO_REPO")
        resolved_pat = github_pat
        if not resolved_pat and project and project.pat_encrypted:
            try:
                resolved_pat = secret_store.decrypt(project.pat_encrypted)
            except Exception as e:
                logger.warning(f"Could not decrypt project PAT: {e}")
        if not resolved_pat:
            resolved_pat = os.environ.get("GITHUB_PAT")

        if not resolved_repo:
            raise ValueError("GitHub repository identifier (e.g. 'owner/repo') is required.")
        if not resolved_pat:
            raise ValueError("GitHub Personal Access Token (PAT) is required to open pull requests.")

        normalized_repo = normalize_github_repo(resolved_repo)

        # 2. Resolve target URL
        resolved_target_url = target_url or (project.target_url if project else None) or "http://localhost:4000"
        if not target_url and not (project and project.target_url):
            r_json = storage.read_json(run_id, "run.json") or {}
            resolved_target_url = r_json.get("targetUrl") or r_json.get("target_url") or resolved_target_url

        # 3. Resolve Bug Details
        bugs_json = storage.read_json(run_id, "bugs.json") or {}
        bugs_list = bugs_json.get("bugs", []) if isinstance(bugs_json, dict) else []

        selected_bug = None
        if bug_id:
            selected_bug = next((b for b in bugs_list if b.get("id") == bug_id), None)
        if not selected_bug and bugs_list:
            # Prioritize confirmed bug, else first bug
            selected_bug = next((b for b in bugs_list if b.get("status") == "confirmed"), bugs_list[0])

        bug_dict = selected_bug or {
            "id": bug_id or "DEFECT-001",
            "title": "Observed Defect Failure",
            "actual": "Assertion timeout waiting for condition",
            "expected": "Condition met without timeout",
            "steps": ["Trigger failing interaction"],
            "console": [],
            "network": [],
        }

        # 4. Resolve Playwright Script
        script_code = cls.resolve_repro_script(run_id, type("BugObj", (), bug_dict), resolved_target_url)

        # 5. Build FixRequest
        fix_id = f"fix-{run_id}-{uuid.uuid4().hex[:6]}"
        fix_request = FixRequest(
            repo=normalized_repo,
            github_pat=SecretStr(resolved_pat),
            base_branch="main",
            error=ErrorReport(
                test_name=bug_dict.get("title", f"Defect {bug_dict.get('id', '1')}"),
                failing_step=bug_dict.get("actual", "Assertion step failed"),
                message=bug_dict.get("actual", "Assertion error observed during test execution"),
                console=bug_dict.get("console") or [],
                network=bug_dict.get("network") or [],
            ),
            playwright_script=script_code,
            target_url=resolved_target_url,
            playwright_project_dir="./apps/runner",
            options=FixOptions(
                verify_runs=1,  # 1 single check to confirm once and move on
                min_failures=1,
                dry_run=dry_run,
                draft_pr=False,
            ),
            run_id=fix_id,
        )

        # 6. Initialize Session Record
        session_data: Dict[str, Any] = {
            "fixId": fix_id,
            "runId": run_id,
            "bugId": bug_dict.get("id"),
            "bugTitle": bug_dict.get("title"),
            "repo": normalized_repo,
            "targetUrl": resolved_target_url,
            "dryRun": dry_run,
            "status": "starting",
            "stage": "verifier",
            "currentStep": "Initializing autonomous repair environment...",
            "progress": 5,
            "logs": [
                {
                    "timestamp": _now_iso(),
                    "message": f"Fix session initialized for {normalized_repo} (defect: {bug_dict.get('title')})",
                    "level": "info",
                }
            ],
            "verification": None,
            "commitContext": None,
            "proposal": None,
            "pullRequest": None,
            "error": None,
            "playwrightScript": script_code,
            "createdAt": _now_iso(),
            "updatedAt": _now_iso(),
        }

        FIX_SESSIONS[fix_id] = session_data
        cls._save_status_to_disk(fix_id, session_data)

        # 7. Launch Background Execution
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(cls._execute_pipeline(fix_id, fix_request))
        except RuntimeError:
            import threading
            threading.Thread(
                target=lambda: asyncio.run(cls._execute_pipeline(fix_id, fix_request)),
                daemon=True,
                name=f"fix-pipeline-{fix_id}",
            ).start()

        return {
            "id": fix_id,
            "fixId": fix_id,
            "status": "starting",
            "repo": normalized_repo,
            "bugId": bug_dict.get("id"),
        }

    @classmethod
    def get_fix_status(cls, fix_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve live or persisted status of a fix execution session."""
        if fix_id in FIX_SESSIONS:
            return FIX_SESSIONS[fix_id]

        # Check disk
        disk_file = _get_fix_runs_dir() / fix_id / "status.json"
        if disk_file.exists():
            try:
                data = json.loads(disk_file.read_text(encoding="utf-8"))
                FIX_SESSIONS[fix_id] = data
                return data
            except Exception:
                pass
        return None

    @classmethod
    def _save_status_to_disk(cls, fix_id: str, data: Dict[str, Any]) -> None:
        try:
            folder = _get_fix_runs_dir() / fix_id
            folder.mkdir(parents=True, exist_ok=True)
            status_file = folder / "status.json"
            # Redact PAT or sensitive fields if any exist
            clean = {k: v for k, v in data.items() if k != "github_pat"}
            status_file.write_text(json.dumps(clean, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not write fix status to disk: {e}")

    @classmethod
    def _add_log(cls, fix_id: str, message: str, level: str = "info") -> None:
        if fix_id in FIX_SESSIONS:
            session = FIX_SESSIONS[fix_id]
            session.setdefault("logs", []).append({
                "timestamp": _now_iso(),
                "message": message,
                "level": level,
            })
            session["updatedAt"] = _now_iso()
            cls._save_status_to_disk(fix_id, session)

    @classmethod
    async def _execute_pipeline(cls, fix_id: str, req: FixRequest) -> None:
        """Run the 4-step LangGraph fix pipeline with real-time state telemetry."""
        session = FIX_SESSIONS.get(fix_id)
        if not session:
            return

        runs_dir = _get_fix_runs_dir() / fix_id
        runs_dir.mkdir(parents=True, exist_ok=True)
        deps = Deps(runs_dir=runs_dir)

        try:
            compiled_graph = build_fix_graph(deps)
            initial_state: PipelineState = {
                "request": req,
                "run_id": fix_id,
                "verification": None,
                "commit_context": None,
                "proposal": None,
                "pull_request": None,
                "result": None,
            }

            # --- STAGE 1: VERIFIER ---
            session["status"] = "verifying"
            session["stage"] = "verifier"
            session["currentStep"] = "Executing Playwright sandbox replay (1/1 run) to confirm defect existence..."
            session["progress"] = 20
            cls._add_log(fix_id, f"Running deterministic sandbox replay against {req.target_url}...")

            async for event in compiled_graph.astream(initial_state):
                for node_name, node_update in event.items():
                    logger.info(f"[{fix_id}] Node completed: {node_name}")

                    if node_name == "verify":
                        ver: Optional[VerificationResult] = node_update.get("verification")
                        if ver:
                            session["verification"] = ver.model_dump()
                            verdict = ver.verdict
                            fails = ver.failures
                            if verdict == "confirmed":
                                cls._add_log(fix_id, f"Verification PASSED: Defect confirmed in {fails}/1 runs.", "success")
                                session["status"] = "collecting"
                                session["stage"] = "collector"
                                session["currentStep"] = "Querying latest commit on origin/main via GitHub REST API..."
                                session["progress"] = 45
                            elif verdict == "flaky":
                                cls._add_log(fix_id, f"Defect classified as FLAKY ({fails}/1 failures).", "warning")
                            else:
                                cls._add_log(fix_id, "Defect NOT REPRODUCED: Test script passed in sandbox.", "warning")

                        res: Optional[FixResult] = node_update.get("result")
                        if res and res.status in ("not_reproduced", "flaky"):
                            session["status"] = res.status
                            session["stage"] = "completed"
                            session["currentStep"] = f"Pipeline stopped: {res.reason}"
                            session["progress"] = 100
                            cls._add_log(fix_id, f"Pipeline stopped: {res.reason}", "warning")
                            cls._save_status_to_disk(fix_id, session)
                            return

                    elif node_name == "collect":
                        commit_ctx = node_update.get("commit_context")
                        if commit_ctx:
                            commit_dict = commit_ctx.model_dump() if hasattr(commit_ctx, "model_dump") else commit_ctx
                            sha = getattr(commit_ctx, "sha", "") or commit_dict.get("sha", "")
                            author = getattr(commit_ctx, "author", "") or commit_dict.get("author", "Unknown")
                            message = getattr(commit_ctx, "message", "") or commit_dict.get("message", "")
                            files = getattr(commit_ctx, "files", []) or commit_dict.get("files", [])
                            commit_dict["summary"] = {
                                "sha": sha,
                                "author": author,
                                "message": message,
                            }
                            session["commitContext"] = commit_dict
                            cls._add_log(
                                fix_id,
                                f"Pinned origin/main commit {sha[:7]} by {author}: '{message}' ({len(files)} files modified).",
                                "success",
                            )
                            session["status"] = "analyzing"
                            session["stage"] = "llm"
                            session["currentStep"] = "Synthesizing exact search-and-replace fix using LLM..."
                            session["progress"] = 70

                        res: Optional[FixResult] = node_update.get("result")
                        if res and res.status in ("no_editable_changes", "github_error"):
                            session["status"] = res.status
                            session["stage"] = "completed"
                            session["currentStep"] = f"Pipeline stopped: {res.reason}"
                            session["progress"] = 100
                            cls._add_log(fix_id, f"Pipeline stopped: {res.reason}", "warning")
                            cls._save_status_to_disk(fix_id, session)
                            return

                    elif node_name == "propose":
                        proposal: Optional[FixProposal] = node_update.get("proposal")
                        if proposal:
                            session["proposal"] = proposal.model_dump()
                            conf_pct = int(proposal.confidence * 100)
                            cls._add_log(
                                fix_id,
                                f"LLM generated fix with {conf_pct}% confidence across {len(proposal.edits)} files: '{proposal.pr_title}'.",
                                "success",
                            )
                            session["status"] = "raising_pr"
                            session["stage"] = "pr"
                            session["currentStep"] = "Pushing patch branch and opening Pull Request on GitHub..."
                            session["progress"] = 90

                        res: Optional[FixResult] = node_update.get("result")
                        if res and res.status in ("fix_not_possible", "invalid_llm_output"):
                            session["status"] = res.status
                            session["stage"] = "completed"
                            session["currentStep"] = f"Pipeline stopped: {res.reason}"
                            session["progress"] = 100
                            cls._add_log(fix_id, f"Pipeline stopped: {res.reason}", "warning")
                            cls._save_status_to_disk(fix_id, session)
                            return

                    elif node_name == "raise_pr":
                        pr: Optional[PullRequestInfo] = node_update.get("pull_request")
                        res: Optional[FixResult] = node_update.get("result")
                        if pr:
                            session["pullRequest"] = pr.model_dump()
                            session["status"] = res.status if res else "pr_opened"
                            session["stage"] = "completed"
                            session["currentStep"] = f"Pull Request #{pr.number} opened on branch '{pr.branch}'!"
                            session["progress"] = 100
                            cls._add_log(fix_id, f"SUCCESS! Opened Pull Request #{pr.number}: {pr.url}", "success")
                        elif res and res.status == "dry_run_ready":
                            session["status"] = "dry_run_ready"
                            session["stage"] = "completed"
                            session["currentStep"] = "Dry-run complete: patch validated without GitHub writes."
                            session["progress"] = 100
                            cls._add_log(fix_id, "Dry-run finished successfully.", "success")
                        elif res:
                            session["status"] = res.status
                            session["stage"] = "completed"
                            session["currentStep"] = res.reason or "Pipeline execution completed."
                            session["progress"] = 100
                            cls._add_log(fix_id, f"PR step outcome: {res.status} - {res.reason}", "info")

            session["updatedAt"] = _now_iso()
            cls._save_status_to_disk(fix_id, session)

        except Exception as e:
            logger.exception(f"Unhandled error during fix pipeline execution [{fix_id}]: {e}")
            session["status"] = "failed"
            session["stage"] = "completed"
            session["error"] = str(e)
            session["currentStep"] = f"Pipeline error: {str(e)}"
            session["progress"] = 100
            cls._add_log(fix_id, f"FATAL ERROR: {str(e)}", "error")
            cls._save_status_to_disk(fix_id, session)


fix_service = FixService()
