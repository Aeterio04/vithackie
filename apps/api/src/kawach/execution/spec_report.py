"""Markdown + PDF report for spec-driven runs. Counts come from the same results.json as the run page."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from kawach.schemas.spec import StructuredSpec
from kawach.storage import artifacts as storage

OK = ("passed", "passed_with_issues")
LABEL = {"passed": "PASS", "passed_with_issues": "PASS+ISSUES", "failed": "FAIL", "script_error": "SCRIPT_ERR",
         "environment_error": "ENV_ERR", "safety_violation": "SAFETY", "not_run": "NOT_RUN", "inconclusive": "INCONCL"}


def _load(run_id: str, name: str) -> Optional[Any]:
    return storage.read_json(run_id, name)


def build_spec_report(run_id: str, official: List[str], calibration_file: str = "calibration.json") -> Dict[str, Any]:
    spec = StructuredSpec.model_validate(_load(run_id, "spec_structured.json"))
    align = _load(run_id, "alignment.json") or {}
    runs = [_load(run_id, f"spec_results_{m}.json") for m in official]
    runs = [r for r in runs if r]
    final = runs[-1]
    by_id = {e["id"]: e for e in final["results"]}
    per_run = {r["mode"]: {e["id"]: e["status"] for e in r["results"]} for r in runs}
    cal = _load(run_id, calibration_file) or []
    cal_by = {c["id"]: c for c in cal}
    counts: Dict[str, int] = {}
    for e in final["results"]:
        counts[e["status"]] = counts.get(e["status"], 0) + 1

    flaky = [t.id for t in spec.testCases if len({per_run[m].get(t.id) for m in per_run}) > 1]

    L: List[str] = []
    w = L.append
    w(f"# iMocha website QA report")
    w("")
    w(f"- Run: `{run_id}`  | Target: https://www.imocha.io/ (read-only, safe mode)")
    w(f"- Spec hash: `{spec.specHash}`  | Catalog version: `{align.get('catalogVersion')}`  | Alignment: {align.get('alignmentPercent')}% ({align.get('catalogCount')}/{align.get('specTcCount')} TCs, {align.get('requirementCount')} REQs, missing {len(align.get('missing', []))}, extra {len(align.get('extra', []))})")
    w(f"- Official runs: {', '.join(official)} (final counts below are from `{final['mode']}`)")
    w("")
    w("## Summary")
    w("")
    w("| Status | Count |\n|---|---|")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        w(f"| {k} | {v} |")
    w(f"| **total** | **{len(final['results'])}** |")
    w("")
    w(f"Flaky TCs across official runs: {', '.join(flaky) if flaky else 'none'}.")
    w("")
    rate = final.get("rate", {})
    w(f"Politeness (final run): workers={final['workers']}, gated requests={rate.get('gatedRequests')}, peak in any 1 s window={rate.get('peakRequestsInAnyOneSecondWindow')}, duration={final['durationSeconds']}s.")
    w("")

    w("## Coverage matrix (REQ -> TC -> status)")
    w("")
    w("| REQ | Requirement | TCs (status) |\n|---|---|---|")
    for r in spec.requirements:
        tcs = [t for t in spec.testCases if r.id in t.specRefs]
        cell = ", ".join(f"{t.id} ({LABEL.get(by_id.get(t.id, {}).get('status', 'not_run'), '?')})" for t in tcs)
        w(f"| {r.id} | {r.text[:90]} | {cell or 'NOT COVERED'} |")
    w("")

    w("## Stability across official runs")
    w("")
    w("| TC | " + " | ".join(per_run.keys()) + " | stable |\n|---|" + "---|" * (len(per_run) + 1))
    for t in spec.testCases:
        row = [LABEL.get(per_run[m].get(t.id, 'not_run'), '?') for m in per_run]
        w(f"| {t.id} | " + " | ".join(row) + f" | {'yes' if t.id not in flaky else '**NO**'} |")
    w("")

    findings = [(e["id"], f) for e in final["results"] for f in e.get("findings", [])]
    w("## Findings")
    w("")
    if findings:
        w("| TC | Severity | Finding | Detail |\n|---|---|---|---|")
        for tid, f in findings:
            w(f"| {tid} | {f['severity']} | {f['title']} | {str(f['detail'])[:160].replace('|', '/')} |")
    else:
        w("No findings.")
    w("")
    w("### Known observations (spec section 3)")
    w("")
    notes = [(e["id"], n) for e in final["results"] for n in e.get("notes", []) if "observation" in n.lower()]
    for i, o in enumerate(spec.knownObservations, 1):
        hit = [f for tid, f in findings if f.get("observation") == i]
        refuted = [n for tid, n in notes if f"#{i} " in n]
        verdict = "CONFIRMED" if hit else ("REFUTED / not reproduced" if refuted else "not tested by a TC (informational in spec)")
        w(f"{i}. {o[:140]} -> **{verdict}**")
    w("")

    if cal:
        w("## Calibration summary")
        w("")
        w("| TC | first result | classification | action | final | evidence |\n|---|---|---|---|---|---|")
        for c in cal:
            w(f"| {c['id']} | {c['first']} | {c['classification']} | {str(c['action'])[:120]} | {c['final']} | {c.get('evidence', '')} |")
        w("")

    w("## Test cases")
    w("")
    for t in spec.testCases:
        e = by_id.get(t.id, {})
        ev = e.get("evidence") or {}
        w(f"### {t.id}: {t.title}")
        w(f"- Priority {t.priority} | {t.type} | confidence {t.confidence} | {', '.join(t.specRefs)} | viewport {t.viewport}")
        w(f"- **Status: {e.get('status', 'not_run')}**  | duration {e.get('durationMs', 0)} ms | video {ev.get('videoDuration', 0)}s ({ev.get('videoQuality')})  | evidence `{ev.get('dir')}`")
        if e.get("errorMessage"):
            w(f"- Error: {e['errorMessage'][:300]}")
        w("- Steps:")
        for s in e.get("steps", []):
            w(f"  {s['n']}. [{s['status']}] {s['text']} ({s['ms']} ms)")
        w("- Expected vs actual:")
        for x in e.get("expected", []):
            w(f"  - [{x['status']}] {x['text']}  =>  {str(x['actual'])[:220]}")
        for f in e.get("findings", []):
            w(f"- Finding ({f['severity']}): {f['title']} - {str(f['detail'])[:200]}")
        w("")

    md = "\n".join(L)
    out_dir = storage.run_dir(run_id)
    (out_dir / "report.md").write_text(md, encoding="utf-8")
    pdf = _pdf(out_dir / "report.pdf", L)
    return {"markdown": str(out_dir / "report.md"), "pdf": pdf, "counts": counts, "flaky": flaky}


def _pdf(path: Path, lines: List[str]) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from xml.sax.saxutils import escape

    st = getSampleStyleSheet()
    small = st["BodyText"].clone("small", fontSize=7.5, leading=9)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    flow: List[Any] = []
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("|") and i + 1 < len(lines) and lines[i + 1].startswith("|---"):
            rows = []
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                if not lines[j].startswith("|---"):
                    rows.append([Paragraph(escape(c.strip().replace("**", "")), small) for c in lines[j].strip().strip("|").split("|")])
                j += 1
            t = Table(rows, repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            flow += [t, Spacer(1, 6)]
            i = j
            continue
        if l.startswith("# "):
            flow.append(Paragraph(escape(l[2:]), st["Title"]))
        elif l.startswith("## "):
            flow.append(Paragraph(escape(l[3:]), st["Heading2"]))
        elif l.startswith("### "):
            flow.append(Paragraph(escape(l[4:]), st["Heading4"]))
        elif l.strip():
            flow.append(Paragraph(escape(l.replace("**", "").replace("`", "")), small))
        i += 1
    doc.build(flow)
    return str(path)
