# Kawach MCP Temporary Tunnel (`scripts/tunnel`)

This directory contains throwaway scripts to expose the local Kawach Model Context Protocol (MCP) HTTP server (`127.0.0.1:8765`) to an outside tester via an encrypted **ngrok** tunnel.

> [!IMPORTANT]
> **Complete Isolation Notice:**
> Nothing in the core Kawach application (`apps/api`, `apps/mcp`, `apps/web`) depends on or references ngrok. Deleting this `scripts/tunnel/` directory completely eliminates the tunnel integration from the repository.

---

## Prerequisites

1. **ngrok CLI**:
   - Install via winget or binary:
     ```powershell
     winget install ngrok
     ```
   - Authenticate with your personal ngrok authtoken:
     ```powershell
     ngrok config add-authtoken <your-ngrok-authtoken>
     ```
     *(Never commit or print this authtoken).*
2. **Kawach Backend API**:
   - Must be running on `http://127.0.0.1:8000`:
     ```powershell
     make backend
     ```
3. **Kawach MCP HTTP Server**:
   - Must be running on `http://127.0.0.1:8765`:
     ```powershell
     kawach-mcp --transport http --port 8765
     ```

---

## Usage

### 1. Start the Tunnel
```powershell
.\scripts\tunnel\start-ngrok.ps1
```
If you have a reserved/static domain on your ngrok account:
```powershell
.\scripts\tunnel\start-ngrok.ps1 -Domain "your-domain.ngrok-free.app"
```

The script will:
- Verify that `http://127.0.0.1:8000` and `http://127.0.0.1:8765/healthz` are responsive.
- Verify ngrok CLI and authtoken.
- Launch ngrok in the background with `--inspect=false`.
- Discover the public HTTPS URL from the ngrok agent API.
- Save the public URL to `.env.local` (`MCP_PUBLIC_URL=...`) and `scripts/tunnel/.current_url` (both untracked and git-ignored).
- Output the full public MCP endpoint (e.g. `https://xxxx-xx-xx.ngrok-free.app/mcp`).

### 2. Stop the Tunnel
```powershell
.\scripts\tunnel\stop-ngrok.ps1
```
Safely terminates only the ngrok process started by `start-ngrok.ps1` and cleans up temporary state files.

---

## Security Architecture & Threat Mitigations

### 1. Disabling Local Inspection (`--inspect=false`)
By default, the ngrok agent runs an HTTP request inspector on `http://127.0.0.1:4040` that captures and displays full HTTP headers—including `Authorization: Bearer kw_live_...`.
- To prevent Bearer token leakage to local viewers, screen-shares, or local processes, `start-ngrok.ps1` enforces `--inspect=false`.
- Request headers and payload bodies are **never** logged by ngrok locally.

### 2. Browser Interstitials vs. API Clients
On ngrok free-tier accounts, visiting a tunnel URL in a standard desktop web browser displays an HTML interstitial warning page (*"You are about to visit an ngrok-hosted site..."*).
- **Automated API & MCP Clients are unaffected**: MCP clients (Cursor, Claude Code, Python scripts) make `POST` requests with `Content-Type: application/json` and `Accept: application/json`, which ngrok passes through directly to localhost without any interstitial.
- If a client makes a `GET` request (e.g. to `/healthz`), sending the header `ngrok-skip-browser-warning: true` ensures the interstitial is completely bypassed.

### 3. Edge Traffic Policy (`traffic-policy.yml`)
`scripts/tunnel/traffic-policy.yml` provides a declarative cloud-edge policy:
- Rejects requests that lack an `Authorization` header directly at ngrok's edge before packets ever reach your machine.
- What it adds on top of the MCP server's own 401 check: prevents malicious automated internet scrapers from consuming local CPU cycles or bandwidth.
- *(Note: Advanced actions like IP allowlists require an ngrok paid plan. On free accounts, the MCP server's own 401, 403, and Origin checks provide primary defense).*

### 4. Ephemeral URL Handling
On free plans without a static domain, ngrok generates a new random URL each time the tunnel starts.
- When you restart the tunnel, send the newly generated URL to your tester.
- The verification script (`scripts/verify_remote_mcp.py`) reads the current URL from `scripts/tunnel/.current_url` automatically.
