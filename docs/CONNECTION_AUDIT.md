# Connection Audit: Frontend (Next.js) & Backend (FastAPI) Disconnect Analysis

**Generated:** 2026-10-24  
**Audit Phase:** Phase 1 — READ-ONLY Exploration & Ground Truth Verification  
**Repository HEAD:** `1e10221` (`feat(agentic): complete A2-A5, Groq rate limiting, OpenAPI contracts, and frontend gap audit`)  
**Data Artifact:** `docs/connection-audit/endpoints.json`

---

## 1. Environment Facts

| Fact | Value | Verification Source |
|---|---|---|
| **FRONTEND_URL** | `http://localhost:3000` | User configuration & `.env.local` |
| **BACKEND_URL** | `http://localhost:8000` | User configuration & `apps/web/next.config.ts` |
| **Frontend Framework** | Next.js 16.4.2 (Turbopack), React 19.3.0 | `apps/web/package.json` |
| **Backend Framework** | FastAPI 0.159.1, Uvicorn 0.54.0, Python 3.14 | System environment & `pip list` |
| **Hosting / Execution** | Local machine (macOS `darwin`) | Operating system runtime |
| **Backend Host Binding** | `0.0.0.0:8000` (Listening on all interfaces) | Uvicorn startup log (Task 89) |
| **Backend Workers** | 1 worker (`uvicorn app.main:app`) | Startup command inspection |
| **Database Engine** | SQLite 3 | `data/kawach.db` |
| **Resolved Database URL** | `sqlite:////Users/parasgajam/Desktop/Vit_it/data/kawach.db` | `kawach.core.config.settings.resolved_database_url` |
| **Alembic Current** | `b2c3d4e5f6a7 (head)` | `alembic -c apps/api/alembic.ini current` |
| **Alembic Head** | `b2c3d4e5f6a7 (head)` | `alembic -c apps/api/alembic.ini heads` |
| **OpenAPI Paths** | 63 paths, 73 operations | Live `/openapi.json` vs `packages/contracts/openapi.json` |
| **TypeScript Types Sync** | 0 diff lines (100% synchronized) | `openapi-typescript` validation against `apps/web/src/generated/api-types.ts` |

---

## 2. Executive Summary & Verdict Counts

All 63 declared OpenAPI paths are actively mounted and served by the running FastAPI backend. There are **0 missing routes**, **0 unmounted routes**, and **0 501-Scaffold endpoints**.

However, the communication between the Next.js frontend and the FastAPI backend is broken across multiple architectural and contract layers:

| Verdict | Count | Description |
|---|:---:|---|
| **SERVED-OK** | **17** | Backend route exists, serves expected payload, conforms to schema, and returns HTTP 200/201. |
| **SERVED-BUT-ERROR** | **14** | Endpoint exists and is reached, but crashes or fails (e.g. ProjectRepository AttributeError 500s, or get_owned_run 404s). |
| **CONTRACT-MISMATCH** | **4** | Route is served, but request/response casing or schema differs (`target_url` vs `targetUrl`, AppMap state-graph vs tree). |
| **URL-MISMATCH** | **1** | Frontend calls legacy un-prefixed/divergent path (`/api/runs/:id/stream` vs `/api/v1/runs/:id/stream`). |
| **AUTH-MISMATCH** | **1** | Cross-origin cookie isolation between port 3000 and 8000 breaks Next.js server `middleware.ts`. |
| **UNUSED** | **12** | Backend routes with no UI trigger in `apps/web` (API Tokens, Saved Test Library, Commit Auto-Fix, Webhooks). |
| **NOT-SERVED** | **0** | No routes returned 404 due to being omitted from the router. |
| **501-SCAFFOLD** | **0** | All previous 501 scaffold endpoints were implemented in A1–A6. |
| **ORPHAN** | **0** | No calls to removed routes. |
| **TOTAL MAPPED** | **49** | Comprehensive frontend-to-backend integration touchpoints. |

---

## 3. Ranked List of Root Causes (Impact Order)

