# kawach-mcp

An MCP (Model Context Protocol) server for the KAWACH / Ordinous AI QA platform. It lets a coding agent in Antigravity run QA
on your app in plain English: validate a target, upload a spec, start a run, review the test plan, read **verified** bugs,
fix the code, and retest. It talks to the KAWACH FastAPI backend over HTTP and to Antigravity over stdio.

Everything the agent does happens under **your KAWACH account**: the same email and password you registered on the website, so
runs started from Antigravity show up on that account's dashboard.

## Install

```bash
cd mcp_server
python -m venv .venv
.venv/Scripts/pip install -e .[dev]        # Windows;  .venv/bin/pip install -e .[dev]  on macOS/Linux
```

Two equivalent ways to run it (Antigravity uses the first):

```bash
.venv/Scripts/python -m kawach_mcp          # stdio MCP server
.venv/Scripts/kawach-mcp                    # same, console script
.venv/Scripts/kawach-mcp --check            # health + login report, exits 0 (ready) or 1 (problem)
```

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `KAWACH_BASE_URL` | `http://localhost:8000` | Backend URL |
| `KAWACH_EMAIL` / `KAWACH_PASSWORD` | none | **Your website account.** The server logs in with them (JWT, kept in memory only) |
| `KAWACH_TOKEN` | none | Alternative: an API token (`kw_live_...`) or JWT. Skips login. API tokens need scopes `runs:read runs:write tests:read tests:write` |
| `KAWACH_TIMEOUT_SECONDS` | `30` | Per-request timeout |
| `KAWACH_DOWNLOAD_DIR` | `./kawach_downloads` | Where exports and artifacts are saved |
| `KAWACH_LOG_LEVEL` | `INFO` | Log level (logs go to **stderr** only) |

Copy `.env.example` to `.env` (git-ignored) for local use. There is no guest mode: the backend returns 401 without an account.

## Connect it to Antigravity

1. Register on the KAWACH website with your email (if you have not), and start the backend.
2. Generate the config for this machine: `.venv/Scripts/python scripts/gen_antigravity_config.py --email you@example.com`.
   It writes `antigravity_mcp_config.json` with this machine's absolute Python path (forward slashes so the JSON is valid on Windows).
3. In Antigravity open the Agent panel, click the `...` menu -> **MCP Servers** -> **Manage MCP Servers** -> **View raw config**.
   That button opens Antigravity's `mcp_config.json` (the file's location varies by version, so use the button instead of hunting for it).
4. Paste the `"kawach"` entry **inside** the existing `"mcpServers"` object. **If the file already lists other servers, merge:
   add `"kawach": {...}` next to them; do not replace the file.** Replace `<your-kawach-password>` with your password. Save.
5. Click **Refresh** in the MCP Servers panel and ask the agent: *"List the KAWACH tools."* Then try *"Check that the KAWACH backend is up and tell me
   which account you are using"* (it calls `health_check` and `whoami`).

The block looks like this (local stdio servers use `command` + `args`; `serverUrl` is only for remote servers, so it is not used):

```json
{
  "mcpServers": {
    "kawach": {
      "command": "D:/path/to/mcp_server/.venv/Scripts/python.exe",
      "args": ["-m", "kawach_mcp"],
      "env": {
        "KAWACH_BASE_URL": "http://localhost:8000",
        "KAWACH_EMAIL": "<your-kawach-email>",
        "KAWACH_PASSWORD": "<your-kawach-password>",
        "KAWACH_DOWNLOAD_DIR": "D:/path/to/mcp_server/kawach_downloads"
      }
    }
  }
}
```

## What it offers (58 tools, 5 prompts, 5 resources)

Full parameter tables: [`docs/TOOL_REFERENCE.md`](docs/TOOL_REFERENCE.md) (generated from the live server by `scripts/gen_tool_reference.py`).

**System and account**
`health_check` backend up? / `get_defaults` budgets and limits / `get_stats` your run counters / `check_target` is this URL allowed? /
`upload_spec` upload a local spec file / `whoami` which account am I acting as.

**Projects and credentials**
`list_projects`, `get_project`, `create_project` (runs the target safety check), `update_project`, `delete_project` (confirm) /
`get_project_credentials`, `set_project_credentials` (write-only, stored encrypted) / `get_project_overview` project + latest runs + saved tests.

**Saved tests and commits**
`list_saved_tests`, `save_test_to_project`, `run_saved_tests`, `delete_saved_test` (confirm) / `list_commits`, `list_github_commits`.

**Run control**
`list_runs`, `get_run`, `start_run`, `retry_run` (failed/cancelled only), `cancel_run` (confirm), `delete_run` (confirm) /
`resume_run` low-level override (prefer the review tools).

**Review gate** (manual mode, stage `awaiting_review`)
`get_catalog`, `get_test`, `update_test`, `add_test` (the planner writes the test from your description), `review_tests`
(rejections need a reason), `approve_all_and_resume`, `reject_tests`, `get_review_log`.

**Verified bugs**
`list_bugs` confirmed first, each with its `3/3 reproduced` evidence / `get_bug` full card with the 3-trial timeline / `download_artifact`.

