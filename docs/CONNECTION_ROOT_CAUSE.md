# Kawach Connection Root Cause Analysis (Phase 2)

**Document Version:** 1.0  
**Generated:** 2026-10-24  
**Scope:** Connection Ladder Layers 2.0 – 2.7 (Frontend `apps/web` on port 3000 <-> Backend `apps/api` on port 8000)  
**Verification Tool:** `scripts/check_connection.py`

---

## 1. Executive Summary & Ladder Status

An exhaustive connection ladder diagnosis was executed across both servers. The results by layer:

| Layer | Title | Status | Findings Summary |
|---|---|---|---|
| **2.1** | Network Layer | **PASS** | Host binding `0.0.0.0:8000` & `localhost:3000` reachable via TCP. No mixed content (both HTTP in development). |
| **2.2** | Base URL & Routing | **PASS** | Next.js rewrites forward `/api/v1/*` cleanly to `http://localhost:8000/api/v1/*`. Trailing slash 307 redirects operate correctly. |
| **2.3** | CORS Preflights & Headers | **PASS** | Origin `http://localhost:3000` allowed with `credentials: true`. `Idempotency-Key` and `X-Request-Id` present in `access-control-allow-headers`. |
| **2.4** | Cookies & Cross-Origin Auth | **PASS** | `auth_token` and session cookies set with `SameSite=Lax`. Authenticated cookie sessions resolve `/api/v1/auth/me` with HTTP 200. Next middleware handles unauthenticated gating. |
| **2.5** | Contract & Runtime Integrity | **FAIL** | **CRITICAL DEFECTS FOUND:** Missing `DbRun` database persistence breaks all run endpoints with universal 404; missing `ProjectRepository` methods crash project settings with HTTP 500; camelCase/snake_case contract mismatch causes HTTP 422. |
| **2.6** | SSE Streaming | **PASS (Route) / FAIL (Event Protocol)** | Route is mounted; however, frontend config points to legacy endpoint `/api/runs/:id/stream` which emits named events that standard browser `EventSource.onmessage` drops. |
| **2.7** | Real Browser Verification | **FAIL** | Direct consequence of Layer 2.5 and 2.6 defects: user cannot open run details or update project settings in browser. |

---

## 2. Confirmed Defects & Root Cause Analysis

### Defect 1: Run State Missing in Database (`DbRun` Record Not Created)

- **Affected Layer:** Layer 2.5 (Contract & Runtime Data Integrity)
- **Severity:** **CRITICAL**
- **Symptom:**
  Immediately after creating a test run via `POST /api/v1/runs`, navigating to the run details page or querying any sub-resource (`GET /api/v1/runs/:id`, `/catalog`, `/execution`, `/tests`, `/bugs`, `/logs`, `/stream`) returns `HTTP 404 Not Found` with message `{"detail": "Run not found"}`.
- **Request / Response Evidence:**
  ```http
  POST /api/v1/runs HTTP/1.1
  Host: localhost:8000
  Authorization: Bearer <masked_jwt>
  Content-Type: application/json

  {"target_url": "http://localhost:3000", "review_mode": "manual", "prompt": "Check run"}

  HTTP/1.1 201 Created
  {"id": "20261023-191126-d6b7", "status": "queued", ...}
  ```
  Immediately followed by:
  ```http
  GET /api/v1/runs/20261023-191126-d6b7 HTTP/1.1
  Host: localhost:8000
  Authorization: Bearer <masked_jwt>

  HTTP/1.1 404 Not Found
  {"detail": "Run not found"}
  ```
- **Root Cause:**
  In `apps/api/src/kawach/services/run_service.py` (`create_run`), runs are written only to the local filesystem (`runs/<run_id>/run.json`). No record is inserted into the SQLite database table `runs` (`DbRun`).
  All v1 run endpoints depend on `_run: DbRun = Depends(get_owned_run)` in `apps/api/src/kawach/api/deps.py`. For logged-in users, `scope.is_system` is `False`, so `get_owned_run` executes:
  ```python
  run = session.exec(select(Run).where(Run.id == run_id)).first()
  if not run:
      raise HTTPException(404, "Run not found")
  ```
  Since the database row was never inserted, every authenticated run lookup fails with 404.
- **Minimal Proposed Fix:**
  In `apps/api/src/kawach/api/v1/runs.py` (inside `create_run`), insert and commit a `DbRun` instance into the database session:
  ```python
  db_run = DbRun(
      id=run.runId,
      project_id=project_id,
      status=run.status or "queued",
      created_by=scope.user_id if scope else None,
  )
  session.add(db_run)
  session.commit()
  ```
- **Verification Steps:**
  1. Create run via `POST /api/v1/runs`.
  2. Query `GET /api/v1/runs/{id}` with JWT Bearer token.
  3. Verify `HTTP 200 OK` with run schema matching OpenAPI specifications.

---

### Defect 2: Missing `update_project` and `archive_project` on `ProjectRepository`

