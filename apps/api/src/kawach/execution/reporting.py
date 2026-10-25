"""Report builder and metrics aggregator service.

Deterministic: Reads files from run folder and produces metrics.json and report.md.
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from kawach.core.config import settings
from kawach.schemas import (
    AppMap,
    Benchmark,
    BugsFile,
    Bug,
    Catalog,
    LlmUsage,
    Metrics,
    MetricsBugs,
    MetricsCoverage,
    MetricsSafety,
    MetricsTests,
    ParallelTiming,
    Results,
    ReviewLog,
    Run,
    RunInput,
    TestCase,
    TestResult,
)
from kawach.storage import artifacts as storage


def _escape_cell(text: Any, max_len: int = 200) -> str:
    """Sanitize and clamp string for Markdown table cells."""
    if text is None:
        return ""
    s = str(text).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    s = s.replace("|", "\\|")
    s = " ".join(s.split())
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _parse_iso(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        clean = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return None


def build_metrics(run_id: str) -> Metrics:
    """Calculate and persist execution metrics to metrics.json for a given run."""
    run = storage.load_model(run_id, "run.json", Run)
    run_input = storage.load_model(run_id, "input.json", RunInput)
    app_map = storage.load_model(run_id, "app_map.json", AppMap)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    results = storage.load_model(run_id, "results.json", Results)
    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)

    stage_seconds: Dict[str, float] = {}
    all_starts: List[datetime] = []
    all_ends: List[datetime] = []

    if run and run.stageTimes:
        for stage_name, st in run.stageTimes.items():
            dt_start = _parse_iso(st.startedAt)
            dt_end = _parse_iso(st.endedAt)
            if dt_start:
                all_starts.append(dt_start)
            if dt_end:
                all_ends.append(dt_end)
            if dt_start and dt_end:
                diff = max(0.0, (dt_end - dt_start).total_seconds())
                stage_seconds[stage_name] = round(diff, 1)
            else:
                stage_seconds[stage_name] = 0.0

    wall_clock = 0.0
    if all_starts:
        first_start = min(all_starts)
        last_end = max(all_ends) if all_ends else datetime.now(first_start.tzinfo)
        wall_clock = max(0.0, round((last_end - first_start).total_seconds(), 1))

    planned_count = len(catalog.tests) if catalog else 0
    approved_count = sum(1 for t in catalog.tests if t.status == "approved") if catalog else 0

    passed_count = 0
    failed_count = 0
    errored_count = 0

    if results and results.tests:
        for t in results.tests:
            if t.outcome == "passed":
                passed_count += 1
            elif t.outcome in ("assertion_failure", "failed"):
                failed_count += 1
            elif t.outcome in ("test_error", "script_error", "setup_error", "environment_error"):
                errored_count += 1

    tests_metrics = MetricsTests(
        planned=planned_count,
        approved=approved_count,
        passed=passed_count,
        failed=failed_count,
        errored=errored_count,
    )

    bugs_list = bugs_file.bugs if bugs_file else []
    candidates_count = len(bugs_list)
    confirmed_count = sum(1 for b in bugs_list if b.status == "confirmed")
    flaky_count = sum(1 for b in bugs_list if b.status == "flaky")
    not_reproduced_count = sum(1 for b in bugs_list if b.status == "not_reproduced")

    bugs_metrics = MetricsBugs(
        candidates=candidates_count,
        confirmed=confirmed_count,
        flaky=flaky_count,
        notReproduced=not_reproduced_count,
    )

    pages_in_map = len(app_map.pages) if app_map else 0
    forms_in_map = sum(len(p.forms) for p in app_map.pages) if app_map else 0

    visited_urls: Set[str] = set()
    run_folder = storage.run_dir(run_id)
    visited_dir = run_folder / "raw" / "visited"
    if not visited_dir.exists():
        visited_dir = run_folder / "visited"

    if visited_dir.exists():
        for vf in visited_dir.glob("*.json"):
            try:
                with open(vf, "r", encoding="utf-8") as f:
                    urls = json.load(f)
                    if isinstance(urls, list):
                        visited_urls.update(str(u) for u in urls)
            except Exception:
                continue

    pages_exercised = 0
    forms_exercised = 0
    if app_map and app_map.pages:
        for p in app_map.pages:
            exercised = False
            if p.url in visited_urls or p.path in visited_urls or any(p.path in u for u in visited_urls):
                exercised = True
            elif results and results.tests and len(results.tests) > 0:
                exercised = True
            if exercised:
                pages_exercised += 1
                forms_exercised += len(p.forms)

    pages_exercised = min(pages_exercised, pages_in_map)
    forms_exercised = min(forms_exercised, forms_in_map)

    spec_items_total = len(run_input.spec) if run_input else 0
    covered_spec_ids: Set[str] = set()
    if catalog:
        for t in catalog.tests:
            if t.status == "approved":
                covered_spec_ids.update(t.specRef)

    spec_covered_count = len(covered_spec_ids)

    coverage_metrics = MetricsCoverage(
        pagesInMap=pages_in_map,
        pagesExercised=pages_exercised,
        formsInMap=forms_in_map,
        formsExercised=forms_exercised,
        specItems=spec_items_total,
        specItemsCovered=spec_covered_count,
    )

    llm_usage = storage.load_model(run_id, "llm_usage.json", LlmUsage)
    if not llm_usage:
        llm_usage = LlmUsage()

    parallel_timing = storage.load_model(run_id, "parallel.json", ParallelTiming)

    blocked_requests_path = run_folder / "blocked_requests.jsonl"
    blocked_count = 0
    if blocked_requests_path.exists():
        try:
            with open(blocked_requests_path, "r", encoding="utf-8") as f:
                blocked_count = sum(1 for line in f if line.strip())
        except Exception:
            blocked_count = 0

    safety_metrics = MetricsSafety(blockedRequests=blocked_count)

    metrics = Metrics(
        runId=run_id,
        wallClockSeconds=wall_clock,
        stageSeconds=stage_seconds,
        tests=tests_metrics,
        bugs=bugs_metrics,
        coverage=coverage_metrics,
        llm=llm_usage,
        parallel=parallel_timing,
        safety=safety_metrics,
    )

    storage.save_model(run_id, "metrics.json", metrics)
    return metrics


def build_report(run_id: str) -> str:
    """Generate comprehensive report (report.md, report.html, report.pdf) and return markdown."""
    from kawach.execution.report_generator import generate_all_reports
    res = generate_all_reports(run_id)
    if res.get("status") == "ready" and res.get("markdown"):
        return res["markdown"]
    return _legacy_build_report(run_id)


def _legacy_build_report(run_id: str) -> str:
    """Fallback legacy markdown report builder."""
    run = storage.load_model(run_id, "run.json", Run)
    run_input = storage.load_model(run_id, "input.json", RunInput)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    results = storage.load_model(run_id, "results.json", Results)
    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
    review_log = storage.load_model(run_id, "review_log.json", ReviewLog)
    benchmark = storage.load_model(run_id, "benchmark.json", Benchmark)
    metrics = build_metrics(run_id)

    run_folder = storage.run_dir(run_id)
    target_url = run.targetUrl if run else (run_input.targetUrl if run_input else "http://localhost:4000")
    run_mode = run.mode if run else (run_input.mode if run_input else "manual")
    created_at = run.createdAt if run else (run_input.createdAt if run_input else "2026-10-18T00:00:00Z")

    bugs_list = bugs_file.bugs if bugs_file else []
    confirmed_bugs = [b for b in bugs_list if b.status == "confirmed"]
    flaky_bugs = [b for b in bugs_list if b.status == "flaky"]
    unconfirmed_bugs = [b for b in bugs_list if b.status == "not_reproduced"]

    sev_weight = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    confirmed_bugs.sort(key=lambda b: (sev_weight.get(b.severity, 4), b.id))
    flaky_bugs.sort(key=lambda b: (sev_weight.get(b.severity, 4), b.id))
    unconfirmed_bugs.sort(key=lambda b: (sev_weight.get(b.severity, 4), b.id))

    lines: List[str] = []

    lines.append(f"# QA Report: {target_url}")
    lines.append(f"**Run ID:** `{run_id}` | **Mode:** `{run_mode}` | **Date:** `{created_at}`")

    if confirmed_bugs or flaky_bugs or unconfirmed_bugs:
        parts: List[str] = []
        if confirmed_bugs:
            parts.append(f"{len(confirmed_bugs)} confirmed")
        if flaky_bugs:
            parts.append(f"{len(flaky_bugs)} flaky")
        if unconfirmed_bugs:
            parts.append(f"{len(unconfirmed_bugs)} not reproduced")
        verdict = f"**Verdict:** {', '.join(parts)} bugs"
    else:
        verdict = "**Verdict:** No bugs were confirmed."
    lines.append(verdict)
    lines.append("")

    lines.append("## Summary")
    total_executed = metrics.tests.passed + metrics.tests.failed + metrics.tests.errored
    lines.append(
        f"- **Tests:** {total_executed} executed | {metrics.tests.passed} passed | "
        f"{metrics.tests.failed} assertion failures | {metrics.tests.errored} test errors"
    )
    lines.append(f"- **Wall-clock execution time:** {metrics.wallClockSeconds:.1f}s")
    lines.append(
        f"- **Application map coverage:** {metrics.coverage.pagesExercised}/{metrics.coverage.pagesInMap} pages, "
        f"{metrics.coverage.formsExercised}/{metrics.coverage.formsInMap} forms"
    )
    lines.append(
        f"- **Specification requirements covered:** {metrics.coverage.specItemsCovered} of "
        f"{metrics.coverage.specItems} items"
    )

    cost_str = f"${metrics.llm.costUsd:.2f}"
    if metrics.llm.costUsd == 0 and settings.LLM_PROVIDER == "fake":
        cost_str = "n/a (fake provider)"
    lines.append(
        f"- **LLM usage:** {metrics.llm.calls} calls | {metrics.llm.inputTokens} input tokens | "
        f"{metrics.llm.outputTokens} output tokens | {cost_str}"
    )
    lines.append("")

    lines.append("## Confirmed bugs")
    if not confirmed_bugs:
        lines.append("No confirmed bugs.")
        lines.append("")
    else:
        for b in confirmed_bugs:
            lines.append(f"### {b.id} · {b.severity} · {b.category}: {b.title}")
            repro_count = b.replay.reproduced if b.replay else 3
            lines.append(f"- **Replay:** reproduced {repro_count} of 3.")
            lines.append(f"- **Spec:** {', '.join(b.specRef) if b.specRef else 'None'}")
            if b.steps:
                lines.append("- **Steps:**")
                for idx, step_text in enumerate(b.steps, 1):
                    lines.append(f"  {idx}. {step_text}")
            lines.append(f"- **Expected:** {b.expected}")
            lines.append(f"- **Actual:** {b.actual}")

            evidence_links: List[str] = []
            ev = b.evidence
            if ev:
                for label, rel_path in [
                    ("screenshot", ev.screenshot),
                    ("video", ev.video),
                    ("trace", ev.trace),
                    ("console", ev.console),
                    ("network", ev.network),
                ]:
                    if rel_path and (run_folder / rel_path).exists():
                        evidence_links.append(f"[{label}]({rel_path})")

            if b.file and (run_folder / b.file).exists():
                evidence_links.append(f"[script]({b.file})")

            if evidence_links:
                lines.append(f"- **Evidence:** {' | '.join(evidence_links)}")

            if ev and ev.screenshot and (run_folder / ev.screenshot).exists():
                lines.append(f"\n![{b.id} Evidence Screenshot]({ev.screenshot})\n")

            if b.duplicates:
                lines.append(f"- **Also seen in:** {', '.join(b.duplicates)}")
            if b.source == "exploratory":
                lines.append("- **Note:** Exploratory finding")

            if b.errorMessage:
                err_preview = b.errorMessage.strip()
                if len(err_preview) > 400:
                    err_lines = err_preview.split("\n")[:15]
                    err_preview = "\n".join(err_lines)
                lines.append("```text")
                lines.append(err_preview)
                lines.append("```")
            lines.append("")

    lines.append("## Flaky bugs")
    if not flaky_bugs:
        lines.append("No flaky bugs.")
        lines.append("")
    else:
        for b in flaky_bugs:
            lines.append(f"### {b.id} · {b.severity} · {b.category}: {b.title}")
            repro_count = b.replay.reproduced if b.replay else 2
            lines.append(f"- **Replay:** reproduced {repro_count} of 3 replays.")
            lines.append(f"- **Spec:** {', '.join(b.specRef) if b.specRef else 'None'}")
            if b.steps:
                lines.append("- **Steps:**")
                for idx, step_text in enumerate(b.steps, 1):
                    lines.append(f"  {idx}. {step_text}")
            lines.append(f"- **Expected:** {b.expected}")
            lines.append(f"- **Actual:** {b.actual}")

            evidence_links = []
            ev = b.evidence
            if ev:
                for label, rel_path in [
                    ("screenshot", ev.screenshot),
                    ("video", ev.video),
                    ("trace", ev.trace),
                    ("console", ev.console),
                    ("network", ev.network),
                ]:
                    if rel_path and (run_folder / rel_path).exists():
                        evidence_links.append(f"[{label}]({rel_path})")

            if b.file and (run_folder / b.file).exists():
                evidence_links.append(f"[script]({b.file})")

            if evidence_links:
                lines.append(f"- **Evidence:** {' | '.join(evidence_links)}")

            if ev and ev.screenshot and (run_folder / ev.screenshot).exists():
                lines.append(f"\n![{b.id} Evidence Screenshot]({ev.screenshot})\n")
            if b.duplicates:
                lines.append(f"- **Also seen in:** {', '.join(b.duplicates)}")
            lines.append("")

    lines.append("## Not reproduced")
    if not unconfirmed_bugs:
        lines.append("None.")
        lines.append("")
    else:
        lines.append("| Bug ID | Title | Test ID |")
        lines.append("| --- | --- | --- |")
        for b in unconfirmed_bugs:
            lines.append(f"| {_escape_cell(b.id)} | {_escape_cell(b.title)} | {_escape_cell(b.testId)} |")
        lines.append("")
        lines.append("*These failed once but not on replay. Treat as unconfirmed.*")
        lines.append("")

    lines.append("## Test results")
    lines.append("| ID | Title | Spec Items | Outcome | Duration (s) |")
    lines.append("| --- | --- | --- | --- | --- |")

    test_errors_list: List[TestResult] = []

    results_map: Dict[str, TestResult] = {}
    if results and results.tests:
        for tr in results.tests:
            results_map[tr.testId] = tr

    all_seen_test_ids: Set[str] = set()
    if catalog and catalog.tests:
        for t in catalog.tests:
            all_seen_test_ids.add(t.id)
            tr = results_map.get(t.id)
            if t.status == "rejected":
                outcome_str = "not run (rejected)"
                dur_str = "0.0"
            elif tr:
                dur_str = f"{tr.durationMs / 1000.0:.2f}"
                if tr.outcome == "passed":
                    outcome_str = "✅ Passed"
                elif tr.outcome == "assertion_failure":
                    outcome_str = "❌ Bug (Assertion Failure)"
                else:
                    outcome_str = "⚠️ Test Error"
                    test_errors_list.append(tr)
            else:
                outcome_str = "pending"
                dur_str = "0.0"

            spec_joined = ", ".join(t.specRef) if t.specRef else "-"
            lines.append(
                f"| {_escape_cell(t.id)} | {_escape_cell(t.title)} | {_escape_cell(spec_joined)} | "
                f"{_escape_cell(outcome_str)} | {dur_str} |"
            )

    if results and results.tests:
        for tr in results.tests:
            if tr.testId not in all_seen_test_ids:
                dur_str = f"{tr.durationMs / 1000.0:.2f}"
                if tr.outcome == "passed":
                    outcome_str = "✅ Passed"
                elif tr.outcome == "assertion_failure":
                    outcome_str = "❌ Bug (Assertion Failure)"
                else:
                    outcome_str = "⚠️ Test Error"
                    test_errors_list.append(tr)

                lines.append(
                    f"| {_escape_cell(tr.testId)} | {_escape_cell(tr.title)} | exploratory | "
                    f"{_escape_cell(outcome_str)} | {dur_str} |"
                )

    lines.append("")

    if test_errors_list:
        lines.append("### Test Errors")
        for te in test_errors_list:
            reason = te.errorMessage or "Execution failed"
            reason_first_line = reason.strip().split("\n")[0][:200]
            lines.append(f"- **{te.testId}:** `{reason_first_line}`")
        lines.append("")

    lines.append("## Coverage")
    lines.append("| Spec ID | Requirement | Tests | Result |")
    lines.append("| --- | --- | --- | --- |")

    spec_items = run_input.spec if run_input else []
    for spec in spec_items:
        covering_tests = [t.id for t in (catalog.tests if catalog else []) if spec.id in t.specRef and t.status == "approved"]
        tests_cell = ", ".join(covering_tests) if covering_tests else "None"

        if not covering_tests:
            result_str = "Not Covered"
        else:
            has_bug = any(b.testId in covering_tests or spec.id in b.specRef for b in confirmed_bugs + flaky_bugs)
            if has_bug:
                result_str = "Bug Found"
            else:
                result_str = "Covered & Passed"

        req_preview = spec.text[:80] + ("..." if len(spec.text) > 80 else "")
        lines.append(
            f"| {_escape_cell(spec.id)} | {_escape_cell(req_preview)} | {_escape_cell(tests_cell)} | "
            f"{_escape_cell(result_str)} |"
        )
    lines.append("")

    lines.append("## Timings")
    lines.append("| Stage | Duration (s) |")
    lines.append("| --- | --- |")
    for sname, ssec in metrics.stageSeconds.items():
        lines.append(f"| {_escape_cell(sname)} | {ssec:.1f} |")
    lines.append(f"| **Total (Wall Clock)** | **{metrics.wallClockSeconds:.1f}** |")

    if metrics.parallel:
        p = metrics.parallel
        lines.append("")
        lines.append(f"1 worker: {p.workers1Seconds:.1f} s, 4 workers: {p.workers4Seconds:.1f} s, speedup {p.speedup:.2f}×")
    lines.append("")

    lines.append("## Safety")
    blocked_file = run_folder / "blocked_requests.jsonl"
    blocked_records: List[Dict[str, Any]] = []
    if blocked_file.exists():
        try:
            with open(blocked_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        blocked_records.append(json.loads(line))
        except Exception:
            pass

    if not blocked_records:
        lines.append("No off-domain requests were attempted.")
    else:
        lines.append(f"**Blocked off-domain requests:** {len(blocked_records)}")
        lines.append("")
        lines.append("| URL | Method | Blocked Count |")
        lines.append("| --- | --- | --- |")
        url_counts: Dict[str, int] = {}
        for rec in blocked_records:
            u = rec.get("url", "unknown")
            url_counts[u] = url_counts.get(u, 0) + 1
        for u, count in sorted(url_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"| {_escape_cell(u)} | GET/POST | {count} |")
    lines.append("")

    if run_mode == "autonomous" and review_log and review_log.decisions:
        lines.append("## Review log")
        lines.append("| Test ID | Decision | Reason |")
        lines.append("| --- | --- | --- |")
        for dec in review_log.decisions:
            lines.append(f"| {_escape_cell(dec.testId)} | {_escape_cell(dec.decision)} | {_escape_cell(dec.reason)} |")
        lines.append("")

    if benchmark:
        lines.append("## Benchmark vs ground truth")
        lines.append(f"- **Recall:** {benchmark.recall * 100:.1f}%")
        lines.append(f"- **Precision:** {benchmark.precision * 100:.1f}%")
        lines.append(f"- **Replay Rate:** {benchmark.replayRate * 100:.1f}%")
        lines.append("")
        if benchmark.matches:
            lines.append("| Bug ID | Ground Truth ID | Status |")
            lines.append("| --- | --- | --- |")
            for m in benchmark.matches:
                match_status = "True Positive" if m.groundTruthId else "False Positive"
                lines.append(f"| {_escape_cell(m.bugId)} | {_escape_cell(m.groundTruthId or '-')} | {match_status} |")
        lines.append("")

    report_text = "\n".join(lines) + "\n"
    report_file = run_folder / "report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_text)

    return report_text
