"""Specification parser service for raw markdown or text requirements."""

import re
from typing import List, Optional, Tuple

from kawach.schemas.catalog import SpecItem


def parse_spec_text(raw_spec: str) -> Tuple[List[SpecItem], List[str]]:
    """Parse spec text: supports legacy S<number>: format as well as standard markdown/requirement ID formats.

    Returns a tuple of (items, errors).
    """
    errors: List[str] = []
    items: List[SpecItem] = []

    from kawach.services.spec_structured import has_test_case_blocks, parse_structured_spec

    if has_test_case_blocks(raw_spec):
        structured = parse_structured_spec(raw_spec)
        errors.extend(f"line {e.line}: {e.tcId or ''} {e.message}".strip() for e in structured.errors)
        items = [SpecItem(id=r.id, text=r.text) for r in structured.requirements]
        if items:
            return items, errors
    lines = raw_spec.splitlines()

    curr_id: Optional[str] = None
    curr_text: List[str] = []

    req_pattern = re.compile(
        r"^[-*]?\s*(?:\d+\.\s*)?(?:\*\*)?\[?([A-Za-z0-9_\-]+)(?:\s*\([^)]*\))?\]?(?:\*\*)?:\s*(.+)$"
    )
    auto_id_counter = 1

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue

        if (line.startswith("  ") or line.startswith("\t")) and curr_id:
            curr_text.append(stripped)
            continue

        m = req_pattern.match(line)
        if m:
            if curr_id:
                items.append(SpecItem(id=curr_id, text=" ".join(curr_text)))
            curr_id = m.group(1).strip()
            curr_text = [m.group(2).strip()]
        elif stripped.startswith("- ") or stripped.startswith("* "):
            bullet_text = stripped.lstrip("-* ").strip()
            if len(bullet_text) > 10:
                if curr_id:
                    items.append(SpecItem(id=curr_id, text=" ".join(curr_text)))
                curr_id = f"REQ-{auto_id_counter:02d}"
                auto_id_counter += 1
                curr_text = [bullet_text]
        elif curr_id:
            curr_text.append(stripped)

    if curr_id and curr_text:
        items.append(SpecItem(id=curr_id, text=" ".join(curr_text)))

    if not items:
        errors.append("Spec must contain at least one requirement item.")

    return items, errors


def parse_spec_raw(spec_raw: str) -> List[SpecItem]:
    """Parse raw requirements text into list of SpecItem objects."""
    items, _ = parse_spec_text(spec_raw)
    return items
