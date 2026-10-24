# Kawach GitHub Fix Pipeline (`kawach_fix`)

Autonomous LangGraph pipeline for the **KAWACH** automated QA framework.

When Playwright test suites encounter assertion defects or regression failures, this standalone module:
1. **Verifies defect determinism** in a pristine sandbox (rule out flakiness before querying APIs).
2. **Collects latest commit context** exclusively from `origin/main` on GitHub via REST APIs.
3. **Synthesizes exact search-and-replace repairs** using an LLM (with prompt-injection defense and in-memory validation).
4. **Opens an autonomous Pull Request** into `main` on a branch named `kawach/fix-<sha7>`.

---

## Architecture Overview

```
                                      [ Start ]
                                          │
                                          ▼
                               ┌─────────────────────┐
                               │    VerifierAgent    │
                               │  (Playwright Replay) │
                               └──────────┬──────────┘
                                          │
                        Failures < Min?   │   Failures >= Min?
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
         [ not_reproduced / flaky ]                     ┌─────────────────────┐
                   (Exit)                               │ GitHubCollectorNode │
                                                        │  (origin/main ONLY) │
                                                        └──────────┬──────────┘
                                                                   │
                                               No Editable Files?  │  Files Found?
                                         ┌─────────────────────────┴─────────────────────────┐
                                         ▼                                                   ▼
                                [ no_editable_changes ]                             ┌─────────────────────┐
                                       (Exit)                                       │     FixLLMAgent     │
                                                                                    │ (Exact Patch Search)│
                                                                                    └──────────┬──────────┘
                                                                                               │
                                                                        Validation Failed? /   │  Valid Patch?
                                                                         can_fix == false?     │
                                                                  ┌────────────────────────────┴───────────┐
                                                                  ▼                                        ▼
                                                       [ invalid_llm_output /                     ┌─────────────────────┐
                                                          fix_not_possible ]                      │     PRAgent Node    │
                                                               (Exit)                             │(Branch + PR to main)│
                                                                                                  └──────────┬──────────┘
                                                                                                             │
                                                                                      dry_run=True? /        │  PR Opened?
                                                                                       PR Exists?            │
                                                                               ┌─────────────────────────────┴──────┐
                                                                               ▼                                    ▼
                                                                     [ dry_run_ready / pr_exists ]             [ pr_opened ]
                                                                                (Exit)                            (Exit)
```

---

## Installation & Setup

Install the standalone package into Kawach's Python environment in editable mode:

```bash
pip install -e fix_pipeline
```

### Dependencies
- Python `>= 3.10`
- `pydantic >= 2.7.0`
- `langgraph >= 0.2.0`
- `httpx >= 0.25.0`
- `pytest >= 8.0.0` (for testing)

---

## Environment Variables

| Variable | Description |
|---|---|
| `GITHUB_PAT` | Fine-grained or classic GitHub Personal Access Token (can also be passed in `FixRequest`). |
| `GROQ_API_KEY` | (Optional) Groq API key for fast Llama-3.3-70B repair synthesis. |
| `GEMINI_API_KEY` | (Optional) Google Gemini API key (`gemini-2.5-flash`). |
| `KAWACH_FIX_RUNS_DIR` | (Optional) Path to persist execution artifacts (defaults to `./fix_runs`). |

---

## Required Fine-Grained GitHub PAT Scopes

When creating a Fine-Grained Personal Access Token in GitHub (**Settings > Developer settings > Personal access tokens > Fine-grained tokens**):

1. **Resource Owner**: Select your account or organization.
2. **Repository Access**: Select **Only select repositories** and pick the target repository.
3. **Repository Permissions**:
   - **Contents**: `Read and write` (to read `commits/main`, fetch file contents at commit ref, and commit patch updates to `kawach/fix-<sha7>`).
   - **Pull requests**: `Read and write` (to query existing PRs and open new PRs targeting `main`).
   - **Metadata**: `Read-only` (automatically assigned by GitHub).

*No other permissions or organizational administrative access are required.*

---

## Running Offline with Fakes (Zero Network & Zero Keys)

Every component adheres to clean Python Protocols (`ScriptRunner`, `GitHubClient`, `LLMClient`), allowing complete offline execution using in-memory fakes.

### Running Test Suite
Execute the 32 offline test cases:

```bash
pytest fix_pipeline/tests -v
```

All tests run in isolation with zero network requests and zero real API keys.

### Programmatic Offline Run
```python
from pathlib import Path
from kawach_fix import run_fix_pipeline, FixRequest, Deps
from tests.fakes import FakeRunner, FakeGitHub, FakeLLM

# 1. Instantiate in-memory test doubles
fake_runner = FakeRunner()
fake_github = FakeGitHub()
fake_llm = FakeLLM(responses=['{"can_fix": false, "confidence": 0.0, "root_cause": "demo", "explanation": "offline test", "edits": [], "pr_title": "", "pr_summary": ""}'])

# 2. Inject doubles into Deps container
deps = Deps(
    runner=fake_runner,
    github=fake_github,
    llm=fake_llm,
    runs_dir=Path("./test_runs"),
)

# 3. Execute
result = run_fix_pipeline(request, deps=deps)
print(result.status)  # "fix_not_possible"
```

