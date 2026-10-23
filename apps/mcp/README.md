# Kawach Model Context Protocol (MCP) Server (`apps/mcp`)

The **Kawach MCP Server** provides a native Model Context Protocol interface to the Kawach Autonomous QA Engineer platform. It acts as the **third front door** to Kawach—sitting alongside the Web Dashboard (`apps/web`) and the GitHub Webhook listener (`apps/api`).

The server operates strictly as a **thin HTTP adapter** over Kawach's canonical REST API (`apps/api`). It holds **no direct database access, no raw LLM keys, and no GitHub personal access tokens**. All business logic, verification routines, scoping, and data isolation remain centrally governed by the backend.

---

## Architecture & Security Model

```
 ┌────────────────────────────────────────────────────────┐
 │  IDE / Developer Agent (Cursor, Claude Code, Zed, etc) │
 └──────────────────────────┬─────────────────────────────┘
                            │ JSON-RPC over stdio
 ┌──────────────────────────▼─────────────────────────────┐
 │  Kawach MCP Server (apps/mcp)                          │
 │  - Zero DB access / Zero LLM keys                      │
 │  - Token redaction (`kw_live_...` -> [REDACTED])       │
 │  - Injection defense (<untrusted_content> sandboxing)  │
 │  - 2-Step Confirmation engine (SHA-256 + 5-min TTL)    │
 │  - Strict Scope Gating & fail-fast on startup          │
 └──────────────────────────┬─────────────────────────────┘
                            │ HTTP + Bearer Token
 ┌──────────────────────────▼─────────────────────────────┐
 │  Kawach REST API (apps/api - http://localhost:8000)    │
 └────────────────────────────────────────────────────────┘
```

### Security Highlights
1. **Scope Gating & Fail-Fast**: On startup, the server calls `GET /api/v1/auth/me` to introspect token scopes. If the token is missing or invalid, it exits immediately with code 1. Tools outside the token's granted scopes are never registered in the tool catalog.
2. **Read-Only by Default**: Destructive or state-mutating actions (`save_test`, `apply_fix_as_pr`, `delete_project`) are hidden unless explicitly enabled via `KAWACH_ALLOW_WRITE_TOOLS=true`.
3. **Two-Step Confirmation Engine**: Write tools require two steps:
   - Call 1 returns a preview + a cryptographic SHA-256 token (`confirmation_token`) valid for 5 minutes.
   - Call 2 executes the action only if `confirm=true` and the exact same parameters are supplied.
4. **Prompt Injection Defense**: Untrusted content returned from external websites, assertion traces, repro scripts, and Git diffs are wrapped in `<untrusted_content>` tags with neutralized closing sequences.
5. **Token Redaction**: Tokens matching `kw_live_[A-Za-z0-9_]+` and `Bearer ...` headers are scrubbed from all tool outputs, error responses, and prompt contents.

---

## Quickstart

### 1. Prerequisites
- Python 3.11+
- Running Kawach Backend (default: `http://localhost:8000`)
- A valid Kawach API token generated from the backend or dashboard (format: `kw_live_...`)

### 2. Installation
From the repository root:
```bash
pip install -r apps/mcp/requirements.txt
# Or install in editable mode:
pip install -e apps/mcp
```

### 3. Environment Configuration
The MCP server accepts configuration via environment variables or a secure token file:

| Variable | Default | Description |
|---|---|---|
| `KAWACH_API_URL` | `http://localhost:8000` | URL of the Kawach backend API |
| `KAWACH_API_TOKEN` | `None` | Kawach API token (`kw_live_...`) |
| `KAWACH_API_TOKEN_FILE` | `~/.kawach/token` | Path to token file (checked if `KAWACH_API_TOKEN` is unset) |
| `KAWACH_ALLOW_WRITE_TOOLS` | `false` | Enable write/mutation tools (`save_test`, `apply_fix_as_pr`) |
| `KAWACH_MAX_RESPONSE_CHARS` | `16000` | Maximum character length for tool outputs before truncation |
| `KAWACH_HTTP_TIMEOUT_SECONDS` | `30.0` | HTTP request timeout in seconds |
| `KAWACH_HTTP_MAX_RETRIES` | `3` | Max HTTP retry attempts on 429 rate limit or 503 transient errors |

#### Storing Token Securely
On Linux / macOS:
```bash
mkdir -p ~/.kawach
echo "kw_live_your_token_here" > ~/.kawach/token
chmod 0600 ~/.kawach/token
```
*(On POSIX systems, permissions looser than 0600 are rejected at startup).*

