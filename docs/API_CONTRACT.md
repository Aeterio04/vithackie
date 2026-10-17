# KAWACH FastAPI Backend API Contract

This document specifies the exact REST endpoints, Pydantic model schemas, request payloads, response bodies, and Server-Sent Event (SSE) contracts required by the KAWACH Next.js frontend.

All endpoints are prefixed with `/api/v1` (configurable in `lib/api/config.ts`).

---

## 1. Authentication Endpoints

### `POST /api/v1/auth/login`
Authenticates user and sets an `httpOnly` session cookie (`session` or `access_token`).

**Request Body:**
```json
{
  "username_or_email": "engineer@company.com",
  "password": "secret_password"
}
```

**Response (200 OK):**
```json
{
  "id": "usr_99812",
  "username": "paras_qa",
  "email": "engineer@company.com",
  "name": "Paras Gajam",
  "role": "QA Engineer"
}
```

### `POST /api/v1/auth/logout`
Clears the session cookie.

**Response (200 OK):**
`{ "status": "logged_out" }`

### `GET /api/v1/auth/me`
Retrieves currently authenticated user from session cookie.

**Response (200 OK):**
Same as `AuthUser` schema above. Returns `401 Unauthorized` if no valid session cookie exists.

---

## 2. System, Health & Configuration

### `GET /api/v1/health`
Polled by frontend every 30 seconds for sandbox worker cluster status.

**Response (200 OK):**
```json
{
  "status": "active", // "active" | "degraded" | "offline"
  "workers_up": 4,
  "queue_depth": 0,
  "message": "Playwright worker cluster operational"
}
```

### `GET /api/v1/config/defaults`
Returns system limits, accepted file extensions, and default run budgets.

**Response (200 OK):**
```json
{
  "default_budgets": {
    "max_pages": 20,
    "max_steps_per_test": 30,
    "max_run_minutes": 15,
    "parallel_workers": 2
  },
  "limits": {
    "min_pages": 1,
    "max_pages": 100,
    "min_steps": 5,
    "max_steps": 100,
    "min_minutes": 1,
    "max_minutes": 60,
    "min_workers": 1,
    "max_workers": 4
  },
  "accepted_spec_extensions": [".md", ".txt", ".pdf", ".json", ".yaml", ".yml"],
  "max_spec_file_size_mb": 10
}
```

### `GET /api/v1/stats`
Returns aggregated KPI counts for Dashboard.

**Response (200 OK):**
```json
{
  "total_runs": 28,
  "confirmed_bugs": 12,
  "flaky_bugs": 4,
  "pending_reviews": 6
}
```

---

## 3. Pre-flight Target Check & Spec Upload

### `POST /api/v1/targets/check`
Pre-flight check before test run creation. Verifies network reachability, TLS, and allowlist.

**Request Body:**
```json
{
  "target_url": "https://staging.example.com"
}
```

**Response (200 OK):**
```json
{
  "reachable": true,
  "allowed": true,
  "reason": null,
  "tls_valid": true,
  "status_code": 200
}
```

### `POST /api/v1/specs/upload`
Uploads specification via multipart form (`file` or `spec_text`).

**Request (Multipart):**
- `file`: binary
- or `spec_text`: string

**Response (200 OK):**
```json
{
  "spec_id": "spec_39102",
  "filename": "onboarding_spec.md",
  "file_size_bytes": 14200,
  "item_count": 8
}
```

---

## 4. Test Runs Pipeline

### `POST /api/v1/runs`
Creates a new test run record.

**Request Body:**
```json
{
  "target_url": "https://staging.example.com",
  "prompt": "Test user signup and password reset flows",
  "spec_id": "spec_39102",
  "spec_text": null,
  "review_mode": "manual", // "manual" | "autonomous"
  "budgets": {
    "max_pages": 20,
    "max_steps_per_test": 30,
    "max_run_minutes": 15,
    "parallel_workers": 2
  },
  "credentials": {
    "username": "test_user",
    "password": "test_password"
  }
}
```

