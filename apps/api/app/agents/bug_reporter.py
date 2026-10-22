"""Bug reporter agent that writes reproducible defect summaries.

Implemented by Track B.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.llm import get_llm
from app.models import Bug, BugsFile, Catalog, Category, RunInput, Severity
from app import prompts
from app import storage

ANSI_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

ALLOWED_CATEGORIES = {
    "validation",
    "auth",
    "data",
    "navigation",
    "console",
    "network",
    "ui",
    "other",
}

ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_REGEX.sub("", text)


def write_bug_reports(run_id: str) -> List[Bug]:
    """Generate structured bug reports with steps and expected/actual outcomes."""
    # 1. Load bugs.json
    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
    if not bugs_file or not bugs_file.bugs:
        return []

    # 2. Load context: catalog.json, input.json
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    run_input = storage.load_model(run_id, "input.json", RunInput)

    catalog_map = {t.id: t for t in catalog.tests} if catalog else {}
    spec_map = {s.id: s.text for s in run_input.spec} if (run_input and run_input.spec) else {}

    llm = get_llm()
    total_bugs = len(bugs_file.bugs)

    for idx, bug in enumerate(bugs_file.bugs):
        storage.set_stage(
            run_id,
            "verifying",
            step=f"Writing bug report {bug.id} ({idx + 1}/{total_bugs})",
        )

        # A. Test context
        test_case = catalog_map.get(bug.testId)
        if test_case:
            test_lines = [
                f"Title: {test_case.title}",
                f"Description: {test_case.description}",
                "Steps:",
            ]
            for s in test_case.steps:
                exp_str = f" [Expected: {s.expected}]" if s.expected else ""
                test_lines.append(f"  {s.n}. {s.action}{exp_str}")
            test_context = "\n".join(test_lines)
        else:
            # Exploratory bug or no catalog entry
            test_context = f"Scenario: {bug.title}"

        # B. Spec lines
        spec_lines = [f"{sid}: {spec_map[sid]}" for sid in bug.specRef if sid in spec_map]
        spec_context = "\n".join(spec_lines) if spec_lines else "(No specific spec item)"

        # C. Cleaned error message
        cleaned_err = _strip_ansi(bug.errorMessage or "").strip()[:1500]

        # D. Console errors from evidence folder
        console_context = "(No console errors observed)"
        evidence_dir = storage.run_dir(run_id) / "evidence" / bug.testId
        console_file = evidence_dir / "console.json"
        if console_file.exists():
            try:
                with open(console_file, "r", encoding="utf-8") as f:
                    c_data = json.load(f)
                if isinstance(c_data, list) and c_data:
                    lines = [str(item)[:300] for item in c_data[:5]]
                    console_context = "\n".join([f"- {l}" for l in lines])
            except Exception:
                pass

        # E. Prompt construction
        prompt_text = prompts.load_prompt(
            "bug_reporter",
            guard=prompts.guard(),
            spec_lines=spec_context,
            test=test_context,
            error_message=prompts.untrusted(cleaned_err or "(No error text provided)", "playwright_error"),
            console=prompts.untrusted(console_context, "console_errors"),
            source=bug.source,
        )

        title = ""
        category: Category = "other"
        severity: Severity = "medium"
        steps: List[str] = []
        expected = ""
        actual = ""

        try:
            resp = llm.complete_json(
                system="You are a senior software QA engineer writing a formal defect report.",
                prompt=prompt_text,
                schema_name="bug_report",
                run_id=run_id,
                max_tokens=650,
            )

            if isinstance(resp, dict):
                title = str(resp.get("title", "")).strip()

                cat_raw = str(resp.get("category", "")).lower().strip()
                category = cat_raw if cat_raw in ALLOWED_CATEGORIES else "other"

                sev_raw = str(resp.get("severity", "")).lower().strip()
                severity = sev_raw if sev_raw in ALLOWED_SEVERITIES else "medium"

                raw_steps = resp.get("steps", [])
                if isinstance(raw_steps, list) and raw_steps:
                    steps = [str(s).strip() for s in raw_steps if str(s).strip()]

                expected = str(resp.get("expected", "")).strip()
                actual = str(resp.get("actual", "")).strip()

        except Exception:
            pass

        # F. Fail-soft fallback if LLM failed or generated incomplete report
        if not title:
            # Strip ID prefix from title if present
            title = re.sub(r"^[A-Z]\d+:\s*", "", test_case.title if test_case else bug.title).strip()
            if not title:
                title = f"Defect in {bug.file}"

        if not category:
            category = "other"
        if not severity:
            severity = "medium"

        if not steps:
            if test_case and test_case.steps:
                steps = [s.action for s in test_case.steps]
            else:
                steps = ["Reproduce with the attached test script"]

        if not expected:
            if test_case and test_case.steps:
                last_exp = next((s.expected for s in reversed(test_case.steps) if s.expected), None)
                expected = last_exp or spec_context
            else:
                expected = spec_context

        if not actual:
            first_err_line = cleaned_err.splitlines()[0] if cleaned_err else "Assertion failed during test execution"
            actual = first_err_line[:200]

        # G. Update bug in-place without touching immutable IDs or evidence links
        bug.title = title
        bug.category = category  # type: ignore
        bug.severity = severity  # type: ignore
        bug.steps = steps
        bug.expected = expected
        bug.actual = actual

        # Save after every bug to persist incremental progress
        storage.save_model(run_id, "bugs.json", bugs_file)

    return bugs_file.bugs
