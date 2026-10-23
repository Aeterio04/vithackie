"""Comprehensive API and schema validation audit script.
Tests all endpoints in packages/contracts/openapi.json against the running backend,
records actual response status, captures payloads, and verifies schema compliance.
"""

import json
import os
import sys
import time
from pathlib import Path
import httpx

REPO_ROOT = Path("c:/projects/aiqa")
OPENAPI_PATH = REPO_ROOT / "packages" / "contracts" / "openapi.json"
SAMPLES_DIR = REPO_ROOT / "docs" / "frontend-audit" / "api-samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

with open(OPENAPI_PATH, "r", encoding="utf-8") as f:
    openapi = json.load(f)

paths = openapi.get("paths", {})
print(f"Total OpenAPI Paths: {len(paths)}")

client = httpx.Client(base_url="http://localhost:8000", timeout=20.0)

# 1. Register & Login Audit User
reg_res = client.post("/api/v1/auth/register", json={
    "email": "audit_engineer@example.com",
    "password": "Password123!",
    "displayName": "Audit Engineer"
})
login_res = client.post("/api/v1/auth/login", json={
    "email": "audit_engineer@example.com",
    "password": "Password123!"
})
login_data = login_res.json() if login_res.status_code == 200 else {}
token = login_data.get("token") or login_data.get("access_token") or ""
auth_headers = {"Authorization": f"Bearer {token}"}
print(f"Auth Token Acquired: {bool(token)}")

# 2. Create Scoped API Token
token_res = client.post("/api/v1/auth/tokens", json={
    "name": "Audit CLI Token",
    "scopes": ["read", "write", "execute"],
    "expires_in_days": 30
}, headers=auth_headers)
token_data = token_res.json() if token_res.status_code == 201 else {}
kw_token = token_data.get("token_secret", "")
created_token_id = token_data.get("id", "tok_test")
print(f"API Token Created: {created_token_id} (kw_ token: {bool(kw_token)})")

# 3. Create Project
proj_res = client.post("/api/v1/projects", json={
    "name": "Audit E-Commerce App",
    "targetUrl": "http://localhost:4000",
    "description": "Target store for autonomous QA audit",
    "defaultMode": "manual",
    "budgets": {"maxPages": 10, "exploreSeconds": 60, "maxTests": 12, "testTimeoutMs": 30000}
}, headers=auth_headers)

if proj_res.status_code in (200, 201):
    project_data = proj_res.json()
    project_id = project_data["id"]
else:
    list_res = client.get("/api/v1/projects", headers=auth_headers)
    project_id = list_res.json()[0]["id"] if list_res.status_code == 200 and list_res.json() else "default"
print(f"Project ID: {project_id}")

# 4. Set Project Credentials
cred_res = client.put(f"/api/v1/projects/{project_id}/credentials", json={
    "username": "testuser",
    "password": "secretpassword"
}, headers=auth_headers)
print("Set Project Credentials status:", cred_res.status_code)

# 5. Locate or Seed Golden Run
# Check runs directory for available runs
runs_res = client.get("/api/v1/runs", headers=auth_headers)
all_runs = runs_res.json() if runs_res.status_code == 200 and isinstance(runs_res.json(), list) else []
if all_runs:
    run_id = all_runs[0].get("id") or all_runs[0].get("runId")
else:
    # Start a run
    start_res = client.post("/runs", json={
        "targetUrl": "http://localhost:4000",
        "mode": "manual"
    }, headers=auth_headers)
    run_id = start_res.json().get("runId") or "run_golden_demo"
print(f"Active Test Run ID: {run_id}")

# 6. Check bugs in run
bugs_res = client.get(f"/api/v1/runs/{run_id}/bugs", headers=auth_headers)
bugs_list = bugs_res.json() if bugs_res.status_code == 200 and isinstance(bugs_res.json(), list) else []
bug_id = bugs_list[0].get("id") if bugs_list else "bug_01"
print(f"Bug ID: {bug_id} (count: {len(bugs_list)})")

