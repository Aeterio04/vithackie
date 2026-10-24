"""Planner agent that designs a multi-level catalog of test cases and edge cases."""

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from kawach.core.clock import now_iso
from kawach.core.config import settings
from kawach.llm import get_llm, guard, load_prompt, untrusted
from kawach.schemas import AppMap, Catalog, CoverageMatrix, RunInput, SpecItem, Step, TestCase
from kawach.storage import artifacts as storage
from kawach.agents.planner.edge_library import EDGE_LIBRARY, compute_risk_score


def _get_spec_items(run_input: Optional[RunInput]) -> Tuple[List[SpecItem], Set[str], str]:
    """Extract SpecItem list, set of IDs, and formatted string from RunInput."""
    if not run_input:
        return [], set(), ""

    spec_items = list(run_input.spec)
    if not spec_items and run_input.specRaw:
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

    journeys_summary = []
    if app_map.journeys:
        for j in app_map.journeys[:5]:
            journeys_summary.append({
                "journeyId": j.journeyId,
                "title": j.title,
                "depth": j.depth,
                "steps": j.steps[:4],
            })

    payload = {
        "pages": compact_pages,
        "deepJourneys": journeys_summary,
        "statesDiscovered": len(app_map.states),
    }

    return json.dumps(payload, ensure_ascii=False)[:12000]


def _build_coverage_matrix(tests: List[TestCase], all_spec_ids: Set[str]) -> CoverageMatrix:
    """Compute spec items x depth levels x edge categories coverage matrix."""
    depth_levels = {"L0": 0, "L1": 0, "L2": 0, "L3+": 0}
    edge_categories: Dict[str, int] = {}
    matrix: Dict[str, Dict[str, List[str]]] = {}

    for s_id in sorted(all_spec_ids):
        matrix[s_id] = {"depths": [], "categories": [], "edgeTags": [], "testIds": []}

    for t in tests:
        # Depth bucket
        if t.depth <= 0:
            depth_levels["L0"] += 1
            d_key = "L0"
        elif t.depth == 1:
            depth_levels["L1"] += 1
            d_key = "L1"
        elif t.depth == 2:
            depth_levels["L2"] += 1
            d_key = "L2"
        else:
            depth_levels["L3+"] += 1
            d_key = "L3+"

        # Edge categories count
        for tag in t.edgeTags:
            edge_def = EDGE_LIBRARY.get(tag)
            cat_name = edge_def.category if edge_def else "general_edge"
            edge_categories[cat_name] = edge_categories.get(cat_name, 0) + 1

        # Spec item matrix links
        for ref in t.specRef:
            if ref in matrix:
                if d_key not in matrix[ref]["depths"]:
                    matrix[ref]["depths"].append(d_key)
                if t.category not in matrix[ref]["categories"]:
                    matrix[ref]["categories"].append(t.category)
                for tag in t.edgeTags:
                    if tag not in matrix[ref]["edgeTags"]:
                        matrix[ref]["edgeTags"].append(tag)
                if t.id not in matrix[ref]["testIds"]:
                    matrix[ref]["testIds"].append(t.id)

    return CoverageMatrix(
        specItems=sorted(list(all_spec_ids)),
        depthLevels=depth_levels,
        edgeCategories=edge_categories,
        matrix=matrix,
    )


