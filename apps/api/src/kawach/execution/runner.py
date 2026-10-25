"""Subprocess client for the Playwright runner.

Handles executing Playwright test suites, listing tests, parsing reports,
and extracting evidence.
"""

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from kawach.core.config import settings
from kawach.execution.triage import clean_error_message, is_assertion_failure
from kawach.schemas import (
    AppMap,
    Catalog,
    Outcome,
    Results,
    ResultsSummary,
    RunInput,
    TestCase,
    TestResult,
)
from kawach.storage import artifacts as storage
from kawach.storage.secrets import read_secret_password


@dataclass
class RawRun:
    """Raw execution output from a Playwright subprocess run."""
    exit_code: int
    report_path: Optional[str]
    stdout: str
    stderr: str
    duration_s: float


@dataclass
class ListResult:
    """Validation result from playwright test --list."""
    ok: bool
    error: Optional[str] = None


def normalize_path(p: Union[Path, str]) -> str:
    """Ensure path has normalized absolute format and uppercase drive letter on Windows."""
    resolved = str(Path(p).resolve())
    if len(resolved) >= 2 and resolved[1] == ":" and resolved[0].isalpha():
        return resolved[0].upper() + resolved[1:]
    return resolved


def is_infrastructure_flake(error_message: Optional[str]) -> bool:
    """Return True if error is caused by runner/network/browser infrastructure, never assertion failure.

    Gated strictly: assertion failures (expect(...).to...) are NEVER considered infrastructure flakes.
    """
    if not error_message:
        return False
    if is_assertion_failure(error_message):
        return False
    cleaned = clean_error_message(error_message).lower()
    infra_markers = [
        "econnrefused",
        "econnreset",
        "etimedout",
        "enotfound",
        "net::err_",
        "target closed",
        "browser closed",
        "browser has been closed",
        "browser.newcontext: timeout",
        "execution context was destroyed",
        "navigation timeout",
        "socket hang up",
        "connection refused",
        "err_name_not_resolved",
        "err_connection_refused",
        "err_connection_timed_out",
        "err_cert_",
        "502 bad gateway",
        "504 gateway timeout",
        "403 forbidden",
        "bad gateway",
        "dns resolution",
    ]
    return any(marker in cleaned for marker in infra_markers)


def parse_report(report_path: str) -> List[Dict[str, Any]]:
    """Walk a Playwright JSON report and return a flat list of test records with step-level telemetry."""
    p = Path(report_path)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    records: List[Dict[str, Any]] = []

    def walk_suite(suite: dict, parent_file: str = ""):
        file = suite.get("file", parent_file)
        for spec in suite.get("specs", []):
            spec_title = spec.get("title", "")
            spec_file = spec.get("file", file)
            for test_obj in spec.get("tests", []):
                for res in test_obj.get("results", []):
                    err_msg = ""
                    if res.get("errors"):
                        err_msg = "\n".join(e.get("message", "") for e in res["errors"])
                    elif res.get("error"):
                        err_msg = res["error"].get("message", "")

                    failed_step = None
                    failed_checkpoint = None
                    steps = res.get("steps", [])
                    total_steps = len(steps) if steps else None
                    if steps:
                        for s_idx, st in enumerate(steps, start=1):
                            if st.get("error") or st.get("errors"):
                                failed_step = s_idx
                                failed_checkpoint = st.get("title")
                                break

                    records.append({
                        "title": spec_title,
                        "file": spec_file,
                        "status": res.get("status", "failed"),
                        "durationMs": int(res.get("duration", 0)),
                        "errorMessage": err_msg,
                        "attachments": res.get("attachments", []),
                        "failedStep": failed_step,
                        "totalSteps": total_steps,
                        "checkpoint": failed_checkpoint,
                        "steps": steps,
                    })
        for child in suite.get("suites", []):
            walk_suite(child, file)

    for root_suite in data.get("suites", []):
        walk_suite(root_suite)

    return records