- **Affected Layer:** Layer 2.5 (Contract & Repository Implementation)
- **Severity:** **HIGH**
- **Symptom:**
  Saving project settings or deleting/archiving a project throws an unhandled `AttributeError`, causing `HTTP 500 Internal Server Error` and abrupt TCP connection drops (`[Errno 54] Connection reset by peer`).
- **Request / Response Evidence:**
  ```http
  PUT /api/v1/projects/47a5289f-9b3e-4094-bb6f-fd0d8b8216c6 HTTP/1.1
  Host: localhost:8000
  Authorization: Bearer <masked_jwt>
  Content-Type: application/json

  {"name": "Updated Project Name"}

  HTTP/1.1 500 Internal Server Error
  ```
  Server Log Traceback:
  ```
  File "apps/api/src/kawach/api/v1/projects.py", line 122, in update_project
    updated = service.update_project(...)
  File "apps/api/src/kawach/services/project_service.py", line 86, in update_project
    project = self.project_repo.update_project(...)
  AttributeError: 'ProjectRepository' object has no attribute 'update_project'. Did you mean: 'create_project'?
  ```
  Similar traceback for `DELETE /api/v1/projects/:id`:
  ```
  File "apps/api/src/kawach/services/project_service.py", line 106, in archive_project
    success = self.project_repo.archive_project(scope, project_id)
  AttributeError: 'ProjectRepository' object has no attribute 'archive_project'. Did you mean: 'create_project'?
  ```
- **Root Cause:**
  `ProjectService` invokes `self.project_repo.update_project(...)` and `self.project_repo.archive_project(...)`, but `apps/api/src/kawach/repositories/project_repo.py` does not define these methods.
- **Minimal Proposed Fix:**
  Add `update_project` and `archive_project` methods to `ProjectRepository` in `apps/api/src/kawach/repositories/project_repo.py`:
  ```python
  def update_project(
      self,
      scope: Any,
      project_id: str,
      name: Optional[str] = None,
      description: Optional[str] = None,
      repository_url: Optional[str] = None,
      budgets: Optional[Dict[str, Any]] = None,
  ) -> Optional[Project]:
      project = self.get_by_id(scope, project_id)
      if not project:
          return None
      if name is not None:
          project.name = name
      if description is not None:
          project.description = description
      if repository_url is not None:
          project.repository_url = repository_url
      if budgets is not None:
          project.budgets = json.dumps(budgets) if isinstance(budgets, dict) else budgets
      self.session.commit()
      self.session.refresh(project)
      return project

  def archive_project(self, scope: Any, project_id: str) -> bool:
      project = self.get_by_id(scope, project_id)
      if not project:
          return False
      project.is_archived = True
      self.session.commit()
      return True
  ```
- **Verification Steps:**
  1. Execute `PUT /api/v1/projects/{id}` -> Expect `HTTP 200 OK`.
  2. Execute `DELETE /api/v1/projects/{id}` -> Expect `HTTP 200 OK` with `{"archived": true}`.

---

### Defect 3: SSE Endpoint URL and Event Stream Parsing Mismatch

- **Affected Layer:** Layer 2.6 (SSE Streaming)
- **Severity:** **MEDIUM**
- **Symptom:**
  Frontend execution logs and live progress remain blank or disconnected during run execution.
- **Request / Response Evidence:**
  - `apps/web/src/shared/lib/api/config.ts`:
    ```typescript
    RUN_STREAM: (runId: string) => `/api/runs/${runId}/stream`,
    ```
  - The endpoint `/api/runs/{id}/stream` formats messages as:
    ```
    event: stage_change
    data: {"runId": "...", "stage": "...", ...}
    ```
  - In `apps/web/src/shared/hooks/useRunStream.ts`, the browser hook attaches:
    ```typescript
    eventSource.onmessage = (event) => { ... }
    ```
    According to the W3C Server-Sent Events standard, `eventSource.onmessage` only triggers for events with NO event field or `event: message`. Messages with `event: stage_change` require `eventSource.addEventListener("stage_change", ...)`.
  - Furthermore, `useRunStream.ts` expects the typed payload `{ type: "run.status", runId, status, progress }` which is only emitted by `/api/v1/runs/{id}/stream`.
- **Root Cause:**
  Frontend configuration points to the legacy SSE endpoint instead of the versioned `/api/v1/runs/${runId}/stream` route.
- **Minimal Proposed Fix:**
  1. Update `apps/web/src/shared/lib/api/config.ts` and `apps/web/lib/api/config.ts`:
     ```typescript
     RUN_STREAM: (runId: string) => `/api/v1/runs/${runId}/stream`,
     ```
  2. Ensure `useRunStream.ts` listens to both `onmessage` and specific SSE event names if present.
- **Verification Steps:**
  1. Open SSE stream to `/api/v1/runs/{id}/stream`.
  2. Verify messages are received and parsed without dropped event warnings.

---

### Defect 4: Payload Casing Mismatch (`targetUrl` vs `target_url`)

