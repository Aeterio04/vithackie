"""FastAPI backend application for Autonomous AI QA Engineer.

Implements all endpoints from CONTRACTS.md Section 8 and API_CONTRACT.md,
supporting both direct routes (/runs, /config, etc.) and /api/v1/* prefixes for Next.js frontend proxy.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import io
import json
import logging
from pathlib import Path
import re
import shutil
import time
import threading
from typing import Any, Dict, List, Optional
import urllib.parse
import zipfile

from fastapi import Body, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.models import (
    AppMap,
    BugsFile,
    Budgets,
    Catalog,
    Metrics,
    Results,
    ReviewLog,
    Run,
    RunInput,
    RunListItem,
    RunView,
    SpecItem,
    StageTime,
    TestCase,
    Verification,
)
from app import graphs
from app.agents import planner
from app import report
from app import storage

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# --- Lifespan Context ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: recover any runs left in active stages when server died
    active_stages = {"exploring", "planning", "scripting", "running", "verifying", "reporting"}
    if settings.runs_dir.exists():
        for entry in settings.runs_dir.iterdir():
            if entry.is_dir() and (entry / "run.json").exists():
                try:
                    r = storage.load_model(entry.name, "run.json", Run)
                    if r and r.stage in active_stages:
                        storage.fail_run(r.runId, "Server restarted while the run was in progress")
                        logger.warning(f"Marked stale active run {r.runId} as failed on startup.")
                except Exception as e:
                    logger.error(f"Error checking run {entry.name} on startup: {e}")
    yield


app = FastAPI(title="Autonomous AI QA Engineer API", lifespan=lifespan)

# Allow frontend dev servers (Vite 5173 and Next.js 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware (never logs request bodies to protect credentials)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 1)
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)")
    return response


# --- Helper Schemas ---
class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    targetUrl: Optional[str] = None
    target_url: Optional[str] = None
    prompt: str = ""
    spec: Optional[str] = None
    specRaw: Optional[str] = None
    spec_raw: Optional[str] = None
    username: str = ""
    password: str = ""
    mode: str = "manual"


class AddTestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt: str


class UpdateCatalogRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tests: Optional[List[TestCase]] = None
    items: Optional[List[TestCase]] = None


# --- Spec Parsing ---
def parse_spec_text(raw_spec: str) -> tuple[List[SpecItem], List[str]]:
    """Parse spec text: S<number>: <text> and continuation lines indented with 2 spaces."""
    errors: List[str] = []
    items: List[SpecItem] = []
    lines = raw_spec.splitlines()

    curr_id: Optional[str] = None
    curr_text: List[str] = []

    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if line.startswith("  "):
            if not curr_id:
                errors.append(f"Line {i} is a continuation line but has no previous S<number> item")
            else:
                curr_text.append(line.strip())
        else:
            m = re.match(r"^S(\d+):\s*(.+)$", line)
            if not m:
                errors.append(f"Line {i} must start with S<number>:")
            else:
                if curr_id:
                    items.append(SpecItem(id=curr_id, text=" ".join(curr_text)))
                curr_id = f"S{m.group(1)}"
                curr_text = [m.group(2).strip()]

    if curr_id:
        items.append(SpecItem(id=curr_id, text=" ".join(curr_text)))

    if not items and not errors:
        errors.append("Spec must contain at least one item like 'S1: ...'")

    return items, errors


def _safe_save_model(run_id: str, rel: str, obj: BaseModel) -> None:
    """Save model with retry for Windows transient file locks."""
    for _ in range(5):
        try:
            storage.save_model(run_id, rel, obj)
            return
        except (PermissionError, OSError):
            time.sleep(0.05)
    target_path = storage.run_dir(run_id) / rel
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(obj.model_dump_json(by_alias=True, indent=2))


# --- Stub Execution Engine (Used in STUB_MODE or when Graphs aren't implemented) ---
def _run_stub_pipeline(run_id: str) -> None:
    """Simulate Graph 1 and Graph 2 execution using contract samples."""
    samples_dir = settings.repo_root / "contracts" / "samples"
    run_dir = storage.run_dir(run_id)

    try:
        run = storage.get_run(run_id)

        # Stage 1: Exploring
        storage.set_stage(run_id, "exploring", step="Crawling application pages", done=1, total=4)
        time.sleep(0.5)

        # Copy app_map.json
        sample_map = samples_dir / "app_map.sample.json"
        if sample_map.exists():
            shutil.copy(sample_map, run_dir / "app_map.json")

        # Stage 2: Planning
        storage.set_stage(run_id, "planning", step="Generating test catalog", done=0, total=11)
        time.sleep(0.5)

        # Copy catalog.json
        sample_cat = samples_dir / "catalog.sample.json"
        if sample_cat.exists():
            with open(sample_cat, "r", encoding="utf-8") as f:
                cat_data = json.load(f)
            cat_data["runId"] = run_id
            if run.mode == "manual":
                for t in cat_data.get("tests", []):
                    t["status"] = "proposed"
                    t["script"] = None
                    t["scriptStatus"] = "pending"
            else:
                for t in cat_data.get("tests", []):
                    t["status"] = "approved"
                    t["script"] = f"scripts/{t['id']}.spec.ts"
                    t["scriptStatus"] = "ok"

            with open(run_dir / "catalog.json", "w", encoding="utf-8") as f:
                json.dump(cat_data, f, indent=2)

        # Stage 3: Review gate
        if run.mode == "manual":
            storage.set_stage(run_id, "awaiting_review", step="Waiting for QA review")
            return

        # Autonomous mode: approve and proceed to Graph 2
        sample_rev = samples_dir / "review_log.sample.json"
        if sample_rev.exists():
            with open(sample_rev, "r", encoding="utf-8") as f:
                rev_data = json.load(f)
            rev_data["runId"] = run_id
            with open(run_dir / "review_log.json", "w", encoding="utf-8") as f:
                json.dump(rev_data, f, indent=2)

        _run_stub_execute(run_id)

    except Exception as e:
        logger.error(f"Stub pipeline failed for {run_id}: {e}")
        storage.fail_run(run_id, str(e))


def _run_stub_execute(run_id: str) -> None:
    """Simulate Graph 2 execution from approved tests to report and done."""
    samples_dir = settings.repo_root / "contracts" / "samples"
    files_dir = samples_dir / "files"
    run_dir = storage.run_dir(run_id)

    try:
        # Stage 4: Scripting
        storage.set_stage(run_id, "scripting", step="Writing Playwright test scripts", done=0, total=11)
        scripts_dir = run_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        sample_script = files_dir / "scripts" / "T02.spec.ts"
        base_script_text = sample_script.read_text(encoding="utf-8") if sample_script.exists() else ""

        cat = storage.load_model(run_id, "catalog.json", Catalog)
        if cat:
            for i, t in enumerate(cat.tests, 1):
                if t.status != "rejected":
                    t.status = "approved"
                    t.script = f"scripts/{t.id}.spec.ts"
                    t.scriptStatus = "ok"
                # Write individual script
                script_file = scripts_dir / f"{t.id}.spec.ts"
                custom_script = base_script_text.replace("T02", t.id).replace(
                    "Signing up with invalid email is rejected", t.title
                )
                script_file.write_text(custom_script, encoding="utf-8")
                storage.set_stage(run_id, "scripting", step=f"Generated script {t.id}", done=i, total=len(cat.tests))
            _safe_save_model(run_id, "catalog.json", cat)

        time.sleep(0.5)

        # Stage 5: Running
        storage.set_stage(run_id, "running", step="Executing test suite with Playwright", done=3, total=13)
        sample_results = samples_dir / "results.sample.json"
        if sample_results.exists():
            with open(sample_results, "r", encoding="utf-8") as f:
                res_data = json.load(f)
            res_data["runId"] = run_id
            with open(run_dir / "results.json", "w", encoding="utf-8") as f:
                json.dump(res_data, f, indent=2)

        # Stage 6: Verifying
        storage.set_stage(run_id, "verifying", step="Writing bug reports and replays", done=0, total=10)
        sample_bugs = samples_dir / "bugs.sample.json"
        if sample_bugs.exists():
            with open(sample_bugs, "r", encoding="utf-8") as f:
                bugs_data = json.load(f)
            bugs_data["runId"] = run_id
            with open(run_dir / "bugs.json", "w", encoding="utf-8") as f:
                json.dump(bugs_data, f, indent=2)

        # Copy evidence
        if (files_dir / "evidence").exists():
            dest_ev = run_dir / "evidence"
            if dest_ev.exists():
                shutil.rmtree(dest_ev)
            shutil.copytree(files_dir / "evidence", dest_ev)

        # Copy verifications
        ver_dir = run_dir / "verification"
        ver_dir.mkdir(parents=True, exist_ok=True)
        sample_v = samples_dir / "verification.B01.sample.json"
        if sample_v.exists():
            shutil.copy(sample_v, ver_dir / "B01.json")

        time.sleep(0.5)

        # Stage 7: Reporting
        storage.set_stage(run_id, "reporting", step="Aggregating metrics and report")
        report.build_metrics(run_id)
        report.build_report(run_id)

        # Stage 8: Done
        storage.set_stage(run_id, "done")

    except Exception as e:
        logger.error(f"Stub execute failed for {run_id}: {e}")
        storage.fail_run(run_id, str(e))


def _start_pipeline_background(run_id: str) -> None:
    def _runner():
        try:
            try:
                graphs.run_pipeline(run_id)
            except NotImplementedError:
                _run_stub_pipeline(run_id)
        except Exception as e:
            logger.error(f"Background pipeline failed for run {run_id}: {e}")
            storage.fail_run(run_id, str(e))

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()


def _start_execute_background(run_id: str) -> None:
    def _runner():
        try:
            try:
                graphs.run_execute(run_id)
            except NotImplementedError:
                _run_stub_execute(run_id)
        except Exception as e:
            logger.error(f"Background execute failed for run {run_id}: {e}")
            storage.fail_run(run_id, str(e))

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()


# ==============================================================================
# HTTP Endpoints (Dual Mounted: root paths and /api/v1/* prefixes)
# ==============================================================================


@app.get("/health")
@app.get("/api/v1/health")
def health() -> dict:
    return {"ok": True}


@app.get("/config")
@app.get("/api/v1/config/defaults")
def get_config() -> dict:
    allowed = getattr(settings, "allowed_hosts", getattr(settings, "ALLOWED_HOSTS", ["localhost", "127.0.0.1"]))
    return {
        "allowedHosts": allowed,
        "budgets": {
            "maxPages": settings.MAX_PAGES,
            "exploreSeconds": settings.EXPLORE_SECONDS,
            "maxTests": settings.MAX_TESTS,
            "testTimeoutMs": settings.TEST_TIMEOUT_MS,
        },
        "defaultTargetUrl": "http://localhost:4000",
        "stubMode": bool(settings.STUB_MODE),
    }


@app.get("/runs")
@app.get("/api/v1/runs")
def list_runs() -> List[RunListItem]:
    return storage.list_runs()


@app.post("/runs", status_code=status.HTTP_201_CREATED)
@app.post("/api/v1/runs/start", status_code=status.HTTP_201_CREATED)
def start_run(payload: CreateRunRequest) -> dict:
    errors: List[dict] = []

    # 1. Target URL validation
    raw_url = payload.targetUrl or payload.target_url or ""
    parsed_url = urllib.parse.urlparse(raw_url)
    if not (parsed_url.scheme in ("http", "https") and parsed_url.netloc):
        errors.append({"field": "targetUrl", "message": "Invalid URL scheme or missing host"})
    else:
        host = parsed_url.hostname or ""
        allowed = getattr(settings, "allowed_hosts", getattr(settings, "ALLOWED_HOSTS", ["localhost", "127.0.0.1"]))
        if host not in allowed:
            errors.append(
                {
                    "field": "targetUrl",
                    "message": "Host not allowed. This tool only tests staging or local apps.",
                }
            )

    # 2. Spec validation
    raw_spec = payload.spec or payload.specRaw or payload.spec_raw or ""
    spec_items, spec_errors = parse_spec_text(raw_spec)
    for serr in spec_errors:
        errors.append({"field": "spec", "message": serr})

    # 3. Mode validation
    mode = payload.mode
    if mode not in ("manual", "autonomous"):
        errors.append({"field": "mode", "message": "Mode must be 'manual' or 'autonomous'"})

    # Return 422 if any validation error
    if errors:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"errors": errors})

    # 4. Check for active run conflict (409)
    active_stages = {"exploring", "planning", "scripting", "running", "verifying", "reporting"}
    for r in storage.list_runs():
        if r.stage in active_stages:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another run is in progress",
            )

    # 5. Initialize run
    run_id = storage.new_run_id()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    run_input = RunInput(
        runId=run_id,
        createdAt=now,
        targetUrl=raw_url,
        prompt=payload.prompt,
        specRaw=raw_spec,
        spec=spec_items,
        username=payload.username,
        mode=mode,
        budgets=Budgets(
            maxPages=settings.MAX_PAGES,
            exploreSeconds=settings.EXPLORE_SECONDS,
            maxTests=settings.MAX_TESTS,
            testTimeoutMs=settings.TEST_TIMEOUT_MS,
        ),
    )

    run = Run(
        runId=run_id,
        createdAt=now,
        updatedAt=now,
        stage="created",
        mode=mode,
        targetUrl=raw_url,
        stageTimes={"created": StageTime(startedAt=now, endedAt=None)},
        golden=False,
    )

    # Save initial files
    storage.save_model(run_id, "input.json", run_input)
    storage.save_model(run_id, "run.json", run)

    # Secure secrets file (password only)
    secrets_path = storage.run_dir(run_id) / "secrets.json"
    with open(secrets_path, "w", encoding="utf-8") as f:
        json.dump({"password": payload.password}, f)
    try:
        secrets_path.chmod(0o600)
    except Exception:
        pass

    # Launch background graph
    _start_pipeline_background(run_id)

    return {"runId": run_id}


@app.get("/runs/{run_id}")
@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str) -> RunView:
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found")

    run_input = storage.load_model(run_id, "input.json", RunInput)
    if not run_input:
        run_input = RunInput(
            runId=run_id,
            createdAt=run.createdAt,
            targetUrl=run.targetUrl,
            prompt="",
            specRaw="",
            spec=[],
            username="",
            mode=run.mode,
            budgets=Budgets(),
        )

    app_map = storage.load_model(run_id, "app_map.json", AppMap)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    review_log = storage.load_model(run_id, "review_log.json", ReviewLog)
    results = storage.load_model(run_id, "results.json", Results)
    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
    bugs = bugs_file.bugs if bugs_file else []

    # Collect verifications
    verifications: List[Verification] = []
    ver_dir = storage.run_dir(run_id) / "verification"
    if ver_dir.exists():
        for vf in sorted(ver_dir.glob("*.json")):
            try:
                v = storage.load_model(run_id, f"verification/{vf.name}", Verification)
                if v:
                    verifications.append(v)
            except Exception:
                continue

    metrics = storage.load_model(run_id, "metrics.json", Metrics)
    has_report = (storage.run_dir(run_id) / "report.md").exists()

    return RunView(
        run=run,
        input=run_input,
        appMap=app_map,
        catalog=catalog,
        reviewLog=review_log,
        results=results,
        bugs=bugs,
        verifications=verifications,
        metrics=metrics,
        hasReport=has_report,
    )


@app.put("/runs/{run_id}/catalog")
@app.put("/api/v1/runs/{run_id}/catalog")
def update_catalog(run_id: str, payload: UpdateCatalogRequest) -> Catalog:
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.stage != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Catalog can only be edited while stage is awaiting_review",
        )

    tests = payload.tests or payload.items or []

    # Validate test IDs are unique
    seen_ids = set()
    for t in tests:
        if t.id in seen_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Duplicate test ID '{t.id}' in catalog",
            )
        seen_ids.add(t.id)

    existing_cat = storage.load_model(run_id, "catalog.json", Catalog)
    gen_at = existing_cat.generatedAt if existing_cat else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    updated_cat = Catalog(runId=run_id, generatedAt=gen_at, tests=tests)
    storage.save_model(run_id, "catalog.json", updated_cat)
    return updated_cat


@app.post("/runs/{run_id}/tests")
@app.post("/api/v1/runs/{run_id}/tests")
def add_test(run_id: str, payload: AddTestRequest) -> TestCase:
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.stage != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tests can only be added while stage is awaiting_review",
        )

    try:
        new_test = planner.plan_single_test(run_id, payload.prompt)
        return new_test
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))
    except NotImplementedError:
        # Fallback for stub mode or before Track B finishes planner
        cat = storage.load_model(run_id, "catalog.json", Catalog)
        if not cat:
            cat = Catalog(runId=run_id, generatedAt=datetime.now(timezone.utc).isoformat(), tests=[])

        next_idx = len(cat.tests) + 1
        new_test = TestCase(
            id=f"T{next_idx:02d}",
            title=f"T{next_idx:02d}: {payload.prompt[:80]}",
            description=payload.prompt,
            specRef=[],
            priority="medium",
            steps=[],
            status="proposed",
            origin="human",
            script=None,
            scriptStatus="pending",
            scriptError=None,
        )
        cat.tests.append(new_test)
        storage.save_model(run_id, "catalog.json", cat)
        return new_test
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@app.post("/runs/{run_id}/execute", status_code=status.HTTP_202_ACCEPTED)
@app.post("/api/v1/runs/{run_id}/catalog/approve-and-execute", status_code=status.HTTP_202_ACCEPTED)
def execute_run(run_id: str) -> dict:
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.stage != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run must be in awaiting_review stage to execute",
        )

    cat = storage.load_model(run_id, "catalog.json", Catalog)
    if not cat:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No catalog found")

    # Every test not 'rejected' becomes 'approved'
    approved_count = 0
    for t in cat.tests:
        if t.status != "rejected":
            t.status = "approved"
            approved_count += 1

    if approved_count == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No tests to run")

    storage.save_model(run_id, "catalog.json", cat)
    storage.set_stage(run_id, "scripting", step="Starting test execution pipeline")

    _start_execute_background(run_id)
    return {"stage": "scripting"}


@app.get("/runs/{run_id}/report", response_class=PlainTextResponse)
@app.get("/api/v1/runs/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str) -> str:
    report_file = storage.run_dir(run_id) / "report.md"
    if not report_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not generated yet")
    return report_file.read_text(encoding="utf-8")


@app.get("/runs/{run_id}/files/{path:path}")
@app.get("/api/v1/runs/{run_id}/files/{path:path}")
def get_run_file(run_id: str, path: str):
    rdir = storage.run_dir(run_id).resolve()
    target_file = (rdir / path).resolve()

    # Block path traversal outside run folder
    try:
        target_file.relative_to(rdir)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Path traversal blocked")

    # Guard secrets and raw inputs
    if target_file.name in ("secrets.json", "input.json"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not target_file.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    ext = target_file.suffix.lower()
    media_map = {
        ".png": "image/png",
        ".webm": "video/webm",
        ".zip": "application/zip",
        ".json": "application/json",
        ".ts": "text/plain",
        ".md": "text/markdown",
    }
    media_type = media_map.get(ext, "application/octet-stream")
    return FileResponse(target_file, media_type=media_type)


@app.get("/runs/{run_id}/export")
@app.get("/api/v1/runs/{run_id}/export")
def export_passing_tests(run_id: str):
    run = storage.load_model(run_id, "run.json", Run)
    results = storage.load_model(run_id, "results.json", Results)
    if not run or not results:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run results not found")

    passed_tests = [t for t in results.tests if t.outcome == "passed"]
    if not passed_tests:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No passed tests to export")

    run_dir = storage.run_dir(run_id)
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add passing scripts with rewritten imports
        for pt in passed_tests:
            script_path = run_dir / (pt.file if pt.file else f"scripts/{pt.testId}.spec.ts")
            if script_path.exists():
                content = script_path.read_text(encoding="utf-8")
                # Rewrite import
                content = content.replace("../../../runner/fixtures", "./fixtures")
                zf.writestr(f"scripts/{pt.testId}.spec.ts", content)

        # 2. Add fixtures.ts
        fixtures_source = settings.repo_root / "runner" / "fixtures.ts"
        if fixtures_source.exists():
            zf.write(fixtures_source, arcname="fixtures.ts")
        else:
            # Fallback fixtures
            minimal_fixtures = """import { test as base, expect } from '@playwright/test';
