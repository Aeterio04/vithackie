"""Structured spec parser: `### TC-<AREA>-<NNN>: title` blocks -> StructuredSpec.

Malformed blocks are reported with line numbers, never silently skipped.
"""

import hashlib
import re
from typing import Dict, List, Optional, Tuple

from kawach.schemas.spec import (
    SpecParseError,
    SpecRequirement,
    SpecTestCase,
    StructuredSpec,
)

TC_HEADING = re.compile(r"^###\s+(TC-[A-Z0-9]+-\d{3})\s*:\s*(.+?)\s*$")
TC_HEADING_LOOSE = re.compile(r"^###\s+TC[-_ ]", re.IGNORECASE)
REQ_ROW = re.compile(r"^\|\s*(REQ-[A-Z0-9\-]+)\s*\|\s*(.+?)\s*\|\s*$")
FIELD_LINE = re.compile(r"^- \*\*([^*:]+?):\*\*\s*(.*)$")
META_PAIR = re.compile(r"\*\*([A-Za-z ]+):\*\*\s*([^|]+)")

VIEWPORT_PROFILES = {
    "desktop": {"name": "desktop", "width": 1440, "height": 900, "touch": False},
    "tablet": {"name": "tablet", "width": 768, "height": 1024, "touch": True},
    "mobile": {"name": "mobile", "width": 390, "height": 844, "touch": True},
}


def spec_hash(raw_spec: str) -> str:
    norm = raw_spec.replace("\r\n", "\n").strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def has_test_case_blocks(raw_spec: str) -> bool:
    return any(TC_HEADING.match(l) or TC_HEADING_LOOSE.match(l) for l in raw_spec.splitlines())


def _split_top_level(text: str, sep: str = ";") -> List[str]:
    """Split on `sep` ignoring separators inside (), backticks."""
    parts: List[str] = []
    buf: List[str] = []
    depth, tick = 0, False
    for ch in text:
        if ch == "`":
            tick = not tick
        elif not tick:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == sep and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
                continue
        buf.append(ch)
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def split_numbered_steps(text: str) -> List[str]:
    """Split '1. a. 2. b.' into ['a.', 'b.'] using strictly sequential markers."""
    text = text.strip()
    if not re.match(r"^1\.\s", text):
        return [text] if text else []
    marks: List[Tuple[int, int]] = []
    pos, k = 0, 1
    while True:
        m = re.compile(rf"(?:^|(?<=\s)){k}\.\s").search(text, pos)
        if not m:
            break
        marks.append((m.start(), m.end()))
        pos = m.end()
        k += 1
    steps = []
    for i, (_, end) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        seg = text[end:stop].strip()
        if seg:
            steps.append(seg)
    return steps


def parse_viewports(value: str) -> List[Dict[str, object]]:
    v = value.lower()
    widths = re.findall(r"\b(\d{3,4})\b", v)
    if "," in v and len(widths) >= 2:
        return [
            {"name": f"w{w}", "width": int(w), "height": 900 if int(w) >= 1024 else 844 if int(w) < 700 else 1024, "touch": int(w) < 1024}
            for w in widths
        ]
    sized = re.findall(r"(\d{3,4})\s*x\s*(\d{3,4})", v)
    if sized:
        w, h = sized[0]
        name = "mobile" if "mobile" in v else "tablet" if "tablet" in v else "custom"
        return [{"name": name, "width": int(w), "height": int(h), "touch": name in ("mobile", "tablet")}]
    for key in ("mobile", "tablet", "desktop"):
        if key in v:
            return [dict(VIEWPORT_PROFILES[key])]
    return [dict(VIEWPORT_PROFILES["desktop"])]


def _table_rows(lines: List[str]) -> List[List[str]]:
    rows = []
    for l in lines:
        s = l.strip()
        if not s.startswith("|") or re.match(r"^\|[\s\-|:]+\|$", s):
            continue
        rows.append([c.strip() for c in s.strip("|").split("|")])
    return rows


def _section(lines: List[str], prefix: str) -> List[str]:
    out, inside = [], False
    for l in lines:
        if l.startswith("## "):
            inside = l[3:].strip().startswith(prefix)
            continue
        if inside:
            out.append(l)
    return out


