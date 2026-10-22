"""Import legacy flat-file runs and assets into SQLite/PostgreSQL database under a system project.

Usage:
    python apps/api/scripts/import_legacy_runs.py [--all] [--run-dir PATH] [--run-id ID]
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Ensure kawach is in sys.path
api_src = Path(__file__).resolve().parent.parent / "src"
if str(api_src) not in sys.path:
    sys.path.insert(0, str(api_src))

from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.core.config import settings
from kawach.core.security import hash_password
from kawach.db.base import Base
from kawach.db.session import engine, SessionLocal
from kawach.db.models.identity import User
from kawach.db.models.project import Project, SpecItem
from kawach.db.models.runs import AppMap, LlmUsage, Run, RunMetric, RunStageTime
from kawach.db.models.tests import ReviewDecision, TestCase, TestCaseSpecRef, TestResult, TestScript
from kawach.db.models.bugs import Bug, BugDuplicate, BugEvidence, Verification, VerificationAttempt
from kawach.db.models.artifacts import Artifact
from kawach.storage.artifact_store import ArtifactStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("import_legacy_runs")


def parse_dt(val: Optional[str]) -> Optional[datetime]:
    """Parse ISO formatted timestamp string safely."""
    if not val:
        return None
    try:
        clean = val.replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return None


def get_or_create_system_user(db: Session) -> User:
    """Ensure a default system administrator user exists for legacy and automated assets."""
    user = db.scalar(select(User).where(User.email == "system@kawach.local"))
    if not user:
        user = User(
            email="system@kawach.local",
            password_hash=hash_password("system-demo-default-2026"),
            display_name="KAWACH System",
            is_active=True,
        )
        db.add(user)
        db.flush()
        logger.info(f"Created system user: {user.id} ({user.email})")
    return user


def get_or_create_legacy_project(db: Session, system_user: User, target_url: str = "http://localhost:4000") -> Project:
    """Ensure the system-owned 'Legacy demo' project exists."""
    project = db.scalar(
        select(Project).where(
            Project.owner_id == system_user.id,
            Project.slug == "legacy-demo",
        )
    )
    if not project:
        project = Project(
            owner_id=system_user.id,
            name="Legacy demo",
            slug="legacy-demo",
            description="Imported historical flat-file runs and golden test assets.",
            target_url=target_url,
            default_mode="autonomous",
            budgets={
                "maxPages": 10,
                "exploreSeconds": 90,
                "maxTests": 12,
                "testTimeoutMs": 30000,
            },
            allowed_hosts=["localhost", "127.0.0.1"],
            spec_version=1,
        )
        db.add(project)
        db.flush()
        logger.info(f"Created legacy project: {project.id} ('{project.name}')")
    return project


def import_run_folder(
    run_path: Path,
    db: Session,
    system_user: User,
    project: Project,
    artifact_store: ArtifactStore,
) -> Optional[str]:
    """Import a single flat-file run directory into the database."""
    run_json_path = run_path / "run.json"
    if not run_json_path.exists():
        logger.warning(f"Skipping {run_path}: no run.json found")
        return None

    with open(run_json_path, "r", encoding="utf-8") as f:
        run_data = json.load(f)

    run_id = run_data.get("runId")
    if not run_id:
        logger.warning(f"Skipping {run_path}: run.json missing runId")
        return None

    logger.info(f"Importing run {run_id} from {run_path}...")

    # Clean existing run record if re-importing
    existing_run = db.get(Run, run_id)
    if existing_run:
        logger.info(f"Run {run_id} already exists in DB. Deleting to re-import cleanly.")
        db.delete(existing_run)
        db.flush()

    # 1. Input and Spec Items
    input_path = run_path / "input.json"
    spec_items_map: Dict[str, SpecItem] = {}
    if input_path.exists():
        with open(input_path, "r", encoding="utf-8") as f:
            input_data = json.load(f)
        spec_list = input_data.get("spec", [])
        for item in spec_list:
            s_key = item.get("id")
            s_text = item.get("text", "")
            if not s_key:
                continue
            # Look up or create spec item on project
            spec_item = db.scalar(
                select(SpecItem).where(
                    SpecItem.project_id == project.id,
                    SpecItem.spec_version == project.spec_version,
                    SpecItem.key == s_key,
                )
            )
            if not spec_item:
                spec_item = SpecItem(
                    project_id=project.id,
                    spec_version=project.spec_version,
                    key=s_key,
                    text=s_text,
                    position=len(spec_items_map),
                )
                db.add(spec_item)
                db.flush()
            spec_items_map[s_key] = spec_item

    # 2. Run record
    created_at = parse_dt(run_data.get("createdAt"))
    updated_at = parse_dt(run_data.get("updatedAt"))
    stage = run_data.get("stage", "done")
    mode = run_data.get("mode", "autonomous")
    is_golden = bool(run_data.get("golden", False))
    error = run_data.get("error")
    progress = run_data.get("progress") or {}

    run = Run(
        id=run_id,
        project_id=project.id,
        created_by=system_user.id,
        trigger_type="manual",
        mode=mode,
        stage=stage,
        spec_version=project.spec_version,
        error=error,
        progress=progress,
        is_golden=is_golden,
        started_at=created_at,
        ended_at=updated_at,
    )
    db.add(run)
    db.flush()

    # 3. Stage Times
    stage_times = run_data.get("stageTimes", {})
    for st_name, st_val in stage_times.items():
        if isinstance(st_val, dict):
            st_start = parse_dt(st_val.get("startedAt"))
            st_end = parse_dt(st_val.get("endedAt"))
            st_record = RunStageTime(
                run_id=run_id,
                stage=st_name,
                started_at=st_start,
                ended_at=st_end,
            )
            db.add(st_record)

    # 4. App Map
    app_map_path = run_path / "app_map.json"
    if app_map_path.exists():
        with open(app_map_path, "r", encoding="utf-8") as f:
            app_map_data = json.load(f)
        pages = app_map_data.get("pages", [])
        app_map = AppMap(
            run_id=run_id,
            data=app_map_data,
            pages_visited=len(pages),
            duration_seconds=float(app_map_data.get("durationSeconds", 0.0)),
            budget_hit=bool(app_map_data.get("budgetHit", False)),
            created_at=created_at or datetime.utcnow(),
        )
        db.add(app_map)

    # 5. Catalog and Test Cases
    catalog_path = run_path / "catalog.json"
    test_cases_map: Dict[str, TestCase] = {}
    if catalog_path.exists():
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog_data = json.load(f)
        for t_data in catalog_data.get("tests", []):
            t_key = t_data.get("id")
            if not t_key:
                continue
            tc = TestCase(
                project_id=project.id,
                run_id=run_id,
                key=t_key,
                title=t_data.get("title", f"Test {t_key}"),
                description=t_data.get("description"),
                priority=t_data.get("priority", "medium"),
                status=t_data.get("status", "approved"),
                origin=t_data.get("origin", "planned"),
                steps=t_data.get("steps", []),
            )
            db.add(tc)
            db.flush()
            test_cases_map[t_key] = tc

            # Spec refs
            for s_ref in t_data.get("specRef", []):
                spec_item = spec_items_map.get(s_ref)
                if spec_item:
                    ref_link = TestCaseSpecRef(
                        test_case_id=tc.id,
                        spec_item_id=spec_item.id,
                    )
                    db.add(ref_link)

            # Test script file (if present)
            script_rel = t_data.get("script") or f"scripts/{t_key}.spec.ts"
            script_file = run_path / script_rel
            if script_file.exists():
                art_id, uri, size, sha = artifact_store.copy_file(
                    script_file,
                    project_id=project.id,
                    kind="script",
                    run_id=run_id,
                )
                art = Artifact(
                    id=art_id,
                    project_id=project.id,
                    run_id=run_id,
                    kind="script",
                    uri=uri,
                    mime="text/x-typescript",
                    size_bytes=size,
                    sha256=sha,
                )
                db.add(art)
                db.flush()

                t_script = TestScript(
                    test_case_id=tc.id,
                    version=1,
                    artifact_id=art_id,
                    content_hash=sha,
                    status=t_data.get("scriptStatus", "ok"),
                    error=t_data.get("scriptError"),
                )
                db.add(t_script)

    # 6. Results
    results_path = run_path / "results.json"
    if results_path.exists():
        with open(results_path, "r", encoding="utf-8") as f:
            results_data = json.load(f)
        for r_item in results_data.get("tests", []):
            t_key = r_item.get("testId")
            tc = test_cases_map.get(t_key)
            result = TestResult(
                run_id=run_id,
                test_case_id=tc.id if tc else None,
                source=r_item.get("source", "planned"),
                outcome=r_item.get("outcome", "passed"),
                duration_ms=int(r_item.get("durationMs", 0)),
                error_message=r_item.get("errorMessage"),
            )
            db.add(result)

    # 7. Review Decisions
    review_path = run_path / "review_log.json"
    if review_path.exists():
        with open(review_path, "r", encoding="utf-8") as f:
            review_data = json.load(f)
        rev_at = parse_dt(review_data.get("reviewedAt")) or datetime.utcnow()
        for d_item in review_data.get("decisions", []):
            t_key = d_item.get("testId")
            tc = test_cases_map.get(t_key)
            if tc:
                decision_str = d_item.get("decision", "approved")
                if decision_str == "approve":
                    decision_str = "approved"
                rev_decision = ReviewDecision(
                    run_id=run_id,
                    test_case_id=tc.id,
                    decision=decision_str,
                    reason=d_item.get("reason"),
                    reviewer_kind="human",
                    reviewer_user_id=system_user.id,
                    created_at=rev_at,
                )
                db.add(rev_decision)

    # 8. Bugs and Evidence
    bugs_path = run_path / "bugs.json"
    bugs_map: Dict[str, Bug] = {}
    if bugs_path.exists():
        with open(bugs_path, "r", encoding="utf-8") as f:
            bugs_data = json.load(f)
        for b_item in bugs_data.get("bugs", []):
            b_key = b_item.get("id")
            if not b_key:
                continue
            t_key = b_item.get("testId")
            tc = test_cases_map.get(t_key)
            sig = b_item.get("signature")
            fingerprint = sig or hashlib.sha256(f"{run_id}_{b_key}".encode()).hexdigest()[:16]

            bug = Bug(
                project_id=project.id,
                run_id=run_id,
                key=b_key,
                test_case_id=tc.id if tc else None,
                signature=sig,
                fingerprint=fingerprint,
                title=b_item.get("title", f"Defect {b_key}"),
                category=b_item.get("category", "functional"),
                severity=b_item.get("severity", "medium"),
                steps=b_item.get("steps", []),
                expected=b_item.get("expected"),
                actual=b_item.get("actual"),
                error_message=b_item.get("errorMessage"),
                status=b_item.get("status", "candidate"),
                first_seen_run_id=run_id,
            )
            db.add(bug)
            db.flush()
            bugs_map[b_key] = bug

            # Duplicates
            for dup_id in b_item.get("duplicates", []):
                db.add(BugDuplicate(bug_id=bug.id, duplicate_test_case_id=str(dup_id)))

            # Evidence artifacts
            ev_dict = b_item.get("evidence") or {}
            for role, rel_uri in ev_dict.items():
                if not rel_uri:
                    continue
                ev_file = run_path / rel_uri
                if ev_file.exists():
                    art_id, uri, size, sha = artifact_store.copy_file(
                        ev_file,
                        project_id=project.id,
                        kind=role,
                        run_id=run_id,
                    )
                    art = Artifact(
                        id=art_id,
                        project_id=project.id,
                        run_id=run_id,
                        kind=role,
                        uri=uri,
                        size_bytes=size,
                        sha256=sha,
                    )
                    db.add(art)
                    db.flush()

                    bug_ev = BugEvidence(
                        bug_id=bug.id,
                        artifact_id=art.id,
                        role=role,
                    )
                    db.add(bug_ev)

    # 9. Verification (3x replay)
    ver_dir = run_path / "verification"
    if ver_dir.exists():
        for ver_file in ver_dir.glob("*.json"):
            try:
                with open(ver_file, "r", encoding="utf-8") as f:
                    ver_data = json.load(f)
                b_key = ver_data.get("bugId") or ver_file.stem
                bug = bugs_map.get(b_key)
                if bug:
                    ver_at = parse_dt(ver_data.get("verifiedAt"))
                    verification = Verification(
                        bug_id=bug.id,
                        kind="bug",
                        reproduced_count=int(ver_data.get("reproduced", 0)),
                        attempts_total=len(ver_data.get("attempts", [])) or 3,
                        status=ver_data.get("status", "confirmed"),
                        verified_at=ver_at,
                    )
                    db.add(verification)
                    db.flush()

                    for att in ver_data.get("attempts", []):
                        v_att = VerificationAttempt(
                            verification_id=verification.id,
                            attempt_no=int(att.get("attempt", 1)),
                            reproduced=bool(att.get("reproduced", False)),
                            outcome=att.get("outcome", "assertion_failure"),
                            duration_ms=int(att.get("durationMs", 0)),
                            error_message=att.get("errorMessage"),
                        )
                        db.add(v_att)
            except Exception as e:
                logger.warning(f"Error parsing verification file {ver_file}: {e}")

    # 10. Metrics and LLM Usage
    metrics_path = run_path / "metrics.json"
    if metrics_path.exists():
        with open(metrics_path, "r", encoding="utf-8") as f:
            metrics_data = json.load(f)
        run_metric = RunMetric(
            run_id=run_id,
            data=metrics_data,
            wall_clock_seconds=float(metrics_data.get("wallClockSeconds", 0.0)),
            created_at=updated_at or datetime.utcnow(),
        )
        db.add(run_metric)

        llm_data = metrics_data.get("llm")
        if llm_data and isinstance(llm_data, dict):
            llm_usage = LlmUsage(
                run_id=run_id,
                agent="pipeline_total",
                calls=int(llm_data.get("calls", 0)),
                cache_hits=int(llm_data.get("cacheHits", 0)),
                input_tokens=int(llm_data.get("inputTokens", 0)),
                output_tokens=int(llm_data.get("outputTokens", 0)),
                cost_usd=float(llm_data.get("costUsd", 0.0)),
                created_at=updated_at or datetime.utcnow(),
            )
            db.add(llm_usage)

    # 11. Report markdown artifact
    report_path = run_path / "report.md"
    if report_path.exists():
        art_id, uri, size, sha = artifact_store.copy_file(
            report_path,
            project_id=project.id,
            kind="report",
            run_id=run_id,
        )
        art = Artifact(
            id=art_id,
            project_id=project.id,
            run_id=run_id,
            kind="report",
            uri=uri,
            mime="text/markdown",
            size_bytes=size,
            sha256=sha,
        )
        db.add(art)

    db.commit()
    logger.info(f"Successfully imported run {run_id} into database.")
    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legacy flat-file runs into KAWACH database.")
    parser.add_argument("--run-dir", type=str, help="Path to specific run directory to import")
    parser.add_argument("--run-id", type=str, help="Specific run ID to search and import")
    parser.add_argument("--all", action="store_true", default=True, help="Scan and import all found runs")
    args = parser.parse_args()

    # Ensure schema is applied
    Base.metadata.create_all(bind=engine)

    artifact_store = ArtifactStore()

    with SessionLocal() as db:
        system_user = get_or_create_system_user(db)
        project = get_or_create_legacy_project(db, system_user)

        target_dirs: List[Path] = []
        if args.run_dir:
            target_dirs.append(Path(args.run_dir).resolve())
        else:
            # Scan runs_dir
            if settings.runs_dir.exists():
                for entry in settings.runs_dir.iterdir():
                    if entry.is_dir() and (entry / "run.json").exists():
                        target_dirs.append(entry)
            # Scan demo-data/golden
            golden_dir = settings.repo_root / "demo-data" / "golden"
            if golden_dir.exists():
                for entry in golden_dir.iterdir():
                    if entry.is_dir() and (entry / "run.json").exists():
                        target_dirs.append(entry)

        if not target_dirs:
            logger.info("No runs found to import.")
            return

        imported_count = 0
        for r_dir in target_dirs:
            if args.run_id and r_dir.name != args.run_id:
                continue
            res = import_run_folder(r_dir, db, system_user, project, artifact_store)
            if res:
                imported_count += 1

        logger.info(f"Done. Successfully imported {imported_count} run(s) into database.")


if __name__ == "__main__":
    main()
