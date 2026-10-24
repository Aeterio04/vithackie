#!/usr/bin/env python3
"""Live proof of per-user isolation against a RUNNING backend.

Registers two throwaway users (A and B), has A create a project and start a run, then asserts that B sees nothing of
A's data through every list and detail endpoint, and that unauthenticated requests get 401. Prints PASS/FAIL per
check and exits non-zero if anything failed.

    python scripts/verify_isolation.py [--base-url http://localhost:8000]

Creates two accounts named isolation-*@example.com on the target backend (point it at a dev/test instance).
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
    pw = f"Iso-{uuid.uuid4().hex[:10]}!"
    a, b, anon = (httpx.Client(base_url=base, timeout=60) for _ in range(3))

    def reg(c: httpx.Client, who: str) -> dict:
        r = c.post(f"{API}/auth/register", json={"email": f"isolation-{who}-{tag}@example.com", "password": pw, "name": who})
        assert r.status_code == 200, f"register {who}: {r.status_code} {r.text}"
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        c.cookies.clear()  # use the Bearer header only, like an API client
        return r.json()

    ua, ub = reg(a, "a"), reg(b, "b")
    check("A and B are different accounts", ua["id"] != ub["id"])

    proj = a.post(f"{API}/projects", json={"name": f"A private {tag}", "targetUrl": "http://localhost:4000"})
    check("A creates a project", proj.status_code == 201, proj.text[:100])
    pid = proj.json()["id"]
    a.put(f"{API}/projects/{pid}/credentials", json={"username": "alice-app-user", "password": "alice-app-secret"})
    run = a.post(f"{API}/runs", json={"target_url": "http://localhost:4000", "project_id": pid, "review_mode": "manual", "prompt": "isolation"})
    check("A starts a run", run.status_code == 201, run.text[:150])
    rid = run.json()["id"]
    check("A sees her project and run",
          pid in [p["id"] for p in a.get(f"{API}/projects").json()] and rid in [r["id"] for r in a.get(f"{API}/runs").json()])
    check("A can read her own run", a.get(f"{API}/runs/{rid}").status_code == 200)

    # ---- B must see nothing ----
    check("B's project list is empty", b.get(f"{API}/projects").json() == [])
    check("B's run list is empty", b.get(f"{API}/runs").json() == [])
    check("B's legacy /runs list is empty", b.get("/runs").json() == [])
    check("B's stats show 0 runs", b.get(f"{API}/stats").json().get("total_runs") == 0)
    paths = [
        ("GET", f"/projects/{pid}"), ("PUT", f"/projects/{pid}"), ("DELETE", f"/projects/{pid}"),
        ("GET", f"/projects/{pid}/credentials"), ("GET", f"/projects/{pid}/runs"),
        ("GET", f"/projects/{pid}/saved-tests"), ("GET", f"/projects/{pid}/commits"),
        ("GET", f"/runs/{rid}"), ("POST", f"/runs/{rid}/cancel"), ("DELETE", f"/runs/{rid}"),
        ("GET", f"/runs/{rid}/catalog"), ("POST", f"/runs/{rid}/review"), ("GET", f"/runs/{rid}/bugs"),
        ("GET", f"/runs/{rid}/logs"), ("GET", f"/runs/{rid}/events"), ("GET", f"/runs/{rid}/execution"),
        ("GET", f"/runs/{rid}/app-map"), ("GET", f"/runs/{rid}/report"), ("GET", f"/runs/{rid}/metrics"),
        ("GET", f"/runs/{rid}/export"), ("GET", f"/runs/{rid}/stream"), ("GET", f"/runs/{rid}/files/run.json"),
    ]
    for method, path in paths:
        body = {"test_ids": [], "decision": "approved", "name": "x", "username": "u", "password": "p"} if method in ("POST", "PUT") else None
        r = b.request(method, API + path, json=body)
        check(f"B -> {method} {path.replace(pid, '<A project>').replace(rid, '<A run>')} is 404", r.status_code == 404, str(r.status_code))
    check("B -> GET legacy /runs/<A run> is 404", b.get(f"/runs/{rid}").status_code == 404)
    r = b.post(f"{API}/runs", json={"target_url": "http://localhost:4000", "project_id": pid})
    check("B cannot start a run inside A's project", r.status_code == 404, str(r.status_code))
    check("B cannot copy A's tests via saved-tests",
          b.post(f"{API}/projects/{pid}/saved-tests", json={"run_id": rid, "test_id": "T01"}).status_code == 404)
    check("B cannot read A's storage folder", b.get(f"{API}/storage/files/by-path/users/{ua['id']}/x.png").status_code == 404)

    # ---- nobody ----
    for path in ("/projects", "/runs", f"/runs/{rid}", f"/runs/{rid}/stream", "/stats", "/auth/me"):
        check(f"anonymous GET {path} is 401", anon.get(API + path).status_code == 401)
    check("anonymous legacy GET /runs is 401", anon.get("/runs").status_code == 401)
    check("query-string ?token= is not accepted", anon.get(f"{API}/auth/me", params={"token": ua["token"]}).status_code == 401)

    # ---- A is untouched ----
    check("A's project is still intact after B's attempts", a.get(f"{API}/projects/{pid}").json()["name"] == f"A private {tag}")
    print(f"\n{'ALL CHECKS PASSED' if not failures else str(failures) + ' CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
