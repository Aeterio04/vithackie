# Kawach MCP Server — Temporary Remote Hosting Architecture (`docs/MCP_TEMP_HOSTING.md`)

This document defines the architectural audit, remote HTTP mode specification, temporary ngrok tunnel setup, tester onboarding protocol, shutdown procedures, and long-term production migration roadmap for the **Kawach Model Context Protocol (MCP) Server** (`apps/mcp`).

---

## Section 1: Architectural Audit & Remote Hosting Feasibility (Task T0)

### 1.1. Existing Transports in `apps/mcp`
Currently, the Kawach MCP Server is strictly implemented for local Standard I/O (`stdio`):
- **Entry Point**: `apps/mcp/src/kawach_mcp/server.py:run_server` defaults unconditionally to `await server.run_stdio_async()`.
- **Command Line**: `kawach-mcp` (or `python -m kawach_mcp.server`) accepts no command-line transport arguments (`--transport`, `--host`, `--port`, `--path`).
- **Target Audience**: Designed as a single-process companion daemon spawned as a child subprocess by local IDE agents (Cursor, Claude Code CLI, Windsurf, Zed).

### 1.2. API Token Acquisition: Environment vs. Per-Request
- **Current Acquisition**: Process-static via `Settings.get_effective_token()` (`apps/mcp/src/kawach_mcp/config.py`). It searches `os.environ["KAWACH_API_TOKEN"]` first, then falls back to `~/.kawach/token` (verifying POSIX 0600 permissions on non-Windows systems).
- **Backend Communication**: `KawachClient._build_headers()` (`apps/mcp/src/kawach_mcp/client.py:97`) injects this static token as `Authorization: Bearer <static_token>` on every outgoing HTTP call.
- **Boot-Time Verification**: On startup, `server.py:run_server` calls `GET /api/v1/auth/me` with this static token to introspect granted scopes. If the token is missing, expired, or invalid, the process exits immediately (`sys.exit(1)`).
- **Audit Finding**: In a remote multi-caller or external tester scenario, a static process-level token is unacceptable. The remote HTTP server must hold **zero shared credentials**. Instead, it must extract `Authorization: Bearer kw_live_...` from each incoming HTTP request, validate/introspect it, and forward that exact caller token to the Kawach backend.

### 1.3. Scope Registration & Dynamic Tool Filtering
- **Current Behavior**: `server.py:create_mcp_server` registers tools into `MCPServer` statically at startup based on `auth_info.scopes` returned by the startup token. Any tool whose `required_scope` is missing is never registered.
- **Audit Finding**: In remote HTTP mode, different callers (or tokens) can possess different scopes (e.g. read-only tokens vs. read+run tokens).
  - Registering tools once at startup with a static scope set breaks multi-caller isolation.
  - **Architecture Solution for T1**:
    1. Register all tools on the `MCPServer` instance.
    2. Intercept `list_tools()` dynamically to return only the subset of tools authorized by the active caller's token (cached in-memory for <= 60s keyed by `sha256(token)`).
    3. In each tool handler, gate execution against the active caller's scopes and return `403 Permission Denied` if the caller lacks required permissions.

### 1.4. Write-Tool Confirmation Store
- **Current Implementation**: Located in `apps/mcp/src/kawach_mcp/tools/confirmation.py:confirmation_manager`.
- **State Model**: A process-global singleton dictionary `_tokens: Dict[str, Tuple[str, float]]` mapping `confirmation_id -> (payload_hash, expires_at)` with a 5-minute TTL.
- **Hash Function**: `_canonical_hash(payload)` computes `sha256(json.dumps(payload))`. It does **not** bind the confirmation ID to the caller's identity or token.
- **Audit Finding**: If two callers connect simultaneously, they share the same global confirmation dictionary. While confirmation IDs are random UUIDs (`conf_...`), Caller B could theoretically confirm an action or collide with Caller A.
  - **Architecture Solution for T1**: Compute payload hash as `sha256(token_hash + ":" + canonical_payload)`. A confirmation ID generated for Caller A cannot be consumed or replayed by Caller B, even with identical arguments.