**Live visibility**
`wait_for_run` (progress, never errors on timeout), `tail_run_stream`, `get_logs`, `get_events`, `get_execution`, `get_app_map`.

**Reports and exports**
`get_report`, `get_metrics` / `export_report_markdown`, `export_playwright_scripts` (zip, optional safe extract), `export_catalog` (JSON/CSV built from the API),
`export_run_archive` (the backend's export zip: the **passing tests as a Playwright project**, or the whole run folder if nothing passed), `read_run_file`.

**Workflow (one call = one useful answer)**
`get_run_summary` digest / `get_bug_fix_context` markdown fix brief / `save_repro_script` / `run_qa_pipeline` / `retest_after_fix` /
`compare_runs` fixed-new-persisting / `run_project_regression` rerun the saved tests.

**Prompts:** `qa_full_run`, `review_catalog`, `triage_and_fix`, `regression_check`, `explain_run`.

**Resources:** `kawach://projects`, `kawach://runs/{run_id}/report`, `/catalog`, `/bugs` (confirmed first), `/app-map`.

## How bugs are judged

A bug is **confirmed only when 3 of 3 deterministic replays reproduce it**. 1/3 and 2/3 are *flaky*, 0/3 is *not reproduced*.
The server re-derives this from the run's real verification record (`verification/<bug>.json`), not from the backend's label, because
the backend's bug API can show placeholder replays. A bug with no complete 3-replay record is reported as *unverified*. Summaries,
fix briefs and `compare_runs` count only confirmed bugs, and always show the flaky/unverified numbers next to them.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot reach the KAWACH backend` / `health_check` says `unreachable` | Start the backend, check `KAWACH_BASE_URL`, run `kawach-mcp --check` |
| `Authentication failed` | Wrong `KAWACH_EMAIL`/`KAWACH_PASSWORD`; register on the website first. 5 wrong attempts per minute lock the email for a minute (`Rate limited`) |
| `Not allowed` (403) with a token | Create the API token with scopes `runs:read runs:write tests:read tests:write`, or use email + password |
| `Not found (it may not exist or may belong to another account)` | The id is wrong or belongs to a different account than the one in `whoami` |
| Spec rejected / too large | `get_defaults` shows accepted extensions and the size limit (10 MB) |
| Tools do not appear in Antigravity | Open **View raw config**: JSON must be valid; `command` must be an absolute path to the venv's `python.exe`; click **Refresh**; run `kawach-mcp --check` in a terminal with the same env |
| Server "connects" then dies / garbled protocol | Something wrote to **stdout**. The server never does (tests enforce it); if you added code, use `logging` (stderr) |
| Windows paths | Use forward slashes (`D:/a/b`) or doubled backslashes (`D:\\a\\b`) in JSON; avoid unquoted spaces in terminal commands |
| `python` not found / wrong Python | Point `command` at `.venv/Scripts/python.exe` of the environment where you ran `pip install -e` |
| Long run, tool call times out | Not an error: `wait_for_run` and `run_qa_pipeline` return `still_running: true`; ask the agent to call `wait_for_run` again |
| `review_tests` refuses | The run must be at `awaiting_review`; a reject needs a reason; if anything would stay approved you must pass `resume=true` because this backend starts executing as soon as a test is approved |

## Security

* Credentials live only in the environment (the Antigravity config). They are never printed, logged, returned in results or written into errors; error text is scrubbed of the password and tokens.
* The JWT is kept in memory only and refreshed before it expires.
* Destructive tools (`delete_run`, `cancel_run`, `delete_project`, `delete_saved_test`) do nothing without `confirm=true`; the agent is told to ask you first.
* Files are only written under `KAWACH_DOWNLOAD_DIR` (sanitised names, no overwriting, zip-slip and size-bomb protection) or, for `save_repro_script`, inside the server's working directory.
* Only the configured backend host is contacted; redirects to other hosts are refused. Responses are size-capped.
* `antigravity_mcp_config.json` contains placeholders, never your password; keep your real password out of git (`.env` is ignored).

## Backend behaviours worth knowing

* Approving tests starts execution immediately; there is no separate resume step. Rejections are therefore sent first.
* In the stub/dev setup tested here, a **rejected test was still executed** and the audit log (`get_review_log`) only kept the last review call's decisions.
* The API cannot return a run's spec text or the app credentials, so `retest_after_fix` asks you for `spec_file_path` (or `allow_default_spec`) instead of guessing.
* The saved repro scripts import fixtures from the KAWACH runner (`apps/runner/fixtures`); adjust that import to your own Playwright setup.

## Development

```bash
.venv/Scripts/python -m pytest -q                       # mocked unit tests (respx)
.venv/Scripts/python scripts/smoke.py                   # live read-only smoke (needs a backend + KAWACH_EMAIL/PASSWORD)
.venv/Scripts/python scripts/e2e.py --register-throwaway  # live end-to-end scenarios A/B/C
.venv/Scripts/python scripts/protocol_proof.py          # spawn the server like Antigravity and show raw results
.venv/Scripts/python scripts/gen_tool_reference.py      # regenerate docs/TOOL_REFERENCE.md
```

See `ENDPOINTS.md` (the real backend routes) and `DECISIONS.md` (assumptions and findings).
