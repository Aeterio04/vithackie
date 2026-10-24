# Auth and data-isolation decisions

## 1. Discovery: what was actually hard-coded

I found **no KAWACH login username/password hard-coded in the current frontend or backend**. The website already had Login
and Register pages calling the real `/api/v1/auth/*` routes. The things that *behaved* like a shared or default login were
these (file and line are from before my change):

| Where | What | Status |
|---|---|---|
| `apps/api/src/kawach/core/config.py:38` | `JWT_SECRET` defaulted to the public string `dev-secret-change-in-production-must-be-32-chars-long`; anyone could forge a valid token | **Removed.** Unset in non-dev = server refuses to start; unset in dev = random secret generated and kept in `data/.jwt_secret` |
| `apps/api/src/kawach/api/deps.py:143-169` | "System user" fallback: unauthenticated requests became `system@kawach.local` (password hash `system_demo_hash`) in dev when `ALLOW_SYSTEM_USER_FALLBACK=true` | **Removed.** No credentials = 401, always. The setting is kept but ignored |
| `apps/api/src/kawach/api/deps.py:262` and `v1/artifacts.py:204` | Anyone whose email was `system@kawach.local` got `is_system` scope = read EVERY user's data (on a fresh DB anyone could register that email first) | **Removed.** Request scope is never "system"; `@kawach.local` emails cannot register or log in |
| `apps/api/src/kawach/api/deps.py:301-327` (`get_owned_run`) | Any signed-in user who asked for a run id that existed on disk but not in the DB got it **auto-assigned to themselves** | **Removed.** 404; use `claim_legacy_data.py` |
| `apps/api/src/kawach/api/legacy.py` (all routes) | Root-level `/runs`, `/runs/{id}/files`, `/report`, `/export`, `/stream`, `PUT /runs/{id}/catalog`, `POST /runs`... had **no authentication at all** and listed every run | **Fixed.** Auth + ownership on every route |
| `apps/web/middleware.ts:29` | `NEXT_PUBLIC_USE_MOCKS=true` skipped the login redirect. Also the file sat in the project root while the app lives in `src/app`, so **Next 16 never ran it: the route guard did not exist** | **Fixed.** Moved to `src/proxy.ts` (Next 16 name), bypass deleted |
| `apps/web/src/shared/lib/mocks/devMockService.ts:315` (and `lib/mocks/`) | Mock `/auth/login` accepting anything when `NEXT_PUBLIC_USE_MOCKS=true` | Cannot run in a production build any more; the flag no longer bypasses the guard |
| `apps/api/src/kawach/core/security.py:77-94` | Passwords hashed with PBKDF2 (100k iterations) | Now argon2id; old hashes still verify and are upgraded at next login |
| (not KAWACH credentials) `qa.tester@example.com` in `agents/script_writer`, `scripts/generate_samples.py`, `verify_live.py` | Login of the *example app under test* | Left alone, unrelated to KAWACH accounts |

Data found in your real `data/kawach.db` (read-only inspection): 36 user rows, mostly leftovers from the test suite
(`scaffold_user_*`, `commit_user_*`, `audit_qa_*`). **Your real work belongs to `tester@example.com`** (4 projects,
17 runs created by it, 24 saved tests, 225 artifacts, files under `storage/users/64b265d4-...`) plus `system@kawach.local`
(1 project). That `tester@example.com` account is what I treated as "the old demo user".

## 2. How auth works now

* `POST /api/v1/auth/register {email, password, name?}` -> 200 `{id,email,displayName,name,user{...},token,access_token,
  token_type:"bearer",refreshToken}`; 409 `An account with this email already exists` (case/whitespace-insensitive);
  422 for a bad email, a password under 8 (or over 128) characters, or a reserved `@kawach.local` address.
* `POST /api/v1/auth/login {email, password}` -> same body. Wrong password, unknown email, disabled account and reserved
  account all return the identical `401 {"detail":"Invalid email or password"}`; unknown emails still burn one hash
  verification so timing does not reveal them. Lockout: 5 failures/minute per email (and 20 per client IP) -> `429` with
  `Retry-After`; a success clears the email counter.