def run_playwright(
    run_id: str,
    *,
    files: Optional[List[str]] = None,
    grep: Optional[str] = None,
    workers: int = 4,
    spec_dir: Optional[str] = None,
    out_name: str = "main",
    extra_env: Optional[Dict[str, str]] = None,
    timeout_s: int = 900,
) -> RawRun:
    """Execute Playwright CLI in apps/runner/ directory with configured environment."""
    r_dir = storage.run_dir(run_id)
    raw_dir = r_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    test_results_dir = raw_dir / "test-results" / out_name
    test_results_dir.mkdir(parents=True, exist_ok=True)
    report_file = raw_dir / f"playwright-{out_name.replace('/', '_')}.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    run_input = storage.load_model(run_id, "input.json", RunInput)
    target_url = run_input.targetUrl if run_input else "http://localhost:4000"
    username = run_input.username if run_input else ""
    timeout_ms = (
        run_input.budgets.testTimeoutMs
        if run_input and run_input.budgets
        else settings.TEST_TIMEOUT_MS
    )

    try:
        secret_password = read_secret_password(run_id)
    except Exception:
        secret_password = ""

    if spec_dir is None:
        target_spec_dir = r_dir / "scripts"
    else:
        target_spec_dir = Path(spec_dir)
    target_spec_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["BASE_URL"] = target_url
    env["SPEC_DIR"] = normalize_path(target_spec_dir)
    env["OUTPUT_DIR"] = normalize_path(test_results_dir)
    env["JSON_REPORT"] = normalize_path(report_file)
    env["WORKERS"] = str(workers)
    env["TEST_TIMEOUT_MS"] = str(timeout_ms)
    env["ALLOWED_HOSTS"] = ",".join(settings.ALLOWED_HOSTS)
    env["BLOCKED_LOG"] = normalize_path(r_dir / "blocked_requests.jsonl")
    env["VISITED_DIR"] = normalize_path(raw_dir / "visited")
    env["TEST_USERNAME"] = username
    env["TEST_PASSWORD"] = secret_password
    live_dir = r_dir / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    env["LIVE_DIR"] = normalize_path(live_dir)

    if extra_env:
        env.update(extra_env)

    npx_bin = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    runner_cwd = normalize_path(settings.repo_root / "apps" / "runner")

    cmd = [npx_bin, "playwright", "test", "--config", "playwright.config.ts"]

    if files:
        for f in files:
            p = Path(f)
            if p.is_absolute():
                try:
                    rel_p = p.relative_to(target_spec_dir)
                    cmd.append(str(rel_p).replace("\\", "/"))
                except ValueError:
                    cmd.append(str(p).replace("\\", "/"))
            else:
                if (target_spec_dir / f).exists():
                    cmd.append(str(f).replace("\\", "/"))
                elif (r_dir / f).exists():
                    full_p = r_dir / f
                    try:
                        rel_p = full_p.relative_to(target_spec_dir)
                        cmd.append(str(rel_p).replace("\\", "/"))
                    except ValueError:
                        cmd.append(str(full_p).replace("\\", "/"))
                elif (target_spec_dir / p.name).exists():
                    cmd.append(p.name)
                else:
                    cmd.append(str(f).replace("\\", "/"))

    if grep:
        cmd.extend(["-g", grep])

    cmd.extend([f"--workers={workers}", "--retries=0"])

    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=runner_cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=True if os.name == "nt" else False,
        )
        duration = time.time() - start_time
        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return RawRun(
            exit_code=-9,
            report_path=None,
            stdout="",
            stderr="timeout",
            duration_s=duration,
        )
    except Exception as exc:
        duration = time.time() - start_time
        return RawRun(
            exit_code=1,
            report_path=None,
            stdout="",
            stderr=str(exc),
            duration_s=duration,
        )

    if secret_password:
        stdout = stdout.replace(secret_password, "***")
        stderr = stderr.replace(secret_password, "***")

    return RawRun(
        exit_code=exit_code,
        report_path=normalize_path(report_file) if report_file.exists() else None,
        stdout=stdout,
        stderr=stderr,
        duration_s=duration,
    )


def list_tests(run_id: str, file: str) -> ListResult:
    """Run playwright test <file> --list to verify script syntax and loadability."""
    file_path = Path(file)
    if not file_path.is_absolute():
        file_path = storage.run_dir(run_id) / file

    spec_folder = file_path.parent
    runner_cwd = normalize_path(settings.repo_root / "apps" / "runner")
    npx_bin = shutil.which("npx.cmd") or shutil.which("npx") or "npx"

    env = os.environ.copy()
    env["SPEC_DIR"] = normalize_path(spec_folder)
    env["ALLOWED_HOSTS"] = ",".join(settings.ALLOWED_HOSTS)

    try:
        rel_file = file_path.relative_to(spec_folder)
        file_arg = str(rel_file).replace("\\", "/")
    except ValueError:
        file_arg = str(file_path).replace("\\", "/")

    cmd = [
        npx_bin,
        "playwright",
        "test",
        "--config",
        "playwright.config.ts",
        file_arg,
        "--list",
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=runner_cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            shell=True if os.name == "nt" else False,
        )
        stdout = clean_error_message(proc.stdout)
        stderr = clean_error_message(proc.stderr)
        ok = proc.returncode == 0 and ("Total:" in stdout or "Listing tests:" in stdout)
        error = None
        if not ok:
            error = (stderr or stdout)[-1500:]
        return ListResult(ok=ok, error=error)
    except Exception as exc:
        return ListResult(ok=False, error=clean_error_message(str(exc))[-1500:])


def _clean_code_fence(raw_text: str) -> str:
    """Extract code from markdown code fences or return raw text."""
    trimmed = raw_text.strip()
    if "```" in trimmed:
        match = re.search(r"```(?:ts|typescript)?\s*([\s\S]*?)\s*```", trimmed, re.IGNORECASE)
        if match:
            trimmed = match.group(1).strip()
        else:
            trimmed = re.sub(r"^```(?:ts|typescript)?\s*", "", trimmed, flags=re.IGNORECASE).strip()
    clean_lines = [l for l in trimmed.splitlines() if not l.strip().startswith("```")]
    return "\n".join(clean_lines).strip()