export const test = base;
export { expect };
export const unique = (prefix: string) => `${prefix}-${Date.now()}`;
"""
            zf.writestr("fixtures.ts", minimal_fixtures)

        # 3. Add playwright.config.ts
        base_url = run.targetUrl or "http://localhost:4000"
        cfg_content = f"""import {{ defineConfig, devices }} from '@playwright/test';

export default defineConfig({{
  testDir: './scripts',
  timeout: 30000,
  use: {{
    baseURL: process.env.BASE_URL ?? '{base_url}',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  }},
  projects: [
    {{
      name: 'chromium',
      use: {{ ...devices['Desktop Chrome'] }},
    }},
  ],
}});
"""
        zf.writestr("playwright.config.ts", cfg_content)

        # 4. Add package.json
        pkg_content = """{
  "name": "qa-exported-tests",
  "private": true,
  "scripts": {
    "test": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "^1.49.0"
  }
}
"""
        zf.writestr("package.json", pkg_content)

        # 5. Add README.md
        readme_content = """# Exported QA Tests

## Setup & Execution
1. Install dependencies:
   ```bash
   npm install
   npx playwright install chromium
   ```
2. Configure credentials in environment:
   ```bash
   export TEST_USERNAME="<user@example.com>"
   export TEST_PASSWORD="<password>"
   ```
