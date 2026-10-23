"""Legacy root-level HTTP routes specified in CONTRACTS.md Section 8.

Maintains strict backwards compatibility with baseline tests and direct runner clients.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
import time
from typing import List, Optional
import urllib.parse

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from kawach.api.deps import get_optional_user
from kawach.db.models.identity import User
from kawach.services.idempotency import IdempotencyService

try:
    from app import graphs
except ImportError:
    from kawach import workflows as graphs

try:
    from app.agents import planner
except ImportError:
    from kawach.agents import planner

from kawach.core.config import settings
from kawach.core.ids import new_run_id
from kawach.schemas import (
    AppMap,
    Budgets,
    BugsFile,
    Catalog,
    Metrics,
    Results,
    ReviewLog,
    Run,
    RunInput,
    RunListItem,
    RunView,
    StageTime,
    TestCase,
    Verification,
)
from kawach.services.export_service import export_scripts_zip
from kawach.services.spec_parser import parse_spec_text
from kawach.storage import artifacts as storage
from kawach.storage.secrets import write_secret_password

logger = logging.getLogger("kawach.api.legacy")
router = APIRouter(tags=["legacy-contracts"])


# --- Schemas ---

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


# --- Background Tasks ---

def _start_pipeline_background(run_id: str) -> None:
    def _runner():
        try:
            try:
                graphs.run_pipeline(run_id)
            except (NotImplementedError, AttributeError):
                from kawach.workflows import run_explore_plan, run_execute
                run_explore_plan(run_id)
                r = storage.get_run(run_id)
                if r.mode == "autonomous" and r.stage not in ("failed", "cancelled"):
                    run_execute(run_id)
        except Exception as e:
            logger.error(f"Background pipeline failed for run {run_id}: {e}")
            storage.fail_run(run_id, str(e))

    threading.Thread(target=_runner, daemon=True).start()


def _start_execute_background(run_id: str) -> None:
    def _runner():
        try:
            try:
                graphs.run_execute(run_id)
            except (NotImplementedError, AttributeError):
                from kawach.workflows import run_execute
                run_execute(run_id)
        except Exception as e:
            logger.error(f"Background execute failed for run {run_id}: {e}")
            storage.fail_run(run_id, str(e))

    threading.Thread(target=_runner, daemon=True).start()


# --- Endpoints ---

@router.get("/health")
def health() -> dict:
    """Service health probe."""
    return {"ok": True}


@router.get("/config")
def get_config() -> dict:
    """System limits, timeouts, and configured budgets."""
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


@router.get("/runs")
def list_runs() -> List[RunListItem]:
    """List summary records for all runs."""
    return storage.list_runs()


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def start_run(
    payload: CreateRunRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Start a new QA test run conforming strictly to Section 8 contract."""
    user_id = current_user.id if current_user else "anonymous"

    # 0. Idempotency Check
    cached = IdempotencyService.check_or_record(
        user_id=user_id,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    if cached:
        status_code, response_data = cached
        return JSONResponse(status_code=status_code, content=response_data)

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
    run_id = new_run_id()
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

    storage.save_model(run_id, "input.json", run_input)
    storage.save_model(run_id, "run.json", run)

    if payload.password:
        write_secret_password(run_id, payload.password)

    _start_pipeline_background(run_id)

    res = {"runId": run_id}
    IdempotencyService.store_response(
        user_id=user_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        response_data=res,
    )
    return res


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> RunView:
    """Retrieve complete state of a run."""
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


@router.put("/runs/{run_id}/catalog")
def update_catalog(run_id: str, payload: UpdateCatalogRequest) -> Catalog:
    """Update test cases in catalog while awaiting review."""
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.stage != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Catalog can only be edited while stage is awaiting_review",
        )

    tests = payload.tests or payload.items or []

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


@router.post("/runs/{run_id}/tests")
def add_test(run_id: str, payload: AddTestRequest) -> TestCase:
    """Generate and append a new test case to the catalog from prompt."""
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


@router.post("/runs/{run_id}/execute", status_code=status.HTTP_202_ACCEPTED)
def execute_run(run_id: str) -> dict:
    """Approve non-rejected catalog tests and launch test execution."""
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


@router.get("/runs/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str) -> str:
    """Retrieve markdown report file."""
    report_file = storage.run_dir(run_id) / "report.md"
    if not report_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not generated yet")
    return report_file.read_text(encoding="utf-8")


@router.get("/runs/{run_id}/files/{path:path}")
def get_run_file(run_id: str, path: str):
    """Retrieve an artifact file from the run directory."""
    rdir = storage.run_dir(run_id).resolve()
    target_file = (rdir / path).resolve()

    try:
        target_file.relative_to(rdir)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Path traversal blocked")

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


@router.get("/runs/{run_id}/export")
def export_passing_tests(run_id: str):
    """Export passing Playwright tests as a standalone ZIP package."""
    try:
        zip_buffer = export_scripts_zip(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run results not found")
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))

    filename = f"{run_id}-passing-tests.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/stream")
@router.get("/api/runs/{run_id}/stream")
async def stream_run_progress(run_id: str):
    """Server-Sent Events endpoint streaming stage changes."""
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    async def event_generator():
        last_stage = None
        last_step = None

        for _ in range(300):
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