def clean_and_sanitize_script(code: str, test_id: str, test_title: str) -> str:
    """Apply hard code-side guarantees: fixture imports, title prefix, forbidden patterns.
    
    AUTO-FIXES common LLM generation issues:
    - Absolute URLs → relative paths
    - Raw CSS selectors → getByRole/getByLabel/getByText
    - waitForTimeout() → page.waitForLoadState()
    """
    raw = _clean_code_fence(code)

    lines = raw.splitlines()
    body_lines = [line for line in lines if not re.match(r"^\s*import\s+", line)]
    cleaned_body = "\n".join(body_lines).strip()

    required_import = "import { test, expect, credentials, unique, expectErrorFeedback, expectNoErrorFeedback, expectSuccessFeedback, uniqueData, uniqueEmail, inspectPageForError, waitForPageReady, dismissConsentOverlays, findControl, expectThemeToggle, expectImagesLoaded, expectModalOpenClose, expectNavigationMenu } from '../../../apps/runner/fixtures';"
    full_code = f"{required_import}\n\n{cleaned_body}"

    clean_title = re.sub(r"^[A-Z]\d+:\s*", "", test_title).strip()
    clean_title = clean_title.replace("`", "").replace("'", "\\'").replace('"', '\\"')
    expected_prefix = f"{test_id}: "

    test_call_pattern = re.compile(r"test\s*\(\s*(['\"`])(.*?)\1", re.DOTALL)

    def _title_repl(m):
        quote = m.group(1)
        existing_t = m.group(2).strip()
        existing_t_clean = re.sub(r"^[A-Z]\d+:\s*", "", existing_t)
        existing_t_clean = existing_t_clean.replace("`", "").replace("'", "\\'").replace('"', '\\"')
        final_t = f"{expected_prefix}{existing_t_clean or clean_title}"
        return f"test({quote}{final_t}{quote}"

    full_code = test_call_pattern.sub(_title_repl, full_code, count=1)
    full_code = re.sub(r"\.fill\(\s*['\"]correctpass['\"]\s*\)", ".fill(credentials.password)", full_code)

    # AUTO-FIX: Absolute URLs → relative paths
    full_code = re.sub(r"https?://localhost(?::\d+)?(?=/|['\"])", "", full_code)
    full_code = re.sub(r"(['\"])//localhost(?::\d+)?", r"\1", full_code)

    # AUTO-FIX: page.querySelector() and page.$ → page.locator()
    full_code = re.sub(r"page\.\$\s*\(", "page.locator(", full_code)
    full_code = re.sub(r"page\.querySelector\s*\(", "page.locator(", full_code)

    # AUTO-FIX: Replace CSS selectors with getByRole when possible
    full_code = re.sub(r"page\.locator\s*\(\s*['\"]button['\"](?:\s*,\s*{[^}]*})?\s*\)", "page.getByRole('button')", full_code)
    full_code = re.sub(r"page\.locator\s*\(\s*['\"]input['\"](?:\s*,\s*{[^}]*})?\s*\)", "page.getByRole('textbox')", full_code)

    non_comment_lines = []
    for line in full_code.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("//"):
            continue
        non_comment_lines.append(line)
    code_for_checks = "\n".join(non_comment_lines)

    forbidden_patterns = [
        (r"\btest\.skip\b", "test.skip is forbidden"),
        (r"\btest\.fixme\b", "test.fixme is forbidden"),
        (r"\brequire\s*\(", "require() is forbidden"),
        (r"process\.env", "process.env is forbidden in generated tests"),
        (r"expect\(.*?\)\.catch\b", "Swallowing assertion errors with .catch() is forbidden"),
        (r"expect\.soft\b", "expect.soft() is forbidden; all expectations must be hard assertions"),
    ]

    for pat, msg in forbidden_patterns:
        if re.search(pat, code_for_checks):
            raise ValueError(msg)

    all_tests = re.findall(r"\btest\s*\(", code_for_checks)
    if len(all_tests) > 1:
        raise ValueError("Script must contain exactly one test() definition")

    return full_code


