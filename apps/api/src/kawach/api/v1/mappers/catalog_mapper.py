"""Mappers for converting Catalog and TestCase models to frontend schemas."""

from typing import Any, Dict, List, Optional

from kawach.schemas import Catalog, Results, TestCase
from kawach.storage import artifacts as storage


def transform_test_to_frontend(t: TestCase) -> dict:
    """Transform backend TestCase model to frontend TestCase schema."""
    review_status_map = {
        "proposed": "pending",
        "approved": "approved",
        "rejected": "rejected",
    }
    status = review_status_map.get(getattr(t, "status", "proposed"), "pending")

    steps_text = []
    if t.steps:
        for s in t.steps:
            if hasattr(s, "action"):
                steps_text.append(f"{s.action}: {getattr(s, 'value', '') or getattr(s, 'target', '')}")
            else:
                steps_text.append(str(s))

    return {
        "id": t.id,
        "title": t.title,
        "spec_item_ids": t.specRef or [],
        "steps": steps_text,
        "expected_result": t.description or t.title,
        "priority": t.priority or "medium",
        "review_status": status,
        "source": getattr(t, "origin", "llm"),
        "suggested_reason": "Generated from specification requirements",
        "last_decision": None,
    }


def build_catalog_frontend(run_id: str) -> List[dict]:
    """Retrieve catalog.json and transform tests to frontend format."""
    cat = storage.load_model(run_id, "catalog.json", Catalog)
    if not cat or not cat.tests:
        return []
    return [transform_test_to_frontend(t) for t in cat.tests]