### 1.5. Global or Per-Process State That Breaks with Multiple Callers
1. **`Settings.api_token` / `_token`**: Must be ignored in remote HTTP mode; no default token must be set.
2. **`KawachClient._client` headers**: Headers must not bake in a static `Authorization` header. Requests must pass caller-specific authorization via per-request headers or context variables.
3. **`confirmation_manager`**: Must bind confirmation tokens to the caller's token hash.
4. **Scope Introspection**: Must not be a single boot-time global; must be a bounded LRU/TTL cache keyed by `sha256(token)`.

### 1.6. Installed MCP SDK (`mcp 2.3.0`) Capabilities
The installed MCP SDK was audited directly on the runtime environment:
- **Streamable HTTP Transport**: Implemented in `mcp.server.streamable_http.StreamableHTTPServerTransport` and exposed via `MCPServer.streamable_http_app(...)`.
- **Stateless HTTP Mode**: Native support via `stateless_http: bool = True`. In stateless mode, the server avoids holding persistent sessions, back-channels, or SSE streams open. Every incoming POST request is dispatched and replied to independently.
- **Plain JSON Responses**: Native support via `json_response: bool = True`. When enabled, the server returns standard `application/json` HTTP responses rather than chunked SSE event streams. This prevents proxies, ngrok tunnels, and intermediate firewalls from buffering or severing long-lived streaming connections.
- **ASGI / Starlette Foundation**: `MCPServer.streamable_http_app` returns a standard `starlette.applications.Starlette` application. This provides full support for custom routes (`/healthz`), custom middleware (`BaseHTTPMiddleware`), CORS, Origin checks, and concurrency limiting.
- **Built-in DNS Rebinding Protection**: `mcp.server.transport_security.TransportSecurityMiddleware` and `TransportSecuritySettings` provide native Host and Origin validation.

### 1.7. Installed ngrok CLI (`ngrok version 3.37.2`) Capabilities & Flags
The installed ngrok binary was audited directly on Windows:
- **Version**: `ngrok version 3.37.2`
- **Configuration**: Active valid config at `%LOCALAPPDATA%\ngrok\ngrok.yml` with valid authtoken already configured.
- **Command**: `ngrok http [port] [flags]`
- **Exact Supported Flags in v3.37.2**:
  - `--url string`: Specify endpoint URL (e.g. `--url https://example.ngrok-free.app` or custom domain). If omitted on a free tier, ngrok assigns a random ephemeral public URL.
  - `--inspect`: Boolean (default: `true`). **Setting `--inspect=false` disables the local HTTP traffic inspection dashboard at `127.0.0.1:4040`**. This is a mandatory security setting to prevent Bearer tokens from appearing in local inspection logs.
  - `--traffic-policy-file string`: Path to YAML/JSON traffic policy file. Supported on ngrok cloud to apply edge rules (e.g., rejecting requests without Authorization headers).
  - `--log string`: Path to log file, `'stdout'`, `'stderr'`, or `'false'` (default `"false"`).
  - `--log-format string`: `'term'`, `'logfmt'`, or `'json'`.
  - `--log-level string`: `'debug'`, `'info'`, `'warn'`, `'error'`, `'crit'`.
- **Local Agent Management API**: Runs at `http://127.0.0.1:4040/api/tunnels` by default, providing JSON metadata to programmatically discover the public tunnel URL.

### 1.8. Threat Model & Risks

