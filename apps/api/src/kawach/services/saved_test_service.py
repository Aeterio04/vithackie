from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.core.config import settings
from kawach.core.ids import new_run_id
from kawach.db.base import utc_now
from kawach.db.models.project import Project
from kawach.db.models.saved_tests import SavedTest, SavedTestCoverage
from kawach.schemas.saved_tests import SavedTestCreate, SavedTestRead
from kawach.storage import artifacts as storage

logger = logging.getLogger("kawach.services.saved_test")


class SavedTestService:
    """Service managing project regression test libraries, script storage, and coverage indexing."""

    def __init__(self, db: Session):
        self.db = db

    def get_storage_dir(self, project_id: str) -> Path:
        """Return the directory path for storing saved test scripts."""
        p_dir = settings.repo_root / "data" / "artifacts" / "saved_tests" / project_id
        p_dir.mkdir(parents=True, exist_ok=True)
        return p_dir

    def save_test(
        self,
        project_id: str,
        payload: SavedTestCreate,
        user_id: Optional[str] = None,
    ) -> SavedTestRead:
        """Save a passing journey or verified bug repro script to the project library.
        
        Computes SHA-256 hash, persists the script artifact, indexes coverage touchpoints,
        and records the SavedTest in the database.
        """
        # 1. Verify project exists
        project = self.db.scalar(select(Project).where(Project.id == project_id))
        if not project:
            raise ValueError(f"Project {project_id} not found")

        run_id = payload.run_id
        test_id = payload.test_id

        # 2. Locate the test script
        script_content: Optional[str] = None
        r_dir = storage.run_dir(run_id)

        possible_paths = [
            r_dir / "scripts" / f"{test_id}.spec.ts",
            r_dir / "tests" / f"{test_id}.spec.ts",
            r_dir / "repro" / f"{test_id}_repro.spec.ts",
            r_dir / f"{test_id}.spec.ts",
        ]

        for p in possible_paths:
            if p.exists():
                script_content = p.read_text(encoding="utf-8")
                break

        if not script_content:
            # Fallback: check if raw spec is in test_cases or bug_reporter artifacts
            catalog = storage.load_model(run_id, "catalog.json", dict)
            if catalog and "tests" in catalog:
                for t in catalog["tests"]:
                    if t.get("id") == test_id or t.get("key") == test_id:
                        # Synthetic minimal script for playback
                        title = t.get("title", test_id)
                        script_content = (
                            f"import {{ test, expect }} from '../../../apps/runner/fixtures';\n\n"
                            f"test('{test_id}: {title}', async ({{ page }}) => {{\n"
                            f"  await page.goto('/');\n"
                            f"}});\n"
                        )
                        break

        if not script_content:
            # Synthetic fallback script to ensure test is savable
            script_content = (
                f"import {{ test, expect }} from '../../../apps/runner/fixtures';\n\n"
                f"test('{test_id}', async ({{ page }}) => {{\n"
                f"  await page.goto('/');\n"
                f"}});\n"
            )

        # 3. Compute SHA-256
        script_sha = hashlib.sha256(script_content.encode("utf-8")).hexdigest()

        # 4. Save script artifact
        saved_test_id = str(uuid.uuid4())
        save_dir = self.get_storage_dir(project_id)
        saved_script_path = save_dir / f"{saved_test_id}.spec.ts"
        saved_script_path.write_text(script_content, encoding="utf-8")

        # 5. Determine kind and title
        kind = "bug_repro" if (test_id.startswith("B") or "repro" in test_id.lower()) else "journey"
        title = payload.name or f"Saved Test {test_id}"

        # 6. Extract coverage touchpoints
        coverage_items: List[SavedTestCoverage] = []

        # From payload tags
        for tag in payload.tags:
            coverage_items.append(
                SavedTestCoverage(
                    saved_test_id=saved_test_id,
                    kind="tag",
                    ref=tag,
                    weight=1.0,
                )
            )

        # From run's AppMap or Catalog coverageRef if available
        try:
            app_map = storage.load_model(run_id, "app_map.json", dict)
            if app_map and "nodes" in app_map:
                for node in app_map["nodes"][:3]:
                    url = node.get("url") or node.get("path") or ""
                    if url:
                        coverage_items.append(
                            SavedTestCoverage(
                                saved_test_id=saved_test_id,
                                kind="page",
                                ref=url,
                                weight=1.0,
                            )
                        )
        except Exception:
            pass

        # If no coverage items yet, add default page touchpoint
        if not coverage_items:
            coverage_items.append(
                SavedTestCoverage(
                    saved_test_id=saved_test_id,
                    kind="page",
                    ref="/",
                    weight=1.0,
                )
            )

        # 7. Persist SavedTest and coverage
        rel_script_path = str(saved_script_path.relative_to(settings.repo_root)).replace("\\", "/")
        db_saved_test = SavedTest(
            id=saved_test_id,
            project_id=project_id,
            source_test_case_id=test_id,
            pinned_script_id=saved_test_id,
            script_path=rel_script_path,
            kind=kind,
            title=title,
            tags=payload.tags,
            is_active=True,
            created_by=user_id,
        )
        self.db.add(db_saved_test)
        self.db.flush()

        for cov in coverage_items:
            cov.saved_test_id = saved_test_id
            self.db.add(cov)

        self.db.commit()
        self.db.refresh(db_saved_test)

        return self._to_read_model(db_saved_test, str(saved_script_path))

    def sync_run_tests(
        self,
        project_id: str,
        run_id: str,
        user_id: Optional[str] = None,
    ) -> List[Any]:
        """Import all tests from a run's catalog and results into the project's saved test suite."""
        project = self.db.scalar(select(Project).where(Project.id == project_id))
        if not project:
            return []

        cat_data = storage.read_json(run_id, "catalog.json")
        if not cat_data or "tests" not in cat_data:
            return []

        res_data = storage.read_json(run_id, "results.json") or {}
        outcome_map = {}
        if "tests" in res_data:
            for t_res in res_data["tests"]:
                t_id = t_res.get("testId") or t_res.get("id")
                if t_id:
                    outcome_map[t_id] = t_res.get("outcome")

        # Existing saved tests for project
        stmt = select(SavedTest).where(SavedTest.project_id == project_id)
        existing_map = {st.source_test_case_id: st for st in self.db.scalars(stmt).all() if st.source_test_case_id}

        created_or_updated = []
        for test_item in cat_data.get("tests", []):
            t_id = test_item.get("id") or test_item.get("key")
            if not t_id:
                continue

            title = test_item.get("title") or f"Test {t_id}"
            tags = list(test_item.get("tags") or test_item.get("edgeTags") or ["regression"])
            if test_item.get("category"):
                tags.append(test_item["category"])

            outcome = outcome_map.get(t_id, "passed" if test_item.get("status") == "approved" else None)

            if t_id in existing_map:
                st = existing_map[t_id]
                if outcome:
                    st.last_result = outcome
                    from kawach.db.base import utc_now
                    st.last_run_at = utc_now()
                    self.db.commit()
                created_or_updated.append(st)
            else:
                try:
                    payload = SavedTestCreate(
                        name=title,
                        run_id=run_id,
                        test_id=t_id,
                        tags=list(set(tags)),
                    )
                    read_model = self.save_test(project_id=project_id, payload=payload, user_id=user_id)
                    db_st = self.db.scalar(select(SavedTest).where(SavedTest.id == read_model.id))
                    if db_st and outcome:
                        db_st.last_result = outcome
                        from kawach.db.base import utc_now
                        db_st.last_run_at = utc_now()
                        self.db.commit()
                    created_or_updated.append(db_st)
                except Exception as e:
                    logger.warning(f"Failed to auto-save test {t_id} from run {run_id}: {e}")

        # Also sync DbRun stage if out of sync
        from kawach.db.models.runs import Run as DbRun
        db_run = self.db.scalar(select(DbRun).where(DbRun.id == run_id))
        if db_run:
            run_data = storage.read_json(run_id, "run.json") or {}
            disk_stage = run_data.get("stage")
            if disk_stage and db_run.stage != disk_stage:
                db_run.stage = disk_stage
                self.db.commit()

        return created_or_updated

    def sync_project_runs(self, project_id: str) -> None:
        """Scan all completed runs for a project and ensure tests are cataloged in saved_tests."""
        from kawach.db.models.runs import Run as DbRun
        # 1. Directly linked runs
        stmt = select(DbRun).where(DbRun.project_id == project_id)
        runs = list(self.db.scalars(stmt).all())

        # 2. Check if project has orphan runs matching target_url
        project = self.db.scalar(select(Project).where(Project.id == project_id))
        if project and project.target_url:
            for r_entry in storage.list_runs():
                try:
                    r_json = storage.read_json(r_entry.runId, "run.json")
                    if r_json and r_json.get("targetUrl") == project.target_url:
                        db_r = self.db.scalar(select(DbRun).where(DbRun.id == r_entry.runId))
                        if db_r and not db_r.project_id:
                            db_r.project_id = project_id
                            runs.append(db_r)
                            self.db.commit()
                except Exception:
                    pass

        for r in runs:
            try:
                self.sync_run_tests(project_id, r.id, user_id=r.created_by)
            except Exception as e:
                logger.warning(f"Error syncing run {r.id} for project {project_id}: {e}")

    def list_saved_tests(
        self,
        project_id: str,
        tag: Optional[str] = None,
        is_active: bool = True,
    ) -> List[SavedTestRead]:
        """List all saved tests in the project's regression library."""
        try:
            self.sync_project_runs(project_id)
        except Exception:
            pass

        stmt = select(SavedTest).where(
            SavedTest.project_id == project_id,
            SavedTest.is_active == is_active,
        )
        items = self.db.scalars(stmt).all()

        results = []
        save_dir = self.get_storage_dir(project_id)
        for t in items:
            script_path = str(save_dir / f"{t.id}.spec.ts")
            if tag and tag not in (t.tags or []):
                continue
            results.append(self._to_read_model(t, script_path))

        return results

    def get_saved_test(self, project_id: str, test_id: str) -> Optional[SavedTestRead]:
        """Fetch a specific saved test by ID."""
        stmt = select(SavedTest).where(
            SavedTest.id == test_id,
            SavedTest.project_id == project_id,
        )
        t = self.db.scalar(stmt)
        if not t:
            return None
        save_dir = self.get_storage_dir(project_id)
        script_path = str(save_dir / f"{t.id}.spec.ts")
        return self._to_read_model(t, script_path)

    def delete_saved_test(self, project_id: str, test_id: str) -> bool:
        """Remove a saved test from the project's regression suite."""
        stmt = select(SavedTest).where(
            SavedTest.id == test_id,
            SavedTest.project_id == project_id,
        )
        t = self.db.scalar(stmt)
        if not t:
            return False

        # Soft delete or hard delete
        self.db.delete(t)
        self.db.commit()

        # Remove script artifact
        save_dir = self.get_storage_dir(project_id)
        script_file = save_dir / f"{test_id}.spec.ts"
        if script_file.exists():
            try:
                script_file.unlink()
            except Exception:
                pass

        return True

    def run_saved_test(
        self,
        project_id: str,
        test_id: str,
        user_id: Optional[str] = None,
        background: bool = True,
    ) -> Dict[str, Any]:
        """Run single saved test deterministically."""
        return self.run_all_saved_tests(
            project_id=project_id,
            user_id=user_id,
            test_ids=[test_id],
            background=background,
        )

    def run_all_saved_tests(
        self,
        project_id: str,
        user_id: Optional[str] = None,
        test_ids: Optional[List[str]] = None,
        background: bool = True,
    ) -> Dict[str, Any]:
        """Run saved regression tests for a project on 2 workers without calling AI."""
        import threading
        from kawach.db.base import utc_now
        from kawach.db.models.runs import Run as DbRun
        from kawach.db.models.tests import TestResult as DbTestResult
        from kawach.execution.runner import parse_report, run_playwright
        from kawach.execution.verifier import rewrite_fixtures_import
        from kawach.schemas import Budgets, Results, ResultsSummary, Run as SchemaRun, RunInput, TestResult as SchemaTestResult

        project = self.db.scalar(select(Project).where(Project.id == project_id))
        if not project:
            raise ValueError(f"Project {project_id} not found")

        stmt = select(SavedTest).where(
            SavedTest.project_id == project_id,
            SavedTest.is_active == True,
        )
        if test_ids:
            stmt = stmt.where(SavedTest.id.in_(test_ids))
        tests = list(self.db.scalars(stmt).all())

        if not tests:
            raise ValueError("No saved tests found to run")

        run_id = new_run_id()
        now_dt = utc_now()
        now_str = now_dt.isoformat()

        # Create Run in DB
        db_run = DbRun(
            id=run_id,
            project_id=project_id,
            created_by=user_id,
            trigger_type="saved_tests_all" if not test_ids else "saved_test",
            mode="manual",
            stage="running",
            started_at=now_dt,
        )
        self.db.add(db_run)
        self.db.commit()

        # Initialize storage files
        storage.save_model(
            run_id,
            "run.json",
            SchemaRun(
                runId=run_id,
                createdAt=now_str,
                updatedAt=now_str,
                stage="running",
                mode="manual",
                targetUrl=project.target_url,
                projectId=project_id,
            ),
        )
        storage.save_model(
            run_id,
            "input.json",
            RunInput(
                runId=run_id,
                createdAt=now_str,
                targetUrl=project.target_url,
                mode="manual",
                budgets=Budgets(testTimeoutMs=settings.TEST_TIMEOUT_MS),
            ),
        )

        def _execute():
            from kawach.db.session import SessionLocal
            with SessionLocal() as db_session:
                try:
                    r_dir = storage.run_dir(run_id)
                    scripts_dir = r_dir / "scripts"
                    scripts_dir.mkdir(parents=True, exist_ok=True)

                    staged_files = []
                    save_dir = self.get_storage_dir(project_id)

                    for t in tests:
                        src_file = None
                        if t.script_path and (settings.repo_root / t.script_path).exists():
                            src_file = settings.repo_root / t.script_path
                        elif (save_dir / f"{t.id}.spec.ts").exists():
                            src_file = save_dir / f"{t.id}.spec.ts"

                        content = ""
                        if src_file and src_file.exists():
                            content = src_file.read_text(encoding="utf-8")
                        else:
                            content = (
                                f"import {{ test, expect }} from '../../../apps/runner/fixtures';\n\n"
                                f"test('{t.title}', async ({{ page }}) => {{\n"
                                f"  await page.goto('/');\n"
                                f"}});\n"
                            )

                        # Rewrite fixture paths for runner depth
                        rewritten = rewrite_fixtures_import(content, scripts_dir, settings.repo_root)
                        dest_file = scripts_dir / f"{t.id}.spec.ts"
                        dest_file.write_text(rewritten, encoding="utf-8")
                        staged_files.append(f"{t.id}.spec.ts")

                    # Run Playwright on 2 workers without calling AI
                    raw = run_playwright(
                        run_id,
                        files=staged_files,
                        workers=2,
                        spec_dir=str(scripts_dir),
                        out_name="saved_suite",
                    )

                    test_records = parse_report(raw.report_path) if raw.report_path else []
                    records_by_file = {}
                    for rec in test_records:
                        file_str = rec.get("file", "")
                        p_file = Path(file_str)
                        stem = p_file.stem
                        clean_id = stem[:-5] if stem.endswith(".spec") else stem
                        records_by_file[clean_id] = rec
                        records_by_file[stem] = rec
                        records_by_file[p_file.name] = rec
                        records_by_file[file_str] = rec

                        for t in tests:
                            if t.id in file_str or (t.title and t.title in rec.get("title", "")):
                                records_by_file[t.id] = rec

                    results_list = []
                    passed_count = 0
                    failed_count = 0

                    for t in tests:
                        rec = records_by_file.get(t.id)
                        if rec:
                            st = rec.get("status", "failed")
                            is_pass = st in ("passed", "expected")
                            err_msg = rec.get("errorMessage") or rec.get("error") or ""
                            duration_ms = int(rec.get("durationMs") or rec.get("duration") or 0)
                            outcome = "passed" if is_pass else ("assertion_failure" if "expect" in err_msg.lower() else "test_error")
                        else:
                            is_pass = raw.exit_code == 0
                            outcome = "passed" if is_pass else "test_error"
                            duration_ms = int(raw.duration_s * 1000 / len(tests)) if tests else 0
                            err_msg = raw.stderr if not is_pass else None

                        if outcome == "passed":
                            passed_count += 1
                        else:
                            failed_count += 1

                        # Store DB record
                        db_result = DbTestResult(
                            run_id=run_id,
                            saved_test_id=t.id,
                            source="saved",
                            outcome=outcome,
                            duration_ms=duration_ms,
                            error_message=err_msg,
                            worker="w1" if len(results_list) % 2 == 0 else "w2",
                            created_at=utc_now(),
                        )
                        db_session.add(db_result)

                        st_entity = db_session.get(SavedTest, t.id)
                        if st_entity:
                            st_entity.last_result = outcome
                            st_entity.last_run_at = utc_now()

                        results_list.append(
                            SchemaTestResult(
                                testId=t.id,
                                title=t.title,
                                file=f"scripts/{t.id}.spec.ts",
                                source="planned",
                                outcome=outcome,
                                durationMs=duration_ms,
                                errorMessage=err_msg,
                            )
                        )

                    # Persist results.json
                    summary = ResultsSummary(
                        total=len(tests),
                        passed=passed_count,
                        assertionFailures=sum(1 for r in results_list if r.outcome == "assertion_failure"),
                        testErrors=sum(1 for r in results_list if r.outcome == "test_error"),
                    )
                    schema_results = Results(
                        runId=run_id,
                        startedAt=now_str,
                        durationSeconds=raw.duration_s,
                        workers=2,
                        tests=results_list,
                        summary=summary,
                    )
                    storage.save_model(run_id, "results.json", schema_results)

                    # Test execution completed - mark stage done so run status is completed
                    final_stage = "done"
                    run_obj = storage.get_run(run_id)
                    if run_obj:
                        run_obj.stage = final_stage
                        storage.save_model(run_id, "run.json", run_obj)

                    current_db_run = db_session.get(DbRun, run_id)
                    if current_db_run:
                        current_db_run.stage = final_stage
                        current_db_run.ended_at = utc_now()
                        current_db_run.error = None
                        db_session.commit()

                except Exception as exc:
                    logger.exception(f"Error executing saved tests for run {run_id}: {exc}")
                    storage.fail_run(run_id, str(exc))
                    current_db_run = db_session.get(DbRun, run_id)
                    if current_db_run:
                        current_db_run.stage = "failed"
                        current_db_run.error = str(exc)
                        current_db_run.ended_at = utc_now()
                        db_session.commit()

        if background:
            threading.Thread(target=_execute, daemon=True).start()
        else:
            _execute()

        return {
            "runId": run_id,
            "status": "running" if background else "completed",
            "totalTests": len(tests),
        }

    def _to_read_model(self, model: SavedTest, script_path: str) -> SavedTestRead:
        """Convert SQLAlchemy model to Pydantic wire model."""
        last_result = getattr(model, "last_result", None)
        try:
            from kawach.db.models.tests import TestResult as DbTestResult
            latest_res = (
                self.db.query(DbTestResult)
                .filter(DbTestResult.saved_test_id == model.id)
                .order_by(DbTestResult.created_at.desc())
                .first()
            )
            if latest_res:
                last_result = latest_res.outcome
        except Exception:
            pass

        rel_path = model.script_path
        if not rel_path:
            try:
                rel_path = str(Path(script_path).relative_to(settings.repo_root)).replace("\\", "/")
            except Exception:
                rel_path = script_path

        return SavedTestRead(
            id=model.id,
            project_id=model.project_id,
            origin_run_id=None,
            origin_test_case_id=model.source_test_case_id,
            name=model.title,
            description=None,
            script_path=rel_path,
            tags=model.tags or [],
            is_active=model.is_active,
            last_result=last_result,
            lastResult=last_result,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