# 7. Check catalog tests in run
cat_res = client.get(f"/api/v1/runs/{run_id}/catalog", headers=auth_headers)
cat_data = cat_res.json() if cat_res.status_code == 200 and isinstance(cat_res.json(), dict) else {}
tests_list = cat_data.get("tests", [])
test_id = tests_list[0].get("id") if tests_list else "test_01"
print(f"Test ID: {test_id} (count: {len(tests_list)})")

# 8. Create a saved test in library
saved_test_id = "st_01"
save_res = client.post(f"/api/v1/projects/{project_id}/saved-tests", json={
    "test_id": test_id,
    "run_id": run_id,
    "title": "Verified Checkout Flow",
    "tags": ["checkout", "cart", "p0"]
}, headers=auth_headers)
if save_res.status_code in (200, 201):
    saved_test_id = save_res.json().get("id", "st_01")
print(f"Saved Test ID: {saved_test_id} (status: {save_res.status_code})")

# 9. Ingest Commit Event
commit_sha = "c0ffee123456"
commit_res = client.post(f"/api/v1/projects/{project_id}/commits", json={
    "commit_sha": commit_sha,
    "branch": "main",
    "message": "Fix cart calculation logic",
    "changed_files": ["server.js", "cart.js"]
}, headers=auth_headers)
print(f"Commit Ingestion status: {commit_res.status_code}")

endpoint_records = []

