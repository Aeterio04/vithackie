"""Script writer agent that generates Playwright test scripts."""

import json
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

from kawach.core.clock import now_iso
from kawach.core.config import settings
from kawach.execution.runner import (
    ListResult,
    _clean_code_fence,
    clean_and_sanitize_script,
    list_tests,
)
from kawach.llm import get_llm, guard, load_prompt, untrusted
from kawach.schemas import AppMap, Catalog, RunInput, Step, TestCase
from kawach.storage import artifacts as storage

CANONICAL_EXAMPLE = """import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T02: Signup rejects an invalid email address', async ({ page }) => {
  await page.goto('/signup');
  await page.getByLabel('Email').fill('not-an-email');
  await page.getByLabel('Password').fill('Passw0rd!23');
  await page.getByRole('button', { name: 'Sign up' }).click();
  // S2
  const isInvalid = await page.getByLabel('Email').evaluate((el: HTMLInputElement) => !el.checkValidity() || Boolean(el.validationMessage)).catch(() => false);
  const hasAlert = await page.getByRole('alert').isVisible().catch(() => false) || await page.getByText(/valid email/i).isVisible().catch(() => false);
  expect(isInvalid || hasAlert).toBe(true);
  await expect(page).toHaveURL(/\\/signup$/);
});"""





