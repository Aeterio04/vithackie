#!/usr/bin/env python3
"""scripts/diagnose_target.py <url> [--out dir]

Comprehensive diagnostic probe matrix for external / deployed web applications.
Evaluates DNS, TCP, TLS, Plain HTTP (legacy vs standard Chrome UA),
Playwright Chromium profiles (current vs new standard vs headed), proxy checks,
WAF/block detection, and layer-by-layer root cause verdict.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

import httpx

CHALLENGE_MARKERS = [
    "attention required",
    "just a moment",
    "access denied",
    "captcha",
    "cf-chl",
    "request unsuccessful",
    "ddos protection",
    "cloudflare ray id",
    "checking your browser",
    "perimeterx",
    "datadome",
    "akamai",
]


def probe_dns_tcp_tls(hostname: str, port: int = 443, use_ssl: bool = True) -> Dict[str, Any]:
    """Probe A: DNS (IPv4 / IPv6), TCP connect, and TLS handshake."""
    res: Dict[str, Any] = {
        "ipv4": [],
        "ipv6": [],
        "dns_time_ms": None,
        "tcp_connect_ms": None,
        "tls_handshake_ms": None,
        "tls_version": None,
        "cipher": None,
        "cert_subject": None,
        "cert_issuer": None,
        "cert_expiry": None,
        "san": [],
        "error": None,
    }

    # DNS
    t0 = time.time()
    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        for family, _, _, _, sockaddr in addr_info:
            ip = sockaddr[0]
            if family == socket.AF_INET and ip not in res["ipv4"]:
                res["ipv4"].append(ip)
            elif family == socket.AF_INET6 and ip not in res["ipv6"]:
                res["ipv6"].append(ip)
        res["dns_time_ms"] = round((time.time() - t0) * 1000, 2)
    except Exception as e:
        res["error"] = f"DNS resolution failed: {e}"
        return res

    target_ip = res["ipv4"][0] if res["ipv4"] else (res["ipv6"][0] if res["ipv6"] else None)
    if not target_ip:
        res["error"] = "No IPv4 or IPv6 address resolved"
        return res

    # TCP
    t_tcp = time.time()
    sock = None
    try:
        family = socket.AF_INET if res["ipv4"] else socket.AF_INET6
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((target_ip, port))
        res["tcp_connect_ms"] = round((time.time() - t_tcp) * 1000, 2)
    except Exception as e:
        res["error"] = f"TCP connection failed to {target_ip}:{port}: {e}"
        if sock:
            sock.close()
        return res

    # TLS
    if use_ssl:
        t_tls = time.time()
        try:
            ctx = ssl.create_default_context()
            ssock = ctx.wrap_socket(sock, server_hostname=hostname)
            res["tls_handshake_ms"] = round((time.time() - t_tls) * 1000, 2)
            res["tls_version"] = ssock.version()
            cipher_info = ssock.cipher()
            if cipher_info:
                res["cipher"] = cipher_info[0]
            cert = ssock.getpeercert()
            if cert:
                res["cert_subject"] = dict(x[0] for x in cert.get("subject", ()))
                res["cert_issuer"] = dict(x[0] for x in cert.get("issuer", ()))
                res["cert_expiry"] = cert.get("notAfter")
                res["san"] = [x[1] for x in cert.get("subjectAltName", ())]
            ssock.close()
        except Exception as e:
            res["error"] = f"TLS handshake failed: {e}"
            if sock:
                sock.close()
            return res
    else:
        if sock:
            sock.close()

    return res


def probe_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
    timeout: float = 15.0,
    trust_env: bool = True,
) -> Dict[str, Any]:
    """Execute plain HTTP request recording hops, headers, status, and body snippet."""
    info: Dict[str, Any] = {
        "method": method,
        "status": None,
        "final_url": None,
        "redirect_chain": [],
        "headers": {},
        "cookies": [],
        "body_snippet": "",
        "body_len": 0,
        "duration_ms": None,
        "error": None,
    }

    t0 = time.time()
    try:
        with httpx.Client(
            follow_redirects=follow_redirects,
            timeout=timeout,
            trust_env=trust_env,
        ) as client:
            resp = client.request(method, url, headers=headers)
            info["duration_ms"] = round((time.time() - t0) * 1000, 2)
            info["status"] = resp.status_code
            info["final_url"] = str(resp.url)

            # Record redirect history
            if resp.history:
                for h in resp.history:
                    info["redirect_chain"].append({
                        "status": h.status_code,
                        "url": str(h.url),
                        "location": h.headers.get("location"),
                    })

            # Key headers
            for k in [
                "server", "via", "cf-ray", "x-cache", "x-amz-cf-id",
                "x-vercel-id", "retry-after", "content-type", "content-length",
            ]:
                if k in resp.headers:
                    info["headers"][k] = resp.headers[k]

            info["cookies"] = list(resp.cookies.keys())
            info["body_len"] = len(resp.content)
            info["body_snippet"] = resp.text[:500]
    except Exception as e:
        info["duration_ms"] = round((time.time() - t0) * 1000, 2)
        info["error"] = str(e)

    return info


def probe_playwright(url: str, out_dir: Optional[Path]) -> Dict[str, Any]:
    """Probe D: Run Playwright profiles (current, new_standard, headed)."""
    script_path = Path(__file__).resolve().parent.parent / "apps" / "runner" / "diagnose_playwright.mjs"
    cwd = Path(__file__).resolve().parent.parent / "apps" / "runner"

    cmd = ["node", str(script_path), url]
    if out_dir:
        cmd.append(str(out_dir))

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout = proc.stdout
        marker_start = "__PLAYWRIGHT_DIAG_OUTPUT_START__"
        marker_end = "__PLAYWRIGHT_DIAG_OUTPUT_END__"

        if marker_start in stdout and marker_end in stdout:
            json_text = stdout.split(marker_start)[1].split(marker_end)[0].strip()
            return json.loads(json_text)
        else:
            return {"error": f"Failed to parse Playwright probe output: {proc.stderr or proc.stdout}"}
    except Exception as e:
        return {"error": f"Playwright probe execution failed: {e}"}


def classify_block(
    probe_name: str,
    status: Optional[int],
    body: str,
    headers: Dict[str, str],
    error: Optional[str] = None,
    text_length: int = 0,
    duration_ms: Optional[float] = None,
) -> str:
    """Probe F: Classify probe outcome."""
    if error:
        err_lower = error.lower()
        if "dns" in err_lower or "name resolution" in err_lower or "getaddrinfo" in err_lower:
            return "dns_error"
        if "tls" in err_lower or "ssl" in err_lower or "certificate" in err_lower:
            return "tls_error"
        if "timeout" in err_lower or "timed out" in err_lower:
            return "timeout"
        if "connection refused" in err_lower:
            return "bad_gateway_from_us"

    if status in (502, 504):
        return "bad_gateway_from_target"

    lower_body = (body or "").lower()
    waf_header = any(k in headers for k in ["cf-ray", "x-amz-cf-id", "x-vercel-id", "via"])
    challenge_found = any(m in lower_body for m in CHALLENGE_MARKERS)

    if status in (403, 429, 503):
        if challenge_found or waf_header:
            return "blocked_by_waf"
        return "blocked_by_waf"

    if status == 200:
        if challenge_found:
            return "blocked_by_waf"
        if text_length == 0 and len(body.strip()) < 50:
            return "empty_page"
        if "<noscript>" in lower_body and len(lower_body) < 300:
            return "js_required"
        if duration_ms and duration_ms > 8000:
            return "ok_but_slow"
        return "ok"

    if status and 300 <= status < 400:
        return "redirect_ok"

    return "ok"


def run_diagnosis(url: str, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Execute complete probe matrix against target URL."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    use_ssl = parsed.scheme == "https"

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"  KAWACH TARGET DIAGNOSIS: {url}")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    # 1. DNS, TCP, TLS
    print("[1/5] Probing DNS, TCP, and TLS handshake...")
    probe_a = probe_dns_tcp_tls(hostname, port, use_ssl)

    # 2. HTTP Legacy (backend default UA / HEAD & GET)
    print("[2/5] Probing HTTP with platform current client defaults (GET & HEAD)...")
    legacy_headers = {
        "User-Agent": "python-httpx/0.27.0",
        "Accept": "*/*",
    }
    probe_b_head = probe_http_request(url, method="HEAD", headers=legacy_headers)
    probe_b_get = probe_http_request(url, method="GET", headers=legacy_headers)

    # 3. HTTP Standard Chrome Desktop
    print("[3/5] Probing HTTP with modern Chrome Desktop User-Agent...")
    chrome_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }
    probe_c = probe_http_request(url, method="GET", headers=chrome_headers)

    # 4. Proxy check
    print("[4/5] Checking effective proxy environment...")
    proxy_env = {
        "HTTP_PROXY": os.environ.get("HTTP_PROXY"),
        "HTTPS_PROXY": os.environ.get("HTTPS_PROXY"),
        "ALL_PROXY": os.environ.get("ALL_PROXY"),
        "NO_PROXY": os.environ.get("NO_PROXY"),
    }
    probe_e_direct = probe_http_request(url, method="GET", headers=chrome_headers, trust_env=False)

    # 5. Playwright Profiles
    print("[5/5] Running Playwright Chromium profiles (Current vs New Standard vs Headed)...")
    probe_d = probe_playwright(url, out_dir)

    # Classifications
    class_b_head = classify_block(
        "HTTP_Legacy_HEAD",
        probe_b_head.get("status"),
        probe_b_head.get("body_snippet", ""),
        probe_b_head.get("headers", {}),
        probe_b_head.get("error"),
    )
    class_b_get = classify_block(
        "HTTP_Legacy_GET",
        probe_b_get.get("status"),
        probe_b_get.get("body_snippet", ""),
        probe_b_get.get("headers", {}),
        probe_b_get.get("error"),
    )
    class_c = classify_block(
        "HTTP_Chrome_GET",
        probe_c.get("status"),
        probe_c.get("body_snippet", ""),
        probe_c.get("headers", {}),
        probe_c.get("error"),
        duration_ms=probe_c.get("duration_ms"),
    )

    pw_curr = probe_d.get("current", {})
    pw_new = probe_d.get("new_standard", {})
    pw_head = probe_d.get("headed", {})

    class_pw_curr = classify_block(
        "PW_Current",
        pw_curr.get("status"),
        "",
        {},
        pw_curr.get("error"),
        text_length=pw_curr.get("textLength", 0),
    )
    class_pw_new = classify_block(
        "PW_NewStandard",
        pw_new.get("status"),
        "",
        {},
        pw_new.get("error"),
        text_length=pw_new.get("textLength", 0),
    )

    # Save HTML snapshot if available from Chrome GET
    if out_dir:
        snapshot_file = out_dir / "snapshot.html"
        try:
            with httpx.Client(follow_redirects=True, timeout=15.0) as client:
                full_resp = client.get(url, headers=chrome_headers)
                snapshot_file.write_text(full_resp.text, encoding="utf-8")
        except Exception:
            pass

    # Synthesize Verdict (Probe G)
    verdict_layer = "none"
    verdict_detail = ""

    if probe_a.get("error"):
        verdict_layer = "network/dns"
        verdict_detail = probe_a["error"]
    elif class_b_head in ("blocked_by_waf", "bad_gateway_from_target") and class_c == "ok":
        verdict_layer = "backend_client"
        verdict_detail = "Target blocks/rejects default python-httpx or HEAD preflight; normal Chrome GET succeeds."
    elif class_pw_curr != "ok" and class_pw_new == "ok":
        verdict_layer = "playwright_config"
        verdict_detail = "Target fails under current aggressive off-domain route aborting, but renders cleanly under new standard configuration."
    elif class_pw_curr == "blocked_by_waf" and class_pw_new == "blocked_by_waf":
        verdict_layer = "target_bot_protection"
        verdict_detail = "Target's WAF / CDN challenge intercepts automated Chromium sessions."
    elif class_pw_new == "empty_page":
        verdict_layer = "target_itself"
        verdict_detail = "Target returns empty body or client-side runtime error."
    else:
        verdict_layer = "ok"
        verdict_detail = "Target is accessible and renders interactive DOM content."

    report: Dict[str, Any] = {
        "target_url": url,
        "hostname": hostname,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "probe_a_dns_tcp_tls": probe_a,
        "probe_b_http_legacy": {
            "head": probe_b_head,
            "get": probe_b_get,
            "class_head": class_b_head,
            "class_get": class_b_get,
        },
        "probe_c_http_chrome": {
            "get": probe_c,
            "class": class_c,
        },
        "probe_d_playwright": {
            "current": pw_curr,
            "new_standard": pw_new,
            "headed": pw_head,
            "class_current": class_pw_curr,
            "class_new_standard": class_pw_new,
        },
        "probe_e_proxy": {
            "env": proxy_env,
            "direct_get": probe_e_direct,
        },
        "probe_g_verdict": {
            "responsible_layer": verdict_layer,
            "evidence": verdict_detail,
        },
    }

    if out_dir:
        out_json = out_dir / "diagnosis.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    # Print summary table
    print("\n" + "=" * 80)
    print(f"                      PROBE MATRIX SUMMARY: {url}")
    print("=" * 80)
    print(f"  Target Host      : {hostname} ({'HTTPS' if use_ssl else 'HTTP'})")
    print(f"  DNS Resolution   : IPv4={probe_a['ipv4']} | IPv6={probe_a['ipv6']} ({probe_a['dns_time_ms']} ms)")
    print(f"  TCP Connect      : {probe_a['tcp_connect_ms']} ms | TLS Handshake: {probe_a['tls_handshake_ms']} ms ({probe_a['tls_version']})")
    print("-" * 80)
    print(f"  [Probe B] HTTP Legacy HEAD  : Status {probe_b_head['status']} ({probe_b_head['duration_ms']} ms) -> {class_b_head}")
    print(f"  [Probe B] HTTP Legacy GET   : Status {probe_b_get['status']} ({probe_b_get['duration_ms']} ms) -> {class_b_get}")
    print(f"  [Probe C] HTTP Chrome GET   : Status {probe_c['status']} ({probe_c['duration_ms']} ms) -> {class_c}")
    print("-" * 80)
    print(f"  [Probe D] Playwright Current: Status {pw_curr.get('status')} | TextLen={pw_curr.get('textLength')} | VisEls={pw_curr.get('visibleElements')} | IdleReached={pw_curr.get('networkIdleReached')} -> {class_pw_curr}")
    print(f"  [Probe D] Playwright Standard: Status {pw_new.get('status')} | TextLen={pw_new.get('textLength')} | VisEls={pw_new.get('visibleElements')} | IdleReached={pw_new.get('networkIdleReached')} -> {class_pw_new}")
    print("-" * 80)
    print(f"  VERDICT LAYER    : {verdict_layer.upper()}")
    print(f"  EVIDENCE         : {verdict_detail}")
    print("=" * 80 + "\n")

    return report


def main():
    parser = argparse.ArgumentParser(description="Diagnose external target URL for automation suitability")
    parser.add_argument("url", help="Target URL (e.g. https://motionpremios.com)")
    parser.add_argument("--out", default=None, help="Output directory to save diagnosis.json, HTML snapshot and screenshots")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else Path("diagnostics") / urllib.parse.quote_plus(args.url.replace("://", "_"))
    run_diagnosis(args.url, out_path)


if __name__ == "__main__":
    main()
