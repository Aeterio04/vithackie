"""Spec-driven catalog: one catalog test per spec TC, lint, and alignment checks.

The catalog in spec_driven mode is built deterministically from the structured
spec. No LLM may add, drop, merge or rewrite test cases; the LLM is only used
later (scripting) to translate steps into executable plans.
"""

import re
from typing import Any, Dict, List, Optional

from kawach.core.clock import now_iso
from kawach.schemas.catalog import Catalog, CatalogMeta, Step, TestCase
from kawach.schemas.spec import SpecTestCase, StructuredSpec

PRIORITY_MAP = {"P0": "critical", "P1": "high", "P2": "medium"}

_ACTION = re.compile(r"\b(navigate|open|click|tap|type|enter|scroll|press|hover|submit|link check|step through)\b", re.I)
_LOOP = re.compile(r"\b(for each|open each|each of)\b", re.I)
_MEASURABLE = re.compile(
    r"(\d|equals?|contains?|ends?|ending|starts?|at least|at most|below|above|within|longer|fewer|exactly|"
    r"naturalWidth|aria-|status|href|zero|\bno\b|\bnot\b|matches|<=|>=|\bnone\b|differ|distinct|restores?|changes?|fails? to load|served from)",
    re.I,
)
_EXISTENCE_ONLY = re.compile(r"^[^,;]*\b(is|are) (visible|present|shown|displayed)\.?$", re.I)
_UNOBSERVABLE = re.compile(r"\b(database|db row|server log|backend log|email (is )?received|inbox|crm)\b", re.I)


def lint_spec_test(tc: SpecTestCase) -> Dict[str, Any]:
    """Quality lint for one test case. Returns {ok, issues}."""
    issues: List[str] = []
    single_loop = len(tc.steps) == 1 and bool(_LOOP.search(tc.steps[0]))
    if len(tc.steps) < 2 and not single_loop:
        issues.append("fewer than 2 steps")
    if not any(_ACTION.search(s) for s in tc.steps):
        issues.append("no concrete action (navigate/click/type/scroll/press)")
    measurable = [e for e in tc.expected if _MEASURABLE.search(e)]
    if not measurable:
        issues.append("no measurable expected result")
    elif all(_EXISTENCE_ONLY.match(e) for e in tc.expected):
        issues.append("expected results are existence checks only")
    for e in tc.expected:
        if _UNOBSERVABLE.search(e):
            issues.append(f"expected result not observable in the browser: {e[:60]}")
    return {"ok": not issues, "issues": issues}


def catalog_version(spec_hash: str) -> str:
    return f"v-{spec_hash[:10]}"


def build_spec_driven_catalog(run_id: str, spec: StructuredSpec) -> Catalog:
    tests: List[TestCase] = []
    for tc in spec.testCases:
        steps = [Step(n=i, action=text) for i, text in enumerate(tc.steps, 1)]
        tests.append(
            TestCase(
                id=tc.id,
                title=tc.title,
                description=tc.title,
                specRef=list(tc.specRefs),
                priority=PRIORITY_MAP[tc.priority],
                preconditions=list(tc.preconditions),
                steps=steps,
                status="proposed",
                origin="human",
                expectedResults=list(tc.expected),
                tcType=tc.type,
                confidence=tc.confidence,
                viewport=tc.viewport,
                viewports=list(tc.viewports),
                calibrationNotes=list(tc.calibrationNotes),
                lint=lint_spec_test(tc),
            )
        )
    return Catalog(
        runId=run_id,
        generatedAt=now_iso(),
        tests=tests,
        meta=CatalogMeta(
            mode="spec_driven",
            specHash=spec.specHash,
            catalogVersion=catalog_version(spec.specHash),
            tcCount=len(spec.testCases),
        ),
    )


def alignment(spec: StructuredSpec, catalog: Optional[Catalog]) -> Dict[str, Any]:
    """Compare spec TCs with the catalog (suggested tests count as extra only if not marked)."""
    spec_ids = [t.id for t in spec.testCases]
    cat = [t for t in (catalog.tests if catalog else []) if not t.suggested]
    cat_ids = [t.id for t in cat]
    missing = [i for i in spec_ids if i not in cat_ids]
    extra = [i for i in cat_ids if i not in spec_ids]

    changed = []
    by_id = {t.id: t for t in cat}
    for tc in spec.testCases:
        ct = by_id.get(tc.id)
        if ct and (
            ct.title != tc.title
            or [s.action for s in ct.steps] != tc.steps
            or ct.expectedResults != tc.expected
        ):
            changed.append(tc.id)

    covered = {r for t in cat for r in t.specRef}
    uncovered_reqs = [r.id for r in spec.requirements if r.id not in covered]
    total = max(len(spec_ids), 1)
    ok = not missing and not extra and not changed and not uncovered_reqs
    return {
        "specTcCount": len(spec_ids),
        "catalogCount": len(cat_ids),
        "missing": missing,
        "extra": extra,
        "changed": changed,
        "uncoveredRequirements": uncovered_reqs,
        "requirementCount": len(spec.requirements),
        "alignmentPercent": round(100.0 * (len(spec_ids) - len(missing) - len(changed)) / total, 1),
        "aligned": ok,
        "canStartExecution": ok,
        "blockReason": None if ok else (
            f"{len(missing)} missing, {len(extra)} extra, {len(changed)} altered test(s); "
            f"{len(uncovered_reqs)} uncovered requirement(s)"
        ),
        "specHash": spec.specHash,
        "catalogVersion": catalog_version(spec.specHash),
    }


def is_spec_driven(run_id: str) -> bool:
    from kawach.storage import artifacts as storage

    cat = storage.load_model(run_id, "catalog.json", Catalog)
    return bool(cat and cat.meta and cat.meta.mode == "spec_driven")


TIER_PRIORITIES = {"P0": {"critical"}, "P0+P1": {"critical", "high"}}
VALID_TIERS = ("P0", "P0+P1", "all", "smoke")


def selected_test_ids(catalog: Optional[Catalog], tier: Optional[str]) -> List[str]:
    """Approved test ids that belong to the chosen priority tier (smoke = first P0 test per area)."""
    tests = [t for t in (catalog.tests if catalog else []) if t.status == "approved"]
    if not tier or tier == "all":
        return [t.id for t in tests]
    if tier == "smoke":
        seen, out = set(), []
        for t in tests:
            area = t.id.split("-")[1] if t.id.count("-") >= 2 else t.id
            if t.priority == "critical" and area not in seen:
                seen.add(area)
                out.append(t.id)
        return out
    pri = TIER_PRIORITIES.get(tier)
    if pri is None:
        raise ValueError(f"unknown priority tier {tier!r}; use one of {VALID_TIERS}")
    return [t.id for t in tests if t.priority in pri]
