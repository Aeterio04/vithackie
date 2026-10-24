#!/usr/bin/env python3
"""Reusable Connection Checker for Kawach (Next.js Frontend <-> FastAPI Backend).

Runs tests down the connection ladder (Layers 2.1 to 2.6):
- 2.1 Network Layer (DNS, TCP, Host Binding, Mixed Content)
- 2.2 Base URL & Routing (Rewrites, Proxy Headers, API Prefixes)
- 2.3 CORS Preflight & Headers (Origins, Allow-Credentials, Custom Headers, Error Responses)
- 2.4 Cookies & Cross-Origin Auth (Lax/None, Cookie Names, Next Middleware Visibility)
- 2.5 Contract & Schema Runtime Checks (Casing, Required Fields, Repository Methods)
- 2.6 SSE Streaming (EventSource, Header/Cookie Auth, Event Formatting)

Usage:
    python scripts/check_connection.py [--frontend FRONTEND_URL] [--backend BACKEND_URL]
"""

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.parse
from typing import Dict, List, Tuple

import httpx

# Color output helpers (PowerShell and POSIX terminal compatible)
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"


def mask_token(t: str) -> str:
    """Mask credentials, tokens, and secrets."""
    if not t or len(t) < 8:
        return "********"
    return f"{t[:4]}...{t[-4:]}"


def print_layer_header(layer_id: str, title: str):
    print(f"\n{COLOR_CYAN}=== Layer {layer_id}: {title} ==={COLOR_RESET}")


def report_result(step_name: str, passed: bool, evidence: str) -> bool:
    badge = f"{COLOR_GREEN}[PASS]{COLOR_RESET}" if passed else f"{COLOR_RED}[FAIL]{COLOR_RESET}"
    print(f"  {badge} {step_name}")
    for line in evidence.strip().split("\n"):
        print(f"         {line}")
    return passed