| Threat / Risk | Impact | Architectural Mitigation in Task T1 & T2 |
|---|---|---|
| **Public Internet Exposure** | Automated scanners hitting the public ngrok endpoint. | Bind MCP server strictly to loopback (`127.0.0.1`). Fail fast with HTTP 401 before any tool runs if `Authorization` header is missing or malformed. |
| **Credential Sniffing via ngrok Dashboard** | ngrok's local dashboard (`127.0.0.1:4040`) displays full HTTP request headers including `Authorization: Bearer kw_live_...`. | Set `--inspect=false` in `start-ngrok.ps1` to disable local HTTP introspection entirely. |
| **Browser Warning Interstitials** | ngrok free tier serves an HTML warning page to interactive web browsers. | API clients and IDE agents send `POST` with `Content-Type: application/json` and `Accept: application/json`, which bypass ngrok browser interstitials. Document `ngrok-skip-browser-warning: true` header for safety. |
| **Shared / Leaked Tokens** | One tester token used across unauthorized actions. | Scope gating: tester token is minted strictly with required scopes (`projects:read`, `runs:read`, `runs:trigger`, `analysis:read`, `tests:read`). Destructive write tools are disabled (`KAWACH_ALLOW_WRITE_TOOLS=false`). |
| **Confirmation Token Hijacking** | Caller B confirms an action initiated by Caller A. | Salt and bind all confirmation IDs to `sha256(token_hash + ":" + payload)`. Replay or cross-caller execution fails. |
| **Denial of Service / Unbounded Payloads** | Malicious caller sends 50MB payload or floods concurrent calls. | Enforce 1MB request body limit, 30s per-request timeout, and per-caller concurrency cap in Starlette middleware. |
| **Log Leakage** | Tokens appearing in server stdout/stderr or access logs. | Access logging logs only request ID, first 8 characters of `sha256(token)`, method, path, status, and duration. `Authorization` header is strictly redacted. |

---

---

## Section 2: Shutting Down the Temporary Test

When testing concludes, follow this 4-step shutdown procedure to ensure no tunnels remain open and no credentials remain valid:

### 2.1. Stop the ngrok Tunnel
Run the stop script from the repository root:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\tunnel\stop-ngrok.ps1
```
This script:
1. Reads the ngrok process ID from `scripts/tunnel/.ngrok.pid`.
2. Terminates only that specific ngrok process (`Stop-Process -Id <pid> -Force`).
3. Deletes temporary state files: `scripts/tunnel/.ngrok.pid` and `scripts/tunnel/.current_url`.
4. Removes the `MCP_PUBLIC_URL` line from `.env.local`.

### 2.2. Stop the Kawach MCP HTTP Server
- If running in an interactive terminal: Press `Ctrl+C`.
- If running as a background service: Terminate the Python process listening on port 8765.

### 2.3. Revoke the Tester API Token
Immediately invalidate the tester's credentials in the backend:
- **Web UI**: Navigate to `http://localhost:3000/settings` -> **API Tokens**, locate `Outside Tester 3-Day Token`, and click **Revoke**.
- **REST API**:
  ```bash
  curl -X DELETE http://localhost:8000/api/v1/auth/tokens/<token_id> \
    -H "Authorization: Bearer <session_jwt>"
  ```
Once revoked in the database:
- The token's `revoked_at` timestamp is permanently recorded.
- Within the $\le$ 60-second cache TTL, any subsequent request using this token is rejected with HTTP 401 Unauthorized.

### 2.4. Verify Complete Teardown
1. Verify no process is listening on ports 8765 or 4040:
   ```powershell
   Get-NetTCPConnection -LocalPort 8765, 4040 -ErrorAction SilentlyContinue
   ```
   *(Must return nothing).*
2. Verify ngrok process is not running:
   ```powershell
   Get-Process -Name "ngrok" -ErrorAction SilentlyContinue
   ```
   *(Must return nothing).*
3. Verify temporary state files are removed:
   ```powershell
   Test-Path scripts\tunnel\.current_url, scripts\tunnel\.ngrok.pid
   ```
   *(Must return False).*

> [!NOTE]
> **Complete Repository Isolation:**
> Nothing in `apps/api`, `apps/mcp`, or `apps/web` references ngrok. Deleting the `scripts/tunnel/` folder completely removes the tunnel scripts without affecting any application code.

---

## Section 3: Migrating to a Real Server Later (Zero Code Changes)

A core design requirement of Task T was that **moving to a production server requires changing configuration only — not code**.

The Kawach MCP Server is implemented on standard **Starlette ASGI** and the official MCP SDK 2.3.0 in stateless HTTP mode (`stateless_http=True`, `json_response=True`). It requires zero code modifications to deploy in a production cloud environment (AWS, GCP, DigitalOcean, Kubernetes, Docker).

