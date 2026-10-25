from pathlib import Path

import pytest

from kawach.services.spec_driven import alignment, build_spec_driven_catalog, lint_spec_test
from kawach.services.spec_parser import parse_spec_text
from kawach.services.spec_structured import parse_structured_spec, split_numbered_steps

SPEC_PATH = Path(__file__).resolve().parents[3] / "QA_inputs" / "IMOCHA_SPEC.md"


@pytest.fixture(scope="module")
def spec():
    return parse_structured_spec(SPEC_PATH.read_text(encoding="utf-8"))


def test_imocha_spec_counts(spec):
    assert len(spec.requirements) == 17
    assert len(spec.testCases) == 46
    assert spec.errors == []
    assert len(spec.knownObservations) == 5
    assert spec.globalRules["Politeness"].startswith("At most 2")


def test_imocha_all_tcs_pass_lint(spec):
    failures = {t.id: lint_spec_test(t)["issues"] for t in spec.testCases if not lint_spec_test(t)["ok"]}
    assert failures == {}


def test_catalog_aligns_with_spec(spec):
    cat = build_spec_driven_catalog("r", spec)
    rep = alignment(spec, cat)
    assert rep["aligned"] and rep["alignmentPercent"] == 100.0
    assert [t.id for t in cat.tests] == [t.id for t in spec.testCases]


def test_alignment_detects_missing_extra_changed(spec):
    cat = build_spec_driven_catalog("r", spec)
    removed = cat.tests.pop(0)
    cat.tests[0].expectedResults = ["rewritten"]
    extra = cat.tests[1].model_copy(update={"id": "TC-X-001"})
    cat.tests.append(extra)
    rep = alignment(spec, cat)
    assert rep["missing"] == [removed.id]
    assert rep["extra"] == ["TC-X-001"]
    assert len(rep["changed"]) == 1
    assert not rep["canStartExecution"]


def test_suggested_tests_not_counted_as_extra(spec):
    cat = build_spec_driven_catalog("r", spec)
    cat.tests.append(cat.tests[0].model_copy(update={"id": "S-1", "suggested": True}))
    assert alignment(spec, cat)["extra"] == []


def test_malformed_block_reported_with_line_numbers():
    raw = "## 2. TEST CASES\n### TC-A-001: ok title\n- **Priority:** P9 | **Type:** functional | **Confidence:** High | **Spec:** REQ-A-01 | **Viewport:** desktop\n- **Steps:** 1. Open `/`. 2. Click it.\n"
    s = parse_structured_spec(raw)
    assert s.testCases == []
    msgs = {(e.line, e.message.split(" ")[0]) for e in s.errors}
    assert (2, "Priority") in msgs
    assert any("Missing Expected" in e.message for e in s.errors)


def test_split_numbered_steps_sequential():
    assert split_numbered_steps("1. Open `/`. 2. Wait up to 2 s. 3. Read.") == ["Open `/`.", "Wait up to 2 s.", "Read."]


def test_legacy_parser_returns_requirements_for_tc_spec():
    items, errors = parse_spec_text(SPEC_PATH.read_text(encoding="utf-8"))
    assert len(items) == 17 and errors == []
    assert items[0].id == "REQ-LOAD-01"


def test_legacy_bullet_spec_still_works():
    items, _ = parse_spec_text("- Users can log in with valid credentials\n- Users can log out\n")
    assert len(items) == 2