def plan_catalog(run_id: str) -> Catalog:
    """Generate a multi-level catalog of test cases from app map and spec with 100% coverage guarantee."""
    storage.set_stage(run_id, "planning", step="Designing multi-level tests and edge cases")

    run_input = storage.load_model(run_id, "input.json", RunInput)
    app_map = storage.load_model(run_id, "app_map.json", AppMap)

    spec_items, all_spec_ids, spec_str = _get_spec_items(run_input)
    prompt_bg = run_input.prompt if run_input and run_input.prompt else "Web application under test."

    min_tests = 8
    max_tests = run_input.budgets.maxTests if (run_input and run_input.budgets) else settings.MAX_TESTS

    compact_map_str = _compact_app_map(app_map)

    prompt_text = load_prompt(
        "planner",
        guard=guard(),
        prompt=prompt_bg,
        spec=spec_str or "(No formal spec provided; test all discovered pages)",
        app_map=untrusted(compact_map_str, "app_map"),
        min_tests=min_tests,
        max_tests=max_tests,
    )

    def _log(msg: str, **kwargs):
        try:
            from kawach.storage.artifacts import log_pipeline
            log_pipeline(run_id, msg, **kwargs)
        except Exception:
            pass

    _log("Planner Agent: Synthesizing multi-level test catalog from app map and requirements...", source="planner")

    llm = get_llm()
    resp = llm.complete_json(
        system="You are a senior QA engineer designing test catalogs.",
        prompt=prompt_text,
        schema_name="planner_catalog",
        run_id=run_id,
        max_tokens=4000,
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

            raw_refs = t.get("specRef", [])
            if isinstance(raw_refs, str):
                raw_refs = [raw_refs]
            valid_refs = [r for r in raw_refs if not all_spec_ids or r in all_spec_ids]

            priority = str(t.get("priority", "medium")).lower()
            if priority not in ("critical", "high", "medium", "low"):
                priority = "medium"

            # Parse steps with assertions and checkpoints
            steps: List[Step] = []
            for idx, s in enumerate(steps_raw):
                if isinstance(s, dict):
                    action = str(s.get("action", "")).strip()
                    expected = s.get("expected")
                    if expected is not None:
                        expected = str(expected).strip() or None
                    checkpoint = s.get("checkpoint") or (f"Step {idx + 1}: Check {expected}" if expected else f"Step {idx + 1}: Action completed")
                    assertion = s.get("assertion") or (f"Assert {expected}" if expected else None)
                    locator = s.get("locator")
                    if action:
                        steps.append(Step(
                            n=idx + 1,
                            action=action,
                            expected=expected,
                            checkpoint=checkpoint,
                            assertion=assertion,
                            locator=locator,
                        ))
                elif isinstance(s, str) and s.strip():
                    steps.append(Step(
                        n=idx + 1,
                        action=s.strip(),
                        expected=None,
                        checkpoint=f"Step {idx + 1}: Action completed",
                        assertion=None,
                        locator=None,
                    ))

            if not steps:
                continue

            # Infer or accept category and depth
            raw_cat = t.get("category")
            if raw_cat in ("single_step", "journey", "deep_path", "edge_case"):
                category = raw_cat
            else:
                # Infer category from step count and edge markers
                lower_title = title.lower()
                if any(k in lower_title for k in ("invalid", "reject", "empty", "boundary", "overflow", "error", "whitespace", "special", "script")):
                    category = "edge_case"
                elif len(steps) == 1:
                    category = "single_step"
                elif len(steps) == 2:
                    category = "journey"
                else:
                    category = "deep_path"

            depth = int(t.get("depth", len(steps)))
            if category == "single_step":
                depth = 1
            elif category == "deep_path":
                depth = max(3, depth)

            edge_tags = list(t.get("edgeTags", []))
            if category == "edge_case" and not edge_tags:
                for k, edge_def in EDGE_LIBRARY.items():
                    if any(kw in title.lower() for kw in (edge_def.tag, edge_def.category)):
                        edge_tags.append(k)
                if not edge_tags:
                    edge_tags.append("input_validation")

            # Determine edge severity for risk score
            edge_sev = 1.0
            if category == "edge_case":
                matching_sevs = [EDGE_LIBRARY[tag].severity for tag in edge_tags if tag in EDGE_LIBRARY]
                edge_sev = max(matching_sevs) if matching_sevs else 2.0

            risk = compute_risk_score(priority, depth, edge_sev)

            valid.append({
                "title": title,
                "description": str(t.get("description", "")).strip() or title,
                "specRef": valid_refs,
                "priority": priority,
                "depth": depth,
                "category": category,
                "preconditions": t.get("preconditions", ["Target web application running"]),
                "setup": t.get("setup", []),
                "edgeTags": edge_tags,
                "coverageRef": t.get("coverageRef", []),
                "riskScore": risk,
                "steps": steps,
                "origin": "planner",
            })
        return valid

    processed = process_test_entries(raw_tests)

    # Check coverage of spec items
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
                max_tokens=1400,
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
                "depth": 1,
                "category": "single_step",
                "preconditions": ["Target web application running"],
                "setup": [],
                "edgeTags": [],
                "coverageRef": [],
                "riskScore": compute_risk_score("medium", 1, 1.0),
                "steps": [
                    Step(
                        n=1,
                        action=f"Check the behaviour described by {missing_id}",
                        expected=spec_desc,
                        checkpoint=f"Verify {missing_id}",
                        assertion=f"Assert {spec_desc}",
                    )
                ],
                "origin": "fallback",
            })

    # Enrich with AppMap deep journeys if room and available
    if app_map and app_map.journeys:
        existing_journey_titles = {t["title"] for t in processed}
        for j in app_map.journeys:
            if len(processed) >= max_tests:
                break
            if j.title in existing_journey_titles:
                continue
            # Associate with first unassociated spec item or all
            cat_type = "deep_path" if j.depth >= 3 else "journey"
            j_steps = [
                Step(n=idx + 1, action=s, expected=None, checkpoint=f"Journey step {idx + 1}")
                for idx, s in enumerate(j.steps)
            ]
            if j_steps:
                j_steps[-1].expected = "End of journey reached without navigation error"
                j_steps[-1].assertion = "Assert page status is healthy"

            processed.append({
                "title": f"Execute Journey: {j.title[:60]}",
                "description": f"End-to-end journey traversing {j.depth} states: {j.title}",
                "specRef": list(all_spec_ids)[:2] if all_spec_ids else [],
                "priority": "high",
                "depth": j.depth,
                "category": cat_type,
                "preconditions": ["Target web application running"],
                "setup": [],
                "edgeTags": [],
                "coverageRef": [j.journeyId],
                "riskScore": compute_risk_score("high", j.depth, 1.0),
                "steps": j_steps,
                "origin": "heuristic",
            })

    # Clamp to max_tests without losing coverage of any spec item
    if len(processed) > max_tests:
        while len(processed) > max_tests:
            # Sort candidate indices by riskScore ascending (remove lowest risk first)
            sorted_indices = sorted(
                range(len(processed)),
                key=lambda i: processed[i]["riskScore"],
            )

            removed = False
            for cand_i in sorted_indices:
                cand_refs = processed[cand_i]["specRef"]
                other_refs = set()
                for j, other_t in enumerate(processed):
                    if j != cand_i:
                        other_refs.update(other_t["specRef"])

                if all(r in other_refs for r in cand_refs):
                    processed.pop(cand_i)
                    removed = True
                    break

            if not removed:
                break

    # Sort final tests by riskScore descending
    processed.sort(key=lambda t: t["riskScore"], reverse=True)

    # Assign sequential IDs T01.. in order of descending riskScore
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
                depth=t["depth"],
                category=t["category"],
                preconditions=t.get("preconditions", []),
                setup=t.get("setup", []),
                edgeTags=t.get("edgeTags", []),
                coverageRef=t.get("coverageRef", []),
                riskScore=t["riskScore"],
                steps=t["steps"],
                status="proposed",
                origin=t["origin"],
                script=None,
                scriptStatus="pending",
                scriptError=None,
            )
        )

    # Build coverage matrix
    coverage_matrix = _build_coverage_matrix(final_tests, all_spec_ids)

    catalog = Catalog(
        runId=run_id,
        generatedAt=now_iso(),
        tests=final_tests,
        coverageMatrix=coverage_matrix,
    )

    storage.save_model(run_id, "catalog.json", catalog)
    return catalog