3. Run tests:
   ```bash
   npx playwright test
   ```
"""
        zf.writestr("README.md", readme_content)

    zip_buffer.seek(0)
    filename = f"{run_id}-passing-tests.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/runs/{run_id}/stream")
@app.get("/api/v1/runs/{run_id}/stream")
async def stream_run_progress(run_id: str):
    """Server-Sent Events endpoint streaming stage changes and execution progress."""
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    async def event_generator():
        last_stage = None
        last_step = None

        for _ in range(300):  # Cap stream at 5 minutes
            r = storage.load_model(run_id, "run.json", Run)
            if not r:
                break

            step_text = r.progress.step if r.progress else ""
            if r.stage != last_stage or step_text != last_step:
                last_stage = r.stage
                last_step = step_text

                event_data = {
                    "runId": r.runId,
                    "stage": r.stage,
                    "progress": r.progress.model_dump() if r.progress else None,
                    "error": r.error,
                    "updatedAt": r.updatedAt,
                }
                yield f"event: stage_change\ndata: {json.dumps(event_data)}\n\n"

            if r.stage in ("done", "failed"):
                break

            time.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Helper routes for frontend forms
@app.post("/api/v1/targets/check")
def check_target(payload: dict = Body(...)) -> dict:
    url = payload.get("url", "")
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    allowlisted = host in settings.ALLOWED_HOSTS
    return {"allowlisted": allowlisted, "host": host}


@app.post("/api/v1/specs/upload")
def upload_spec(payload: dict = Body(...)) -> dict:
    spec_text = payload.get("specText", "")
    items, errors = parse_spec_text(spec_text)
    if errors:
        return JSONResponse(status_code=422, content={"errors": errors})
    return {"spec": [item.model_dump() for item in items]}
