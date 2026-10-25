"""Deterministic script generation for spec-driven runs: one Playwright file per spec TC.

The step text and expected text embedded in each file are copied verbatim from the
catalog (which is copied verbatim from the spec). Test bodies are implemented in
apps/runner/spec_driven/tcs*.ts and keyed by TC id, so the LLM never rewrites tests.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from kawach.core.config import settings
from kawach.schemas import Catalog, TestCase
from kawach.storage import artifacts as storage

from kawach.services.spec_budgets import test_timeout_ms


def _meta(t: TestCase) -> Dict[str, Any]:
    steps = [s.action for s in t.steps]
    return {
        "id": t.id,
        "title": t.title,
        "type": t.tcType,
        "priority": {"critical": "P0", "high": "P1", "medium": "P2"}.get(t.priority, "P2"),
        "steps": steps,
        "expected": list(t.expectedResults),
        "timeoutMs": test_timeout_ms(t.id),
        # TCs whose own steps submit a form (empty / invalid input) are explicitly allowed to click submit.
        "allowSubmitClicks": bool(re.search(r"\bsubmit\b", " ".join(steps), re.I)),
    }


def render_script(t: TestCase, rel_runner: str) -> str:
    vp = (t.viewports or [{"name": "desktop", "width": 1440, "height": 900, "touch": False}])[0]
    touch = bool(vp.get("touch"))
    w, h = int(vp["width"]), int(vp["height"])
    meta = json.dumps(_meta(t), ensure_ascii=False, indent=2)
    use = {
        "viewport": {"width": w, "height": h},
        "hasTouch": touch,
        "isMobile": touch and w < 700,
        "video": {"mode": "on", "size": {"width": w, "height": h}},
        # trace without per-action screenshots: still replayable, but teardown no longer takes minutes
        "trace": {"mode": "on", "screenshots": False, "snapshots": True, "sources": False},
    }
    return f"""// GENERATED from the spec by kawach.services.spec_scripts. Do not edit; edit the spec or apps/runner/spec_driven.
import {{ test }} from '{rel_runner}/fixtures';
import {{ runTc }} from '{rel_runner}/spec_driven/lib';
import {{ TCS }} from '{rel_runner}/spec_driven/tcs';

const meta = {meta} as any;
test.use({json.dumps(use)} as any);

const impl = TCS[meta.id];
if (!impl) {{
  test(`${{meta.id}}: ${{meta.title}}`, async () => {{ throw new Error('SCRIPT_ERROR: no implementation registered for ' + meta.id); }});
}} else {{
  runTc(meta, impl);
}}
"""


def write_spec_scripts(run_id: str) -> Catalog:
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    if not catalog:
        raise ValueError("no catalog")
    scripts_dir = storage.run_dir(run_id) / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    runner_dir = Path(settings.repo_root) / "apps" / "runner"
    rel = os.path.relpath(runner_dir, scripts_dir).replace("\\", "/")
    for t in catalog.tests:
        if t.status != "approved":
            continue
        rel_path = f"scripts/{t.id}.spec.ts"
        (scripts_dir / f"{t.id}.spec.ts").write_text(render_script(t, rel), encoding="utf-8")
        t.script = rel_path
        t.scriptStatus = "ok"
        t.scriptError = None
    storage.save_model(run_id, "catalog.json", catalog)
    return catalog
