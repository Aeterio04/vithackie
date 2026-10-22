"""Specification parser service for raw markdown or text requirements."""

import re
from typing import List, Optional, Tuple

from kawach.schemas.catalog import SpecItem


def parse_spec_text(raw_spec: str) -> Tuple[List[SpecItem], List[str]]:
    """Parse spec text: S<number>: <text> and continuation lines indented with 2 spaces.

    Returns a tuple of (items, errors).
    """
    errors: List[str] = []
    items: List[SpecItem] = []
    lines = raw_spec.splitlines()

    curr_id: Optional[str] = None
    curr_text: List[str] = []

    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if line.startswith("  "):
            if not curr_id:
                errors.append(f"Line {i} is a continuation line but has no previous S<number> item")
            else:
                curr_text.append(line.strip())
        else:
            m = re.match(r"^S(\d+):\s*(.+)$", line)
            if not m:
                errors.append(f"Line {i} must start with S<number>:")
            else:
                if curr_id:
                    items.append(SpecItem(id=curr_id, text=" ".join(curr_text)))
                curr_id = f"S{m.group(1)}"
                curr_text = [m.group(2).strip()]

    if curr_id:
        items.append(SpecItem(id=curr_id, text=" ".join(curr_text)))

    if not items and not errors:
        errors.append("Spec must contain at least one item like 'S1: ...'")

    return items, errors


def parse_spec_raw(spec_raw: str) -> List[SpecItem]:
    """Parse raw requirements text into list of SpecItem objects."""
    items, _ = parse_spec_text(spec_raw)
    return items