- **Affected Layer:** Layer 2.5 (Contract & Schema Runtime Casing)
- **Severity:** **MEDIUM**
- **Symptom:**
  Frontend triggers `POST /api/v1/runs` with JSON body `{ "targetUrl": "http://..." }`, receiving `HTTP 422 Unprocessable Entity` ("Field required: target_url").
- **Request / Response Evidence:**
  ```http
  POST /api/v1/runs HTTP/1.1
  Host: localhost:8000
  Content-Type: application/json

  {"targetUrl": "http://localhost:3000", "reviewMode": "manual"}

  HTTP/1.1 422 Unprocessable Entity
  {"detail": [{"loc": ["body", "target_url"], "msg": "Field required", "type": "missing"}]}
  ```
- **Root Cause:**
  `CreateRunPayload` in `apps/api/src/kawach/api/v1/runs.py` only defines `target_url: str` without an alias for `targetUrl`.
- **Minimal Proposed Fix:**
  In `apps/api/src/kawach/api/v1/runs.py`, allow both casing conventions:
  ```python
  class CreateRunPayload(BaseModel):
      target_url: Optional[str] = None
      targetUrl: Optional[str] = None
      review_mode: Optional[str] = "manual"
      reviewMode: Optional[str] = None
      prompt: Optional[str] = None
      project_id: Optional[str] = None
      projectId: Optional[str] = None

      @model_validator(mode="after")
      def normalize_casing(self) -> "CreateRunPayload":
          self.target_url = self.target_url or self.targetUrl
          self.review_mode = self.review_mode or self.reviewMode or "manual"
          self.project_id = self.project_id or self.projectId
          if not self.target_url:
              raise ValueError("target_url or targetUrl is required")
          return self
  ```
- **Verification Steps:**
  Send `POST /api/v1/runs` with `{ "targetUrl": "http://localhost:3000" }` -> verify `HTTP 201 Created`.

---

### Defect 5: Unhandled Backend Exception Handling (Section 2.0 Visibility)

- **Affected Layer:** Layer 2.0 / 2.5 (Error Surfacing)
- **Severity:** **MEDIUM**
- **Symptom:**
  When an unhandled exception occurs in FastAPI, connections can reset or return generic non-standard error responses without requestId or error code.
- **Root Cause:**
  Lack of a centralized exception handler conforming to the required contract:
  `{ "error": { "code": "INTERNAL_SERVER_ERROR", "message": "...", "requestId": "..." } }`.
- **Minimal Proposed Fix:**
  Add a global exception handler in `apps/api/src/app/main.py` formatting all unhandled exceptions into the standard error envelope.
- **Verification Steps:**
  Simulate an internal error; verify client receives HTTP 500 with proper JSON envelope and `X-Request-Id` header.

---

### Defect 6: Frontend Error Surfacing & Diagnostic Page (Section 2.0 Visibility)

- **Affected Layer:** Layer 2.0 (Visibility & Diagnostics)
- **Severity:** **MEDIUM**
- **Symptom:**
  Users have no visual feedback when background requests fail (no toast/banner with HTTP status, URL, backend errorCode, and requestId).
- **Minimal Proposed Fix:**
  1. Add a connection health indicator dot in the frontend navigation bar.
  2. Create a `/debug/connection` page in `apps/web/src/app/debug/connection/page.tsx` displaying live Layer 2.1–2.6 checks.
  3. Ensure `apiClient` surfaces structured error toasts when requests fail.
- **Verification Steps:**
  Navigate to `http://localhost:3000/debug/connection` in browser, verify all connection layers display live status.

---

## 3. Recommended Sequential Fix Plan

Following the strict project rule: **one fix at a time, smallest possible change, each verified and logged before proceeding**.

1. **Fix 1:** Add `update_project` and `archive_project` to `ProjectRepository` (`apps/api/src/kawach/repositories/project_repo.py`).
   *Verification:* Re-run `python3 scripts/check_connection.py`. Layer 2.5 project checks will flip to `[PASS]`.
2. **Fix 2:** Add database record insertion (`DbRun`) on run creation in `apps/api/src/kawach/api/v1/runs.py`.
   *Verification:* Re-run `python3 scripts/check_connection.py`. Layer 2.5 run persistence check will flip to `[PASS]`.
3. **Fix 3:** Add camelCase support (`targetUrl`, `reviewMode`) in `CreateRunPayload` (`apps/api/src/kawach/api/v1/runs.py`).
   *Verification:* Re-run test sending camelCase payload.
4. **Fix 4:** Update `RUN_STREAM` in `apps/web/src/shared/lib/api/config.ts` to `/api/v1/runs/${runId}/stream`.
   *Verification:* Confirm SSE stream returns typed JSON events.
5. **Fix 5:** Add centralized exception handler in `apps/api/src/app/main.py` (Section 2.0).
   *Verification:* Test error response envelope and `X-Request-Id` presence.
6. **Fix 6:** Add `/debug/connection` page and error surfacing in `apps/web` (Section 2.0).
   *Verification:* Playwright browser test visits `/debug/connection` and confirms all checks green.