def parse_structured_spec(raw_spec: str) -> StructuredSpec:
    lines = raw_spec.replace("\r\n", "\n").splitlines()
    spec = StructuredSpec(specHash=spec_hash(raw_spec))

    for r in _table_rows(_section(lines, "0.")):
        if len(r) >= 2 and r[0].lower() != "rule":
            spec.globalRules[r[0]] = r[1].strip("`")

    for l in lines:
        m = REQ_ROW.match(l.strip())
        if m:
            spec.requirements.append(SpecRequirement(id=m.group(1), text=m.group(2)))

    for r in _table_rows(_section(lines, "3.")):
        if len(r) >= 2 and r[0] != "#":
            spec.knownObservations.append(r[1])

    starts = [i for i, l in enumerate(lines) if TC_HEADING.match(l) or TC_HEADING_LOOSE.match(l)]
    seen = set()
    for bi, si in enumerate(starts):
        end = starts[bi + 1] if bi + 1 < len(starts) else len(lines)
        for j in range(si + 1, end):
            if lines[j].startswith("## "):
                end = j
                break
        hm = TC_HEADING.match(lines[si])
        if not hm:
            spec.errors.append(SpecParseError(line=si + 1, message=f"Malformed TC heading: {lines[si]!r}"))
            continue
        tc_id, title = hm.group(1), hm.group(2)
        if tc_id in seen:
            spec.errors.append(SpecParseError(line=si + 1, tcId=tc_id, message="Duplicate test case id"))
            continue
        seen.add(tc_id)

        fields: Dict[str, List[str]] = {}
        cur: Optional[str] = None
        meta: Dict[str, str] = {}
        for l in lines[si + 1:end]:
            if not l.strip() or re.match(r"^-{3,}\s*$", l.strip()):
                continue
            fm = FIELD_LINE.match(l)
            if fm:
                label = fm.group(1).strip()
                if label == "Priority":
                    meta = {k.strip(): v.strip() for k, v in META_PAIR.findall(l)}
                    cur = None
                    continue
                cur = label.split("(")[0].strip().lower()
                fields.setdefault(cur, []).append(fm.group(2).strip())
            elif cur:
                fields[cur].append(l.strip())

        problems = []
        pr = meta.get("Priority", "")
        if pr not in ("P0", "P1", "P2"):
            problems.append(f"Priority must be P0/P1/P2 (got {pr!r})")
        ty = meta.get("Type", "functional").lower()
        if ty not in ("functional", "informational"):
            problems.append(f"Type must be functional/informational (got {ty!r})")
        conf = meta.get("Confidence", "Medium")
        if conf not in ("High", "Medium", "Calibrate"):
            problems.append(f"Confidence must be High/Medium/Calibrate (got {conf!r})")
        refs = re.findall(r"REQ-[A-Z0-9\-]+", meta.get("Spec", ""))
        if not refs:
            problems.append("Missing Spec: REQ reference")
        steps = split_numbered_steps(" ".join(fields.get("steps", [])))
        if not steps:
            problems.append("Missing Steps")
        exp_lines = fields.get("expected", [])
        bullets = [e[2:].strip() for e in exp_lines if e.startswith("- ")]
        expected = bullets or _split_top_level(" ".join(exp_lines).strip())
        if not expected:
            problems.append("Missing Expected")
        if problems:
            for p in problems:
                spec.errors.append(SpecParseError(line=si + 1, tcId=tc_id, message=p))
            continue

        notes = [" ".join(fields[k]).strip() for k in ("calibration note", "known observation to record") if k in fields]
        vp = meta.get("Viewport", "desktop")
        spec.testCases.append(
            SpecTestCase(
                id=tc_id, title=title, priority=pr, type=ty, confidence=conf,
                specRefs=refs, viewport=vp, viewports=parse_viewports(vp),
                preconditions=[" ".join(fields["preconditions"]).strip()] if "preconditions" in fields else [],
                steps=steps, expected=expected, calibrationNotes=notes, startLine=si + 1,
            )
        )
    return spec
