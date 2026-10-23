# Kawach MCP — Outside Tester Onboarding Guide (`docs/TESTER_ONBOARDING.md`)

Welcome to the **Kawach Model Context Protocol (MCP)** testing program! This guide will get you connected in under 2 minutes using your favorite AI IDE assistant (Claude Code CLI, Cursor, Windsurf, Zed, or any standard MCP client).

---

## 1. What is Kawach MCP?

Kawach is an **Autonomous AI QA Engineer**. The Kawach MCP Server allows your AI coding assistant to:
- Inspect autonomous test runs and crawl progress.
- Discover confirmed defects, reproduction scripts, and screenshots.
- Perform automated failure analysis (pinpointing suspect files, lines of code, and git commit culprits).
- Trigger on-demand exploratory and Playwright regression test runs directly from your editor.

---

## 2. Your Connection Parameters

You should have received two items from your Kawach host:

| Parameter | Example / Format | Notes |
|---|---|---|
| **Public MCP URL** | `https://xxxx.ngrok-free.dev/mcp` | Hosted on a temporary encrypted tunnel. *Note: On the free tier, this URL changes if the host restarts the tunnel.* |
| **Bearer Token** | `kw_live_...` | Your scoped API key. Valid for 3 days with `read + run` privileges. |

---

## 3. Client Setup

### Option A: Claude Code CLI
Add the Kawach remote MCP server using the `claude mcp add` command:

```bash
claude mcp add kawach \
  https://<YOUR_NGROK_URL>/mcp \
  --header "Authorization: Bearer <YOUR_TOKEN>" \
  --header "ngrok-skip-browser-warning: 1"
```

Or add it directly to your `~/.claude.json` (or `.claude.json` in your project root):

```json
{
  "mcpServers": {
    "kawach": {
      "url": "https://<YOUR_NGROK_URL>/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_TOKEN>",
        "ngrok-skip-browser-warning": "1"
      }
    }
  }
}
```

---

### Option B: Cursor IDE
1. Open **Settings** (`Ctrl+,` or `Cmd+,`).
2. Navigate to **Features** $\to$ **MCP**.
3. Click **"+ Add New MCP Server"**.
4. Configure the fields:
   - **Name**: `kawach`
   - **Type**: `sse` (or `http`)
   - **Server URL**: `https://<YOUR_NGROK_URL>/mcp`
   - **Custom Headers**:
     - `Authorization`: `Bearer <YOUR_TOKEN>`
     - `ngrok-skip-browser-warning`: `1`
5. Save the configuration. Cursor will display a green indicator when connected.

---

### Option C: Generic / Python MCP SDK Client
The server runs over standard **Streamable HTTP (Stateless JSON Mode)**. All JSON-RPC 2.0 messages are dispatched via `POST https://<YOUR_NGROK_URL>/mcp`.

```python
import httpx

headers = {
    "Authorization": "Bearer <YOUR_TOKEN>",
    "ngrok-skip-browser-warning": "1",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Example: List available tools
payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
res = httpx.post("https://<YOUR_NGROK_URL>/mcp", json=payload, headers=headers)
print(res.json())
```

---

## 4. Important Notice: ngrok Browser Interstitial

Because the temporary tunnel is hosted on ngrok's free tier:
- Standard HTTP `GET` requests from web browsers will see an HTML interstitial warning page (`ERR_NGROK_6024`).
- **How to bypass**: All automated API calls and JSON-RPC clients bypass this automatically by providing the HTTP header:
  ```http
  ngrok-skip-browser-warning: 1
  ```
  Ensure this header is included in your client configuration as shown above.

---

## 5. Five Prompts to Try in Your IDE

Once connected, test Kawach's capabilities by pasting these prompts into your AI chat window:

### Prompt 1: Verify Connectivity & Granted Scopes
> *"Can you check the Kawach server status and list the QA tools and scopes available in this session?"*
- **Under the hood**: Calls `get_server_status`.
- **Expected result**: Confirms connection to the backend, lists your granted scopes (`projects:read`, `runs:read`, `runs:write`, `analysis:read`, `tests:read`).

### Prompt 2: Explore Available Projects
> *"List all accessible QA projects in Kawach and show me their target URLs and settings."*
- **Under the hood**: Calls `list_projects` and `get_project`.
- **Expected result**: Returns the seeded sample application (e.g. `Target Store Demo` at `http://127.0.0.1:4000`).

### Prompt 3: Inspect Discovered Defects & Test Results
> *"What are the latest test run results for the target app, and what confirmed defects or bugs were found?"*
- **Under the hood**: Calls `list_runs`, `get_run_status`, and `list_failures`.
- **Expected result**: Displays confirmed bugs, reproduction replay counts, and step-by-step failure paths.

### Prompt 4: Root-Cause & Suspect Code Analysis
> *"Perform failure analysis on the latest failed run. Pinpoint which files and lines of code are suspect culprits and summarize why."*
- **Under the hood**: Calls `get_failure_analysis` and `get_fix_suggestion`.
- **Expected result**: Returns culprit candidate source files, confidence scores, and potential fix diffs.

### Prompt 5: Trigger an On-Demand QA Run
> *"Trigger a new exploratory test run against the target store application."*
- **Under the hood**: Calls `start_run` (authorized because your token includes `runs:write`).
- **Expected result**: Initializes a new autonomous exploration run and returns the live progress handle.

---

## 6. Disconnecting & Reporting Issues

### How to Disconnect
To remove Kawach from your client:
- In **Claude Code**: Run `claude mcp remove kawach` or delete the entry from `.claude.json`.
- In **Cursor**: Toggle the `kawach` entry off or click the trash icon in `Settings -> Features -> MCP`.

### Support & Feedback
- If you receive HTTP `401 Unauthorized`, your token has expired (3-day limit) or was revoked by the host. Contact the host to receive an updated token.
- If you receive HTTP `404 Not Found`, the temporary tunnel has been restarted and a new ephemeral URL has been generated. Ask the host for the current URL.
- Report any unexpected tool errors or reproduction inconsistencies to your Kawach host contact.