### 🔴 Root Cause 1: Tenant Run Persistence Disconnect (Severity: Critical)
- **Symptom:** As soon as any authenticated user logs into the web application, clicking on any run, catalog, execution cockpit, or bug report returns **HTTP 404 Not Found**.
- **Evidence:**
  - `POST /runs` and `create_run_service` save run artifacts exclusively to the filesystem (`runs/<run_id>/run.json`).
  - No database record is inserted into the SQLite `runs` table (`DbRun`).
  - All v1 run endpoints (`GET /api/v1/runs/{id}`, `/catalog`, `/execution`, `/tests`, `/bugs`, `/logs`, `/stream`) enforce `_run: DbRun = Depends(get_owned_run)`.
  - In `apps/api/src/kawach/api/deps.py`:
    ```python
    def get_owned_run(run_id: str, scope: Scope = Depends(get_user_scope), db: Session = Depends(get_db)):
        repo = RunRepository(db)
        run = repo.get_run(scope, run_id)
        if run: return run
        # Legacy fallback ONLY runs if scope.is_system is True:
        if scope.is_system:
            if (storage.run_dir(run_id) / "run.json").exists():
                return Run(id=run_id, project_id="legacy-demo", created_by="system")
        raise HTTPException(status_code=404, detail="Run not found")
    ```
  - For any logged-in user, `scope.is_system == False`. Since the run is not in the database, `get_owned_run` unconditionally raises `404 Not Found`.

### 🔴 Root Cause 2: Missing Methods on `ProjectRepository` (Severity: High / Crash)
- **Symptom:** Saving Project Settings or deleting a project immediately crashes the backend with **HTTP 500 Internal Server Error**.
- **Evidence (Captured Traceback from Uvicorn Task 89):**
  - `PUT /api/v1/projects/:id` -> `500 Internal Server Error`:
    ```python
    File "apps/api/src/kawach/services/project_service.py", line 86, in update_project
      project = self.project_repo.update_project(...)
    AttributeError: 'ProjectRepository' object has no attribute 'update_project'. Did you mean: 'create_project'?
    ```
  - `DELETE /api/v1/projects/:id` -> `500 Internal Server Error`:
    ```python
    File "apps/api/src/kawach/services/project_service.py", line 106, in archive_project
      success = self.project_repo.archive_project(scope, project_id)
    AttributeError: 'ProjectRepository' object has no attribute 'archive_project'. Did you mean: 'create_project'?
    ```
  - `apps/api/src/kawach/repositories/project_repo.py` defines `create_project` and `get_project`, but omits `update_project` and `archive_project`.

### 🟠 Root Cause 3: Real-Time SSE Stream Endpoint & Event Format Mismatch (Severity: Medium)
- **Symptom:** The Execution Cockpit SSE stream disconnects or falls back to polling; browser never receives live stage/worker/bug updates.
- **Evidence:**
  - `apps/web/src/shared/lib/api/config.ts` configures:
    ```typescript
    RUN_STREAM: (runId: string) => `/api/runs/${runId}/stream`,
    ```
  - `/api/runs/{run_id}/stream` (legacy) sends:
    `event: stage_change\ndata: {"runId": "...", "stage": "..."}\n\n`
  - In `apps/web/src/shared/hooks/useRunStream.ts`, the browser registers `es.onmessage = (e) => handleSSEMessage(e.data)`. In browser `EventSource`, `onmessage` **never fires for custom named events** (`event: stage_change`).
  - Furthermore, `handleSSEMessage` validates events against `SSEEventSchema`, expecting `{ type: "run.status", ... }`, which is only produced by `/api/v1/runs/{run_id}/stream`.