* `GET /api/v1/auth/me`, `POST /api/v1/auth/logout` (clears cookies, revokes the refresh token), `POST /api/v1/auth/refresh`
  (already existed, unchanged).
* Token: HS256 JWT, `sub`=user id, `exp` 24h (`ACCESS_TOKEN_EXPIRE_MINUTES`), signed with `JWT_SECRET`.
* Returned in the JSON body **and** set as httpOnly, SameSite=Lax cookies (`Secure` outside dev). Protected routes accept
  `Authorization: Bearer <jwt>` **or** the cookie (Bearer wins). The `?token=` query-string form was removed: URLs get logged.
  Browsers' `EventSource` (SSE) sends the cookie; non-browser clients send the Bearer header.
* Frontend stores nothing: the JWT lives only in the httpOnly cookie (`credentials: "include"`), so scripts cannot read it
  and SSE keeps working. After login/register the page does a full navigation so the new cookie is seen by the route guard.
* MCP server: `POST /auth/login` with `KAWACH_EMAIL`/`KAWACH_PASSWORD`, token in memory only, `Authorization: Bearer`,
  re-login on 401 and 60 s before the JWT expires, cookie jar emptied after login, token never logged or returned.
  `whoami` returns `email`.

## 3. Ownership model (unchanged tables, stricter enforcement)

`users` (unique email, stored lowercased; plus a case-insensitive unique index created at startup, skipped with a warning if
old data contains case-duplicates) -> `projects.owner_id` -> `runs.project_id` (and `runs.created_by`) -> bugs, catalog,
test cases, artifacts (`artifacts.user_id`, files under `storage/users/<user_id>/`), `saved_tests.project_id`,
`commit_events`. Foreign resources are 404 (not 403).

Endpoints that were **not** correctly scoped and are now fixed: all legacy routes (above); `GET /stats` (global and
unauthenticated -> own runs, auth required); `POST /runs` (accepted any `project_id`, now 404 unless owned);
`POST /specs/upload` + `spec_id` (open and shared in memory -> auth required, usable only by the uploader);
`POST /targets/check` (open -> auth); `POST /projects/{id}/saved-tests` (copied scripts from ANY run id -> source run
must be yours); `GET /projects/{id}/runs` (200 `[]` for foreign projects -> 404); `GET /storage/files/by-path/...`
(any signed-in user could read paths outside `users/<id>/` -> only your own folder).

## 4. Decisions and assumptions

* Hashing: argon2id via `argon2-cffi` (bcrypt is not installed in this environment; both are acceptable per the request).
  Added to `apps/api/requirements.txt` and `pyproject.toml`. **Run `pip install argon2-cffi` in any other environment.**
* **Everyone has to sign in again once.** Existing browser sessions were signed with the old public secret and are rejected.
* Credential vault compatibility: stored project passwords/PATs are encrypted with a key derived from the *old default*
  `JWT_SECRET` when `SECRET_ENCRYPTION_KEY` is unset. Changing the signing secret would have made them undecryptable, so the
  vault keeps deriving from that legacy value (`Settings.secret_store_basis`). In production set `SECRET_ENCRYPTION_KEY`.
* Registration returns 200 (not 201) to keep existing clients and tests working. Registration stays open (`ALLOW_SIGNUP`).
* Reserved domain `@kawach.local` is for internal identities; it can never register or log in.
* `proxy.ts` only checks that a session cookie *exists* (fast redirect); the backend validates the token and any API 401
  sends the user to `/login?reason=expired`.
* Mock mode and the duplicated frontend trees (`lib/`, `components/` at the app root versus `src/shared/`) were left in
  place except where auth code touched them; `lib/api/client.ts` now re-exports the `src/` client so they cannot drift.
* A pre-existing build break (`useSearchParams` without Suspense in `StartTestForm`'s two pages) was fixed so `next build` works.
* The 2 failing tests and 5 errors in `test_a1_hardening.py` / `test_commit_loop.py` (missing `workspace_id` column in their own
  test database setup) also fail on the untouched code and are not related to this work.
* Running the backend test-suite earlier wrote rows into your real `data/kawach.db` (it did before my change too). I ran
  every later test run against a temporary DB/storage, and importing the backend created `data/.jwt_secret`.
