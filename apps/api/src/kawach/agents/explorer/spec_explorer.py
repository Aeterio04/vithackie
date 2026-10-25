"""Spec-driven exploration: visit only the URLs the spec's test cases need (no random crawl)."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import List
from urllib.parse import urljoin, urlparse

from kawach.core.clock import now_iso
from kawach.core.config import settings
from kawach.schemas import AppMap, RunInput
from kawach.schemas.app_map import AppMapStats, ButtonInfo, HeadingInfo, LinkInfo, PageInfo
from kawach.schemas.spec import StructuredSpec
from kawach.services.spec_preset import derive_urls
from kawach.storage import artifacts as storage


def run_spec_explorer(run_id: str) -> AppMap:
    ri = storage.load_model(run_id, "input.json", RunInput)
    base = ri.targetUrl if ri else ""
    from kawach.services.spec_structured import parse_structured_spec

    spec: StructuredSpec = parse_structured_spec(ri.specRaw)
    needed = derive_urls(spec, cap=10_000)
    budget = ri.budgets.maxPages
    log = lambda m, **k: storage.log_pipeline(run_id, m, source="explorer", **k)  # noqa: E731
    if budget < len(needed):
        # never silently drop required pages: raise the budget to what the spec needs and say so
        log(f"Explorer: page budget {budget} is lower than the {len(needed)} distinct URLs the spec needs; using {len(needed)}.", level="warn")
    urls = [u if u.startswith("http") else urljoin(base, u) for u in needed]
    urls = [u for u in dict.fromkeys(urls) if urlparse(u).hostname and urlparse(u).hostname.endswith(urlparse(base).hostname.replace("www.", ""))]
    cap_n = max(budget, len(urls))
    urls = urls[:cap_n]

    storage.set_stage(run_id, "exploring", step=f"Snapshotting {len(urls)} spec URLs", done=0, total=len(urls))
    d = storage.run_dir(run_id)
    urls_file, out_file = d / "spec_urls.json", d / "spec_snapshots.json"
    urls_file.write_text(json.dumps(urls), encoding="utf-8")
    preset = storage.read_json(run_id, "preset.json") or {}
    env = os.environ.copy()
    env.update(URLS_FILE=str(urls_file), OUT_FILE=str(out_file), MAX_RPS=str(preset.get("maxRequestsPerSecond", 2)), UA=preset.get("userAgent", ""))
    node = shutil.which("node") or "node"
    log(f"Explorer: spec-driven mode, visiting {len(urls)} URLs required by the test cases (no random crawl).")
    t0 = time.time()
    p = subprocess.run([node, "spec_driven/snapshot.mjs"], cwd=str(settings.repo_root / "apps" / "runner"), env=env, capture_output=True, text=True, timeout=max(120, len(urls) * 12))
    if p.returncode != 0 or not out_file.exists():
        raise RuntimeError(f"spec explorer failed: {p.stderr[-300:]}")
    data = json.loads(out_file.read_text(encoding="utf-8"))
    pages: List[PageInfo] = []
    for r in data["pages"]:
        if not r.get("ok"):
            continue
        dd = r["data"]
        pages.append(PageInfo(
            url=r["finalUrl"], path=urlparse(r["finalUrl"]).path or "/", title=r.get("title", ""), status=r.get("status", 0),
            headings=[HeadingInfo(**h) for h in dd["headings"]], links=[LinkInfo(**l) for l in dd["links"] if l["href"]],
            buttons=[ButtonInfo(**b) for b in dd["buttons"]],
        ))
    failed = [r["url"] for r in data["pages"] if not r.get("ok")]
    amap = AppMap(
        baseUrl=base, generatedAt=now_iso(), pages=pages,
        summary=f"Spec-driven snapshot of {len(pages)} of {len(urls)} URLs required by {len(spec.testCases)} test cases.",
        stats=AppMapStats(pagesVisited=len(pages), durationSeconds=round(time.time() - t0, 1)),
        error=("could not load: " + ", ".join(failed)) if failed else None,
    )
    storage.save_model(run_id, "app_map.json", amap)
    log(f"Explorer: {len(pages)}/{len(urls)} spec URLs captured in {amap.stats.durationSeconds}s" + (f"; failed: {failed}" if failed else ""))
    return amap