**Response (201 Created):**
```json
{
  "id": "run_01j7xyz",
  "target_url": "https://staging.example.com",
  "prompt": "Test user signup and password reset flows",
  "review_mode": "manual",
  "status": "created",
  "progress": 0,
  "created_at": "2026-10-18T00:00:00Z",
  "finished_at": null,
  "budgets": {
    "max_pages": 20,
    "max_steps_per_test": 30,
    "max_run_minutes": 15,
    "parallel_workers": 2
  },
  "budget_usage": {
    "pages_crawled": 0,
    "steps_executed": 0,
    "elapsed_minutes": 0,
    "active_workers": 0
  },
  "counts": {
    "total_tests": 0,
    "passed_tests": 0,
    "failed_tests": 0,
    "suspected_bugs": 0,
    "confirmed_bugs": 0,
    "flaky_bugs": 0,
    "not_reproduced_bugs": 0,
    "pending_reviews": 0
  }
}
```

### `POST /api/v1/runs/{id}/start`
Starts the autonomous agent pipeline (Explorer -> Planner).

### `POST /api/v1/runs/{id}/cancel`
Terminates all worker containers and sets status to `cancelled`.

### `POST /api/v1/runs/{id}/retry`
Re-queues tests that failed due to infrastructure `error`.

### `GET /api/v1/runs`
Returns array of all runs.

### `GET /api/v1/runs/{id}`
Returns a single run object.

---

## 5. Test Catalog & Review Gate

### `GET /api/v1/runs/{id}/catalog`
Returns tests built by the Planner agent.

**Response (200 OK):**
```json
[
  {
    "id": "test_101",
    "title": "User Registration with Valid Credentials",
    "spec_item_ids": ["AUTH-01", "AUTH-02"],
    "steps": [
      "Navigate to /signup",
      "Fill email with unique timestamp",
      "Submit registration form"
    ],
    "expected_result": "User is redirected to onboarding dashboard",
    "priority": "high", // "low" | "medium" | "high" | "critical"
    "review_status": "pending", // "pending" | "approved" | "rejected"
    "last_decision": null
  }
]
```

### `PATCH /api/v1/runs/{id}/catalog/{test_id}`
Updates an editable test.

**Request Body:**
```json
{
  "title": "Updated Test Title",
  "expected_result": "Updated expectation",
  "steps": ["Step 1", "Step 2"],
  "priority": "critical"
}
```

### `POST /api/v1/runs/{id}/review`
Submits review gate decisions.

**Request Body:**
```json
{
  "test_ids": ["test_101", "test_102"],
  "decision": "approved", // "approved" | "rejected"
  "reason": "Approved for execution"
}
```

### `GET /api/v1/runs/{id}/review-log`
Audit log of all decisions.

**Response (200 OK):**
```json
[
  {
    "test_id": "test_101",
    "decision": "approved",
    "actor": "human", // "human" | "reviewer_agent"
    "reason": "Approved for execution",
    "at": "2026-10-18T00:05:00Z"
  }
]
```

### `GET /api/v1/runs/{id}/app-map`
Discovered pages tree from Explorer.

**Response (200 OK):**
```json
{
  "run_id": "run_01j7xyz",
  "total_pages": 5,
  "max_pages_budget": 20,
  "root_node": {
    "id": "node_0",
    "url": "https://staging.example.com",
    "title": "Homepage",
    "depth": 0,
    "status_code": 200,
    "actions_found": ["btn#signup", "a[href='/pricing']"],
    "children": []
  }
}
```

---

## 6. Execution & Bugs

### `GET /api/v1/runs/{id}/execution`
Returns live state of workers and test execution queue.

**Response (200 OK):**
```json
{
  "workers": [
    {
      "id": "worker-1",
      "kind": "runner", // "runner" | "exploratory"
      "current_test_id": "test_101",
      "current_step": "Filling email input",
      "status": "running", // "idle" | "running" | "verifying" | "offline" | "error"
      "latest_screenshot_url": "/api/v1/artifacts/worker-1-latest.png",
      "screenshot_updated_at": "2026-10-18T00:06:10Z"
    }
  ],
  "tests": [],
  "budget_usage": {
    "pages_crawled": 5,
    "steps_executed": 34,
    "elapsed_minutes": 4,
    "active_workers": 2
  }
}
```

### `GET /api/v1/runs/{id}/bugs` and `GET /api/v1/bugs/{bug_id}`
Returns bug records with 3x replay trials and evidence.

