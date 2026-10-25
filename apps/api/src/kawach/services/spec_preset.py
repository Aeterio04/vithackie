"""Project preset + URL plan derived from the spec's global rules table (nothing hard-coded to one site)."""

import re
from typing import Any, Dict, List

from kawach.schemas.spec import StructuredSpec

STD_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _find(rules: Dict[str, str], key: str) -> str:
    for k, v in rules.items():
        if k.lower().startswith(key.lower()):
            return v
    return ""


def build_preset(spec: StructuredSpec, name: str = "iMocha website") -> Dict[str, Any]:
    r = spec.globalRules
    base = re.search(r"https?://[^\s`)]+", _find(r, "Base URL"))
    pol = _find(r, "Politeness")
    workers = re.search(r"(\d+)\s*(?:parallel\s*)?workers", pol)
    rps = re.search(r"(\d+)\s*requests?\s*per\s*second", pol)
    noise_raw = _find(r, "Third-party noise")
    noise = [t.strip() for t in re.split(r",|\band\b", noise_raw) if t.strip()]
    noise = [re.sub(r"\s*requests?$", "", t) for t in noise]
    vp_rule = _find(r, "Default viewport")
    viewports = []
    for kind in ("Desktop", "Mobile", "Tablet"):
        m = re.search(kind + r"[^.]*?(\d{3,4})x(\d{3,4})", vp_rule, re.I)
        if m:
            viewports.append({"name": kind.lower(), "width": int(m.group(1)), "height": int(m.group(2)), "touch": kind != "Desktop"})
    return {
        "name": name,
        "target": base.group(0).rstrip("/") + "/" if base else "",
        "safeMode": "never" in _find(r, "Safe mode").lower() or bool(_find(r, "Safe mode")),
        "workers": int(workers.group(1)) if workers else 2,
        "maxRequestsPerSecond": int(rps.group(1)) if rps else 2,
        "userAgent": STD_UA,
        "credentials": None,
        "readiness": _find(r, "Readiness"),
        "overlaysPolicy": _find(r, "Overlays"),
        "externalLinksPolicy": _find(r, "External links"),
        "noiseAllowList": noise,
        "noiseRegex": "|".join(re.escape(t) for t in noise),
        "firstPartyErrorsPolicy": _find(r, "First-party errors"),
        "viewports": viewports,
        "specHash": spec.specHash,
        "rulesLoadedFromSpec": sorted(r.keys()),
    }


_URL = re.compile(r"`(/[^`\s*]*|https?://[^`\s*]+)`")


def derive_urls(spec: StructuredSpec, cap: int = 40) -> List[str]:
    """URLs the TCs need (Open/Navigate steps + explicit page lists), first-seen order, capped."""
    seen: List[str] = []
    for tc in spec.testCases:
        for step in tc.steps:
            for m in _URL.findall(step):
                u = m.split("#")[0]
                if u and "..." not in u and u not in seen and (u.startswith("/") or "imocha.io" in u):
                    seen.append(u)
    return seen[:cap]
