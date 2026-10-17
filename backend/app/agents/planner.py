"""Planner agent that designs a catalog of test cases.

Implemented by Track B.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import settings
from app.llm import get_llm
from app.models import AppMap, Catalog, RunInput, SpecItem, Step, TestCase
from app import prompts
from app import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_spec_items(run_input: Optional[RunInput]) -> Tuple[List[SpecItem], Set[str], str]:
    """Extract SpecItem list, set of IDs, and formatted string from RunInput."""
    if not run_input:
        return [], set(), ""

    spec_items = list(run_input.spec)
    if not spec_items and run_input.specRaw:
        # Parse lines like "S1: Text"
        for line in run_input.specRaw.splitlines():
            line_str = line.strip()
            match = re.match(r"^(S\d+):\s*(.*)$", line_str)
            if match:
                spec_items.append(SpecItem(id=match.group(1), text=match.group(2).strip()))

    all_ids = {s.id for s in spec_items}
    spec_lines = [f"{s.id}: {s.text}" for s in spec_items]
    return spec_items, all_ids, "\n".join(spec_lines)


def _compact_app_map(app_map: Optional[AppMap]) -> str:
    """Produce compact JSON representation of app map (capped at 12000 chars)."""
    if not app_map:
        return "[]"

    compact_pages = []
    for p in app_map.pages:
        compact_pages.append({
            "path": p.path,
            "title": p.title,
            "requiresAuth": p.requiresAuth,
            "headings": [h.text for h in p.headings[:5]],
            "forms": [
                {
                    "id": f.id,
                    "method": f.method,
                    "fields": [
                        {
                            "label": fld.label,
                            "type": fld.type,
                            "role": fld.role,
                            "name": fld.name,
                        }
                        for fld in f.fields
                    ],
                }
                for f in p.forms
            ],
            "buttons": [b.text for b in p.buttons[:8]],
        })

    return json.dumps(compact_pages, ensure_ascii=False)[:12000]


def plan_catalog(run_id: str) -> Catalog:
    """Generate a catalog of test cases from app map and spec with 100% coverage guarantee."""
    # 1. Update run stage
    storage.set_stage(run_id, "planning", step="Designing tests")

    run_input = storage.load_model(run_id, "input.json", RunInput)
    app_map = storage.load_model(run_id, "app_map.json", AppMap)

    spec_items, all_spec_ids, spec_str = _get_spec_items(run_input)
    prompt_bg = run_input.prompt if run_input and run_input.prompt else "Web application under test."

    min_tests = 8
    max_tests = run_input.budgets.maxTests if (run_input and run_input.budgets) else settings.MAX_TESTS

    compact_map_str = _compact_app_map(app_map)

    # 2. Build planner prompt
    prompt_text = prompts.load_prompt(
        "planner",
        guard=prompts.guard(),
        prompt=prompt_bg,
        spec=spec_str or "(No formal spec provided; test all discovered pages)",
        app_map=prompts.untrusted(compact_map_str, "app_map"),
        min_tests=min_tests,
        max_tests=max_tests,
    )

    llm = get_llm()
    resp = llm.complete_json(
        system="You are a senior QA engineer designing test catalogs.",
        prompt=prompt_text,
        schema_name="planner_catalog",
        run_id=run_id,
        max_tokens=6000,
    )

    raw_tests = resp.get("tests", []) if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])

    def process_test_entries(test_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        valid = []
        for t in test_entries:
            if not isinstance(t, dict):
                continue
            steps_raw = t.get("steps", [])
            if not steps_raw or not isinstance(steps_raw, list):
                continue
            title = str(t.get("title", "")).strip()
            if not title:
                continue

            # Clean and normalise specRef
            raw_refs = t.get("specRef", [])
            if isinstance(raw_refs, str):
                raw_refs = [raw_refs]
            valid_refs = [r for r in raw_refs if not all_spec_ids or r in all_spec_ids]

            priority = str(t.get("priority", "medium")).lower()
            if priority not in ("high", "medium", "low"):
                priority = "medium"

            # Parse steps
            steps: List[Step] = []
            for idx, s in enumerate(steps_raw):
                if isinstance(s, dict):
                    action = str(s.get("action", "")).strip()
                    expected = s.get("expected")
                    if expected is not None:
                        expected = str(expected).strip() or None
                    if action:
                        steps.append(Step(n=idx + 1, action=action, expected=expected))
                elif isinstance(s, str) and s.strip():
                    steps.append(Step(n=idx + 1, action=s.strip(), expected=None))

            if steps:
                valid.append({
                    "title": title,
                    "description": str(t.get("description", "")).strip() or title,
                    "specRef": valid_refs,
                    "priority": priority,
                    "steps": steps,
                    "origin": "planner",
                })
        return valid

    processed = process_test_entries(raw_tests)

    # 3. Check coverage of spec items
    covered_ids: Set[str] = set()
    for t in processed:
        covered_ids.update(t["specRef"])

    missing_ids = all_spec_ids - covered_ids

    # Retry once if any spec items are missing
    if missing_ids:
        retry_prompt = (
            prompt_text
            + f"\n\nThese spec items have no test yet: {', '.join(sorted(missing_ids))}. "
            "Return the COMPLETE catalog again including concrete tests for them."
        )
        try:
            retry_resp = llm.complete_json(
                system="You are a senior QA engineer designing test catalogs.",
                prompt=retry_prompt,
                schema_name="planner_catalog",
                run_id=run_id,
                max_tokens=6000,
            )
            retry_tests = (
                retry_resp.get("tests", [])
                if isinstance(retry_resp, dict)
                else (retry_resp if isinstance(retry_resp, list) else [])
            )
            retry_processed = process_test_entries(retry_tests)
            if retry_processed:
                processed = retry_processed
                covered_ids = set()
                for t in processed:
                    covered_ids.update(t["specRef"])
                missing_ids = all_spec_ids - covered_ids
        except Exception:
            pass

    # Fallback tests for any still missing spec items
    if missing_ids:
        for missing_id in sorted(missing_ids):
            spec_item = next((s for s in spec_items if s.id == missing_id), None)
            spec_desc = spec_item.text if spec_item else f"Verify spec requirement {missing_id}"
            fallback_title = f"Verify: {spec_desc[:60]}"
            processed.append({
                "title": fallback_title,
                "description": "Fallback test generated from the spec item.",
                "specRef": [missing_id],
                "priority": "medium",
                "steps": [
                    Step(n=1, action=f"Check the behaviour described by {missing_id}", expected=spec_desc)
                ],
                "origin": "fallback",
            })

    # 4. Clamp to max_tests without losing coverage of any spec item
    if len(processed) > max_tests:
        # Priority sort order for shedding: low (0), medium (1), high (2)
        priority_weight = {"low": 0, "medium": 1, "high": 2}

        # Keep removing lowest priority tests while count > max_tests
        idx = 0
        while len(processed) > max_tests and idx < len(processed):
            # Sort candidate indices by priority ascending
            sorted_indices = sorted(
                range(len(processed)),
                key=lambda i: priority_weight.get(processed[i]["priority"], 1),
            )

            removed = False
            for cand_i in sorted_indices:
                cand_refs = processed[cand_i]["specRef"]
                # Can only remove if all its specRef items are covered by some other test
                other_refs = set()
                for j, other_t in enumerate(processed):
                    if j != cand_i:
                        other_refs.update(other_t["specRef"])

                if all(r in other_refs for r in cand_refs):
                    processed.pop(cand_i)
                    removed = True
                    break

            if not removed:
                # Could not remove without losing coverage; stop clamping
                break

    # 5. Assign IDs T01.. in sequential order
    final_tests: List[TestCase] = []
    for idx, t in enumerate(processed):
        test_id = f"T{idx + 1:02d}"
        final_tests.append(
            TestCase(
                id=test_id,
                title=t["title"],
                description=t["description"],
                specRef=t["specRef"],
                priority=t["priority"],
                steps=t["steps"],
                status="proposed",
                origin=t["origin"],
                script=None,
                scriptStatus="pending",
                scriptError=None,
            )
        )

    catalog = Catalog(
        runId=run_id,
        generatedAt=_now_iso(),
        tests=final_tests,
    )

    storage.save_model(run_id, "catalog.json", catalog)
    return catalog


def plan_single_test(run_id: str, user_prompt: str) -> TestCase:
    """Plan a single test case from a user-provided prompt string and append to catalog."""
    if not user_prompt or not user_prompt.strip():
        raise ValueError("User prompt cannot be empty")
    if len(user_prompt) > 500:
        raise ValueError("User prompt must not exceed 500 characters")

    # Load existing catalog, app_map, input
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    if catalog is None:
        catalog = Catalog(runId=run_id, generatedAt=_now_iso(), tests=[])

    if settings.STUB_MODE:
        max_num = 0
        for t in catalog.tests:
            match = re.match(r"^T(\d+)$", t.id)
            if match:
                max_num = max(max_num, int(match.group(1)))
        next_id = f"T{max_num + 1:02d}"

        new_test = TestCase(
            id=next_id,
            title=f"{next_id}: {user_prompt.strip()[:80]}",
            description=user_prompt.strip(),
            specRef=[],
            priority="medium",
            steps=[Step(n=1, action=user_prompt.strip(), expected="Verify expected behaviour")],
            status="proposed",
            origin="human",
            script=None,
            scriptStatus="pending",
            scriptError=None,
        )
        catalog.tests.append(new_test)
        catalog.generatedAt = _now_iso()
        storage.save_model(run_id, "catalog.json", catalog)
        return new_test

    run_input = storage.load_model(run_id, "input.json", RunInput)
    app_map = storage.load_model(run_id, "app_map.json", AppMap)

    spec_items, all_spec_ids, spec_str = _get_spec_items(run_input)
    compact_map_str = _compact_app_map(app_map)

    existing_titles = "\n".join([f"- {t.title}" for t in catalog.tests])

    prompt_text = prompts.load_prompt(
        "planner_single",
        guard=prompts.guard(),
        user_prompt=user_prompt.strip(),
        existing_titles=existing_titles or "(none)",
        spec=spec_str or "(No formal spec provided)",
        app_map=prompts.untrusted(compact_map_str, "app_map"),
    )

    llm = get_llm()
    resp = llm.complete_json(
        system="You are a senior QA engineer designing single test cases.",
        prompt=prompt_text,
        schema_name="planner_single",
        run_id=run_id,
        max_tokens=2000,
    )

    test_data = resp.get("test", resp) if isinstance(resp, dict) else {}
    title = str(test_data.get("title", user_prompt.strip()))
    description = str(test_data.get("description", title))
    priority = str(test_data.get("priority", "medium")).lower()
    if priority not in ("high", "medium", "low"):
        priority = "medium"

    raw_refs = test_data.get("specRef", [])
    if isinstance(raw_refs, str):
        raw_refs = [raw_refs]
    valid_refs = [r for r in raw_refs if not all_spec_ids or r in all_spec_ids]

    steps_raw = test_data.get("steps", [])
    steps: List[Step] = []
    if isinstance(steps_raw, list):
        for idx, s in enumerate(steps_raw):
            if isinstance(s, dict):
                act = str(s.get("action", "")).strip()
                exp = s.get("expected")
                if exp is not None:
                    exp = str(exp).strip() or None
                if act:
                    steps.append(Step(n=idx + 1, action=act, expected=exp))
            elif isinstance(s, str) and s.strip():
                steps.append(Step(n=idx + 1, action=s.strip(), expected=None))

    if not steps:
        steps = [Step(n=1, action=user_prompt.strip(), expected="Verify expected behaviour")]

    # Compute next test ID: find highest among existing T##
    max_num = 0
    for t in catalog.tests:
        match = re.match(r"^T(\d+)$", t.id)
        if match:
            max_num = max(max_num, int(match.group(1)))

    next_id = f"T{max_num + 1:02d}"

    new_test = TestCase(
        id=next_id,
        title=title,
        description=description,
        specRef=valid_refs,
        priority=priority,
        steps=steps,
        status="proposed",
        origin="human",
        script=None,
        scriptStatus="pending",
        scriptError=None,
    )

    # Append and save immediately
    catalog.tests.append(new_test)
    catalog.generatedAt = _now_iso()
    storage.save_model(run_id, "catalog.json", catalog)

    return new_test