---

## Sample `request.json`

```json
{
  "repo": "owner/example-repo",
  "github_pat": "github_pat_11AAAAAA0000000000000000000000000000000000000000000000000000000000",
  "base_branch": "main",
  "error": {
    "test_name": "T05: Item count increment on click",
    "failing_step": "Click button:has-text('Add')",
    "message": "Error: Timed out waiting for element text to equal 'Count: 1'. Received: 'Count: 0'",
    "console": [
      "[error] Counter failed to increment due to state mutation"
    ],
    "network": [
      "POST /api/items 200 OK"
    ]
  },
  "playwright_script": "import { test, expect } from '@playwright/test';\ntest('T05: Item count increment', async ({ page }) => {\n  await page.goto('/counter');\n  await page.click('button#add');\n  await expect(page.locator('#count')).toHaveText('Count: 1');\n});",
  "target_url": "http://localhost:4000",
  "playwright_project_dir": "./apps/runner",
  "options": {
    "verify_runs": 3,
    "min_failures": 2,
    "dry_run": false,
    "draft_pr": false,
    "max_files": 15,
    "max_file_bytes": 100000,
    "max_patch_chars": 20000,
    "run_timeout_sec": 30
  }
}
```

---

## CLI Usage

Run directly from the command line:

```bash
# Execute against a request JSON file
python -m kawach_fix run request.json

# Perform dry-run (verifies defect, computes patch, but performs 0 GitHub writes)
python -m kawach_fix run request.json --dry-run

# Override or provide PAT on the command line
python -m kawach_fix run request.json --pat "$GITHUB_PAT"
```

Exit Codes:
- `0`: Success (`pr_opened`, `pr_exists`, or `dry_run_ready`).
- `1`: Pipeline stopped with non-PR terminal status (`not_reproduced`, `flaky`, `no_editable_changes`, `fix_not_possible`, `invalid_llm_output`, `github_error`).
- `2`: Bad arguments or invalid JSON input file.

---

## How Kawach Will Call This

When the Kawach QA execution engine detects a verified assertion defect, the backend service can dispatch a background repair task to `kawach_fix`:

```python
import os
from pydantic import SecretStr
from kawach_fix import arun_fix_pipeline, FixRequest, ErrorReport, FixOptions

async def trigger_autonomous_repair(run_id: str, defect: Any, script_content: str, repo_url: str):
    """Example integration service function inside Kawach."""
    
    # 1. Map defect data into FixRequest
    request = FixRequest(
        repo=repo_url,  # "owner/repo" or "https://github.com/owner/repo"
        github_pat=SecretStr(os.environ["GITHUB_PAT"]),
        base_branch="main",
        error=ErrorReport(
            test_name=defect.test_name,
            failing_step=defect.step_action,
            message=defect.error_message,
            console=defect.console_logs or [],
            network=defect.network_logs or [],
        ),
        playwright_script=script_content,
        target_url="http://localhost:4000",
        playwright_project_dir="./apps/runner",
        options=FixOptions(
            verify_runs=3,
            min_failures=2,
            dry_run=False,
            draft_pr=False,
        ),
        run_id=run_id,
    )

    # 2. Invoke pipeline asynchronously
    result = await arun_fix_pipeline(request)

    # 3. Store result status and PR url on the Kawach run record
    if result.status == "pr_opened" and result.pull_request:
        print(f"Opened PR #{result.pull_request.number}: {result.pull_request.url}")
    elif result.status == "pr_exists" and result.pull_request:
        print(f"PR already exists: {result.pull_request.url}")
    else:
        print(f"Repair did not open PR. Status: {result.status}. Reason: {result.reason}")

    # Artifacts are automatically persisted to ./fix_runs/<run_id>/
    # (verification.json, commit_context.json, llm_request_redacted.json, llm_response.json, result.json)
```

---

## Security Guarantees
- **Secret Hygiene**: GitHub PAT and LLM keys are never serialized into `FixResult`, logged to stderr, or committed into artifact JSON files.
- **Subprocess Isolation**: Playwright test runs execute in a stripped environment containing only standard system paths and `BASE_URL`.
- **API-Only GitHub Access**: Uses GitHub REST API only (Contents API and Pulls API). No local `git clone` or credentialed remote URLs.
- **Untrusted Code Containment**: All repository code and test traces are enclosed in `<untrusted_data>` prompt guards. Edits are restricted strictly to the allowlist of files touched in the latest commit on `main`.