def _list_tests_fallback(run_id: str, rel_file: str) -> ListResult:
    """Fallback syntax verification using npx playwright test <file> --list."""
    script_abs = (storage.run_dir(run_id) / rel_file).resolve()
    runner_dir = (settings.repo_root / "apps" / "runner").resolve()

    cmd = ["npx", "playwright", "test", str(script_abs), "--list"]
    if os.name == "nt":
        cmd = ["cmd", "/c", "npx", "playwright", "test", str(script_abs), "--list"]

    env = os.environ.copy()
    env["BASE_URL"] = "http://localhost:4000"
    env["SPEC_DIR"] = str((storage.run_dir(run_id) / "scripts").resolve())
    env["TEST_USERNAME"] = "qa.tester@example.com"
    env["TEST_PASSWORD"] = "Passw0rd!23"

    try:
        res = subprocess.run(
            cmd,
            cwd=str(runner_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if res.returncode == 0:
            return ListResult(ok=True)
        else:
            err = (res.stderr or res.stdout).strip()
            return ListResult(ok=False, error=err or "list_tests exited with non-zero code")
    except Exception as e:
        return ListResult(ok=False, error=str(e))


def validate_script_loadable(run_id: str, rel_file: str) -> ListResult:
    """Validate that script loads without syntax/import errors using runner_client with fallback."""
    try:
        return list_tests(run_id, rel_file)
    except NotImplementedError:
        return _list_tests_fallback(run_id, rel_file)
    except Exception as e:
        return ListResult(ok=False, error=str(e))


def write_scripts(run_id: str) -> Catalog:
    """Generate Playwright TypeScript scripts for all approved test cases."""
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    if not catalog or not catalog.tests:
        return Catalog(runId=run_id, generatedAt=now_iso(), tests=[])

    approved_tests = [t for t in catalog.tests if t.status == "approved"]
    total_approved = len(approved_tests)

    if total_approved == 0:
        return catalog

    storage.set_stage(run_id, "scripting", step="Writing scripts", done=0, total=total_approved)

    run_input = storage.load_model(run_id, "input.json", RunInput)
    app_map = storage.load_model(run_id, "app_map.json", AppMap)

    spec_map: Dict[str, str] = {}
    if run_input and run_input.spec:
        spec_map = {s.id: s.text for s in run_input.spec}

    compact_pages = []
    if app_map and app_map.pages:
        for p in app_map.pages:
            compact_pages.append({
                "path": p.path,
                "title": p.title,
                "headings": [h.text for h in p.headings[:3]],
                "buttons": [b.text for b in p.buttons[:6]],
                "forms": [
                    {
                        "action": f.action,
                        "method": f.method,
                        "fields": [{"label": fld.label, "type": fld.type, "role": fld.role} for fld in f.fields],
                    }
                    for f in p.forms
                ],
            })
    compact_map_str = json.dumps(compact_pages, ensure_ascii=False)[:2500]

    scripts_dir = storage.run_dir(run_id) / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    llm = get_llm()

    def _log(msg: str, **kwargs):
        try:
            from kawach.storage.artifacts import log_pipeline
            log_pipeline(run_id, msg, **kwargs)
        except Exception:
            pass

    _log(f"Starting test script generation for {total_approved} approved test cases...", source="script_writer")

    for idx, test_case in enumerate(approved_tests):
        test_id = test_case.id
        test_title = test_case.title
        storage.set_stage(
            run_id,
            "scripting",
            step=f"Writing script for {test_id} ({idx + 1}/{total_approved})",
            done=idx,
            total=total_approved,
        )
        _log(
            f"Worker w1: Synthesizing Playwright test script for {test_id} ({test_title})...",
            source="script_writer",
        )

        step_lines = []
        for s in test_case.steps:
            exp_str = f" -> Expected: {s.expected}" if s.expected else ""
            step_lines.append(f"{s.n}. {s.action}{exp_str}")
        steps_str = "\n".join(step_lines)

        relevant_spec = [f"{sid}: {spec_map[sid]}" for sid in test_case.specRef if sid in spec_map]
        spec_lines_str = "\n".join(relevant_spec) if relevant_spec else "(Verify steps as specified)"

        prompt_text = load_prompt(
            "script_writer",
            guard=guard(),
            test_id=test_id,
            test_title=re.sub(r"^[A-Z]\d+:\s*", "", test_title),
            description=test_case.description,
            steps=steps_str,
            spec_lines=spec_lines_str,
            app_map=untrusted(compact_map_str, "app_map"),
            example=CANONICAL_EXAMPLE,
        )

        raw_script = ""
        sanitized_script = ""
        script_error: Optional[str] = None

        try:
            raw_script = llm.complete_text(
                system="You are an expert Playwright TypeScript automation engineer.",
                prompt=prompt_text,
                schema_name="script_writer",
                run_id=run_id,
                max_tokens=500,
                temperature=0.1,
            )
            sanitized_script = clean_and_sanitize_script(raw_script, test_id, test_title)
        except Exception as gen_err:
            script_error = str(gen_err)
            _log(f"Generation note for {test_id}: {gen_err}", level="warn", source="script_writer")

        rel_path = f"scripts/{test_id}.spec.ts"
        script_abs = storage.run_dir(run_id) / rel_path

        code_to_write = sanitized_script if sanitized_script else (raw_script or f"// Generation failed: {script_error}")
        script_abs.write_text(code_to_write, encoding="utf-8")

        list_res = validate_script_loadable(run_id, rel_path)
        if list_res.ok:
            _log(f"Worker w1: Syntax and import verified for {test_id}.spec.ts", source="script_writer")

        if not list_res.ok:
            repair_err = list_res.error or script_error or "Syntax or import validation failed"
            repair_prompt = (
                f"{prompt_text}\n\n"
                f"Your previous file failed validation with this error:\n{repair_err[:1500]}\n\n"
                f"Here is the failed file:\n{code_to_write}\n\n"
                "Return the corrected complete file fixing the error."
            )
            try:
                repair_reply = llm.complete_text(
                    system="You are an expert Playwright TypeScript automation engineer.",
                    prompt=repair_prompt,
                    schema_name="script_writer",
                    run_id=run_id,
                    max_tokens=500,
                    temperature=0.1,
                )
                repaired_sanitized = clean_and_sanitize_script(repair_reply, test_id, test_title)
                script_abs.write_text(repaired_sanitized, encoding="utf-8")
                list_res = validate_script_loadable(run_id, rel_path)
            except Exception as repair_fail:
                list_res = ListResult(ok=False, error=str(repair_fail))

        test_case.script = rel_path
        if list_res.ok:
            test_case.scriptStatus = "ok"
            test_case.scriptError = None
        else:
            test_case.scriptStatus = "error"
            test_case.scriptError = (list_res.error or "Validation failed")[:500]

        catalog.generatedAt = now_iso()
        storage.save_model(run_id, "catalog.json", catalog)

        time.sleep(1.2)

    storage.set_stage(run_id, "scripting", step="All scripts written", done=total_approved, total=total_approved)
    _log(f"Completed script generation for {total_approved} tests.", source="script_writer")
    return catalog