def plan_single_test(run_id: str, user_prompt: str) -> TestCase:
    """Plan a single test case from a user-provided prompt string and append to catalog."""
    if not user_prompt or not user_prompt.strip():
        raise ValueError("User prompt cannot be empty")
    if len(user_prompt) > 500:
        raise ValueError("User prompt must not exceed 500 characters")

    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    if catalog is None:
        catalog = Catalog(runId=run_id, generatedAt=now_iso(), tests=[])

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
            depth=1,
            category="single_step",
            preconditions=["Target web application running"],
            setup=[],
            edgeTags=[],
            coverageRef=[],
            riskScore=compute_risk_score("medium", 1, 1.0),
            steps=[
                Step(
                    n=1,
                    action=user_prompt.strip(),
                    expected="Verify expected behaviour",
                    checkpoint="Step 1: Check expected behaviour",
                    assertion="Assert expected behaviour",
                )
            ],
            status="proposed",
            origin="human",
            script=None,
            scriptStatus="pending",
            scriptError=None,
        )
        catalog.tests.append(new_test)
        catalog.generatedAt = now_iso()
        all_specs = {ref for t in catalog.tests for ref in t.specRef}
        catalog.coverageMatrix = _build_coverage_matrix(catalog.tests, all_specs)
        storage.save_model(run_id, "catalog.json", catalog)
        return new_test

    run_input = storage.load_model(run_id, "input.json", RunInput)
    app_map = storage.load_model(run_id, "app_map.json", AppMap)

    spec_items, all_spec_ids, spec_str = _get_spec_items(run_input)
    compact_map_str = _compact_app_map(app_map)

    existing_titles = "\n".join([f"- {t.title}" for t in catalog.tests])

    prompt_text = load_prompt(
        "planner_single",
        guard=guard(),
        user_prompt=user_prompt.strip(),
        existing_titles=existing_titles or "(none)",
        spec=spec_str or "(No formal spec provided)",
        app_map=untrusted(compact_map_str, "app_map"),
    )

    llm = get_llm()
    resp = llm.complete_json(
        system="You are a senior QA engineer designing single test cases.",
        prompt=prompt_text,
        schema_name="planner_single",
        run_id=run_id,
        max_tokens=800,
    )

    test_data = resp.get("test", resp) if isinstance(resp, dict) else {}
    title = str(test_data.get("title", user_prompt.strip()))
    description = str(test_data.get("description", title))
    priority = str(test_data.get("priority", "medium")).lower()
    if priority not in ("critical", "high", "medium", "low"):
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
                chk = s.get("checkpoint") or (f"Step {idx + 1}: Check {exp}" if exp else f"Step {idx + 1}: Completed")
                asrt = s.get("assertion") or (f"Assert {exp}" if exp else None)
                if act:
                    steps.append(Step(n=idx + 1, action=act, expected=exp, checkpoint=chk, assertion=asrt))
            elif isinstance(s, str) and s.strip():
                steps.append(Step(n=idx + 1, action=s.strip(), expected=None, checkpoint=f"Step {idx + 1}: Completed"))

    if not steps:
        steps = [Step(n=1, action=user_prompt.strip(), expected="Verify expected behaviour", checkpoint="Step 1: Check behaviour")]

    max_num = 0
    for t in catalog.tests:
        match = re.match(r"^T(\d+)$", t.id)
        if match:
            max_num = max(max_num, int(match.group(1)))

    next_id = f"T{max_num + 1:02d}"
    depth = max(1, len(steps))
    category = "single_step" if len(steps) == 1 else ("journey" if len(steps) == 2 else "deep_path")
    risk = compute_risk_score(priority, depth, 1.0)

    new_test = TestCase(
        id=next_id,
        title=title,
        description=description,
        specRef=valid_refs,
        priority=priority,
        depth=depth,
        category=category,
        preconditions=["Target web application running"],
        setup=[],
        edgeTags=[],
        coverageRef=[],
        riskScore=risk,
        steps=steps,
        status="proposed",
        origin="human",
        script=None,
        scriptStatus="pending",
        scriptError=None,
    )

    catalog.tests.append(new_test)
    catalog.generatedAt = now_iso()
    all_specs = {ref for t in catalog.tests for ref in t.specRef}
    catalog.coverageMatrix = _build_coverage_matrix(catalog.tests, all_specs)
    storage.save_model(run_id, "catalog.json", catalog)

    return new_test
