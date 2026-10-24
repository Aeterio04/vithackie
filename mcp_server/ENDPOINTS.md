# KAWACH / Ordinous backend endpoints (derived from code)

Source of truth: `apps/api/src/kawach/api/v1/*.py`, mounted at `/api/v1` by `kawach/main.py`.
`FRONTEND_DEVELOPMENT_GUIDE.md` does **not exist in this repository** (searched the whole tree), so the
"in guide" column below uses the closest documents (`docs/API_CONTRACT.md`, `docs/KAWACH_FRONTEND.md`,
`FRONTEND_AUDIT.md`). Where unsure the status is "NEW since guide" only for routes clearly added by the
isolation / Project Manager / token work. The backend was **not running** when this file was written, so
`/openapi.json` was not fetched; everything below is from reading the code.

## Auth model

* **Login:** `POST /api/v1/auth/login` with `{email|username_or_email, password}`. Returns
  `{id,email,displayName,name,username,token,refreshToken}` and sets httpOnly cookies. A failed login is
  `401 {"detail": "..."}`.
* **Cookies set:** `auth_token`, `access_token`, `token`, `kawach_session`, `session` (all hold the JWT,
  24h) and `refresh_token` (30d). There is **no cookie called `session_id`**.
* **Bearer accepted:** yes. `Authorization: Bearer <jwt>` (from login) or `Authorization: Bearer kw_live_...`
  (personal API token, intended for MCP/CLI). Resolution order: bearer header, then the cookies above, then
  `?token=` query param (SSE).
* **API tokens:** `POST /auth/tokens` creates one, but it requires an **interactive JWT session** (a token
  cannot mint a token). Plaintext secret `token_secret` is shown once. IMPORTANT: `require_scope("runs:read")`
  etc. are checked against the token's scopes and the default scopes are `["read","write"]`, which do **not**
  satisfy `runs:read/runs:write/tests:read/tests:write` (403 `Insufficient permissions`). Create the token with
  scopes `runs:read, runs:write, tests:read, tests:write` (or use login mode, whose JWT has all scopes).
* **Guest / no auth:** there is none. Every route except `/health`, `/config/defaults` and the auth routes returns
  401 `Authentication required` without a valid token (the old dev "system user" fallback was removed). Register on the
  website, then use the same email/password (`KAWACH_EMAIL` / `KAWACH_PASSWORD`) so the MCP acts as your own account.
  Login failures are always `401 Invalid email or password`; 5 failures/min per email gives `429`. The `?token=` query
  parameter is no longer accepted anywhere.
* **Cross-tenant access:** 404 (`Project not found`, `Run not found`, `Bug not found`).
* **CORS:** allow-list of browser origins on :3000/:5173 with credentials. Irrelevant for a non-browser client.
  No CSRF token is required (cookie `SameSite=lax`, JSON bodies).
* **Idempotency:** `POST /runs` honours an `Idempotency-Key` header.
* **Refresh:** `POST /auth/refresh` (cookie `refresh_token` or `{refreshToken}`).

## Error shapes

* FastAPI `HTTPException`: `{"detail": "message"}` (status 400/401/403/404/...).
* Validation: 422 `{"detail": [{"loc": ["body","field"], "msg": "...", "type": "..."}]}`.
* Unhandled: 500 `{"error": {"code":"INTERNAL_SERVER_ERROR","message":"...","requestId":"req_..."}}`.
* Note the backend almost never returns 409. Stage conflicts (resume a run that is not awaiting review) are
  **not enforced server-side** (`resume_run` has a no-op `pass`), so the MCP server checks the stage itself.

## Route table

Auth needed: `none` = open, `user` = any authenticated user, scope names are the required API-token scopes.

