"""Subprocess client for the Playwright runner in runner/.

Handles executing Playwright test suites, listing tests, parsing reports,
extracting evidence, classifying test failures vs assertion failures, and triaging bugs.
"""

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Union

from app.config import settings
from app.models import (
    Bug,
    BugReplay,
    BugsFile,
    Catalog,
    Evidence,
    Outcome,
    Results,
    ResultsSummary,
    RunInput,
    TestResult,
)
from app import storage

ANSI_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


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


def clean_error_message(msg: Optional[str]) -> str:
    """Strip ANSI escape codes and leading/trailing whitespace."""
    if not msg:
        return ""
    return ANSI_REGEX.sub("", msg).strip()


def is_assertion_failure(error_message: str) -> bool:
    r"""Return True if the error matches expect() assertion pattern and is not a timeout.

    Follows CONTRACTS.md Section 9:
    Matches r"expect\(.*?\)\.(not\.)?to\w+" and does NOT begin with "Test timeout of".
    """
    cleaned = clean_error_message(error_message)
    if cleaned.startswith("Test timeout of"):
        return False
    return bool(re.search(r"expect\(.*?\)\.(not\.)?to\w+", cleaned, re.DOTALL))


def signature(error_message: str) -> str:
    """Compute 10-hex SHA1 error signature following CONTRACTS.md Section 9.

    Take first 400 characters of cleaned message,
    replace runs of 4+ digits with 'N',
    replace patterns like [a-z]+-\\d{13}-[a-z0-9]{4} with 'U',
    collapse whitespace, lower-case, sha1 and keep 10 hex characters.
    """
    cleaned = clean_error_message(error_message)[:400]
    cleaned = re.sub(r"[a-z]+-\d{13}-[a-z0-9]{4}", "U", cleaned)
    cleaned = re.sub(r"\d{4,}", "N", cleaned)
    cleaned = " ".join(cleaned.split()).lower()
    return hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:10]


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
    """Execute Playwright CLI in runner/ directory with configured environment."""
    r_dir = storage.run_dir(run_id)
    raw_dir = r_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    test_results_dir = raw_dir / "test-results" / out_name
    test_results_dir.mkdir(parents=True, exist_ok=True)
    report_file = raw_dir / f"playwright-{out_name.replace('/', '_')}.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    # Load input configuration
    run_input = storage.load_model(run_id, "input.json", RunInput)
    target_url = run_input.targetUrl if run_input else "http://localhost:4000"
    username = run_input.username if run_input else ""
    timeout_ms = (
        run_input.budgets.testTimeoutMs
        if run_input and run_input.budgets
        else settings.TEST_TIMEOUT_MS
    )

    try:
        secret_password = storage.read_secret_password(run_id)
    except Exception:
        secret_password = ""

    # Default spec_dir to runs/<id>/scripts
    if spec_dir is None:
        target_spec_dir = r_dir / "scripts"
    else:
        target_spec_dir = Path(spec_dir)
    target_spec_dir.mkdir(parents=True, exist_ok=True)

    # Build environment
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

    if extra_env:
        env.update(extra_env)

    # Locate npx
    npx_bin = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    runner_cwd = normalize_path(settings.repo_root / "runner")

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

    # Mask password
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
    runner_cwd = normalize_path(settings.repo_root / "runner")
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

    num_workers = workers if workers is not None else 4
    start_wall = time.time()

    raw_run = run_playwright(
        run_id,
        workers=num_workers,
        out_name="main",
    )

    probes_run = None
    if include_probes:
        probes_dir = settings.repo_root / "runner" / "probes"
        if probes_dir.exists():
            probes_run = run_playwright(
                run_id,
                spec_dir=normalize_path(probes_dir),
                out_name="probes",
                workers=1,
                extra_env={"APP_MAP_PATH": normalize_path(r_dir / "app_map.json")},
            )

    wall_duration = time.time() - start_wall

    # Parse reports
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

    # Process each recorded result
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

    # Any approved test case with no result recorded gets test_error
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


def triage(run_id: str) -> List[Bug]:
    """Triage test results into assertion failures (candidates) and de-duplicate."""
    results_obj = storage.load_model(run_id, "results.json", Results)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    catalog_map = {t.id: t for t in catalog.tests} if catalog else {}

    r_dir = storage.run_dir(run_id)
    candidate_failures = [
        t for t in (results_obj.tests if results_obj else [])
        if t.outcome == "assertion_failure"
    ]

    candidate_bugs: List[Bug] = []

    for t in candidate_failures:
        test_case = catalog_map.get(t.testId)
        title = test_case.title if test_case else t.title
        spec_ref = test_case.specRef if test_case else []
        steps = [s.action for s in test_case.steps] if test_case else []

        expected = ""
        if test_case and test_case.steps:
            for s in reversed(test_case.steps):
                if s.expected:
                    expected = s.expected
                    break

        cleaned_err = clean_error_message(t.errorMessage or "")
        first_line = cleaned_err.split("\n")[0] if cleaned_err else ""
        err_sig = signature(cleaned_err)

        # Check evidence files
        ev_dir = r_dir / "evidence" / t.testId
        ev_obj = Evidence(
            screenshot=f"evidence/{t.testId}/screenshot.png" if (ev_dir / "screenshot.png").exists() else None,
            video=f"evidence/{t.testId}/video.webm" if (ev_dir / "video.webm").exists() else None,
            trace=f"evidence/{t.testId}/trace.zip" if (ev_dir / "trace.zip").exists() else None,
            console=f"evidence/{t.testId}/console.json" if (ev_dir / "console.json").exists() else None,
            network=f"evidence/{t.testId}/network.json" if (ev_dir / "network.json").exists() else None,
        )

        candidate_bugs.append(
            Bug(
                id="",  # assigned after deduplication
                testId=t.testId,
                source=t.source,
                title=title,
                grep=f"{t.testId}:",
                file=f"scripts/{t.testId}.spec.ts",
                category="other",
                severity="medium",
                specRef=spec_ref,
                steps=steps,
                expected=expected,
                actual=first_line,
                errorMessage=cleaned_err[:3000],
                signature=err_sig,
                duplicates=[],
                evidence=ev_obj,
                status="candidate",
                replay=None,
            )
        )

    # De-duplicate by signature
    seen_sigs: Dict[str, Bug] = {}
    unique_bugs: List[Bug] = []

    for b in candidate_bugs:
        if b.signature in seen_sigs:
            seen_sigs[b.signature].duplicates.append(b.testId)
        else:
            seen_sigs[b.signature] = b
            unique_bugs.append(b)

    # Assign IDs B01, B02, ...
    for idx, b in enumerate(unique_bugs, start=1):
        b.id = f"B{idx:02d}"

    bugs_file = BugsFile(runId=run_id, bugs=unique_bugs)
    storage.save_model(run_id, "bugs.json", bugs_file)
    return unique_bugs