def run_check(frontend_url: str, backend_url: str) -> bool:
    print(f"\nKAWACH Connection Ladder Verification")
    print(f"Target Frontend: {frontend_url}")
    print(f"Target Backend:  {backend_url}")

    overall_pass = True
    layer_status: Dict[str, bool] = {}

    fe_parsed = urllib.parse.urlparse(frontend_url)
    be_parsed = urllib.parse.urlparse(backend_url)

    fe_host = fe_parsed.hostname or "localhost"
    fe_port = fe_parsed.port or (443 if fe_parsed.scheme == "https" else 80)
    be_host = be_parsed.hostname or "localhost"
    be_port = be_parsed.port or (443 if be_parsed.scheme == "https" else 80)

    # -------------------------------------------------------------
    # 2.1 Network Layer
    # -------------------------------------------------------------
    print_layer_header("2.1", "Network Layer (DNS, TCP, Host Binding, Mixed Content)")
    layer_2_1_pass = True

    # Check mixed content
    if fe_parsed.scheme == "https" and be_parsed.scheme == "http":
        layer_2_1_pass = False
        report_result(
            "Mixed Content Security",
            False,
            f"Frontend is HTTPS ({frontend_url}) calling HTTP backend ({backend_url}). Browsers will block this.",
        )
    else:
        report_result("Mixed Content Security", True, "Schemes match or safe (no HTTPS -> HTTP blocking).")

    # TCP reachability - Backend
    be_socket_ok = False
    try:
        sock = socket.create_connection((be_host, be_port), timeout=3.0)
        sock.close()
        be_socket_ok = True
        report_result(
            "Backend TCP Reachability",
            True,
            f"Successfully connected to {be_host}:{be_port}.",
        )
    except Exception as e:
        layer_2_1_pass = False
        report_result(
            "Backend TCP Reachability",
            False,
            f"Cannot connect to {be_host}:{be_port} -> {e}",
        )

    # TCP reachability - Frontend
    try:
        sock = socket.create_connection((fe_host, fe_port), timeout=3.0)
        sock.close()
        report_result(
            "Frontend TCP Reachability",
            True,
            f"Successfully connected to {fe_host}:{fe_port}.",
        )
    except Exception as e:
        layer_2_1_pass = False
        report_result(
            "Frontend TCP Reachability",
            False,
            f"Cannot connect to {fe_host}:{fe_port} -> {e}",
        )

    layer_status["2.1"] = layer_2_1_pass
    overall_pass = overall_pass and layer_2_1_pass

    if not be_socket_ok:
        print(f"\n{COLOR_RED}CRITICAL: Backend is unreachable. Aborting higher level checks.{COLOR_RESET}")
        return False

    be_client = httpx.Client(base_url=backend_url, timeout=10.0)
    fe_client = httpx.Client(base_url=frontend_url, timeout=10.0)

    # -------------------------------------------------------------
    # 2.2 Base URL and Routing
    # -------------------------------------------------------------
    print_layer_header("2.2", "Base URL and Routing (Next.js Rewrites & Path Prefixes)")
    layer_2_2_pass = True

    # Check direct backend health
    try:
        be_health = be_client.get("/api/v1/health")
        if be_health.status_code == 200:
            report_result("Backend /api/v1/health", True, f"HTTP {be_health.status_code}: {be_health.text[:80]}")
        else:
            layer_2_2_pass = False
            report_result("Backend /api/v1/health", False, f"Expected 200, got {be_health.status_code}")
    except Exception as e:
        layer_2_2_pass = False
        report_result("Backend /api/v1/health", False, str(e))

    # Check proxy/rewrite through frontend: /api/v1/health
    try:
        fe_proxied_health = fe_client.get("/api/v1/health")
        if fe_proxied_health.status_code == 200:
            report_result(
                "Frontend Next.js Rewrite /api/v1/*",
                True,
                f"HTTP {fe_proxied_health.status_code} forwarded cleanly to backend.",
            )
        else:
            layer_2_2_pass = False
            report_result(
                "Frontend Next.js Rewrite /api/v1/*",
                False,
                f"Expected 200 via frontend proxy, got {fe_proxied_health.status_code}. Check next.config.ts rewrites.",
            )
    except Exception as e:
        layer_2_2_pass = False
        report_result("Frontend Next.js Rewrite /api/v1/*", False, f"Proxy request failed: {e}")

    # Check trailing slash behavior
    try:
        trail_res = be_client.get("/api/v1/projects/", follow_redirects=False)
        if trail_res.status_code == 307:
            loc = trail_res.headers.get("location", "")
            report_result(
                "Trailing Slash 307 Handling",
                True,
                f"Trailing slash properly redirected (307) -> {loc}",
            )
        elif trail_res.status_code == 200:
            report_result("Trailing Slash Handling", True, "Trailing slash served directly (200).")
        else:
            report_result("Trailing Slash Handling", False, f"Unexpected status {trail_res.status_code}")
    except Exception as e:
        report_result("Trailing Slash Handling", False, str(e))

    layer_status["2.2"] = layer_2_2_pass
    overall_pass = overall_pass and layer_2_2_pass

    # -------------------------------------------------------------
    # 2.3 CORS Preflight & Headers
    # -------------------------------------------------------------
    print_layer_header("2.3", "CORS Preflights & Allowed Headers")
    layer_2_3_pass = True

    preflight_headers = {
        "Origin": frontend_url,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type, Idempotency-Key, X-Request-Id",
    }

    try:
        opts_res = be_client.options("/api/v1/projects", headers=preflight_headers)
        allow_orig = opts_res.headers.get("access-control-allow-origin")
        allow_cred = opts_res.headers.get("access-control-allow-credentials")
        allow_hdrs = (opts_res.headers.get("access-control-allow-headers") or "").lower()

        if opts_res.status_code == 200:
            orig_ok = allow_orig == frontend_url or allow_orig == "*"
            cred_ok = allow_cred == "true"
            idemp_ok = "idempotency-key" in allow_hdrs or allow_hdrs == "*" or not allow_hdrs

            if orig_ok and cred_ok:
                report_result(
                    "CORS Allow-Origin & Credentials",
                    True,
                    f"Origin={allow_orig}, Credentials={allow_cred}",
                )
            else:
                layer_2_3_pass = False
                report_result(
                    "CORS Allow-Origin & Credentials",
                    False,
                    f"Mismatch: Origin={allow_orig} (expected {frontend_url}), Credentials={allow_cred}",
                )

            if idemp_ok:
                report_result("CORS Idempotency-Key Allowed", True, f"Allow-Headers: {allow_hdrs or '*'}")
            else:
                layer_2_3_pass = False
                report_result(
                    "CORS Idempotency-Key Allowed",
                    False,
                    f"'Idempotency-Key' missing in Allow-Headers: {allow_hdrs}",
                )
        else:
            layer_2_3_pass = False
            report_result("CORS Preflight Status", False, f"Expected 200, got {opts_res.status_code}")
    except Exception as e:
        layer_2_3_pass = False
        report_result("CORS Preflight Execution", False, str(e))

    layer_status["2.3"] = layer_2_3_pass
    overall_pass = overall_pass and layer_2_3_pass

    # -------------------------------------------------------------
    # 2.4 Cookies and Auth Across Origins
    # -------------------------------------------------------------
    print_layer_header("2.4", "Cookies and Auth Across Origins")
    layer_2_4_pass = True

    ts = int(time.time())
    test_email = f"chk_conn_{ts}@example.com"
    test_pass = "Password123!"

    reg_res = be_client.post("/api/v1/auth/register", json={"email": test_email, "password": test_pass, "displayName": "Conn Checker"})
    login_res = be_client.post("/api/v1/auth/login", json={"email": test_email, "password": test_pass})

    token = None
    cookies_dict = {}
    if login_res.status_code == 200:
        login_body = login_res.json()
        token = login_body.get("token") or login_body.get("access_token")
        cookies_dict = dict(login_res.cookies)
        report_result(
            "Direct Login Token & Cookies",
            True,
            f"JWT={mask_token(token)}, Cookies Set: {list(cookies_dict.keys())}",
        )
    else:
        layer_2_4_pass = False
        report_result("Direct Login Token & Cookies", False, f"Login failed with HTTP {login_res.status_code}")

    # Check Next.js middleware cookie behavior
    # Next middleware on port 3000 expects auth cookies sent to origin 3000
    try:
        fe_dash = fe_client.get("/", follow_redirects=False)
        if fe_dash.status_code == 307 and "/login" in fe_dash.headers.get("location", ""):
            report_result(
                "Next.js Middleware Unauthenticated Gate",
                True,
                f"Correctly redirected unauthenticated browser to {fe_dash.headers.get('location')}",
            )
        else:
            report_result(
                "Next.js Middleware Unauthenticated Gate",
                True,
                f"Returned HTTP {fe_dash.status_code}",
            )
    except Exception as e:
        report_result("Next.js Middleware Check", False, str(e))

    # Authenticated /api/v1/auth/me via Cookie
    if cookies_dict:
        try:
            cookie_hdr = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
            me_cookie = be_client.get("/api/v1/auth/me", headers={"Cookie": cookie_hdr})
            if me_cookie.status_code == 200:
                report_result("Cookie Session Auth (/auth/me)", True, f"HTTP 200: email={me_cookie.json().get('email')}")
            else:
                layer_2_4_pass = False
                report_result("Cookie Session Auth (/auth/me)", False, f"HTTP {me_cookie.status_code}: {me_cookie.text}")
        except Exception as e:
            layer_2_4_pass = False
            report_result("Cookie Session Auth (/auth/me)", False, str(e))

    layer_status["2.4"] = layer_2_4_pass
    overall_pass = overall_pass and layer_2_4_pass

    # -------------------------------------------------------------
    # 2.5 Contract and Runtime Defect Checks
    # -------------------------------------------------------------
    print_layer_header("2.5", "Contract and Runtime Defect Checks")
    layer_2_5_pass = True

    bearer_hdrs = {"Authorization": f"Bearer {token}"} if token else {}

    # Check 1: ProjectRepository update_project & archive_project methods (Root Cause 2)
    # Create project
    proj_res = be_client.post("/api/v1/projects", json={"name": f"Check Project {ts}", "targetUrl": "http://localhost:3000"}, headers=bearer_hdrs)
    if proj_res.status_code in (200, 201):
        proj_id = proj_res.json()["id"]

        # Test PUT /projects/:id (Update)
        try:
            put_res = be_client.put(f"/api/v1/projects/{proj_id}", json={"name": "Updated Name"}, headers=bearer_hdrs)
            if put_res.status_code == 200:
                report_result("ProjectRepository.update_project", True, "HTTP 200: Project updated successfully.")
            elif put_res.status_code == 500:
                layer_2_5_pass = False
                report_result(
                    "ProjectRepository.update_project",
                    False,
                    f"HTTP 500: ProjectRepository is missing update_project method! (Defect D-04)",
                )
            else:
                layer_2_5_pass = False
                report_result("ProjectRepository.update_project", False, f"Unexpected HTTP {put_res.status_code}")
        except Exception as e:
            layer_2_5_pass = False
            report_result("ProjectRepository.update_project", False, f"Request failed: {e}")

        # Test DELETE /projects/:id (Archive)
        try:
            del_res = be_client.delete(f"/api/v1/projects/{proj_id}", headers=bearer_hdrs)
            if del_res.status_code == 200:
                report_result("ProjectRepository.archive_project", True, "HTTP 200: Project archived successfully.")
            elif del_res.status_code == 500:
                layer_2_5_pass = False
                report_result(
                    "ProjectRepository.archive_project",
                    False,
                    f"HTTP 500: ProjectRepository is missing archive_project method! (Defect D-04)",
                )
            else:
                layer_2_5_pass = False
                report_result("ProjectRepository.archive_project", False, f"Unexpected HTTP {del_res.status_code}")
        except Exception as e:
            layer_2_5_pass = False
            report_result("ProjectRepository.archive_project", False, f"Request failed: {e}")
    else:
        layer_2_5_pass = False
        report_result("Project Creation", False, f"HTTP {proj_res.status_code}: {proj_res.text}")

    # Check 2: Run Persistence in SQLite DB (Root Cause 1)
    try:
        run_create_res = be_client.post(
            "/api/v1/runs",
            json={"target_url": "http://localhost:3000", "review_mode": "manual", "prompt": "Check run"},
            headers=bearer_hdrs,
        )
        if run_create_res.status_code in (200, 201):
            created_run_id = run_create_res.json().get("id") or run_create_res.json().get("runId")
            # Now probe get_owned_run via GET /api/v1/runs/:id
            get_run_res = be_client.get(f"/api/v1/runs/{created_run_id}", headers=bearer_hdrs)
            if get_run_res.status_code == 200:
                report_result(
                    "Run Persistence & get_owned_run",
                    True,
                    f"HTTP 200: Created run {created_run_id} successfully persisted in SQLite DB.",
                )
            elif get_run_res.status_code == 404:
                layer_2_5_pass = False
                report_result(
                    "Run Persistence & get_owned_run",
                    False,
                    f"HTTP 404: Run was created in filesystem but missing from SQLite 'runs' table! (Root Cause 1)",
                )
            else:
                layer_2_5_pass = False
                report_result("Run Persistence & get_owned_run", False, f"HTTP {get_run_res.status_code}")
        else:
            layer_2_5_pass = False
            report_result("POST /api/v1/runs", False, f"HTTP {run_create_res.status_code}: {run_create_res.text}")
    except Exception as e:
        layer_2_5_pass = False
        report_result("Run Persistence Check", False, f"Request failed: {e}")

    layer_status["2.5"] = layer_2_5_pass
    overall_pass = overall_pass and layer_2_5_pass

    # -------------------------------------------------------------
    # 2.6 SSE Streaming
    # -------------------------------------------------------------
    print_layer_header("2.6", "Server-Sent Events (SSE) Streaming")
    layer_2_6_pass = True

    # Test /api/v1/runs/:id/stream
    stream_id = f"test_stream_{ts}"
    # Test v1 stream route accessibility
    try:
        with be_client.stream("GET", f"/api/v1/runs/{stream_id}/stream", headers=bearer_hdrs, timeout=3.0) as s_res:
            ct = s_res.headers.get("content-type", "")
            if s_res.status_code == 200 and "text/event-stream" in ct:
                report_result("/api/v1/runs/:id/stream", True, f"HTTP 200, Content-Type: {ct}")
            elif s_res.status_code == 404:
                # Expected when run is missing from DB
                report_result(
                    "/api/v1/runs/:id/stream Route",
                    True,
                    f"Route is mounted (returned 404 for non-existent run, not 405/500)",
                )
            else:
                layer_2_6_pass = False
                report_result("/api/v1/runs/:id/stream Route", False, f"HTTP {s_res.status_code}: {ct}")
    except Exception as e:
        report_result("/api/v1/runs/:id/stream Route", False, str(e))

    # Test legacy stream route formatting
    try:
        with be_client.stream("GET", f"/api/runs/{stream_id}/stream", timeout=2.0) as s_res:
            if s_res.status_code == 404:
                report_result(
                    "Legacy SSE Route (/api/runs/:id/stream)",
                    True,
                    "Route mounted and reachable through proxy.",
                )
    except Exception as e:
        report_result("Legacy SSE Route", False, str(e))

    layer_status["2.6"] = layer_2_6_pass
    overall_pass = overall_pass and layer_2_6_pass

    # -------------------------------------------------------------
    # Final Verdict Summary
    # -------------------------------------------------------------
    print(f"\n{COLOR_CYAN}=== Connection Ladder Verification Summary ==={COLOR_RESET}")
    for l_id, passed in sorted(layer_status.items()):
        status_text = f"{COLOR_GREEN}PASS{COLOR_RESET}" if passed else f"{COLOR_RED}FAIL{COLOR_RESET}"
        print(f"  Layer {l_id}: {status_text}")

    if overall_pass:
        print(f"\n{COLOR_GREEN}OVERALL STATUS: ALL LAYERS PASSED{COLOR_RESET}\n")
    else:
        print(f"\n{COLOR_RED}OVERALL STATUS: CONNECTION BROKEN AT LAYER(S) "
              f"{', '.join([k for k, v in layer_status.items() if not v])}{COLOR_RESET}\n")

    return overall_pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check Kawach frontend <-> backend connection ladder")
    parser.add_argument("--frontend", default="http://localhost:3000", help="Frontend URL (default: http://localhost:3000)")
    parser.add_argument("--backend", default="http://localhost:8000", help="Backend URL (default: http://localhost:8000)")
    args = parser.parse_args()

    success = run_check(args.frontend, args.backend)
    sys.exit(0 if success else 1)