### 🟠 Root Cause 4: Casing Contract Mismatches (`target_url` vs `targetUrl`) (Severity: Medium)
- **Symptom:** `useTargetCheck` and project run forms fail validation with **HTTP 422 Unprocessable Content**.
- **Evidence:**
  - Backend `TargetCheckPayload` in `kawach.api.v1.config` and `CreateRunPayload` in `kawach.api.v1.runs` define `target_url: str` without `alias="targetUrl"`.
  - Frontend forms submit `{ "targetUrl": "..." }`, which Pydantic rejects with:
    `{"loc": ["body", "target_url"], "msg": "Field required", "type": "missing"}`.

### 🟡 Root Cause 5: Cross-Origin Cookie Session vs Next.js Middleware (Severity: Medium)
- **Symptom:** Browser login succeeds at the API level, but navigating to any page on `http://localhost:3000` immediately redirects back to `/login?returnUrl=...`.
- **Evidence:**
  - `apps/web/middleware.ts` runs on Next.js frontend origin (`localhost:3000`).
  - If frontend components make direct cross-origin requests to `http://localhost:8000`, the `Set-Cookie` header sets cookies on origin `8000`.
  - The Next.js frontend server never receives `localhost:8000` cookies on page requests to `localhost:3000`, leading `middleware.ts` lines 31-34 to assume the user is unauthenticated and issue an infinite redirect loop.
  - Mitigated only when all requests route through `next.config.ts` rewrites (`/api/:path*` -> `http://localhost:8000/api/:path*`).

---

## 4. Backend Inventory & Comparison

### 4.1 Declared vs. Live vs. Mounted Comparison
- **Declared OpenAPI (`packages/contracts/openapi.json`):** 63 paths, 73 operations.
- **Live OpenAPI (`http://localhost:8000/openapi.json`):** 63 paths, 73 operations.
- **Diff:** **0 paths missing, 0 paths extra**. Schemas and operation IDs are identical.
- **Mounted Route Objects in FastAPI (`app.routes`):** 77 route objects.
  - 60 mounted under `/api/v1` router prefix.
  - 13 mounted under legacy un-prefixed router (`/health`, `/config`, `/runs`, `/runs/{run_id}`, etc.).
  - 4 built-in documentation routes (`/openapi.json`, `/docs`, `/redoc`, `/docs/oauth2-redirect`).

### 4.2 Database & Migration Integrity
- **Command:** `PYTHONPATH=apps/api/src python3 -m alembic -c apps/api/alembic.ini current`
  - Output: `b2c3d4e5f6a7 (head)`
- **Command:** `PYTHONPATH=apps/api/src python3 -m alembic -c apps/api/alembic.ini heads`
  - Output: `b2c3d4e5f6a7 (head)`
- **Verification:** Current revision equals head revision.
- **Table Verification (`sqlite3 data/kawach.db`):**
  - Verified presence of all 32 tables: `alembic_version`, `users`, `projects`, `runs`, `api_tokens`, `audit_logs`, `saved_tests`, `commit_events`, `test_cases`, `bugs`, `fix_suggestions`, `failure_analyses`, etc.
  - Verified `api_tokens` columns: `id`, `user_id`, `name`, `token_prefix`, `token_hash`, `scopes`, `expires_at`, `revoked_at`, `last_used_at`, `created_at`.
  - Verified `audit_logs` columns: `id`, `user_id`, `project_id`, `action`, `entity_type`, `entity_id`, `metadata_json`, `ip`, `created_at`, `client_type`.
  - Verified that neither `kawach.main` nor `app.main` relies on `Base.metadata.create_all()` in production code.

---

## 5. Live Protocol & Network Behavior

### 5.1 Trailing-Slash Redirects
| Request Path | Status | Location Header | Analysis |
|---|:---:|---|---|
| `GET /runs` | 200 OK | — | Correctly served directly. |
| `GET /runs/` | 307 Temporary Redirect | `http://localhost:8000/runs` | Redirects to non-slash canonical route. |
| `GET /api/v1/runs` | 200 OK | — | Correctly served directly. |
| `GET /api/v1/runs/` | 307 Temporary Redirect | `http://localhost:8000/api/v1/runs` | Redirects to non-slash canonical route. |
| `GET /api/v1/projects` | 200 OK | — | Correctly served directly. |
| `GET /api/v1/projects/` | 307 Temporary Redirect | `http://localhost:8000/api/v1/projects` | Redirects to non-slash canonical route. |