def find_ffmpeg_bin() -> Optional[str]:
    """Find system or Playwright-bundled ffmpeg executable."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    lad = os.environ.get("LOCALAPPDATA", "")
    if lad:
        for p in sorted(Path(lad).glob("ms-playwright/ffmpeg-*/ffmpeg*.exe"), reverse=True):
            if p.is_file():
                return str(p)
    pw_cache = Path.home() / ".cache" / "ms-playwright"
    if pw_cache.exists():
        for p in sorted(pw_cache.glob("ffmpeg-*/ffmpeg*"), reverse=True):
            if p.is_file() and os.access(p, os.X_OK):
                return str(p)
    return None


def post_process_video(src: Path, dest: Path) -> Tuple[float, str, Optional[str]]:
    """Remuxes raw WebM with ffmpeg stream copy to inject EBML segment duration metadata.
    
    Returns (duration_seconds, evidence_quality, evidence_reason).
    """
    ffmpeg_bin = find_ffmpeg_bin()
    duration_s = 0.0

    if ffmpeg_bin and src.exists():
        temp_dest = dest.with_suffix(".remux.webm")
        try:
            res = subprocess.run(
                [ffmpeg_bin, "-y", "-i", str(src), "-c", "copy", str(temp_dest)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode == 0 and temp_dest.exists() and temp_dest.stat().st_size > 0:
                shutil.move(str(temp_dest), str(dest))
            else:
                shutil.copy2(src, dest)
        except Exception:
            shutil.copy2(src, dest)
        finally:
            if temp_dest.exists():
                try:
                    temp_dest.unlink()
                except Exception:
                    pass

        try:
            info_res = subprocess.run(
                [ffmpeg_bin, "-i", str(dest)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", info_res.stderr)
            if m:
                h, mn, s = m.groups()
                duration_s = int(h) * 3600 + int(mn) * 60 + float(s)
        except Exception:
            pass
    elif src.exists():
        shutil.copy2(src, dest)

    if duration_s <= 0.0 and dest.exists():
        size_bytes = dest.stat().st_size
        if size_bytes > 50000:
            duration_s = round(size_bytes / 15000.0, 2)
        else:
            duration_s = round(max(0.1, size_bytes / 25000.0), 2)

    quality = "good"
    reason = None
    if duration_s < 1.5:
        quality = "poor"
        reason = f"Video duration ({duration_s:.2f}s) is shorter than the 1.5s evidentiary threshold."

    return round(duration_s, 2), quality, reason


def run_tests(
    run_id: str,
    workers: Optional[int] = None,
    include_probes: bool = False,
) -> Results:
    """Execute test suite against target app, record evidence, and return Results."""
    r_dir = storage.run_dir(run_id)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    catalog_map: Dict[str, TestCase] = {t.id: t for t in catalog.tests} if catalog else {}

    approved_tests = (
        [t for t in catalog.tests if t.status == "approved"]
        if catalog
        else []
    )

    storage.set_stage(
        run_id,
        "running",
        step="Running tests",
        done=0,
        total=len(approved_tests),
    )

    test_results: List[TestResult] = []
    tests_to_run: List[str] = []

    for t in approved_tests:
        if t.scriptStatus == "error":
            test_results.append(
                TestResult(
                    testId=t.id,
                    title=t.title,
                    file=t.script or f"scripts/{t.id}.spec.ts",
                    source="planned",
                    outcome="test_error",
                    durationMs=0,
                    errorMessage=f"Script did not load: {t.scriptError}",
                    evidenceDir=None,
                    depth=t.depth,
                    totalSteps=len(t.steps) if t.steps else 1,
                )
            )
        else:
            tests_to_run.append(t.id)

    # Exploratory tester: generate targeted mutations starting from deepest frontier states & journeys
    run_input = storage.load_model(run_id, "input.json", RunInput)
    target_url = run_input.targetUrl if run_input else "http://localhost:4000"
    app_map = storage.load_model(run_id, "app_map.json", AppMap)
    if app_map and (app_map.unexploredFrontier or app_map.journeys):
        try:
            from kawach.execution.exploratory import ExploratoryTester
            exp_tester = ExploratoryTester(run_id=run_id, budget_tests=5)
            exploratory_cases = exp_tester.plan_exploratory_tests(app_map)
            if exploratory_cases:
                exp_tester.generate_exploratory_specs(
                    exploratory_cases,
                    target_url=target_url,
                    scripts_dir=r_dir / "scripts",
                )
                for ec in exploratory_cases:
                    catalog_map[ec.id] = ec
                    tests_to_run.append(ec.id)
        except Exception:
            pass

    def _log(msg: str, **kwargs):
        try:
            from kawach.storage.artifacts import log_pipeline
            log_pipeline(run_id, msg, **kwargs)
        except Exception:
            pass

    is_local = "localhost" in target_url or "127.0.0.1" in target_url
    if workers is not None:
        num_workers = workers
    elif not is_local:
        num_workers = 2
    else:
        num_workers = 4
    _log(
        f"Runner: Dispatching {len(tests_to_run)} executable test specs across {num_workers} parallel Playwright workers...",
        source="runner",
    )
    start_wall = time.time()

    raw_run = run_playwright(
        run_id,
        workers=num_workers,
        out_name="main",
    )
    _log(
        f"Runner: Playwright execution batch finished in {time.time() - start_wall:.1f}s. Parsing reports and traces...",
        source="runner",
    )

    probes_run = None
    if include_probes:
        probes_dir = settings.repo_root / "apps" / "runner" / "probes"
        if probes_dir.exists():
            probes_run = run_playwright(
                run_id,
                spec_dir=normalize_path(probes_dir),
                out_name="probes",
                workers=1,
                extra_env={"APP_MAP_PATH": normalize_path(r_dir / "app_map.json")},
            )

    wall_duration = time.time() - start_wall

    records: List[Dict[str, Any]] = []
    if raw_run.report_path:
        records.extend(parse_report(raw_run.report_path))
    if probes_run and probes_run.report_path:
        records.extend(parse_report(probes_run.report_path))

    records_by_id: Dict[str, Dict[str, Any]] = {}
    for r in records:
        match = re.search(r"^(T|X)\d+", r["title"])
        if match:
            test_id = match.group(0)
            records_by_id[test_id] = r

    for test_id, r in records_by_id.items():
        source = "exploratory" if test_id.startswith("X") else "planned"
        status = r["status"]
        err_msg = clean_error_message(r["errorMessage"])

        test_case = catalog_map.get(test_id)
        depth = test_case.depth if test_case else 1
        failed_step = r.get("failedStep")
        total_steps = r.get("totalSteps")
        checkpoint = r.get("checkpoint")

        if total_steps is None and test_case and test_case.steps:
            total_steps = len(test_case.steps)

        # 1. Evidence extraction and remuxing for ALL tests (passed and failed)
        ev_dir = r_dir / "evidence" / test_id
        ev_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir_rel = f"evidence/{test_id}"

        video_dur = 0.0
        ev_quality = "good"
        ev_reason: Optional[str] = None
        console_items: List[str] = []
        network_items: Dict[str, Any] = {}
        control_check: Dict[str, Any] = {}

        for att in r.get("attachments", []):
            name = att.get("name", "")
            att_path = att.get("path")
            att_body = att.get("body")
            content_type = att.get("contentType", "")

            target_filename: Optional[str] = None
            file_type = "other"
            if content_type == "image/png" or name == "screenshot" or (att_path and Path(att_path).suffix == ".png"):
                target_filename = "screenshot.png"
                file_type = "screenshot"
            elif content_type == "video/webm" or name == "video" or (att_path and Path(att_path).suffix == ".webm"):
                target_filename = "video.webm"
                file_type = "screen_recording"
            elif content_type == "application/zip" or name == "trace" or (att_path and Path(att_path).name == "trace.zip"):
                target_filename = "trace.zip"
                file_type = "trace"
            elif name == "console.json":
                target_filename = "console.json"
                file_type = "log"
            elif name == "network.json":
                target_filename = "network.json"
                file_type = "log"
            elif name == "control_check.json":
                target_filename = "control_check.json"
                file_type = "log"

            if target_filename:
                dest = ev_dir / target_filename
                data_bytes = None
                if att_body:
                    try:
                        data_bytes = base64.b64decode(att_body)
                        dest.write_bytes(data_bytes)
                    except Exception:
                        pass
                elif att_path and Path(att_path).exists():
                    try:
                        data_bytes = Path(att_path).read_bytes()
                        dest.write_bytes(data_bytes)
                    except Exception:
                        pass

                # Post-process video to remux EBML duration header and measure duration
                if target_filename == "video.webm":
                    video_src = Path(att_path) if (att_path and Path(att_path).exists()) else dest
                    video_dur, ev_quality, ev_reason = post_process_video(video_src, dest)

                # Parse logs for verdict engine
                if target_filename == "console.json" and data_bytes:
                    try:
                        console_items = json.loads(data_bytes.decode("utf-8"))
                    except Exception:
                        pass
                elif target_filename == "network.json" and data_bytes:
                    try:
                        network_items = json.loads(data_bytes.decode("utf-8"))
                    except Exception:
                        pass
                elif target_filename == "control_check.json" and data_bytes:
                    try:
                        control_check = json.loads(data_bytes.decode("utf-8"))
                    except Exception:
                        pass

                # Persist in storage if database is available
                if data_bytes:
                    try:
                        from kawach.db.models.runs import Run as DbRun
                        from kawach.db.session import SessionLocal
                        from kawach.storage.file_storage import save_artifact_file

                        with SessionLocal() as db_session:
                            db_run = db_session.get(DbRun, run_id)
                            owner_user_id = (db_run.created_by if db_run and db_run.created_by else None) or "system"
                            proj_id = db_run.project_id if db_run else None
                            ext = Path(target_filename).suffix.lstrip(".")
                            save_artifact_file(
                                user_id=owner_user_id,
                                test_id=test_id,
                                data=data_bytes,
                                file_type=file_type,
                                ext=ext,
                                mime_type=content_type or None,
                                project_id=proj_id,
                                run_id=run_id,
                                db=db_session,
                            )
                            db_session.commit()
                    except Exception:
                        pass

        # 2. Structured Verdict Engine
        failure_type: Optional[str] = None
        if status == "passed":
            # Rule: Test with zero assertions executed can never be marked passed
            steps = r.get("steps", [])
            has_assertion = any(
                st.get("category") == "expect" or st.get("title", "").startswith("expect")
                for st in steps
            )
            if not has_assertion and steps:
                outcome: Outcome = "inconclusive"
                failure_type = "no_assertions"
                err_msg = "Inconclusive: Test finished without executing any expect assertions."
            else:
                # Check for unexpected first-party errors
                uncaught_list = []
                allowlist = ["favicon.ico", "download the react devtools", "chrome-extension://", "webpackhotupdate"]
                for cmsg in console_items:
                    cmsg_lower = str(cmsg).lower()
                    if any(al in cmsg_lower for al in allowlist):
                        continue
                    if "uncaught" in cmsg_lower or "typeerror:" in cmsg_lower or "referenceerror:" in cmsg_lower or "syntaxerror:" in cmsg_lower:
                        uncaught_list.append(cmsg)

                server_5xx = []
                for br in network_items.get("badResponses", []):
                    if isinstance(br, dict) and br.get("status", 0) >= 500:
                        server_5xx.append(br)

                if server_5xx:
                    outcome = "passed_with_issues"
                    failure_type = "server_error_5xx"
                    bad_st = server_5xx[0].get("status")
                    bad_u = server_5xx[0].get("url")
                    err_msg = f"Passed with issues: Server returned HTTP {bad_st} on {bad_u}"
                elif uncaught_list:
                    outcome = "passed_with_issues"
                    failure_type = "uncaught_exception"
                    err_msg = f"Passed with issues: Uncaught exception in page console: {uncaught_list[0]}"
                else:
                    outcome = "passed"
                    failure_type = None
        else:
            # Deterministic failure classification
            if is_infrastructure_flake(err_msg):
                outcome = "environment_error"
                failure_type = "environment_error"
            elif "before hooks" in err_msg.lower():
                outcome = "setup_error"
                failure_type = "setup_error"
            elif is_assertion_failure(err_msg):
                # Second-opinion check: Did the page actually exhibit expected feedback?
                # Applies to 'expected feedback not found' failures where page genuinely has alert/validity feedback
                is_feedback_failure = any(
                    k in err_msg.lower() or k in r["title"].lower()
                    for k in ("feedback", "error message", "reject", "invalid", "credential", "password", "validation", "alert", "toast")
                )
                if is_feedback_failure and control_check.get("found") is True:
                    outcome = "script_error"
                    failure_type = "script_error"
                    err_msg = f"Script oracle failure: Page exhibited expected feedback ({control_check.get('reason')}), but test expectation was too strict."
                else:
                    outcome = "assertion_failure"
                    failure_type = "assertion_failure"
            else:
                outcome = "script_error"
                failure_type = "script_error"

            if failed_step is not None and test_case and test_case.steps and 1 <= failed_step <= len(test_case.steps):
                if not checkpoint:
                    step_obj = test_case.steps[failed_step - 1]
                    checkpoint = step_obj.checkpoint or step_obj.action
            elif failed_step is None and test_case and test_case.steps:
                for s_idx, st in enumerate(test_case.steps, start=1):
                    if st.assertion or (st.checkpoint and st.checkpoint.lower() in err_msg.lower()):
                        failed_step = s_idx
                        checkpoint = st.checkpoint or st.action
                        break
                if failed_step is None:
                    failed_step = len(test_case.steps)
                    checkpoint = test_case.steps[-1].checkpoint or test_case.steps[-1].action

            if outcome in ("script_error", "setup_error") and video_dur < 1.5:
                ev_reason = f"Poor video duration caused by script error / crash: {err_msg[:60]}"

        test_results.append(
            TestResult(
                testId=test_id,
                title=r["title"],
                file=r["file"],
                source=source,
                outcome=outcome,
                durationMs=r["durationMs"],
                errorMessage=err_msg if err_msg else None,
                evidenceDir=evidence_dir_rel,
                failedStep=failed_step,
                totalSteps=total_steps,
                depth=depth,
                checkpoint=checkpoint,
                videoDuration=video_dur,
                evidenceQuality=ev_quality,
                evidenceReason=ev_reason,
                failureType=failure_type,
            )
        )

    recorded_ids = set(t.testId for t in test_results)
    for t in approved_tests:
        if t.id not in recorded_ids:
            is_script_err = t.scriptStatus == "error"
            outcome = "script_error" if is_script_err else "not_run"
            err_msg = t.scriptError if is_script_err else "Not run: skipped by test runner"
            test_results.append(
                TestResult(
                    testId=t.id,
                    title=t.title,
                    file=t.script or f"scripts/{t.id}.spec.ts",
                    source="planned",
                    outcome=outcome,
                    durationMs=0,
                    errorMessage=err_msg,
                    evidenceDir=None,
                    depth=t.depth,
                    totalSteps=len(t.steps) if t.steps else 1,
                    failureType=outcome,
                )
            )

    # -------------------------------------------------------------------------
    # In-Suite Circuit Breaker Check:
    # -------------------------------------------------------------------------
    # If 3 or more consecutive tests fail with environment errors on initial step / navigation,
    # or all executed tests failed on initial step with environment errors:
    # Abort remaining tests as 'not_run', record an environment issue, and set stage to 'done_with_environment_issue'.
    env_failed_step1 = [
        t for t in test_results
        if t.outcome == "environment_error" and (t.failedStep is None or t.failedStep <= 1)
    ]
    is_circuit_broken = False
    if len(env_failed_step1) >= 3 or (
        len(test_results) > 0
        and len(env_failed_step1) == len(test_results)
        and all(t.outcome == "environment_error" for t in test_results)
    ):
        is_circuit_broken = True

    if is_circuit_broken and env_failed_step1:
        first_err = env_failed_step1[0].errorMessage or ""
        first_err_l = first_err.lower()
        if "err_name_not_resolved" in first_err_l or "dns" in first_err_l:
            classification = "dns_error"
        elif "err_cert_" in first_err_l or "ssl" in first_err_l or "tls" in first_err_l:
            classification = "tls_error"
        elif "502" in first_err_l or "504" in first_err_l or "bad gateway" in first_err_l:
            classification = "bad_gateway_from_target"
        elif "403" in first_err_l or "waf" in first_err_l or "forbidden" in first_err_l:
            classification = "blocked_by_waf"
        elif "timeout" in first_err_l or "timed out" in first_err_l:
            classification = "timeout"
        else:
            classification = "target_unreachable"

        _log(
            f"Circuit Breaker TRIPPED: In-suite consecutive environment errors detected ({classification}). Aborting remaining tests as not_run.",
            level="error",
            source="runner",
        )

        first_test_id = env_failed_step1[0].testId
        for t in test_results:
            if t.testId != first_test_id and t.outcome == "environment_error":
                t.outcome = "not_run"
                t.failureType = "not_run"
                t.errorMessage = f"Aborted by in-suite circuit breaker: target unreachable ({classification})."

        from kawach.execution.circuit_breaker import generate_owner_guidance
        guidance = generate_owner_guidance(classification, target_url)
        finding = {
            "title": f"Target not testable: {classification}",
            "classification": classification,
            "reason": f"In-suite circuit breaker tripped: consecutive tests failed on initial navigation with {first_err[:250]}.",
            "targetUrl": target_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "guidance": guidance,
            "origin": "target",
        }
        finding_file = r_dir / "environment_issue.json"
        with open(finding_file, "w", encoding="utf-8") as f:
            json.dump(finding, f, indent=2)

        storage.set_stage(
            run_id,
            "done_with_environment_issue",  # type: ignore
            step=f"Target not testable: {classification} ({first_err[:120]})",
        )

    # 1. Retry infrastructure flakes (network timeouts, connection refused, browser context drops)
    # Strictly gated: assertion failures are NEVER retried, and bypassed if circuit breaker tripped.
    infra_flakes = [
        t for t in test_results
        if t.outcome == "test_error" and is_infrastructure_flake(t.errorMessage)
    ] if not is_circuit_broken else []
    if infra_flakes:
        _log(f"Runner: Detected {len(infra_flakes)} infrastructure flake(s). Attempting 1-time automated infra retry...", source="runner")
        for t in infra_flakes:
            retry_run = run_playwright(
                run_id,
                grep=f"{t.testId}:",
                out_name=f"infra_retry_{t.testId}",
                workers=1,
                timeout_s=30,
            )
            if retry_run.report_path:
                re_records = parse_report(retry_run.report_path)
                match_rec = next((rec for rec in re_records if t.testId in rec.get("title", "")), None)
                if match_rec and match_rec.get("status") == "passed":
                    t.outcome = "passed"
                    t.errorMessage = None
                    t.durationMs = int(match_rec.get("durationMs", 0))
                    _log(f"Runner: {t.testId} passed after infrastructure retry.", source="runner")

    # 2. Self-Healing: For test_error scripts with syntax/locator timeouts (NOT assertion failures and NOT infra flakes)
    recoverable_failures = [
        t for t in test_results
        if t.outcome == "test_error" and t.testId.startswith("T") and not is_infrastructure_flake(t.errorMessage)
    ] if not is_circuit_broken else []

    if recoverable_failures:
        _log(
            f"Self-Healing: Detected {len(recoverable_failures)} locator timeout / syntax error(s). Requesting 1-time automated repair from LLM...",
            source="runner",
        )
        for t in recoverable_failures:
            script_path = r_dir / "scripts" / f"{t.testId}.spec.ts"
            if not script_path.exists():
                continue
            original_code = script_path.read_text(encoding="utf-8")
            repair_prompt = (
                f"You are an expert Playwright TypeScript engineer. A test script failed execution due to a locator timeout, syntax error, or timing issue.\n\n"
                f"Test ID: {t.testId}\n"
                f"Test Title: {t.title}\n"
                f"Execution Error / Stack Trace:\n{t.errorMessage or 'Locator timeout or execution error'}\n\n"
                f"Current Failed Script:\n{original_code}\n\n"
                "TASK:\n"
                "Analyze the failure and fix the locator timeout, missing wait/navigation, or syntax issue.\n"
                "RULES:\n"
                "1. If an action timed out (e.g. waiting for 'Log out' or waiting for an element), ensure proper preceding actions completed, wait for URL/navigation if needed, or check the right locator.\n"
                "2. Maintain the exact same test intent and KEEP ALL CORE ASSERTIONS intact. Do not remove expectations or invert checks.\n"
                "3. Return ONLY valid TypeScript code starting with import and test(). No explanations.\n"
            )
            try:
                from kawach.llm import get_llm
                llm = get_llm()
                fixed_code_raw = llm.complete_text(
                    system="You are an expert Playwright TypeScript automation engineer.",
                    prompt=repair_prompt,
                    schema_name="script_writer",
                    run_id=run_id,
                    max_tokens=1500,
                    temperature=0.1,
                )
                fixed_code = clean_and_sanitize_script(fixed_code_raw, t.testId, t.title)
                script_path.write_text(fixed_code, encoding="utf-8")

                _log(f"Self-Healing: Re-running repaired script for {t.testId} (single retry attempt)...", source="runner")
                retry_run = run_playwright(
                    run_id,
                    grep=f"{t.testId}:",
                    out_name=f"retry_{t.testId}",
                    workers=1,
                    timeout_s=30,
                )
                if retry_run.report_path:
                    re_records = parse_report(retry_run.report_path)
                    match_rec = next((rec for rec in re_records if t.testId in rec.get("title", "")), None)
                    if match_rec:
                        re_status = match_rec.get("status")
                        re_err = clean_error_message(match_rec.get("errorMessage", ""))
                        if re_status == "passed":
                            t.outcome = "passed"
                            t.errorMessage = None
                            t.durationMs = int(match_rec.get("durationMs", 0))
                            _log(f"Self-Healing: {t.testId} PASSED on retry after LLM repair!", source="runner")
                        elif is_assertion_failure(re_err):
                            t.outcome = "assertion_failure"
                            t.failureType = "assertion_failure"
                            t.errorMessage = re_err
                            t.durationMs = int(match_rec.get("durationMs", 0))
                            ev_dir = r_dir / "evidence" / t.testId
                            ev_dir.mkdir(parents=True, exist_ok=True)
                            t.evidenceDir = f"evidence/{t.testId}"
                            for att in match_rec.get("attachments", []):
                                apath = att.get("path")
                                aname = att.get("name", "")
                                if apath and Path(apath).exists():
                                    if aname == "video" or Path(apath).suffix == ".webm":
                                        v_dur, ev_q, ev_r = post_process_video(Path(apath), ev_dir / "video.webm")
                                        t.videoDuration = v_dur
                                        t.evidenceQuality = ev_q
                                        t.evidenceReason = ev_r
                                    elif aname == "screenshot" or Path(apath).suffix == ".png":
                                        shutil.copy2(Path(apath), ev_dir / "screenshot.png")
                                    elif aname == "trace" or Path(apath).suffix == ".zip":
                                        shutil.copy2(Path(apath), ev_dir / "trace.zip")
                            _log(f"Self-Healing: {t.testId} repaired; confirmed application assertion failure.", source="runner")
                        else:
                            t.outcome = "script_error"
                            t.failureType = "script_error"
                            t.errorMessage = f"Persistent execution failure after 1 repair attempt: {re_err}"
                            _log(f"Self-Healing: {t.testId} still failed after 1 repair attempt. Excluded from bugs and flagged as environment/target infrastructure defect.", level="warn", source="runner")

                        live_json_path = r_dir / "live" / f"{t.testId}.json"
                        if live_json_path.exists():
                            try:
                                with open(live_json_path, "r", encoding="utf-8") as jf:
                                    ldata = json.load(jf)
                                ldata["status"] = t.outcome
                                ldata["duration_ms"] = t.durationMs
                                ldata["error_message"] = t.errorMessage
                                with open(live_json_path, "w", encoding="utf-8") as jf:
                                    json.dump(ldata, jf, indent=2)
                            except Exception:
                                pass
            except Exception as repair_exc:
                _log(f"Self-Healing: Repair attempt for {t.testId} encountered error: {repair_exc}", level="warn", source="runner")

    test_results.sort(key=lambda x: x.testId)

    summary = ResultsSummary(
        total=len(test_results),
        passed=sum(1 for t in test_results if t.outcome == "passed"),
        passedWithIssues=sum(1 for t in test_results if t.outcome == "passed_with_issues"),
        failed=sum(1 for t in test_results if t.outcome in ("failed", "assertion_failure")),
        assertionFailures=sum(1 for t in test_results if t.outcome == "assertion_failure"),
        testErrors=sum(1 for t in test_results if t.outcome == "test_error"),
        scriptErrors=sum(1 for t in test_results if t.outcome == "script_error"),
        setupErrors=sum(1 for t in test_results if t.outcome == "setup_error"),
        environmentErrors=sum(1 for t in test_results if t.outcome == "environment_error"),
        flaky=sum(1 for t in test_results if t.outcome == "flaky"),
        inconclusive=sum(1 for t in test_results if t.outcome == "inconclusive"),
        notRun=sum(1 for t in test_results if t.outcome == "not_run"),
    )

    results_obj = Results(
        runId=run_id,
        startedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_wall)),
        durationSeconds=round(wall_duration, 2),
        workers=num_workers,
        tests=test_results,
        summary=summary,
    )

    storage.save_model(run_id, "results.json", results_obj)
    return results_obj