| Method | Path | Auth needed | Request body / params | Response shape | Status |
|---|---|---|---|---|---|
| POST | /auth/register | none | `{email,password,displayName?}` | `{id,email,displayName,token,refreshToken}` | in guide |
| POST | /auth/login | none | `{email,password}` | `{id,email,displayName,name,username,token,refreshToken}` | in guide |
| POST | /auth/refresh | refresh token | `{refreshToken?}` | `{token,refreshToken,user}` | in guide |
| GET | /auth/me | user | | `{id,email,displayName,name,username,role,isActive}` | in guide |
| POST | /auth/logout | none | `{refreshToken?}` | `{ok:true}` | in guide |
| POST | /auth/tokens | JWT session only | `{name,scopes[],expires_in_days}` | `{id,name,token_prefix,scopes,expires_at,token_secret,...}` | NEW since guide |
| GET | /auth/tokens | JWT session only | | `[ApiTokenRead]` | NEW since guide |
| DELETE | /auth/tokens/{id} | JWT session only | | `{ok,message}` | NEW since guide |
| GET | /health | none | | `{ok,status,workers_up,queue_depth,message}` | in guide |
| GET | /stats | none (global, not per-user) | | `{total_runs,confirmed_bugs,flaky_bugs,pending_reviews}` | in guide |
| GET | /config/defaults | none | | `{allowedHosts,default_budgets{max_pages,max_steps_per_test,max_run_minutes,parallel_workers},limits{min_/max_ pages,steps,minutes,workers},accepted_spec_extensions[],max_spec_file_size_mb}` | in guide |
| POST | /targets/check | none | `{target_url}` | `{reachable,allowed,reason,tls_valid,status_code}` (backend does not really probe; `reachable` is true for any well-formed URL) | in guide |
| POST | /specs/upload | none | multipart `file` and/or form `spec_text` | `{spec_id,filename,file_size_bytes,item_count}` (stored in process memory only) | in guide |
| GET | /projects | runs:read | | `[Project]` | NEW since guide |
| POST | /projects | runs:write | `{name,targetUrl|testUrl,githubUrl?,pat?,workspaceId?,slug?,description?,defaultMode,budgets?,allowedHosts?}` | Project (201) | NEW since guide |
| GET | /projects/{id} | runs:read | | Project | NEW since guide |
| PUT | /projects/{id} | runs:write | partial: `name,targetUrl,githubUrl,pat,description,defaultMode,budgets` | Project | NEW since guide |
| DELETE | /projects/{id} | runs:write | | `{ok:true}` (soft archive) | NEW since guide |
| PUT | /projects/{id}/credentials | runs:write | `{username,password}` | service result (no password) | NEW since guide |
| GET | /projects/{id}/credentials | runs:read | | `{hasSecret,username}` (camelCase, **no updated_at**) | NEW since guide |
| GET | /projects/{id}/runs | runs:read | | `[Run]` | NEW since guide |
| GET | /runs | runs:read | `?project_id=` | `[Run]` (no server-side stage filter) | in guide |
| POST | /runs | runs:write | `{target_url,prompt,spec_id?,spec_text?,review_mode,project_id?,budgets?,credentials{username,password}?}` | Run (201) | in guide |
| GET | /runs/{id} | runs:read | | Run | in guide |
| POST | /runs/{id}/start | runs:write | | Run (calls resume) | in guide |
| POST | /runs/{id}/resume | runs:write | | Run | in guide |
| POST | /runs/{id}/cancel | runs:write | | Run | in guide |
| POST | /runs/{id}/retry | runs:write | | Run (calls resume; not stage-checked) | in guide |
| DELETE | /runs/{id} | runs:write | | `{ok,run_id}` | in guide |
| GET | /runs/{id}/catalog | user | | catalog | in guide |
| PATCH | /runs/{id}/catalog/{test_id} | user | `{title,expected_result,steps[],priority}` | test | in guide |
| POST | /runs/{id}/catalog/test | user | `{prompt}` | test | in guide |
| POST | /runs/{id}/review | user | `{test_ids[],decision:approved|rejected,reason}` | `{applied_count,run_status}` | in guide |
| GET | /runs/{id}/review-log | user | | log | in guide |
| GET | /runs/{id}/bugs | user | | bugs | in guide |
| GET | /bugs/{bug_id} | user | | bug | in guide |
| POST | /runs/{id}/bugs/{bug_id}/retest | user | | bug | in guide |
| GET | /runs/{id}/report, /results, /metrics | user | | report / results / metrics | in guide |
| GET | /runs/{id}/export, /tests/export, /report/export, /export/scripts | user | | zip stream | in guide |
| GET | /runs/{id}/execution, /tests, /logs, /events, /stream (SSE) | user | | live state / SSE | in guide |
| GET | /runs/{id}/files/{path}, /runs/{id}/app-map | user | | file / app map | in guide |
| POST | /artifacts/upload, /storage/upload | user | multipart | artifact | NEW since guide |
| GET/DELETE | /artifacts/{id}, /storage/files/{id}, /storage/files/by-path/{p}, DELETE /storage/tests/{id} | user | | file (Range streaming) | NEW since guide |
| GET | /projects/{id}/saved-tests | tests:read | `?tag=` | `[SavedTest]` | NEW since guide |
| POST | /projects/{id}/saved-tests | tests:write | `{run_id,test_id,name?,tags[]}` | SavedTest (201) | NEW since guide |
| DELETE | /projects/{id}/saved-tests/{test_id} | tests:write | | 204 | NEW since guide |
| POST | /projects/{id}/saved-tests/run-all | tests:write | | run info (background) | NEW since guide |
| POST | /projects/{id}/saved-tests/{test_id}/run | tests:write | | run info (background) | NEW since guide |
| GET | /projects/{id}/commits/github | tests:read | | `{configured,message,commits[]}` | NEW since guide |
| GET | /projects/{id}/commits | tests:read | | `[CommitEvent]` | NEW since guide |
| POST | /projects/{id}/commits | tests:write | `{sha,files_changed[],branch,message,author,webhook_delivery_id}` | CommitEvent (201; triggers regression run) | NEW since guide |
| GET | /projects/{id}/commits/{cid}/analysis | tests:read | | failure analysis | NEW since guide |
| POST | /projects/{id}/commits/{cid}/suggest-fix | tests:write | | fix suggestion | NEW since guide |
| POST | /projects/{id}/commits/{cid}/auto-fix | tests:write | | fix suggestion (opens PR) | NEW since guide |
| POST | /webhooks/github | HMAC signature | GitHub push payload | 202 | NEW since guide |
| GET | /projects/{id}/overview | - | - | **does not exist** | guide only, missing in code |