*Finding:* Trailing slash routes return 307 redirects to non-trailing slash routes. Both scheme (`http`) and host (`localhost:8000`) are preserved.

### 5.2 CORS & OPTIONS Preflight
Tested using real preflight headers (`Origin: http://localhost:3000`, `Access-Control-Request-Method: POST`, `Access-Control-Request-Headers: Authorization, Content-Type, Idempotency-Key, X-Request-Id`):
- `OPTIONS /api/v1/projects` -> **200 OK**
  - `Access-Control-Allow-Origin`: `http://localhost:3000`
  - `Access-Control-Allow-Credentials`: `true`
  - `Access-Control-Allow-Methods`: `DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT, QUERY`
  - `Access-Control-Allow-Headers`: `Authorization, Content-Type, Idempotency-Key, X-Request-Id`
- `OPTIONS /api/v1/runs` -> **200 OK** (Headers match)
- `OPTIONS /api/v1/auth/login` -> **200 OK** (Headers match)

*Finding:* FastAPI `CORSMiddleware` correctly validates the `http://localhost:3000` origin and supports `Idempotency-Key` and `X-Request-Id` headers.

### 5.3 HEAD Method Handling
- `HEAD /api/v1/health` -> **405 Method Not Allowed**
- `HEAD /api/v1/projects` -> **405 Method Not Allowed**
- `HEAD /health` -> **405 Method Not Allowed**

*Finding:* Standard REST endpoints do not implement explicit `HEAD` handlers and Starlette returns 405 when probed with HEAD.

### 5.4 Server-Sent Events (SSE) Inspection
Tested `/api/runs/{run_id}/stream` vs `/api/v1/runs/{run_id}/stream`:
1. **Legacy Route (`/api/runs/:id/stream`):**
   - Connects with Bearer header, Cookie session, or without auth.
   - Formats events as: `event: stage_change\ndata: {"runId":..., "stage":...}\n\n`.
   - **Flaw:** Browser `EventSource` listening with `es.onmessage` ignores named `stage_change` events.
2. **V1 Route (`/api/v1/runs/:id/stream`):**
   - Emits typed events (`type: "run.status"`, `type: "log"`, `type: "worker.update"`).
   - Formats events as default: `data: {...}\n\n`.
   - **Flaw:** Returns 404 for real authenticated users due to `get_owned_run` missing SQL record (Root Cause 1).

---

## 6. Frontend Call Matrix & Cross-Reference

