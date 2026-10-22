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
import subprocess
import time
from typing import Any, Dict, List, Optional, Union

from kawach.core.config import settings
from kawach.execution.triage import clean_error_message, is_assertion_failure
from kawach.schemas import (
    Catalog,
    Outcome,
    Results,
    ResultsSummary,
    RunInput,
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


def parse_report(report_path: str) -> List[Dict[str, Any]]:
    """Walk a Playwright JSON report and return a flat list of test records."""
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

                    records.append({
                        "title": spec_title,
                        "file": spec_file,
                        "status": res.get("status", "failed"),
                        "durationMs": int(res.get("duration", 0)),
                        "errorMessage": err_msg,
                        "attachments": res.get("attachments", []),
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
                full_p = r_dir / f
                try:
                    rel_p = full_p.relative_to(target_spec_dir)
                    cmd.append(str(rel_p).replace("\\", "/"))
                except ValueError:
                    cmd.append(str(full_p).replace("\\", "/"))

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


def run_tests(
    run_id: str,
    workers: Optional[int] = None,
    include_probes: bool = False,
) -> Results:
    """Execute test suite against target app, record evidence, and return Results."""
    r_dir = storage.run_dir(run_id)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
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
                )
            )
        else:
            tests_to_run.append(t.id)

def _clean_code_fence(raw_text: str) -> str:
    """Extract code from markdown code fences or return raw text."""
    trimmed = raw_text.strip()
    if "```" in trimmed:
        match = re.search(r"```(?:ts|typescript)?\s*([\s\S]*?)\s*```", trimmed, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return trimmed


def clean_and_sanitize_script(code: str, test_id: str, test_title: str) -> str:
    """Apply hard code-side guarantees: fixture imports, title prefix, forbidden patterns."""
    raw = _clean_code_fence(code)

    lines = raw.splitlines()
    body_lines = [line for line in lines if not re.match(r"^\s*import\s+", line)]
    cleaned_body = "\n".join(body_lines).strip()

    required_import = "import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';"
    full_code = f"{required_import}\n\n{cleaned_body}"

    clean_title = re.sub(r"^[A-Z]\d+:\s*", "", test_title).strip()
    expected_prefix = f"{test_id}: "

    test_call_pattern = re.compile(r"test\s*\(\s*(['\"`])(.*?)\1", re.DOTALL)

    def _title_repl(m):
        quote = m.group(1)
        existing_t = m.group(2).strip()
        existing_t_clean = re.sub(r"^[A-Z]\d+:\s*", "", existing_t)
        final_t = f"{expected_prefix}{existing_t_clean or clean_title}"
        return f"test({quote}{final_t}{quote}"

    full_code = test_call_pattern.sub(_title_repl, full_code, count=1)
    full_code = re.sub(r"\.fill\(\s*['\"]correctpass['\"]\s*\)", ".fill(credentials.password)", full_code)

    non_comment_lines = []
    for line in full_code.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("//"):
            continue
        non_comment_lines.append(line)
    code_for_checks = "\n".join(non_comment_lines)

    forbidden_patterns = [
        (r"waitForTimeout", "waitForTimeout is forbidden; use web-first assertions"),
        (r"\btest\.skip\b", "test.skip is forbidden"),
        (r"\btest\.fixme\b", "test.fixme is forbidden"),
        (r"\brequire\s*\(", "require() is forbidden"),
        (r"process\.env", "process.env is forbidden in generated tests"),
        (r"https?://", "Absolute URLs are forbidden; use relative paths"),
        (r"page\.locator\s*\(\s*['\"][#\.\w]", "Raw CSS/XPath selectors forbidden; use getByRole/Label/Text"),
    ]

    for pat, msg in forbidden_patterns:
        if re.search(pat, code_for_checks):
            raise ValueError(msg)

    all_tests = re.findall(r"\btest\s*\(", code_for_checks)
    if len(all_tests) > 1:
        raise ValueError("Script must contain exactly one test() definition")

    return full_code


    def _log(msg: str, **kwargs):
        try:
            from kawach.storage.artifacts import log_pipeline
            log_pipeline(run_id, msg, **kwargs)
        except Exception:
            pass

    num_workers = workers if workers is not None else 4
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

        if status == "passed":
            outcome: Outcome = "passed"
        elif is_assertion_failure(err_msg):
            outcome = "assertion_failure"
        else:
            outcome = "test_error"

        evidence_dir_rel: Optional[str] = None
        if outcome != "passed":
            ev_dir = r_dir / "evidence" / test_id
            ev_dir.mkdir(parents=True, exist_ok=True)
            evidence_dir_rel = f"evidence/{test_id}"

            for att in r["attachments"]:
                name = att.get("name", "")
                att_path = att.get("path")
                att_body = att.get("body")
                content_type = att.get("contentType", "")

                target_filename: Optional[str] = None
                if content_type == "image/png" or name == "screenshot" or (att_path and Path(att_path).suffix == ".png"):
                    target_filename = "screenshot.png"
                elif content_type == "video/webm" or name == "video" or (att_path and Path(att_path).suffix == ".webm"):
                    target_filename = "video.webm"
                elif content_type == "application/zip" or name == "trace" or (att_path and Path(att_path).name == "trace.zip"):
                    target_filename = "trace.zip"
                elif name == "console.json":
                    target_filename = "console.json"
                elif name == "network.json":
                    target_filename = "network.json"

                if target_filename:
                    dest = ev_dir / target_filename
                    if att_body:
                        try:
                            data = base64.b64decode(att_body)
                            dest.write_bytes(data)
                        except Exception:
                            pass
                    elif att_path and Path(att_path).exists():
                        shutil.copy2(Path(att_path), dest)

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
            )
        )

    recorded_ids = set(t.testId for t in test_results)
    for t in approved_tests:
        if t.id not in recorded_ids:
            test_results.append(
                TestResult(
                    testId=t.id,
                    title=t.title,
                    file=t.script or f"scripts/{t.id}.spec.ts",
                    source="planned",
                    outcome="test_error",
                    durationMs=0,
                    errorMessage="No result recorded",
                    evidenceDir=None,
                )
            )

    recoverable_failures = [
        t for t in test_results
        if t.outcome == "test_error" and t.testId.startswith("T")
    ]

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
                    max_tokens=750,
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
                            t.errorMessage = re_err
                            t.durationMs = int(match_rec.get("durationMs", 0))
                            ev_dir = r_dir / "evidence" / t.testId
                            ev_dir.mkdir(parents=True, exist_ok=True)
                            t.evidenceDir = f"evidence/{t.testId}"
                            _log(f"Self-Healing: {t.testId} repaired; confirmed application assertion failure.", source="runner")
                        else:
                            t.outcome = "test_error"
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
        assertionFailures=sum(1 for t in test_results if t.outcome == "assertion_failure"),
        testErrors=sum(1 for t in test_results if t.outcome == "test_error"),
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