---

## Client Integration Snippets

### Claude Code CLI
Add Kawach MCP directly via the Claude Code CLI:
```bash
claude mcp add kawach -- env KAWACH_API_URL=http://localhost:8000 KAWACH_API_TOKEN=kw_live_your_token python -m kawach_mcp.server
```

### Cursor (`.cursor/mcp.json` or `~/.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "kawach": {
      "command": "python",
      "args": ["-m", "kawach_mcp.server"],
      "env": {
        "KAWACH_API_URL": "http://localhost:8000",
        "KAWACH_API_TOKEN": "kw_live_YOUR_TOKEN_HERE",
        "KAWACH_ALLOW_WRITE_TOOLS": "false"
      }
    }
  }
}
```

### Generic Stdio MCP Client (VS Code, Windsurf, Zed)
```json
{
  "kawach": {
    "command": "kawach-mcp",
    "args": [],
    "env": {
      "KAWACH_API_URL": "http://localhost:8000",
      "KAWACH_API_TOKEN": "kw_live_YOUR_TOKEN_HERE"
    }
  }
}
```

### MCP Inspector (Interactive Debugging)
To test and inspect all tools, resources, and prompts interactively:
```bash
npx @modelcontextprotocol/inspector python -m kawach_mcp.server
```
Or use the Makefile target:
```bash
make mcp-inspect
```

---

## Available Primitives

### 23 Tools
- **Read Tools (15)**: `list_projects`, `get_project`, `get_app_map`, `list_runs`, `get_run`, `list_test_cases`, `get_test_case`, `list_failures`, `get_failure_analysis`, `get_fix_suggestion`, `get_regression_report`, `list_saved_tests`, `get_saved_test`, `list_flaky_tests`, `get_server_status`.
- **Action Tools (4)**: `start_run`, `wait_for_run`, `run_regression`, `stop_run`.
- **Write Tools (3)**: `save_test`, `apply_fix_as_pr`, `delete_project` (all require `KAWACH_ALLOW_WRITE_TOOLS=true` and two-step confirmation).

### 5 Resource URI Templates
- `kawach://projects/{project_id}/runs/{run_id}/report`
- `kawach://projects/{project_id}/failures/{failure_id}/repro.py`
- `kawach://projects/{project_id}/commits/{commit_sha}/analysis`
- `kawach://projects/{project_id}/app-map`
- `kawach://projects/{project_id}/saved-tests/{test_id}/test.py`

### 4 Workflow Prompts
- `triage-failing-commit`: Analyzes commit regressions, suspect files, and reproduction scripts.
- `explain-bug`: Explains root causes, confidence scores, and reproduction paths for a verified failure.
- `review-fix-before-apply`: Reviews unified diffs, affected lines, and risks before applying a fix.
- `explore-app-surface`: Summarizes routes, interactive elements, forms, and coverage gaps.

See [`docs/MCP_USAGE.md`](../../docs/MCP_USAGE.md) for the complete tool catalog and schema documentation.

---

## Troubleshooting

### 1. `401 Unauthorized` on Startup
- **Cause**: Missing, expired, or invalid `KAWACH_API_TOKEN`.
- **Fix**: Check `GET /api/v1/auth/me` on the backend. Ensure token matches format `kw_live_...` and is active in the backend database.

### 2. `403 Forbidden` / Missing Tools
- **Cause**: Token lacks required scopes (`runs:trigger`, `analysis:read`, `tests:write`).
- **Fix**: The MCP server dynamically gates tools based on the token's granted scopes. Issue a token with full developer scopes (`projects:read`, `runs:read`, `runs:trigger`, `analysis:read`, `tests:read`).

### 3. Insecure Token Permissions (Error at Startup)
- **Cause**: On Linux/macOS, `~/.kawach/token` has file permissions broader than `0600` (e.g. `0644`).
- **Fix**: Run `chmod 0600 ~/.kawach/token`.

### 4. Stdio Buffering or JSON-RPC Desync
- **Cause**: Non-MCP debug logs printed directly to `stdout`.
- **Fix**: The Kawach MCP server routes all internal logging to `stderr`. Never print to `stdout` within MCP subprocesses.

---

## Testing
Run unit and integration tests:
```bash
pytest apps/mcp/tests/ -v
# Or via Makefile:
make mcp-test
```