| Frontend Call / Hook | File & Line | Target Backend Route | Method | Status | Verdict |
|---|---|---|:---:|:---:|:---:|
| `useAuthMe()` | `hooks.ts:47` | `/api/v1/auth/me` | GET | 200 | **SERVED-OK** |
| `useLogin()` | `hooks.ts:64` | `/api/v1/auth/login` | POST | 200 | **SERVED-OK** |
| `useLogout()` | `hooks.ts:79` | `/api/v1/auth/logout` | POST | 200 | **SERVED-OK** |
| `authApi.register()` | `features/auth/api.ts:26` | `/api/v1/auth/register` | POST | 200 | **SERVED-OK** |
| `authApi.login()` | `features/auth/api.ts:33` | `/api/v1/auth/login` | POST | 200 | **SERVED-OK** |
| `authApi.me()` | `features/auth/api.ts:40` | `/api/v1/auth/me` | GET | 200 | **SERVED-OK** |
| `authApi.logout()` | `features/auth/api.ts:44` | `/api/v1/auth/logout` | POST | 200 | **SERVED-OK** |
| `useHealth()` | `hooks.ts:99` | `/api/v1/health` | GET | 200 | **SERVED-OK** |
| `useConfigDefaults()` | `hooks.ts:111` | `/api/v1/config/defaults` | GET | 200 | **SERVED-OK** |
| `useStats()` | `hooks.ts:130` | `/api/v1/stats` | GET | 200 | **SERVED-OK** |
| `useTargetCheck()` | `hooks.ts:144` | `/api/v1/targets/check` | POST | 200/422 | **CONTRACT-MISMATCH** |
| `useUploadSpec()` | `hooks.ts:183` | `/api/v1/specs/upload` | POST | 200 | **SERVED-OK** |
| `useRuns()` | `hooks.ts:201` | `/api/v1/runs` | GET | 200 | **SERVED-OK** |
| `useRun(runId)` | `hooks.ts:212` | `/api/v1/runs/{run_id}` | GET | 404 | **SERVED-BUT-ERROR** |
| `useCreateRun()` | `hooks.ts:249` | `/api/v1/runs` | POST | 201/422 | **CONTRACT-MISMATCH** |
| `useStartRun()` | `hooks.ts:265` | `/api/v1/runs/{run_id}/start` | POST | 404 | **SERVED-BUT-ERROR** |
| `useCancelRun()` | `hooks.ts:280` | `/api/v1/runs/{run_id}/cancel` | POST | 404 | **SERVED-BUT-ERROR** |
| `useRetryRun()` | `hooks.ts:295` | `/api/v1/runs/{run_id}/retry` | POST | 404 | **SERVED-BUT-ERROR** |
| `useRunStream()` | `useRunStream.ts:302` | `/api/runs/{run_id}/stream` | GET | 200 | **URL-MISMATCH** |
| `useRunStream()` log preload | `useRunStream.ts:45` | `/api/v1/runs/{run_id}/logs` | GET | 404 | **SERVED-BUT-ERROR** |
| `useRunEventsPoll()` | `hooks.ts:37` | `/api/v1/runs/{run_id}/events` | GET | 404 | **SERVED-BUT-ERROR** |
| `useAppMap()` | `hooks.ts:314` | `/api/v1/runs/{run_id}/app-map` | GET | 200 | **CONTRACT-MISMATCH** |
| `useCatalog()` | `hooks.ts:329` | `/api/v1/runs/{run_id}/catalog` | GET | 404 | **SERVED-BUT-ERROR** |
| `useAddCatalogTest()` | `hooks.ts:344` | `/api/v1/runs/{run_id}/catalog/test` | POST | 200 | **SERVED-OK** |
| `useUpdateReview()` | `hooks.ts:374` | `/api/v1/runs/{run_id}/review` | POST | 422 | **CONTRACT-MISMATCH** |
| `useReviewLog()` | `hooks.ts:436` | `/api/v1/runs/{run_id}/review-log` | GET | 200 | **SERVED-OK** |
| `useExecution()` | `hooks.ts:458` | `/api/v1/runs/{run_id}/execution` | GET | 404 | **SERVED-BUT-ERROR** |
| `useTests()` | `hooks.ts:470` | `/api/v1/runs/{run_id}/tests` | GET | 404 | **SERVED-BUT-ERROR** |
| `useBugs()` | `hooks.ts:486` | `/api/v1/runs/{run_id}/bugs` | GET | 404 | **SERVED-BUT-ERROR** |
| `useBug(bugId)` | `hooks.ts:497` | `/api/v1/bugs/{bug_id}` | GET | 404 | **SERVED-BUT-ERROR** |
| `useReport()` | `hooks.ts:512` | `/api/v1/runs/{run_id}/report` | GET | 404 | **SERVED-BUT-ERROR** |
| `projectApi.list()` | `projects/api.ts:36` | `/api/v1/projects` | GET | 200 | **SERVED-OK** |
| `projectApi.get(id)` | `projects/api.ts:40` | `/api/v1/projects/{id}` | GET | 200 | **SERVED-OK** |
| `projectApi.create()` | `projects/api.ts:44` | `/api/v1/projects` | POST | 201 | **SERVED-OK** |
| `projectApi.delete(id)` | `projects/api.ts:48` | `/api/v1/projects/{id}` | DELETE | 500 | **SERVED-BUT-ERROR** |
| `projectApi.update(id)` | `projects/api.ts:52` | `/api/v1/projects/{id}` | PUT | 500 | **SERVED-BUT-ERROR** |
| `Next.js middleware` | `middleware.ts:24` | `N/A (Frontend Server)` | EDGE | 307 | **AUTH-MISMATCH** |
| `API Tokens List` | *No UI component* | `/api/v1/auth/tokens` | GET | 200 | **UNUSED** |
| `API Token Create` | *No UI component* | `/api/v1/auth/tokens` | POST | 201 | **UNUSED** |
| `API Token Revoke` | *No UI component* | `/api/v1/auth/tokens/{id}` | DELETE | 200 | **UNUSED** |
| `Saved Tests List` | *No UI component* | `/api/v1/projects/{id}/saved-tests` | GET | 200 | **UNUSED** |
| `Saved Test Save` | *No UI component* | `/api/v1/projects/{id}/saved-tests` | POST | 201 | **UNUSED** |
| `Saved Test Delete` | *No UI component* | `/api/v1/projects/{id}/saved-tests/{id}` | DELETE | 204 | **UNUSED** |
| `Project Commits List` | `commits/page.tsx` (Empty Card) | `/api/v1/projects/{id}/commits` | GET | 200 | **UNUSED** |
| `Commit Ingest` | *No UI component* | `/api/v1/projects/{id}/commits` | POST | 422 | **UNUSED** |
| `Failure Analysis` | *No UI component* | `/api/v1/projects/{id}/commits/{id}/analysis` | GET | 404 | **UNUSED** |
| `Suggest Fix` | *No UI component* | `/api/v1/projects/{id}/commits/{id}/suggest-fix` | POST | 404 | **UNUSED** |
| `Auto Fix PR` | *No UI component* | `/api/v1/projects/{id}/commits/{id}/auto-fix` | POST | 422 | **UNUSED** |
| `GitHub Webhook Ingest` | *No UI component* | `/api/v1/webhooks/github` | POST | 401 | **UNUSED** |