## Object shapes

**Run** (`transform_run_to_frontend`): `{id, runId, projectId, project_id, target_url, targetUrl, prompt,
review_mode, status (frontend enum), stage (raw stage), progress (int 0-100), created_at, finished_at,
duration_seconds, budgets{max_pages,...}, budget_usage{pages_crawled,steps_executed,elapsed_minutes,
active_workers}, counts{total_tests,passed_tests,failed_tests,suspected_bugs,confirmed_bugs,flaky_bugs,
not_reproduced_bugs,pending_reviews}}`. There is **no** `progress{step,done,total}` object and **no** `error`
field; the step text is in `GET /runs/{id}/execution` (`workers[].current_step`).
Stages: created, exploring, planning, awaiting_review, scripting, running, verifying, reporting, done, failed,
cancelled. Frontend `status` maps scripting/running to `executing` and done to `completed`.

**Project** (`format_project_response`, camelCase plus snake_case duplicates): `id, ownerId, workspaceId, name,
slug, targetUrl, testUrl, githubUrl, patMasked, hasPat, description, defaultMode, budgets, allowedHosts,
specVersion, lastRunStatus, savedTestCount, createdAt, updatedAt, archivedAt`.

**SavedTest:** `id, project_id, origin_run_id, origin_test_case_id, name, description, script_path, tags,
is_active, last_result, created_at, updated_at`.

**Run budgets on create:** keys read are `max_pages, explore_seconds, max_tests, test_timeout_ms`
(different from the `default_budgets`/`limits` keys of `/config/defaults`).

## Project Manager routes (wrapped as tools in prompt 1)

| Route | Tool |
|---|---|
| GET /projects/{id}/saved-tests | `list_saved_tests` |
| POST /projects/{id}/saved-tests/run-all | `run_saved_tests` (all) |
| POST /projects/{id}/saved-tests/{test_id}/run | `run_saved_tests` (with `test_id`) |
| POST /projects/{id}/saved-tests | `save_test_to_project` |
| DELETE /projects/{id}/saved-tests/{test_id} | `delete_saved_test` (confirm-guarded) |
| GET /projects/{id}/commits | `list_commits` |
| GET /projects/{id}/commits/github | `list_github_commits` |
| (no overview route) | `get_project_overview` composed client-side from project + latest runs + saved tests |

Commit analysis / suggest-fix / auto-fix routes are left for prompt 2 or 3 (workflow tools).

## Addendum (prompt 2): routes used by the review / bug / observability / report tools

| Method | Path | Notes |
|---|---|---|
| GET | /runs/{id}/catalog | list of `{id,title,spec_item_ids[],steps[str],expected_result,priority,review_status(pending\|approved\|rejected),source}` |
| PATCH | /runs/{id}/catalog/{test_id} | `{title,expected_result,steps[str],priority}`; no status |
| POST | /runs/{id}/catalog/test | `{prompt}` only; LLM generates the test |
| POST | /runs/{id}/review | `{test_ids[],decision:"approved"\|"rejected",reason}` -> `{applied_count,run_status}`; auto-starts execution if any test is approved |
| GET | /runs/{id}/review-log | `[{test_id,decision,actor,reason,at}]` |
| GET | /runs/{id}/bugs, /bugs/{bug_id} | `{id,run_id,title,severity,status,replays[{index,result,duration_ms,video_url}],steps_to_reproduce,expected,actual,evidence{screenshots[],video_url,trace_url,console[]},repro_script_url,spec_item_ids}`; replays are synthesised when verification files are missing |
| GET | /runs/{id}/logs | full list `[{id,timestamp,level,source,message}]`, no paging |
| GET | /runs/{id}/events | last 50 `[{id,data(json string)}]`, `?since=<id>` |
| GET | /runs/{id}/stream | SSE `data: {"type": log\|run.status\|catalog.ready\|test.update\|worker.update\|budget.update\|run.done, ...}`; replays log history first; ~10 min max |
| GET | /runs/{id}/execution | `{workers[],tests[],budget_usage}` |
| GET | /runs/{id}/app-map | `{root_url,total_pages,pages[{url,title,status_code,forms_count,interactive_elements}],nodes[]}` |
| GET | /runs/{id}/report | structured JSON; markdown is `files/report.md` |
| GET | /runs/{id}/metrics | `Metrics` (wallClockSeconds, tests, bugs, coverage, llm{calls,inputTokens,outputTokens,costUsd}) |
| GET | /runs/{id}/export, /export/scripts | zip streams (see DECISIONS.md) |
| GET | /runs/{id}/files/{path} | run-folder files; `secrets.json` / `input.json` refused; path traversal blocked |
| GET | /artifacts/{id}, /storage/files/{id} | artifact bytes with Range support |