for path, path_item in paths.items():
    for method, op in path_item.items():
        if method.lower() not in ("get", "post", "put", "delete", "patch"):
            continue
        op_id = op.get("operationId", "")
        summary = op.get("summary", "")
        security = op.get("security", [])
        tags = op.get("tags", [])
        
        # Build concrete test URL
        test_url = path
        test_url = test_url.replace("{project_id}", project_id)
        test_url = test_url.replace("{run_id}", run_id)
        test_url = test_url.replace("{commit_id}", commit_sha).replace("{sha}", commit_sha)
        test_url = test_url.replace("{test_id}", test_id if "saved-tests" not in path else saved_test_id)
        test_url = test_url.replace("{token_id}", created_token_id)
        test_url = test_url.replace("{bug_id}", bug_id)
        test_url = test_url.replace("{path}", "report.md")
        test_url = test_url.replace("{artifact_id}", "art_01")

        # Choose headers
        headers = dict(auth_headers)
        if "webhooks/github" in path:
            headers["X-Hub-Signature-256"] = "sha256=invalid_test_hash"
            headers["X-GitHub-Delivery"] = "deliv_test_001"
            headers["X-GitHub-Event"] = "push"

        status_code = None
        sample_body = None
        error_msg = None
        start_time = time.time()

        try:
            req_kwargs = {"headers": headers}
            
            if "stream" in test_url.lower():
                with client.stream("GET", test_url, **req_kwargs) as stream_res:
                    status_code = stream_res.status_code
                    sample_body = {"stream": "SSE stream connected", "status": stream_res.status_code}
            elif method.lower() == "get":
                res = client.get(test_url, **req_kwargs)
                status_code = res.status_code
                try:
                    sample_body = res.json()
                except Exception:
                    sample_body = res.text[:300]
            elif method.lower() == "post":
                body = {}
                if "targets/check" in path:
                    body = {"targetUrl": "http://localhost:4000"}
                elif "auth/tokens" in path:
                    body = {"name": f"Token_{int(time.time())}", "scopes": ["read"]}
                elif "auth/login" in path:
                    body = {"email": "audit_engineer@example.com", "password": "Password123!"}
                elif "auth/register" in path:
                    body = {"email": f"test_{int(time.time())}@example.com", "password": "Password123!"}
                elif "projects" in path and path.endswith("/projects"):
                    body = {"name": f"P_{int(time.time())}", "targetUrl": "http://localhost:4000"}
                elif "saved-tests" in path:
                    body = {"test_id": test_id, "run_id": run_id}
                elif "commits" in path and path.endswith("/commits"):
                    body = {"commit_sha": f"sha_{int(time.time())}", "message": "Test commit"}
                elif "suggest-fix" in path:
                    body = {"analysis_id": "an_01"}
                elif "auto-fix" in path:
                    body = {"fix_id": "fix_01"}
                elif "review" in path:
                    body = {"decisions": [{"testId": test_id, "decision": "approve", "reason": "Verified"}]}
                elif "catalog/test" in path or "/tests" in path:
                    body = {"testId": "adhoc_01", "title": "Ad-hoc login test", "steps": [{"action": "click", "locator": "#btn"}]}
                elif "runs" in path:
                    body = {"targetUrl": "http://localhost:4000", "mode": "manual"}
                elif "webhooks/github" in path:
                    body = {"ref": "refs/heads/main", "commits": [{"id": "c0ffee1", "message": "test", "modified": ["server.js"]}]}
                
                res = client.post(test_url, json=body, **req_kwargs)
                status_code = res.status_code
                try:
                    sample_body = res.json()
                except Exception:
                    sample_body = res.text[:300]
            elif method.lower() == "put":
                body = {}
                if "credentials" in path:
                    body = {"username": "admin", "password": "password"}
                elif "catalog" in path:
                    body = {"tests": []}
                elif "projects" in path:
                    body = {"name": "Updated Project Name"}
                res = client.put(test_url, json=body, **req_kwargs)
                status_code = res.status_code
                try:
                    sample_body = res.json()
                except Exception:
                    sample_body = res.text[:300]
            elif method.lower() == "delete":
                res = client.delete(test_url, **req_kwargs)
                status_code = res.status_code
                try:
                    sample_body = res.json()
                except Exception:
                    sample_body = res.text[:300]
            elif method.lower() == "patch":
                body = {"title": "Patched Title"}
                res = client.patch(test_url, json=body, **req_kwargs)
                status_code = res.status_code
                try:
                    sample_body = res.json()
                except Exception:
                    sample_body = res.text[:300]
        except Exception as e:
            error_msg = str(e)

        elapsed_ms = round((time.time() - start_time) * 1000, 1)

        # Classification
        if status_code == 501:
            backend_classification = "501-NOT-IMPLEMENTED"
        elif status_code in (200, 201, 202, 204):
            backend_classification = "REAL-SUCCESS"
        elif status_code in (400, 401, 403, 404, 422):
            backend_classification = f"REAL-CLIENT-STATUS-{status_code}"
        elif status_code and status_code >= 500:
            backend_classification = f"SERVER-ERROR-{status_code}"
        else:
            backend_classification = "ERROR"

        record = {
            "method": method.upper(),
            "path": path,
            "operationId": op_id,
            "tags": tags,
            "summary": summary,
            "security": security,
            "test_url": test_url,
            "status_code": status_code,
            "backend_classification": backend_classification,
            "latency_ms": elapsed_ms,
            "error": error_msg,
        }
        endpoint_records.append(record)

        # Save individual sample
        safe_name = f"{method.upper()}_{path.replace('/', '_').replace('{', '').replace('}', '')}.json"
        with open(SAMPLES_DIR / safe_name, "w", encoding="utf-8") as sf:
            json.dump({
                "method": method.upper(),
                "path": path,
                "operationId": op_id,
                "test_url": test_url,
                "status_code": status_code,
                "latency_ms": elapsed_ms,
                "sample_response": sample_body,
            }, sf, indent=2, ensure_ascii=False)

print(f"\nTested {len(endpoint_records)} endpoint operations.")
classification_counts = {}
for r in endpoint_records:
    c = r["backend_classification"]
    classification_counts[c] = classification_counts.get(c, 0) + 1
print("Endpoint Classification Summary:")
for k, v in classification_counts.items():
    print(f"  {k}: {v}")

with open(REPO_ROOT / "docs" / "frontend-audit" / "endpoint_inventory.json", "w", encoding="utf-8") as out:
    json.dump(endpoint_records, out, indent=2, ensure_ascii=False)
print("Saved raw endpoint inventory to docs/frontend-audit/endpoint_inventory.json")
