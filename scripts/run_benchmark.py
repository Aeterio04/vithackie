#!/usr/bin/env python3
"""KAWACH Reliability Benchmark Runner

Measures pipeline fidelity, oracle robustness, video quality, and stale data isolation.
Usage:
    python scripts/run_benchmark.py [--repeat N] [--probes-only] [--clean-only] [--buggy-only] [--gate-check]
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = REPO_ROOT / "qa_benchmark"
SHOP_DIR = BENCHMARK_DIR / "shop"
PROBES_SPEC = BENCHMARK_DIR / "probes" / "probes.spec.ts"
GROUND_TRUTH_FILE = BENCHMARK_DIR / "ground_truth.json"
SPEC_FILE = BENCHMARK_DIR / "spec.md"
RUNNER_DIR = REPO_ROOT / "apps" / "runner"

API_BASE = os.environ.get("KAWACH_API_URL", "http://localhost:8000")
SHOP_BASE = os.environ.get("BENCHMARK_SHOP_URL", "http://localhost:3100")

ALL_PLANTED_BUGS = [
    "login-no-error",
    "cart-total-wrong",
    "signup-accepts-invalid-email",
    "checkout-500",
    "silent-console-error",
    "broken-image",
    "flaky-random",
    "price-format",
]


def find_ffmpeg_bin() -> Optional[str]:
    """Locate ffmpeg binary in ms-playwright cache or PATH."""
    system_bin = shutil.which("ffmpeg")
    if system_bin:
        return system_bin
    user_home = os.path.expanduser("~")
    matches = glob.glob(os.path.join(user_home, "AppData", "Local", "ms-playwright", "**", "ffmpeg*.exe"), recursive=True)
    if matches:
        return matches[0]
    return None


def get_video_duration(video_path: Path) -> float:
    """Extract real duration in seconds using ffmpeg or container parsing."""
    if not video_path.exists() or video_path.stat().st_size == 0:
        return 0.0
    ffmpeg_bin = find_ffmpeg_bin()
    if ffmpeg_bin:
        try:
            res = subprocess.run(
                [ffmpeg_bin, "-i", str(video_path)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = res.stderr or res.stdout
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
            if match:
                hrs, mins, secs = match.groups()
                return float(hrs) * 3600 + float(mins) * 60 + float(secs)
        except Exception:
            pass
    return 0.1 if video_path.stat().st_size > 0 else 0.0


class BenchmarkShopController:
    """Manages local shop test app lifecycle with feature toggle env."""

    def __init__(self, port: int = 3100):
        self.port = port
        self.proc: Optional[subprocess.Popen] = None

    def start(self, bugs: List[str]) -> None:
        self.stop()
        env = os.environ.copy()
        env["PORT"] = str(self.port)
        env["BUGS"] = ",".join(bugs)
        node_bin = shutil.which("node") or "node"
        server_js = str(SHOP_DIR / "server.js")

        self.proc = subprocess.Popen(
            [node_bin, server_js],
            cwd=str(SHOP_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for shop to accept connections
        url = f"http://localhost:{self.port}/"
        for _ in range(30):
            try:
                r = requests.get(url, timeout=1)
                if r.status_code == 200:
                    return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError(f"Benchmark shop failed to start on port {self.port}")

    def stop(self) -> None:
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        # Also clean up any lingering processes on Windows
        if os.name == "nt":
            try:
                subprocess.run(
                    f'powershell -Command "Get-Process node -ErrorAction SilentlyContinue | Where-Object {{ $_.CommandLine -like \'*qa_benchmark*\' }} | Stop-Process -Force"',
                    shell=True,
                    capture_output=True,
                )
            except Exception:
                pass


class BenchmarkClient:
    """Interacts with KAWACH backend API."""

    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None
        self.session = requests.Session()

    def authenticate(self, email: str = "benchmark@example.com", password: str = "BenchmarkPass123!") -> str:
        # Try login
        login_url = f"{self.base_url}/api/v1/auth/login"
        r = self.session.post(login_url, json={"email": email, "password": password})
        if r.status_code == 200:
            data = r.json()
            self.token = data.get("token") or data.get("access_token")
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            return self.token

        # Register if needed
        reg_url = f"{self.base_url}/api/v1/auth/register"
        r = self.session.post(reg_url, json={"email": email, "password": password, "displayName": "Benchmark Agent"})
        if r.status_code in (200, 201):
            data = r.json()
            self.token = data.get("token") or data.get("access_token")
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            return self.token

        raise RuntimeError(f"Authentication failed: {r.status_code} {r.text}")

    def create_run(self, target_url: str, spec_text: str, project_id: Optional[str] = None) -> str:
        url = f"{self.base_url}/api/v1/runs"
        payload = {
            "target_url": target_url,
            "review_mode": "autonomous",
            "spec_text": spec_text,
            "prompt": "Full autonomous QA verification for ShopDemo application.",
            "credentials": {
                "username": "qa.tester@example.com",
                "password": "Password123!",
            },
            "budgets": {
                "max_pages": 8,
                "explore_seconds": 25,
                "max_tests": 12,
                "test_timeout_ms": 30000,
            },
        }
        if project_id:
            payload["project_id"] = project_id
        r = self.session.post(url, json=payload)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Run creation failed: {r.status_code} {r.text}")
        data = r.json()
        return data.get("id") or data.get("runId")

    def wait_for_run(self, run_id: str, timeout_sec: int = 650) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/runs/{run_id}"
        start = time.time()
        while time.time() - start < timeout_sec:
            r = self.session.get(url)
            if r.status_code == 200:
                data = r.json()
                stage = data.get("stage")
                status = data.get("status")
                if stage in ("done", "completed", "failed", "cancelled") or status in ("completed", "failed", "done"):
                    return data
            time.sleep(2)
        raise TimeoutError(f"Run {run_id} timed out after {timeout_sec}s")

    def get_run_results(self, run_id: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/runs/{run_id}/results"
        r = self.session.get(url)
        return r.json() if r.status_code == 200 else None

    def get_run_bugs(self, run_id: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/runs/{run_id}/bugs"
        r = self.session.get(url)
        if r.status_code == 200:
            res = r.json()
            return res.get("bugs", res) if isinstance(res, dict) else res
        return []


def run_probe_suite(shop_url: str, is_buggy: bool) -> Dict[str, Any]:
    """Run hand-written probes through Playwright test runner and check accuracy."""
    report_file = REPO_ROOT / "test-results" / ("probes_buggy.json" if is_buggy else "probes_clean.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)

    spec_dir = str(BENCHMARK_DIR / "probes")
    if len(spec_dir) >= 2 and spec_dir[1] == ":" and spec_dir[0].isalpha():
        spec_dir = spec_dir[0].upper() + spec_dir[1:]

    env = os.environ.copy()
    env["SPEC_DIR"] = spec_dir
    env["BASE_URL"] = shop_url
    env["JSON_REPORT"] = str(report_file)
    env["WORKERS"] = "4"

    cmd = ["npx.cmd" if os.name == "nt" else "npx", "playwright", "test"]
    proc = subprocess.run(
        cmd,
        cwd=str(RUNNER_DIR),
        env=env,
        capture_output=True,
        text=True,
        shell=True if os.name == "nt" else False,
    )

    probe_results = {}
    if report_file.exists():
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                data = json.load(f)

                def get_all_specs(suite_list):
                    collected = []
                    for s in suite_list:
                        collected.extend(s.get("specs", []))
                        if s.get("suites"):
                            collected.extend(get_all_specs(s["suites"]))
                    return collected

                all_specs = get_all_specs(data.get("suites", []))
                for spec in all_specs:
                    title = spec.get("title", "")
                    match = re.search(r"P\d+", title)
                    probe_id = match.group(0) if match else title
                    tests = spec.get("tests", [])
                    status = "unknown"
                    if tests:
                        results = tests[0].get("results", [])
                        if results:
                            status = results[0].get("status", "unknown")
                    probe_results[probe_id] = {
                        "title": title,
                        "status": status,
                    }
        except Exception:
            pass

    # Expected probe statuses
    # Clean: All 12 probes PASS
    # Buggy: P01(FAIL), P02(FAIL), P03(FAIL), P04(PASS), P05(PASS), P06(PASS), P07(FAIL), P08(PASS), P09(FAIL), P10(FAIL), P11(FAIL), P12(FAIL)
    expected_buggy_failures = {"P01", "P02", "P03", "P07", "P09", "P10", "P11", "P12"}
    expected_clean_failures = set()

    expected_failures = expected_buggy_failures if is_buggy else expected_clean_failures
    correct = 0
    total = len(probe_results) or 12

    evaluations = {}
    for pid, res in probe_results.items():
        actual_pass = res["status"] == "passed"
        expected_pass = pid not in expected_failures
        is_accurate = (actual_pass == expected_pass)
        if is_accurate:
            correct += 1
        evaluations[pid] = {
            "title": res["title"],
            "actual": res["status"],
            "expected": "passed" if expected_pass else "failed",
            "accurate": is_accurate,
        }

    accuracy_pct = round((correct / total) * 100, 1) if total else 0.0
    return {
        "accuracy_pct": accuracy_pct,
        "correct": correct,
        "total": total,
        "evaluations": evaluations,
        "exit_code": proc.returncode,
    }


def evaluate_run_artifacts(run_id: str, ground_truth: Dict[str, Any], is_clean: bool) -> Dict[str, Any]:
    """Inspect disk artifacts, evidence, videos, console logs, and bug confirmations."""
    run_dir = REPO_ROOT / "runs" / run_id
    if not run_dir.exists():
        return {
            "error": f"Run directory {run_dir} not found",
            "confirmed_bugs": 0,
            "false_positives": 0,
            "silent_passes": 0,
            "videos_valid": 0,
            "videos_total": 0,
        }

    # 1. Load results.json
    results_path = run_dir / "results.json"
    results = {}
    if results_path.exists():
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                results = json.load(f)
        except Exception:
            pass

    # 2. Inspect video files
    video_files = list(run_dir.glob("evidence/*/video.webm")) + list(run_dir.glob("verification/*/video.webm")) + list(run_dir.glob("verification/*/trial_*/video.webm"))
    videos_valid = 0
    video_durations = []
    video_table = []
    test_results_map = {t.get("testId"): t for t in results.get("tests", [])}

    for vf in video_files:
        dur = get_video_duration(vf)
        video_durations.append(dur)
        parent_id = vf.parent.name
        t_obj = test_results_map.get(parent_id, {})
        test_dur = (t_obj.get("durationMs", 0) / 1000.0)
        ev_q = t_obj.get("evidenceQuality", "good")
        ev_r = t_obj.get("evidenceReason")

        is_valid = False
        if dur >= 1.5 or (test_dur > 0 and dur >= 0.8 * test_dur):
            is_valid = True
        elif ev_q == "poor" and ev_r:
            is_valid = True  # Accounted for with valid recorded reason

        if is_valid:
            videos_valid += 1

        video_table.append({
            "file": str(vf.relative_to(run_dir)),
            "test_duration": round(test_dur, 2),
            "video_duration": round(dur, 2),
            "ratio": round(dur / max(0.01, test_dur), 2) if test_dur else 1.0,
            "quality": ev_q,
            "reason": ev_r,
            "valid": is_valid,
        })

    # 3. Detect silent passes (tests marked 'passed' despite uncaught pageerror / console.error / 4xx/5xx)
    silent_passes = 0
    tests = results.get("tests", [])
    for t in tests:
        outcome = t.get("outcome") or t.get("status")
        tid = t.get("testId") or t.get("id")
        if outcome == "passed" and tid:
            # Check attached console and network evidence
            ev_dir = run_dir / "evidence" / tid
            console_file = ev_dir / "console.json"
            network_file = ev_dir / "network.json"

            has_error = False
            if console_file.exists():
                try:
                    with open(console_file, "r", encoding="utf-8") as cf:
                        c_entries = json.load(cf)
                        if any("Uncaught" in str(e) or "TypeError" in str(e) for e in c_entries):
                            has_error = True
                except Exception:
                    pass

            if network_file.exists():
                try:
                    with open(network_file, "r", encoding="utf-8") as nf:
                        n_data = json.load(nf)
                        bad_resps = n_data.get("badResponses", [])
                        if any(r.get("status", 0) >= 500 for r in bad_resps):
                            has_error = True
                except Exception:
                    pass

            if has_error:
                silent_passes += 1

    # 4. Check Bugs & Confirmations
    bugs_path = run_dir / "bugs.json"
    reported_bugs = []
    if bugs_path.exists():
        try:
            with open(bugs_path, "r", encoding="utf-8") as bf:
                bugs_data = json.load(bf)
                reported_bugs = bugs_data.get("bugs", bugs_data) if isinstance(bugs_data, dict) else bugs_data
        except Exception:
            pass

    confirmed_bugs = []
    false_positives = []
    flaky_bugs = []

    defects = ground_truth.get("defects", [])
    must_not_flag = ground_truth.get("must_not_flag", [])

    for b in reported_bugs:
        b_status = b.get("status")
        title = (b.get("title") or "").lower()
        err_m = (b.get("errorMessage") or "").lower()
        act_m = (b.get("actual") or "").lower()
        combined = f"{title} {err_m} {act_m}"

        is_confirmed = b_status in ("confirmed", "verified")
        if b_status == "flaky":
            flaky_bugs.append(b)

        # Check against must_not_flag (K1 to K8)
        matched_good = next((k for k in must_not_flag if k["id"].lower() in combined or any(w in combined for w in k["name"].split("-"))), None)
        if matched_good or (is_clean and is_confirmed):
            false_positives.append({
                "bug": b,
                "rule": matched_good or "clean-shop-violation",
            })

        if is_confirmed:
            confirmed_bugs.append(b)

    # Calculate recall on planted defects
    detected_planted = set()
    for b in confirmed_bugs:
        combined = f"{b.get('title', '')} {b.get('errorMessage', '')} {b.get('actual', '')} {b.get('expected', '')} {' '.join(b.get('steps', []))}".lower()
        for d in defects:
            if d.get("expected_status", "confirmed") == "confirmed":
                if any(kw in combined for kw in d["keywords"]):
                    detected_planted.add(d["id"])

    # Include B7 flaky detection (Gate G3: flaky defect detected and marked flaky)
    for b in flaky_bugs:
        combined = f"{b.get('title', '')} {b.get('errorMessage', '')} {b.get('actual', '')} {b.get('expected', '')} {' '.join(b.get('steps', []))}".lower()
        for d in defects:
            if d.get("expected_status") == "flaky":
                if any(kw in combined for kw in d["keywords"]):
                    detected_planted.add(d["id"])

    # Include B5 passed_with_issues detection (Gate G3: silent uncaught error detected)
    for t in tests:
        if t.get("outcome") == "passed_with_issues":
            combined = f"{t.get('title', '')} {t.get('errorMessage', '')}".lower()
            for d in defects:
                if d.get("expected_status") == "passed_with_issues":
                    if any(kw in combined for kw in d["keywords"]) or any(k in combined for k in ("console", "telemetry", "typeerror", "uncaught")):
                        detected_planted.add(d["id"])

    recall_pct = round((len(detected_planted) / len(defects)) * 100, 1) if defects else 0.0
    confirmed_planted = len([b for b in confirmed_bugs if any(any(kw in f"{b.get('title', '')} {b.get('errorMessage', '')} {b.get('actual', '')}".lower() for kw in d['keywords']) for d in defects)])
    precision_pct = 100.0 if not confirmed_bugs and is_clean else round((confirmed_planted / max(1, len(confirmed_bugs))) * 100, 1)

    return {
        "run_id": run_id,
        "is_clean": is_clean,
        "total_tests": len(tests),
        "total_bugs": len(reported_bugs),
        "confirmed_bugs": len(confirmed_bugs),
        "false_positives": len(false_positives),
        "flaky_bugs": len(flaky_bugs),
        "silent_passes": silent_passes,
        "detected_planted": list(detected_planted),
        "recall_pct": recall_pct,
        "precision_pct": precision_pct,
        "videos_total": len(video_files),
        "videos_valid": videos_valid,
        "video_durations": video_durations,
        "video_table": video_table,
    }


def main():
    parser = argparse.ArgumentParser(description="KAWACH Reliability Benchmark Suite")
    parser.add_argument("--repeat", type=int, default=1, help="Repetitions for each mode")
    parser.add_argument("--probes-only", action="store_true", help="Run only probe tests")
    parser.add_argument("--clean-only", action="store_true", help="Run only clean shop")
    parser.add_argument("--buggy-only", action="store_true", help="Run only buggy shop")
    parser.add_argument("--gate-check", action="store_true", help="Enforce quality gates and exit non-zero on failure")
    parser.add_argument("--shop-port", type=int, default=3100, help="Benchmark shop port")
    args = parser.parse_args()

    overall_start = time.time()
    shop_url = f"http://localhost:{args.shop_port}"

    print("=" * 72)
    print("  KAWACH END-TO-END QA RELIABILITY BENCHMARK")
    print(f"  Target Shop: {shop_url} | Backend API: {API_BASE}")
    print(f"  Repeat: {args.repeat} | Probes Only: {args.probes_only} | Gate Check: {args.gate_check}")
    print("=" * 72)

    with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    with open(SPEC_FILE, "r", encoding="utf-8") as f:
        spec_text = f.read()

    shop = BenchmarkShopController(port=args.shop_port)
    client = BenchmarkClient(base_url=API_BASE)

    try:
        token = client.authenticate()
        print(f"[*] Authenticated with KAWACH API (Token acquired)")
    except Exception as e:
        print(f"[-] Failed to authenticate with KAWACH API: {e}")
        if not args.probes_only:
            sys.exit(1)

    clean_probe_eval = {}
    buggy_probe_eval = {}
    clean_runs = []
    buggy_runs = []

    # 1. RUN CLEAN SHOP
    if not args.buggy_only:
        print("\n[+] Starting Benchmark Shop in CLEAN mode...")
        shop.start(bugs=[])
        print(f"[*] Shop active at {shop_url} (BUGS=none)")

        print("[*] Running Deterministic Playwright Probes on Clean Shop...")
        clean_probe_eval = run_probe_suite(shop_url, is_buggy=False)
        print(f"    Clean Probes Accuracy: {clean_probe_eval['accuracy_pct']}% ({clean_probe_eval['correct']}/{clean_probe_eval['total']})")

        if not args.probes_only:
            for i in range(args.repeat):
                print(f"\n[*] Executing KAWACH Autonomous Run {i+1}/{args.repeat} against Clean Shop...")
                try:
                    run_id = client.create_run(target_url=shop_url, spec_text=spec_text)
                    print(f"    Run initiated: {run_id}")
                    client.wait_for_run(run_id)
                    print(f"    Run completed: {run_id}")
                    art = evaluate_run_artifacts(run_id, ground_truth, is_clean=True)
                    clean_runs.append(art)
                    print(f"    Confirmed Bugs: {art['confirmed_bugs']} (False Positives: {art['false_positives']}) | Silent Passes: {art['silent_passes']}")
                except Exception as e:
                    print(f"[-] Run execution failed: {e}")

    # 2. RUN BUGGY SHOP
    if not args.clean_only:
        print("\n[+] Starting Benchmark Shop in BUGGY mode...")
        shop.start(bugs=ALL_PLANTED_BUGS)
        print(f"[*] Shop active at {shop_url} (BUGS={','.join(ALL_PLANTED_BUGS)})")

        print("[*] Running Deterministic Playwright Probes on Buggy Shop...")
        buggy_probe_eval = run_probe_suite(shop_url, is_buggy=True)
        print(f"    Buggy Probes Accuracy: {buggy_probe_eval['accuracy_pct']}% ({buggy_probe_eval['correct']}/{buggy_probe_eval['total']})")

        if not args.probes_only:
            for i in range(args.repeat):
                print(f"\n[*] Executing KAWACH Autonomous Run {i+1}/{args.repeat} against Buggy Shop...")
                try:
                    run_id = client.create_run(target_url=shop_url, spec_text=spec_text)
                    print(f"    Run initiated: {run_id}")
                    client.wait_for_run(run_id)
                    print(f"    Run completed: {run_id}")
                    art = evaluate_run_artifacts(run_id, ground_truth, is_clean=False)
                    buggy_runs.append(art)
                    print(f"    Confirmed Bugs: {art['confirmed_bugs']} (Planted Detected: {art['detected_planted']}) | Silent Passes: {art['silent_passes']}")
                except Exception as e:
                    print(f"[-] Run execution failed: {e}")

    shop.stop()
    total_duration = round(time.time() - overall_start, 1)

    # 3. SCORECARD AGGREGATION
    print("\n" + "=" * 72)
    print("                      BENCHMARK SCORECARD")
    print("=" * 72)

    probe_acc = 0.0
    if clean_probe_eval and buggy_probe_eval:
        probe_acc = round((clean_probe_eval["accuracy_pct"] + buggy_probe_eval["accuracy_pct"]) / 2, 1)
    elif clean_probe_eval:
        probe_acc = clean_probe_eval["accuracy_pct"]
    elif buggy_probe_eval:
        probe_acc = buggy_probe_eval["accuracy_pct"]

    total_clean_fps = sum(r["false_positives"] for r in clean_runs)
    total_clean_confirmed = sum(r["confirmed_bugs"] for r in clean_runs)

    avg_recall = round(sum(r["recall_pct"] for r in buggy_runs) / max(1, len(buggy_runs)), 1) if buggy_runs else 0.0
    avg_precision = round(sum(r["precision_pct"] for r in buggy_runs) / max(1, len(buggy_runs)), 1) if buggy_runs else 0.0
    total_silent_passes = sum(r["silent_passes"] for r in clean_runs + buggy_runs)

    total_videos = sum(r["videos_total"] for r in clean_runs + buggy_runs)
    valid_videos = sum(r["videos_valid"] for r in clean_runs + buggy_runs)
    video_ratio_pct = round((valid_videos / max(1, total_videos)) * 100, 1)

    print(f"| Metric                                | Value            | Gate Target     |")
    print(f"|---------------------------------------|------------------|-----------------|")
    print(f"| Probe Verdict Accuracy                | {probe_acc}%           | 100%            |")
    print(f"| Clean Shop False Positive Bugs        | {total_clean_confirmed}                | 0               |")
    print(f"| Buggy Shop Defect Recall              | {avg_recall}%           | >= 85%          |")
    print(f"| Buggy Shop Precision                  | {avg_precision}%           | 100%            |")
    print(f"| Silent Passes (Uncaught Errors)       | {total_silent_passes}                | 0               |")
    print(f"| Valid Videos (Duration >= 1.5s)       | {video_ratio_pct}% ({valid_videos}/{total_videos}) | 100%            |")
    print(f"| Total Benchmark Execution Time        | {total_duration}s            | -               |")
    print("=" * 72)

    # 4. GATE CHECKS (G1 to G8)
    gate_failures = []
    if probe_acc < 100.0:
        gate_failures.append(f"G4 Failed: Probe Accuracy {probe_acc}% < 100%")
    if total_clean_confirmed > 0:
        gate_failures.append(f"G1 Failed: Clean shop reported {total_clean_confirmed} confirmed bugs")
    if avg_recall < 85.0 and buggy_runs:
        gate_failures.append(f"G2 Failed: Defect recall {avg_recall}% < 85%")
    if total_silent_passes > 0:
        gate_failures.append(f"G5 Failed: Detected {total_silent_passes} silent passes")
    if video_ratio_pct < 100.0 and total_videos > 0:
        gate_failures.append(f"G6 Failed: Valid video ratio {video_ratio_pct}% < 100%")

    scorecard_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe_accuracy_pct": probe_acc,
        "clean_false_positives": total_clean_confirmed,
        "buggy_recall_pct": avg_recall,
        "buggy_precision_pct": avg_precision,
        "silent_passes": total_silent_passes,
        "videos_total": total_videos,
        "videos_valid": valid_videos,
        "video_valid_pct": video_ratio_pct,
        "total_runtime_s": total_duration,
        "gate_failures": gate_failures,
    }

    out_json = BENCHMARK_DIR / "scorecard_latest.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(scorecard_data, f, indent=2)
    print(f"Scorecard saved to {out_json}")

    if args.gate_check and gate_failures:
        print("\n[-] GATES FAILED:")
        for gf in gate_failures:
            print(f"    - {gf}")
        sys.exit(1)
    else:
        print("\n[+] Benchmark finished successfully.")


if __name__ == "__main__":
    main()
