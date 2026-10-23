# Kawach Demo Tenant Setup & Scoped Token Provisioning (`docs/DEMO_TENANT_SETUP.md`)

This guide explains how to set up an isolated demo tenant, seed a sample target application project, mint a time-bounded scoped API token via an interactive web session, and revoke credentials immediately when testing concludes.

---

## 1. Overview & Isolation Guarantee

The Kawach MCP server operates as a multi-tenant gateway over the core Kawach REST API.
- **Tenant Isolation**: Every database entity (`Project`, `Run`, `Bug`, `ApiToken`, `SavedTest`) is bound to the owner's `user_id`. An API token minted for the tester can only see and interact with entities created within their tenant workspace.
- **No Shared Secrets**: The MCP server holds zero shared secrets. All operations run under the specific identity and granted scopes of the caller's `kw_live_...` token.
- **Scope Gating**: The token is restricted to `read + run` privileges. Mutating administrative tools (e.g. project deletion, database modifications, or global test suite overwrites) are strictly hidden and rejected.

---

## 2. Step 1: Create the Demo Tenant Account

1. Ensure the Kawach backend API (`http://127.0.0.1:8000`) and Web Dashboard (`http://127.0.0.1:3000`) are running.
2. In your browser, navigate to the Kawach Registration page:
   ```text
   http://localhost:3000/register
   ```
3. Register a dedicated demo account for the tester:
   - **Email**: `tester-demo@kawach.local` (or a tenant email of your choice)
   - **Display Name**: `Outside Tester Demo`
   - **Password**: *(Use a strong, unique password)*
4. Log into the account. An interactive session cookie / JWT is established.

---

## 3. Step 2: Seed the Sample Target Application Project

To provide immediate value to the tester upon first connection, seed a project pointing to the local target application:

1. Navigate to **New Project** in the web dashboard:
   ```text
   http://localhost:3000/projects/new
   ```
2. Enter the project configuration:
   - **Project Name**: `Target Store Demo`
   - **Slug**: `target-store-demo`
   - **Target URL**: `http://127.0.0.1:4000` *(or your staging environment URL)*
   - **Description**: `E-commerce target application with planted test defects for exploratory QA evaluation.`
   - **Default Mode**: `manual` (human-in-the-loop review)
3. Click **Create Project**.
4. *(Recommended)* Run an initial exploration from the Web UI:
   - Click **"Start QA Run"** on the project page.
   - Wait 1–2 minutes for the agent to crawl states and discover initial defects.
   - This ensures `list_projects`, `get_run_status`, `list_failures`, and `get_failure_analysis` immediately have rich diagnostic data for the tester to inspect through their IDE agent.

---

## 4. Step 3: Mint Scoped Token via Interactive Web Session

> [!IMPORTANT]
> **Security Rule**: API tokens must always be minted through an authenticated user session (`require_session_auth`), never through seed scripts or CLI defaults. This ensures that every token is logged in the audit trail with `client_type="web"`.

### Option A: Using the Web Dashboard
1. In the web dashboard, open the project settings or user profile menu and navigate to **API Tokens**.
2. Click **"Create Token"**.
3. Fill in the parameters:
   - **Token Name**: `Outside Tester 3-Day Token`
   - **Validity**: `3 days`
   - **Scopes**: Select the following 5 scopes for **Read + Run** access:
     - `projects:read` — View projects and target URLs
     - `runs:read` — Inspect run status, test catalogs, results, bugs, and AppMap
     - `runs:write` — Trigger test runs and approve catalogs
     - `analysis:read` — View root-cause suspect files and fix suggestions
     - `tests:read` — View saved Playwright regression suites
4. Click **Generate Token**.
5. Copy the plaintext bearer secret (`kw_live_...`).
   > [!WARNING]
   > The plaintext secret is displayed **only once**. Only its SHA-256 hash is retained on the server. Never commit this token to git.

### Option B: Using the Backend REST API (with Session JWT)
If generating the token via terminal while authenticated:
```bash
# 1. Obtain JWT session
JWT_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"tester-demo@kawach.local","password":"YourPasswordHere"}' \
  | jq -r .token)

# 2. Mint 3-day scoped token
curl -s -X POST http://localhost:8000/api/v1/auth/tokens \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Outside Tester 3-Day Token",
    "scopes": ["projects:read", "runs:read", "runs:write", "analysis:read", "tests:read"],
    "expires_in_days": 3
  }'
```

---

## 5. Step 4: Token Revocation Protocol

If the token is leaked, testing finishes early, or the testing window expires, revoke the token immediately.

### Immediate Web Revocation
1. Log into `http://localhost:3000` with the tenant account.
2. Navigate to **API Tokens**.
3. Find `Outside Tester 3-Day Token` and click **"Revoke"**.

### Immediate API Revocation
```bash
curl -X DELETE http://localhost:8000/api/v1/auth/tokens/<token_id> \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Verification of Revocation
- In `data/kawach.db`, `api_tokens.revoked_at` is set to the current UTC timestamp.
- The MCP server's scope cache TTL is $\le$ 60 seconds.
- Any subsequent tool execution with the revoked token is rejected with **HTTP 401 Unauthorized**:
  ```json
  {"error": "Unauthorized: Authentication failed. The provided KAWACH_API_TOKEN is invalid or expired."}
  ```
