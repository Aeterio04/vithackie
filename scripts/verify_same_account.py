#!/usr/bin/env python3
"""The key scenario: what the MCP server does shows up in the same user's website dashboard.

1. Register a throwaway user.
2. "MCP side": log in via POST /api/v1/auth/login and use only `Authorization: Bearer <token>` (no cookies) to create a
   project and start a run.
3. "Website side": a fresh client logs in the way the browser does (httpOnly cookie, no Authorization header) and
   asserts the project and run appear in its lists and details.
4. A different user must not see them.

    python scripts/verify_same_account.py [--base-url http://localhost:8000]   # backend directly
    python scripts/verify_same_account.py --base-url http://localhost:3000     # through the website's /api proxy
"""

import argparse
import sys
import uuid

import httpx

API = "/api/v1"
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""))
    failures += 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    base = ap.parse_args().base_url.rstrip("/")
    tag = uuid.uuid4().hex[:8]
    email, pw = f"same-account-{tag}@example.com", f"Same-{uuid.uuid4().hex[:10]}!"

    boot = httpx.Client(base_url=base, timeout=60)
    r = boot.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": "Same Account"})
    check("register", r.status_code == 200, r.text[:120])

    # --- MCP side: Bearer token only ---
    mcp = httpx.Client(base_url=base, timeout=60)
    r = mcp.post(f"{API}/auth/login", json={"email": email, "password": pw})
    check("MCP-style login returns a JWT", r.status_code == 200 and bool(r.json().get("token")), r.text[:120])
    mcp.cookies.clear()
    mcp.headers["Authorization"] = f"Bearer {r.json()['token']}"
    check("MCP whoami shows the account email", mcp.get(f"{API}/auth/me").json().get("email") == email)
    p = mcp.post(f"{API}/projects", json={"name": f"From MCP {tag}", "targetUrl": "http://localhost:4000"})
    check("MCP creates a project", p.status_code == 201, p.text[:120])
    pid = p.json()["id"]
    run = mcp.post(f"{API}/runs", json={"target_url": "http://localhost:4000", "project_id": pid, "review_mode": "manual", "prompt": "same-account"})
    check("MCP starts a run", run.status_code == 201, run.text[:150])
    rid = run.json()["id"]

    # --- website side: cookie only ---
    web = httpx.Client(base_url=base, timeout=60)
    r = web.post(f"{API}/auth/login", json={"email": email.upper(), "password": pw})  # also proves case-insensitive email
    check("website-style login sets an httpOnly cookie", r.status_code == 200 and "auth_token" in web.cookies, r.text[:120])
    check("website session has no Authorization header", "authorization" not in {k.lower() for k in web.headers})
    check("website sees the same account", web.get(f"{API}/auth/me").json().get("email") == email)
    check("project from MCP appears in the website's project list", pid in [x["id"] for x in web.get(f"{API}/projects").json()])
    check("run from MCP appears in the website's run list", rid in [x["id"] for x in web.get(f"{API}/runs").json()])
    check("run appears under the project", rid in [x["id"] for x in web.get(f"{API}/projects/{pid}/runs").json()])
    check("website can open the run's detail", web.get(f"{API}/runs/{rid}").status_code == 200)
    check("website can open the run's event stream (cookie auth)", _sse_ok(web, rid))

    # --- reverse: website-created project is visible to the MCP token ---
    p2 = web.post(f"{API}/projects", json={"name": f"From web {tag}", "targetUrl": "http://localhost:4000"})
    check("website creates a project", p2.status_code == 201)
    check("project from the website appears for the MCP token", p2.json()["id"] in [x["id"] for x in mcp.get(f"{API}/projects").json()])

    # --- someone else sees nothing ---
    other = httpx.Client(base_url=base, timeout=60)
    o = other.post(f"{API}/auth/register", json={"email": f"other-{tag}@example.com", "password": pw})
    other.headers["Authorization"] = f"Bearer {o.json()['token']}"
    check("another user sees none of it", other.get(f"{API}/projects").json() == [] and other.get(f"{API}/runs").json() == [])

    print(f"\n{'ALL CHECKS PASSED' if not failures else str(failures) + ' CHECK(S) FAILED'}")
    return 1 if failures else 0


def _sse_ok(client: httpx.Client, rid: str) -> bool:
    try:
        with client.stream("GET", f"{API}/runs/{rid}/stream", timeout=10) as r:
            if r.status_code != 200 or "text/event-stream" not in r.headers.get("content-type", ""):
                return False
            for _ in r.iter_lines():
                return True
            return True
    except httpx.HTTPError:
        return False


if __name__ == "__main__":
    sys.exit(main())
