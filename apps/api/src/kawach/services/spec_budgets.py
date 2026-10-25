"""Stage-aware time/page budgets derived from the spec (never a silent crawl cap)."""

import math
from typing import Any, Dict, Optional

from kawach.schemas.run import Budgets
from kawach.services.spec_preset import derive_urls
from kawach.services.spec_structured import parse_structured_spec

# Measured request-heavy TCs (gated requests at 2 req/s => at least requests/2 seconds) and their extra budget.
BULK_REQUESTS = {"TC-LINK-001": 80, "TC-FOOT-004": 45, "TC-PAGE-006": 9, "TC-PAGE-001": 6, "TC-PAGE-002": 6, "TC-NAV-005": 12, "TC-LEGAL-001": 4}
BASE_TEST_SECONDS = 25
HARD_TEST_TIMEOUT_MS = 60000


def test_timeout_ms(tc_id: str) -> int:
    """60 s hard timeout per test; request-heavy tests get 60 s + the time their gated requests need at 2 req/s."""
    n = BULK_REQUESTS.get(tc_id, 0)
    extra = int(n / 2 * 1000 * 1.6) if n > 12 else (n * 8000 if n else 0)
    return HARD_TEST_TIMEOUT_MS + extra


def estimate(raw_spec: str, tier: Optional[str] = None, workers: int = 2) -> Dict[str, Any]:
    spec = parse_structured_spec(raw_spec)
    urls = derive_urls(spec, cap=10_000)
    pages_needed = len(urls)
    tests = spec.testCases
    pri = {"P0": {"P0"}, "P0+P1": {"P0", "P1"}}.get(tier or "all")
    chosen = [t for t in tests if pri is None or t.priority in pri]
    per_test = [max(BASE_TEST_SECONDS, test_timeout_ms(t.id) / 1000 * 0.35) for t in chosen]
    run_seconds = math.ceil(sum(per_test) / workers * 1.2)
    return {
        "pagesNeeded": pages_needed,
        "pagesBudget": math.ceil(pages_needed * 1.1),
        "testsInTier": len(chosen),
        "tier": tier or "all",
        "stageSeconds": {
            "gate": 40,
            "explore": max(60, math.ceil(pages_needed * 1.1) * 3),
            "plan": 15,
            "scripting": 30,
            "running": run_seconds,
            "report": 30,
        },
        "totalSeconds": 40 + max(60, math.ceil(pages_needed * 1.1) * 3) + 15 + 30 + run_seconds + 30,
    }


def suggest_budgets(raw_spec: str, current: Budgets, requested: Optional[Budgets] = None) -> Budgets:
    """Spec-driven defaults: pages = distinct URLs + 10 %, tests = every TC, time from the estimate.

    A budget the caller set explicitly is kept but a warning-bearing value is never lower than needed.
    """
    est = estimate(raw_spec)
    spec_tcs = len(parse_structured_spec(raw_spec).testCases)
    b = current.model_copy()
    b.maxPages = max(est["pagesBudget"], requested.maxPages if requested else 0)
    b.maxTests = max(spec_tcs, requested.maxTests if requested else 0)
    b.exploreSeconds = max(est["stageSeconds"]["explore"], requested.exploreSeconds if requested else 0)
    b.testTimeoutMs = HARD_TEST_TIMEOUT_MS
    return b