### 3.1. Production Architecture Overview

```text
[External Clients: Cursor / Claude Code]
                 │  HTTPS (TLS 1.3)
                 ▼
     [Reverse Proxy: Nginx / Caddy / Cloudflare]
     ├── SSL Termination (Certbot / Let's Encrypt)
     ├── DDoS & Rate Limiting
     └── Header Forwarding (Host, X-Real-IP, X-Request-ID)
                 │  HTTP (Loopback / Private VPC)
                 ├──> http://127.0.0.1:8765 (/mcp, /healthz)  -> Kawach MCP Server
                 └──> http://127.0.0.1:8000 (/api/v1/...)      -> Kawach Backend API
```

### 3.2. Step-by-Step Production Deployment

#### Step 1: Run apps/mcp under a Process Supervisor
In production, run the MCP server using `uvicorn` with multiple workers or via a systemd service:

```bash
# Production launch with Uvicorn
uvicorn kawach_mcp.server:create_http_app \
  --factory \
  --host 127.0.0.1 \
  --port 8765 \
  --workers 4 \
  --log-level info
```

Example systemd unit file (`/etc/systemd/system/kawach-mcp.service`):
```ini
[Unit]
Description=Kawach MCP Streamable HTTP Service
After=network.target

[Service]
Type=simple
User=kawach
WorkingDirectory=/opt/kawach
Environment="PYTHONPATH=apps/mcp/src:apps/api/src"
EnvironmentFile=/etc/kawach/mcp.env
ExecStart=/opt/kawach/.venv/bin/python -m kawach_mcp.server --transport http --host 127.0.0.1 --port 8765 --path /mcp
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### Step 2: Configure Reverse Proxy with TLS (Nginx Example)
Configure Nginx to terminate SSL and proxy requests to `127.0.0.1:8765`:

```nginx
# /etc/nginx/sites-available/mcp.kawach.ai
server {
    listen 80;
    server_name mcp.kawach.ai;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name mcp.kawach.ai;

    # SSL Certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/mcp.kawach.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.kawach.ai/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security & Size Limits
    client_max_body_size 1M;
    proxy_read_timeout 60s;
    proxy_connect_timeout 10s;

    # Streamable HTTP MCP Endpoint
    location /mcp {
        proxy_pass http://127.0.0.1:8765/mcp;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;

        # Disable proxy buffering for smooth MCP JSON-RPC delivery
        proxy_buffering off;
    }

    # Unauthenticated Healthcheck
    location /healthz {
        proxy_pass http://127.0.0.1:8765/healthz;
        access_log off;
    }
}
```

#### Step 3: Production Environment Configuration Only
Configure the MCP server via standard environment variables:

| Variable | Production Value | Purpose |
|---|---|---|
| `KAWACH_API_URL` | `http://127.0.0.1:8000` *(or internal DNS)* | URL of the core Kawach backend REST API |
| `MCP_HOST` | `127.0.0.1` | Loopback bind address (proxy handles public traffic) |
| `MCP_PORT` | `8765` | Internal port |
| `MCP_PATH` | `/mcp` | Path prefix |
| `MCP_PUBLIC_URL` | `https://mcp.kawach.ai/mcp` | Canonical public URL distributed to clients |
| `KAWACH_ALLOWED_ORIGINS` | `https://app.kawach.ai,https://mcp.kawach.ai` | Allowed Origin headers |
| `KAWACH_ALLOW_WRITE_TOOLS` | `true` *(or `false` for read-only instances)* | Gate for mutating tools |
| `MAX_REQUEST_BODY_SIZE` | `1048576` (1MB) | Body size limit |
| `PER_CALLER_CONCURRENCY_LIMIT` | `10` | Per-token concurrent request cap |
| `PER_REQUEST_TIMEOUT_SECONDS` | `30` | Per-request timeout |

#### Step 4: Verification of Production Endpoint
Run the existing verification script against the production domain:
```bash
python scripts/verify_remote_mcp.py https://mcp.kawach.ai/mcp <token>
```
All 7 tests will execute and pass without modifying a single line of application code.