**Response (200 OK):**
```json
{
  "id": "bug_9901",
  "run_id": "run_01j7xyz",
  "title": "Unhandled 500 when submitting password with special characters",
  "severity": "high", // "low" | "medium" | "high" | "critical"
  "source": "test_runner", // "test_runner" | "exploratory"
  "spec_item_ids": ["AUTH-02"],
  "status": "confirmed", // "suspected" | "verifying" | "confirmed" | "flaky" | "not_reproduced"
  "replays": [
    {
      "index": 1,
      "result": "reproduced", // "reproduced" | "not_reproduced" | "error" | "pending"
      "duration_ms": 1420,
      "video_url": "/api/v1/artifacts/bug_9901_replay_1.webm",
      "timestamp": "2026-10-18T00:07:00Z"
    },
    {
      "index": 2,
      "result": "reproduced",
      "duration_ms": 1390,
      "video_url": "/api/v1/artifacts/bug_9901_replay_2.webm",
      "timestamp": "2026-10-18T00:07:30Z"
    },
    {
      "index": 3,
      "result": "reproduced",
      "duration_ms": 1450,
      "video_url": "/api/v1/artifacts/bug_9901_replay_3.webm",
      "timestamp": "2026-10-18T00:08:00Z"
    }
  ],
  "steps_to_reproduce": [
    "Navigate to /signup",
    "Enter password with characters: &%#$*",
    "Click submit"
  ],
  "expected": "Validation error or successful password hashing",
  "actual": "Page rendered unhandled 500 Internal Server Error",
  "evidence": {
    "screenshots": ["/api/v1/artifacts/bug_9901_screen.png"],
    "video_url": "/api/v1/artifacts/bug_9901_replay_1.webm",
    "trace_url": "/api/v1/artifacts/bug_9901_trace.zip",
    "logs": "[Playwright] Error: page received 500 response",
    "console": ["Uncaught TypeError: Cannot read properties of undefined"],
    "network": []
  },
  "repro_script_url": "/api/v1/artifacts/bug_9901_repro.ts"
}
```

---

## 7. Server-Sent Events (SSE) Contract

Endpoint: `GET /api/v1/runs/{id}/stream`
Stream headers:
```
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no
```

### Event Payloads (JSON encoded in `data:`)
Each SSE event has a `type` matching this union:

1. `run.status`
```json
{ "type": "run.status", "status": "executing", "progress": 45 }
```

2. `log`
```json
{
  "type": "log",
  "timestamp": "2026-10-18T00:06:12Z",
  "level": "info", // "info" | "warn" | "error" | "debug"
  "source": "worker-1",
  "message": "Clicking button #submit-signup"
}
```

3. `catalog.ready`
```json
{ "type": "catalog.ready", "tests": [...] }
```

4. `review.decision`
```json
{ "type": "review.decision", "decision": { "test_id": "test_1", "decision": "approved", "actor": "human", "reason": "Looks good", "at": "..." } }
```

5. `worker.update`
```json
{ "type": "worker.update", "worker": { "id": "worker-1", "kind": "runner", "status": "running", ... } }
```

6. `test.update`
```json
{ "type": "test.update", "test": { "id": "test_1", "title": "Signup", "status": "passed", "duration_ms": 2300 } }
```

7. `bug.suspected`
```json
{ "type": "bug.suspected", "bug": { "id": "bug_1", "title": "Crash on click", "status": "suspected", ... } }
```

8. `bug.verification`
```json
{
  "type": "bug.verification",
  "bug_id": "bug_1",
  "replay_index": 1,
  "result": "reproduced", // "reproduced" | "not_reproduced" | "error"
  "duration_ms": 1200,
  "video_url": "/api/v1/artifacts/replay_1.webm"
}
```

9. `bug.final`
```json
{ "type": "bug.final", "bug": { "id": "bug_1", "status": "confirmed", ... } }
```

10. `budget.update`
```json
{
  "type": "budget.update",
  "usage": { "pages_crawled": 6, "steps_executed": 42, "elapsed_minutes": 5, "active_workers": 2 }
}
```

11. `run.done`
```json
{ "type": "run.done", "run": { "id": "run_1", "status": "completed", ... } }
```

---

## 8. Polling Fallback

`GET /api/v1/runs/{id}/events?since={cursor}`
Returns JSON array of missed events if SSE encounters connection interruptions:
```json
[
  { "id": "evt_101", "data": "{\"type\":\"log\", ...}" }
]
```