---

## 7. Verified vs. Unverified Status

### ✅ Explicitly Verified
1. **Live Backend Startup & Route Inventory:**
   - Ran live FastAPI server via Uvicorn on `0.0.0.0:8000`.
   - Verified all 63 paths / 73 operations in live `/openapi.json` matching `packages/contracts/openapi.json`.
   - Confirmed 77 mounted Starlette routes including 13 legacy routes.
2. **Database & Alembic Head:**
   - Confirmed `alembic current` matches `alembic heads` at `b2c3d4e5f6a7 (head)`.
   - Verified columns in `api_tokens` and `audit_logs` exist and match schemas.
3. **Live Endpoint Execution:**
   - Generated throwaway test user, web session (JWT cookie + Bearer), and scoped API token (`kw_live_...`).
   - Hit all 73 operations and recorded status, response latency, and content type in `docs/connection-audit/endpoints.json`.
4. **CORS Preflights & Trailing Slash:**
   - Proven: Trailing slash produces 307 redirects to non-slash canonical paths.
   - Proven: OPTIONS preflight returns 200 with credentials allowed and includes custom headers (`Idempotency-Key`, `X-Request-Id`).
5. **Traceback Cause for 500s:**
   - Proven: `ProjectRepository` lacks `archive_project` and `update_project` methods.
6. **Cause for Universal 404s on Run Routes:**
   - Proven: `create_run_service` saves run to disk but fails to insert `DbRun` into SQLite `runs` table, causing `get_owned_run` dependency to fail for all authenticated users.

### ⏳ Unverified (Deferred to Phase 2 Browser Flow)
1. Real browser-based session persistence across Next.js Turbopack client components and Next.js middleware using Playwright.
2. Cross-origin cookie exchange when FRONTEND_URL and BACKEND_URL are served on separate network hosts/domains.
3. Streaming performance and buffering behavior through Next.js rewrite proxy.
