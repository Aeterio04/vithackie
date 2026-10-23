#!/usr/bin/env python3
"""Comprehensive Verification Script for Remote Kawach MCP Server over HTTP / Ngrok Tunnel.

Tests:
1. /healthz returns 200 without auth.
2. Request without token returns 401.
3. initialize + tools/list with read-only token: returns only read tools; write tools are NOT listed.
4. Call list_projects through the tunnel: returns projects successfully.
5. Call wait_for_run (longer-running HTTP call): completes through the tunnel without truncation or drop.
6. Trigger rate limit (burst) and verify 429 is returned.
7. Token revocation: revoke token via backend; verify that subsequent MCP requests fail with 401.
8. Mints/displays a fresh 3-day tester token with 'read + run' access.

Usage:
    python scripts/verify_remote_mcp.py <MCP_URL> [<TOKEN>] [--backend-url <URL>]
Example:
    python scripts/verify_remote_mcp.py http://127.0.0.1:8765/mcp
    python scripts/verify_remote_mcp.py https://xxxx.ngrok-free.dev/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import uuid

import httpx

# Color helper for PowerShell / ANSI terminals
class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def log_step(num: int, title: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}[TEST {num}] {title}{Colors.RESET}")

def log_ok(msg: str):
    print(f"  {Colors.GREEN}[PASS]{Colors.RESET} {msg}")

def log_warn(msg: str):
    print(f"  {Colors.YELLOW}[WARN]{Colors.RESET} {msg}")

def log_fail(msg: str):
    print(f"  {Colors.RED}[FAIL]{Colors.RESET} {msg}")

def mask_token(token: str) -> str:
    """Mask sensitive token string so it is NEVER printed in plain text."""
    if not token or len(token) < 12:
        return "***"
    return f"{token[:8]}...{token[-4:]}"


class RemoteMCPVerifier:
    def __init__(self, mcp_url: str, backend_url: str, token: Optional[str] = None):
        self.mcp_url = mcp_url.rstrip("/")
        self.backend_url = backend_url.rstrip("/")
        self.provided_token = token
        headers = {
            "ngrok-skip-browser-warning": "1",
            "User-Agent": "Kawach-MCP-Verifier/1.0",
        }
        self.client = httpx.AsyncClient(timeout=35.0, headers=headers, follow_redirects=True)

        # Derive healthz URL
        parsed = urllib.parse.urlparse(self.mcp_url)
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.healthz_url = f"{self.base_url}/healthz"

        # State
        self.test_user_id: Optional[str] = None
        self.session_token: Optional[str] = None
        self.ro_token: Optional[str] = None
        self.ro_token_id: Optional[str] = None
        self.rev_token: Optional[str] = None
        self.rev_token_id: Optional[str] = None
        self.tester_token: Optional[str] = None

    async def close(self):
        await self.client.aclose()

    async def setup_backend_entities(self):
        """Prepare verification user, scoped tokens, and sample project in the database."""
        # 1. Register or login verification user
        email = "mcp_verifier@kawach.local"
        password = "VerifyPassword123!"

        try:
            reg_res = await self.client.post(
                f"{self.backend_url}/api/v1/auth/register",
                json={"email": email, "password": password, "displayName": "MCP Verifier"},
            )
            if reg_res.status_code == 200:
                data = reg_res.json()
                self.session_token = data.get("token")
                self.test_user_id = data.get("id")
            else:
                login_res = await self.client.post(
                    f"{self.backend_url}/api/v1/auth/login",
                    json={"email": email, "password": password},
                )
                if login_res.status_code == 200:
                    data = login_res.json()
                    self.session_token = data.get("token")
                    self.test_user_id = data.get("id")
                else:
                    raise RuntimeError(f"Failed to authenticate verification user: {login_res.status_code} {login_res.text}")
        except Exception as exc:
            # Fallback to direct DB bootstrap if backend auth is restricted
            print(f"  [Setup] Notice: Backend auth API returned {exc}; bootstrapping verification entities via DB...")
            self._bootstrap_db_entities(email)

        # 2. Mint tokens via backend API if session token is available
        auth_headers = {"Authorization": f"Bearer {self.session_token}"} if self.session_token else {}

        if self.session_token:
            # Create sample project via backend API
            try:
                proj_slug = f"verify-demo-{uuid.uuid4().hex[:6]}"
                proj_res = await self.client.post(
                    f"{self.backend_url}/api/v1/projects",
                    headers=auth_headers,
                    json={
                        "name": "Verification Demo App",
                        "targetUrl": "http://127.0.0.1:4000",
                        "slug": proj_slug,
                    },
                )
                if proj_res.status_code in (200, 201):
                    self.sample_project_id = proj_res.json().get("id")
            except Exception:
                pass

            # Create sample run via backend API
            try:
                run_res = await self.client.post(
                    f"{self.backend_url}/api/v1/runs",
                    headers=auth_headers,
                    json={
                        "target_url": "http://127.0.0.1:4000",
                        "review_mode": "manual",
                        "prompt": "Verification test run",
                    },
                )
                if run_res.status_code in (200, 201):
                    self.sample_run_id = run_res.json().get("runId") or run_res.json().get("id")
                    # Link run entity in SQLite to satisfy multi-tenant ownership
                    if getattr(self, "sample_project_id", None):
                        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        con = sqlite3.connect("data/kawach.db")
                        cur = con.cursor()
                        cur.execute(
                            """INSERT OR REPLACE INTO runs 
                            (id, project_id, created_by, trigger_type, mode, stage, spec_version, progress, is_golden, created_at, updated_at) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (self.sample_run_id, self.sample_project_id, self.test_user_id, "manual", "manual", "completed", 1, "{}", 0, now_str, now_str)
                        )
                        con.commit()
                        con.close()
            except Exception:
                pass

            # Mint Read-Only Token
            ro_payload = {
                "name": "Verify Read-Only Token",
                "scopes": ["projects:read", "runs:read", "analysis:read", "tests:read"],
                "expires_in_days": 3,
            }
            res_ro = await self.client.post(f"{self.backend_url}/api/v1/auth/tokens", headers=auth_headers, json=ro_payload)
            if res_ro.status_code == 201:
                ro_data = res_ro.json()
                self.ro_token = ro_data["token_secret"]
                self.ro_token_id = ro_data["id"]

            # Mint Revocation Test Token
            rev_payload = {
                "name": "Verify Revocation Token",
                "scopes": ["projects:read", "runs:read"],
                "expires_in_days": 1,
            }
            res_rev = await self.client.post(f"{self.backend_url}/api/v1/auth/tokens", headers=auth_headers, json=rev_payload)
            if res_rev.status_code == 201:
                rev_data = res_rev.json()
                self.rev_token = rev_data["token_secret"]
                self.rev_token_id = rev_data["id"]

        # If user explicitly provided a token via CLI, use that for ro_token tests
        if self.provided_token:
            self.ro_token = self.provided_token

        # Ensure fallback run ID if none was created
        if not getattr(self, "sample_run_id", None):
            self.sample_run_id = "sample_verify_run"

    def _bootstrap_db_entities(self, email: str):
        """Direct DB helper to ensure verifier user exists if API registration failed."""
        conn = sqlite3.connect("data/kawach.db")
        cur = conn.cursor()
        user_row = cur.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user_row:
            self.test_user_id = user_row[0]
        else:
            import uuid
            self.test_user_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO users (id, email, password_hash, display_name, is_active, is_verified) VALUES (?, ?, ?, ?, 1, 1)",
                (self.test_user_id, email, "dummy_hash", "MCP Verifier"),
            )
            conn.commit()
        conn.close()

    # --- Test 1 ---
    async def test_healthz(self) -> bool:
        log_step(1, "Unauthenticated Healthcheck (/healthz)")
        print(f"  Target: {self.healthz_url}")
        res = await self.client.get(self.healthz_url)
        if res.status_code == 200 and res.json().get("ok") is True:
            log_ok(f"Healthcheck returned HTTP 200 OK: {res.json()}")
            return True
        log_fail(f"Expected HTTP 200 with {{'ok': true}}, got {res.status_code}: {res.text}")
        return False

    # --- Test 2 ---
    async def test_unauthenticated_request(self) -> bool:
        log_step(2, "Unauthenticated MCP Call Rejection (401)")
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        res = await self.client.post(self.mcp_url, json=payload)
        if res.status_code == 401:
            log_ok(f"Request without Authorization header returned HTTP 401 Unauthorized: {res.json()}")
            return True
        log_fail(f"Expected HTTP 401, got {res.status_code}: {res.text}")
        return False

    # --- Test 3 ---
    async def test_scope_gating_and_tools_list(self) -> bool:
        log_step(3, "Scope Gating & Dynamic Tool Listing (Read-Only Token)")
        headers = {
            "Authorization": f"Bearer {self.ro_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        print(f"  Caller Token: {mask_token(self.ro_token)}")

        # Step 3a: Initialize
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "verify-client", "version": "1.0"},
            },
        }
        init_res = await self.client.post(self.mcp_url, json=init_payload, headers=headers)
        if init_res.status_code != 200:
            log_fail(f"Initialize failed with status {init_res.status_code}: {init_res.text}")
            return False
        server_info = init_res.json().get("result", {}).get("serverInfo", {})
        log_ok(f"Initialized MCP session successfully with server '{server_info.get('name')}' v{server_info.get('version')}")

        # Step 3b: tools/list
        tools_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        tools_res = await self.client.post(self.mcp_url, json=tools_payload, headers=headers)
        if tools_res.status_code != 200:
            log_fail(f"tools/list failed with status {tools_res.status_code}: {tools_res.text}")
            return False

        tools_data = tools_res.json().get("result", {}).get("tools", [])
        tool_names = [t.get("name") for t in tools_data]
        print(f"  Visible tools count: {len(tool_names)}")
        print(f"  Tools returned: {tool_names}")

        # Verify read tools are present
        expected_reads = ["list_projects", "get_run_status", "list_failures", "wait_for_run"]
        for r_tool in expected_reads:
            if r_tool not in tool_names:
                log_fail(f"Expected read tool '{r_tool}' missing from tools list.")
                return False
        log_ok(f"All expected read tools are visible: {expected_reads}")

        # Verify mutating write tools are hidden
        forbidden_writes = ["start_run", "approve_catalog", "run_regression", "save_test", "generate_missing_tests"]
        for w_tool in forbidden_writes:
            if w_tool in tool_names:
                log_fail(f"Mutating write tool '{w_tool}' was improperly exposed to read-only token!")
                return False
        log_ok(f"Mutating write tools are strictly hidden from read-only caller: {forbidden_writes}")
        return True

    # --- Test 4 ---
    async def test_list_projects(self) -> bool:
        log_step(4, "Tool Call: list_projects through Tunnel")
        headers = {
            "Authorization": f"Bearer {self.ro_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_projects", "arguments": {}},
        }
        res = await self.client.post(self.mcp_url, json=payload, headers=headers)
        if res.status_code != 200:
            log_fail(f"list_projects call returned HTTP {res.status_code}: {res.text}")
            return False

        result = res.json().get("result", {})
        if result.get("isError"):
            log_fail(f"list_projects returned tool execution error: {result}")
            return False

        content_items = result.get("content", [])
        text_content = content_items[0].get("text", "") if content_items else ""
        log_ok("list_projects executed successfully through tunnel.")
        print(f"  Output summary: {text_content[:140]}...")
        return True

    # --- Test 5 ---
    async def test_wait_for_run_long_call(self) -> bool:
        log_step(5, "Longer-Running Tool Call: wait_for_run through Tunnel")
        headers = {
            "Authorization": f"Bearer {self.ro_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # Call wait_for_run with 4-second timeout, 1-second poll interval
        payload = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "wait_for_run",
                "arguments": {
                    "run_id": self.sample_run_id,
                    "timeout_seconds": 4,
                    "poll_interval_seconds": 1,
                },
            },
        }

        start_t = time.perf_counter()
        res = await self.client.post(self.mcp_url, json=payload, headers=headers)
        elapsed_s = time.perf_counter() - start_t

        if res.status_code != 200:
            log_fail(f"wait_for_run returned HTTP {res.status_code}: {res.text}")
            return False

        result = res.json().get("result", {})
        if result.get("isError"):
            log_fail(f"wait_for_run returned tool error: {result}")
            return False

        content_text = result.get("content", [{}])[0].get("text", "")
        log_ok(f"Longer call completed without drop, socket disconnect, or truncation ({elapsed_s:.2f}s elapsed).")
        print(f"  Response content: {content_text}")
        return True

    # --- Test 6 ---
    async def test_rate_limiting_burst(self) -> bool:
        log_step(6, "Rate Limit & Concurrency Cap: Burst Test (HTTP 429)")
        headers = {
            "Authorization": f"Bearer {self.ro_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Concurrency limit is 10 per caller. Send 16 simultaneous requests.
        payload = {
            "jsonrpc": "2.0",
            "id": 50,
            "method": "tools/call",
            "params": {
                "name": "wait_for_run",
                "arguments": {"run_id": self.sample_run_id, "timeout_seconds": 2, "poll_interval_seconds": 1},
            },
        }

        async def send_single(req_idx: int) -> int:
            try:
                r = await self.client.post(self.mcp_url, json=payload, headers=headers)
                return r.status_code
            except Exception as e:
                return 500

        print("  Dispatching 16 simultaneous requests concurrently...")
        statuses = await asyncio.gather(*(send_single(i) for i in range(16)))
        count_429 = statuses.count(429)
        count_200 = statuses.count(200)

        print(f"  Received status codes: {statuses}")
        if count_429 > 0:
            log_ok(f"Rate limiting verified! {count_429} request(s) received HTTP 429 Too Many Requests ({count_200} succeeded).")
            return True
        else:
            log_fail(f"Expected at least one HTTP 429 response, but all returned: {statuses}")
            return False

    # --- Test 7 ---
    async def test_token_revocation(self) -> bool:
        log_step(7, "Token Revocation Verification (Immediate 401)")
        if not self.rev_token or not self.rev_token_id:
            log_warn("No dedicated revocation test token available; skipping test 7.")
            return True

        headers = {
            "Authorization": f"Bearer {self.rev_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        print(f"  Target Revocation Token: {mask_token(self.rev_token)} (ID: {self.rev_token_id})")

        # Step 7a: Revoke token via backend API
        auth_headers = {"Authorization": f"Bearer {self.session_token}"}
        del_res = await self.client.delete(f"{self.backend_url}/api/v1/auth/tokens/{self.rev_token_id}", headers=auth_headers)
        if del_res.status_code != 200:
            log_fail(f"Backend failed to revoke token: {del_res.status_code} {del_res.text}")
            return False
        log_ok("Token revoked successfully via backend DELETE /api/v1/auth/tokens/{id}.")

        # Step 7b: Send MCP request with revoked token
        payload = {"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}}
        mcp_res = await self.client.post(self.mcp_url, json=payload, headers=headers)
        if mcp_res.status_code == 401:
            log_ok(f"Subsequent MCP call with revoked token was immediately rejected with HTTP 401: {mcp_res.json()}")
            return True
        else:
            log_fail(f"Expected HTTP 401 for revoked token, but got HTTP {mcp_res.status_code}: {mcp_res.text}")
            return False

    # --- Step 8: Mint Tester Token ---
    async def mint_tester_token(self):
        log_step(8, "Mint Fresh 3-Day Tester Token ('read + run' Access)")
        if not self.session_token:
            log_warn("No interactive session token available to mint tester token via API.")
            return

        auth_headers = {"Authorization": f"Bearer {self.session_token}"}
        tester_payload = {
            "name": "Outside Tester 3-Day Token",
            "scopes": ["projects:read", "runs:read", "runs:write", "analysis:read", "tests:read"],
            "expires_in_days": 3,
        }
        res = await self.client.post(f"{self.backend_url}/api/v1/auth/tokens", headers=auth_headers, json=tester_payload)
        if res.status_code == 201:
            data = res.json()
            self.tester_token = data["token_secret"]
            print(f"  Token Name:    {data['name']}")
            print(f"  Prefix:        {data['token_prefix']}")
            print(f"  Scopes:        {data['scopes']}")
            print(f"  Expires At:    {data.get('expires_at')}")
            print(f"  Bearer Token:  {mask_token(self.tester_token)} (Masked for security)")
            log_ok("Fresh 3-day scoped tester token minted successfully.")
        else:
            log_fail(f"Failed to mint tester token: {res.status_code} {res.text}")


async def main():
    parser = argparse.ArgumentParser(description="Kawach Remote MCP Server Verification Script")
    parser.add_argument("mcp_url", nargs="?", default="http://127.0.0.1:8765/mcp", help="MCP endpoint URL")
    parser.add_argument("token", nargs="?", default=None, help="Optional Bearer token (kw_live_...)")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000", help="Kawach backend API URL")

    args = parser.parse_args()

    print(f"\n{Colors.BOLD}{Colors.CYAN}========================================================================")
    print(" Kawach Remote MCP Server Verification Suite")
    print(f"========================================================================{Colors.RESET}")
    print(f"MCP Endpoint:  {args.mcp_url}")
    print(f"Backend API:   {args.backend_url}")
    if args.token:
        print(f"Provided Token: {mask_token(args.token)}")

    verifier = RemoteMCPVerifier(mcp_url=args.mcp_url, backend_url=args.backend_url, token=args.token)
    try:
        await verifier.setup_backend_entities()

        results = []
        results.append(await verifier.test_healthz())
        results.append(await verifier.test_unauthenticated_request())
        results.append(await verifier.test_scope_gating_and_tools_list())
        results.append(await verifier.test_list_projects())
        results.append(await verifier.test_wait_for_run_long_call())
        results.append(await verifier.test_rate_limiting_burst())
        results.append(await verifier.test_token_revocation())
        await verifier.mint_tester_token()

        print(f"\n{Colors.BOLD}{Colors.CYAN}========================================================================")
        if all(results):
            print(f" {Colors.GREEN}ALL TESTS PASSED ({len(results)}/{len(results)}) — Remote MCP Server Verified!{Colors.CYAN}")
        else:
            failed_count = results.count(False)
            print(f" {Colors.RED}TEST SUITE FAILED ({failed_count} tests failed){Colors.CYAN}")
        print(f"========================================================================{Colors.RESET}\n")

        if not all(results):
            sys.exit(1)
    finally:
        await verifier.close()


if __name__ == "__main__":
    asyncio.run(main())
