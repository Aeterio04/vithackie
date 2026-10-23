# Kawach MCP Reference Catalog (`docs/MCP_USAGE.md`)

This document is the complete reference catalog for the **Kawach Model Context Protocol (MCP) Server** (`apps/mcp`). It provides detailed specifications for all 23 tools, 5 resource templates, and 4 workflow prompts, including required OAuth scopes, input schemas, return types, error codes, and injection defense wrapping.

---

## Tool Categories & Execution Policies

Kawach MCP tools are partitioned into three distinct tiers:

1. **Read Tools (15 tools)**:
   - Purely observational and read-only.
   - Always enabled (subject to the granted scopes on the API token).
   - Wrap untrusted backend text (DOM snippets, user inputs, stack traces, assertion messages, diffs) in `<untrusted_content>` tags.
2. **Action Tools (4 tools)**:
   - Initiate background tasks, execution runs, bounded polling, or cancellations.
   - Idempotency-enabled with automatic UUID key generation.
   - Require specific execution scopes (e.g. `runs:trigger`, `analysis:run`).
3. **Write Tools (3 tools)**:
   - Perform state mutations or external PR generation (`save_test`, `apply_fix_as_pr`, `delete_project`).
   - Hidden by default unless `KAWACH_ALLOW_WRITE_TOOLS=true`.
   - **Enforce a Two-Step Confirmation Engine**: The first invocation returns a human-readable preview and a cryptographically bound SHA-256 `confirmation_token` (valid for 5 minutes). The second invocation requires passing `confirm=true` and the exact `confirmation_token`. Any payload tampering causes immediate rejection.

---

## Complete Tools Catalog

### Tier 1: Read Tools (15)

#### 1. `list_projects`
- **Scope Required**: `projects:read`
- **Description**: List all registered projects accessible to the authenticated tenant.
- **Arguments**:
  - `page` (integer, optional, default: `1`): Page number (>= 1).
  - `page_size` (integer, optional, default: `20`): Page size (1..100).
- **Return Shape**:
  ```json
  {
    "items": [
      {
        "id": "proj_123",
        "name": "Target App",
        "repo_url": "https://github.com/org/repo",
        "base_url": "http://localhost:4000",
        "created_at": "2026-10-23T12:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
  ```

#### 2. `get_project`
- **Scope Required**: `projects:read`
- **Description**: Fetch detailed metadata, statistics, and settings for a project.
- **Arguments**:
  - `project_id` (string, required): Unique identifier of the project.
- **Return Shape**: Single project record.

#### 3. `get_app_map`
- **Scope Required**: `projects:read`
- **Description**: Retrieve the crawled application surface map (routes, interactive elements, forms).
- **Arguments**:
  - `project_id` (string, required): Project identifier.
  - `summary_only` (boolean, optional, default: `true`): If `true`, returns route counts and state statistics; if `false`, returns full element graph.
- **Return Shape**:
  ```json
  {
    "project_id": "proj_123",
    "route_count": 8,
    "routes": ["/", "/login", "/products", "/checkout"],
    "total_elements": 42,
    "form_count": 3
  }
  ```

#### 4. `list_runs`
- **Scope Required**: `runs:read`
- **Description**: List test and crawl execution runs for a project with optional status filtering.
- **Arguments**:
  - `project_id` (string, required): Project identifier.
  - `status` (string, optional): Filter by status (`pending`, `running`, `completed`, `failed`).
  - `page` (integer, optional, default: `1`): Page number.
  - `page_size` (integer, optional, default: `20`): Page size.
- **Return Shape**: Paginated list of execution run summaries.

#### 5. `get_run`
- **Scope Required**: `runs:read`
- **Description**: Fetch real-time status, test counts (passed, failed, flaky), and timings of an execution run.
- **Arguments**:
  - `run_id` (string, required): Unique run ID.
- **Return Shape**:
  ```json
  {
    "id": "run_abc",
    "project_id": "proj_123",
    "status": "completed",
    "started_at": "2026-10-23T12:00:00Z",
    "completed_at": "2026-10-23T12:02:15Z",
    "tests_total": 12,
    "tests_passed": 10,
    "tests_failed": 2,
    "tests_flaky": 0
  }
  ```

#### 6. `list_test_cases`
- **Scope Required**: `tests:read`
- **Description**: List test cases generated or executed within a project or run.
- **Arguments**:
  - `project_id` (string, required): Project identifier.
  - `run_id` (string, optional): Filter test cases by execution run.
  - `page` (integer, optional, default: `1`): Page number.
  - `page_size` (integer, optional, default: `20`): Page size.

#### 7. `get_test_case`
- **Scope Required**: `tests:read`
- **Description**: Fetch individual test case specification, assertions, and target routes.
- **Arguments**:
  - `test_case_id` (string, required): Test case identifier.

#### 8. `list_failures`
- **Scope Required**: `analysis:read`
- **Description**: List verified bugs and test failures for a run. Assertion messages and trace snippets are sandboxed.
- **Arguments**:
  - `run_id` (string, required): Execution run identifier.
- **Return Shape**:
  ```json
  {
    "failures": [
      {
        "id": "fail_123",
        "test_name": "test_checkout_discount_code",
        "error_type": "AssertionError",
        "error_message": "<untrusted_content>Expected $45.00 but got $50.00</untrusted_content>",
        "verified": true,
        "is_flaky": false
      }
    ]
  }
  ```

#### 9. `get_failure_analysis`
- **Scope Required**: `analysis:read`
- **Description**: Fetch root-cause analysis, confidence score, suspect files with repo-relative paths and line ranges.
- **Arguments**:
  - `failure_id` (string, required): Failure identifier.
- **Return Shape**:
  ```json
  {
    "failure_id": "fail_123",
    "root_cause": "Discount calculation omitted percentage coupon deduction.",
    "confidence": 0.94,
    "suspect_files": [
      {
        "path": "server.js",
        "line_range": [84, 98],
        "reason": "applyDiscount function returns original total when coupon is percentage"
      }
    ],
    "repro_script": "<untrusted_content>import requests\nres = requests.post(...)...</untrusted_content>"
  }
  ```

#### 10. `get_fix_suggestion`
- **Scope Required**: `analysis:read`
- **Description**: Fetch the AI-generated code fix for a failure. Unified diff is sandboxed.
- **Arguments**:
  - `failure_id` (string, required): Failure identifier.
- **Return Shape**:
  ```json
  {
    "failure_id": "fail_123",
    "explanation": "Correct the percentage calculation in applyDiscount to subtract discount amount.",
    "target_file": "server.js",
    "diff": "<untrusted_content>--- a/server.js\n+++ b/server.js\n@@ -88,3 +88,3 @@\n- return total;\n+ return total - (total * rate / 100);</untrusted_content>"
  }
  ```

#### 11. `get_regression_report`
- **Scope Required**: `analysis:read`
- **Description**: Fetch the regression analysis report for a specific commit SHA.
- **Arguments**:
  - `project_id` (string, required): Project identifier.
  - `commit_sha` (string, required): 40-character Git commit hash.

#### 12. `list_saved_tests`
- **Scope Required**: `tests:read`
- **Description**: List saved regression suite tests promoted from successful runs.
- **Arguments**:
  - `project_id` (string, required): Project identifier.

#### 13. `get_saved_test`
- **Scope Required**: `tests:read`
- **Description**: Fetch executable Playwright test script for a saved test.
- **Arguments**:
  - `test_id` (string, required): Saved test identifier.

#### 14. `list_flaky_tests`
- **Scope Required**: `analysis:read`
- **Description**: List test cases flagged as flaky across recent runs, with flip rate and pass/fail distribution.
- **Arguments**:
  - `project_id` (string, required): Project identifier.

#### 15. `get_server_status`
- **Scope Required**: None (public health and scope introspection)
- **Description**: Inspect MCP server version, backend connectivity, latency, and active token scopes.
- **Arguments**: None.
- **Return Shape**:
  ```json
  {
    "status": "healthy",
    "version": "0.1.0",
    "backend_url": "http://localhost:8000",
    "latency_ms": 12.4,
    "authenticated": true,
    "active_scopes": ["projects:read", "runs:read", "runs:trigger", "analysis:read", "tests:read"]
  }
  ```

---

### Tier 2: Action Tools (4)

#### 16. `start_run`
- **Scope Required**: `runs:trigger`
- **Description**: Start an autonomous QA test run against a project.
- **Arguments**:
  - `project_id` (string, required): Target project ID.
  - `commit_sha` (string, optional): Git commit hash to associate with the run.
  - `branch` (string, optional, default: `"main"`): Git branch.
  - `idempotency_key` (string, optional): Unique UUID for safe retries.

#### 17. `wait_for_run`
- **Scope Required**: `runs:read`
- **Description**: Bounded polling helper that waits for an execution run to reach terminal status (`completed`, `failed`).
- **Arguments**:
  - `run_id` (string, required): Run identifier.
  - `timeout_seconds` (integer, optional, default: `120`, max: `600`): Maximum seconds to poll.
  - `poll_interval_seconds` (integer, optional, default: `3`): Polling interval.
- **Return Shape**: Final run status object when terminal state is reached, or intermediate state if timed out.

#### 18. `run_regression`
- **Scope Required**: `runs:trigger`
- **Description**: Trigger regression tests specifically focused on changes introduced in a commit.
- **Arguments**:
  - `project_id` (string, required): Project identifier.
  - `commit_sha` (string, required): Git commit SHA to analyze and test.

#### 19. `stop_run`
- **Scope Required**: `runs:trigger`
- **Description**: Cancel an in-progress execution run.
- **Arguments**:
  - `run_id` (string, required): Run identifier.

---

### Tier 3: Write Tools with Two-Step Confirmation (3)

All write tools require:
1. `KAWACH_ALLOW_WRITE_TOOLS=true` environment setting.
2. Two-step confirmation handshake.

#### Protocol:
1. **Step 1 (Preview)**:
   Invoke tool with desired payload parameters and `confirm=false` (or omit).
   The server responds with:
   ```json
   {
     "status": "confirmation_required",
     "message": "Action 'save_test' requires confirmation. Call again with confirm=true and confirmation_token.",
     "confirmation_token": "a4f89b...",
     "expires_in_seconds": 300,
     "payload_summary": { ... }
   }
   ```
2. **Step 2 (Execution)**:
   Invoke tool with the **exact same payload**, `confirm=true`, and `confirmation_token="a4f89b..."`.
   If parameters differ or token is expired (> 300s), call fails with `400 Bad Request`.

#### 20. `save_test`
- **Scope Required**: `tests:write`
- **Arguments**:
  - `project_id` (string, required): Project identifier.
  - `name` (string, required): Name of the test.
  - `script_content` (string, required): Playwright test script.
  - `confirm` (boolean, optional, default: `false`): Confirmation flag.
  - `confirmation_token` (string, optional): SHA-256 confirmation token from Step 1.

#### 21. `apply_fix_as_pr`
- **Scope Required**: `analysis:run`
- **Arguments**:
  - `failure_id` (string, required): Failure identifier with approved fix.
  - `branch_name` (string, optional, default: `"kawach/fix-<failure_id>"`): Target branch name.
  - `pr_title` (string, optional): GitHub Pull Request title.
  - `confirm` (boolean, optional, default: `false`): Confirmation flag.
  - `confirmation_token` (string, optional): SHA-256 confirmation token from Step 1.

#### 22. `delete_project`
- **Scope Required**: `projects:write`
- **Arguments**:
  - `project_id` (string, required): Project identifier to delete.
  - `confirm` (boolean, optional, default: `false`): Confirmation flag.
  - `confirmation_token` (string, optional): SHA-256 confirmation token from Step 1.

---

## Resource URI Templates (5)

Clients can read live Kawach data via standard MCP resource templates:

| URI Pattern | MIME Type | Description |
|---|---|---|
| `kawach://projects/{project_id}/runs/{run_id}/report` | `text/markdown` | Formatted summary of a completed run with pass/fail counts and failures. |
| `kawach://projects/{project_id}/failures/{failure_id}/repro.py` | `text/x-python` | Standalone Python repro script to trigger the bug locally. Wrapped in sandboxing. |
| `kawach://projects/{project_id}/commits/{commit_sha}/analysis` | `text/markdown` | Commit diff summary, affected components, and regression risk level. |
| `kawach://projects/{project_id}/app-map` | `application/json` | Discovered routes, input fields, buttons, and API dependencies. |
| `kawach://projects/{project_id}/saved-tests/{test_id}/test.py` | `text/x-python` | Playwright test script ready to execute in local browser. |

---

## Workflow Prompts (4)

Prompts provide structured, role-based workflows for developer agents:

### 1. `triage-failing-commit`
- **Arguments**: `project_id` (required), `commit_sha` (required).
- **Behavior**: Retrieves commit analysis, finds all related failures, inspects suspect files, and presents a prioritized checklist for the developer.

### 2. `explain-bug`
- **Arguments**: `failure_id` (required).
- **Behavior**: Retrieves failure analysis, root cause, confidence score, and repro script. Guides the IDE agent to explain the bug in plain English and formulate a fix strategy.

### 3. `review-fix-before-apply`
- **Arguments**: `failure_id` (required).
- **Behavior**: Retrieves the AI-generated unified diff, highlights affected lines, warns about potential side effects or test regressions, and requests explicit user confirmation before applying.

### 4. `explore-app-surface`
- **Arguments**: `project_id` (required).
- **Behavior**: Inspects the crawled app map and identifies untested endpoints, unsubmitted forms, and routes needing QA coverage.

---

## Standard Error Mapping

| HTTP Code | MCP Error Mapping | Developer Explanation |
|---|---|---|
| `401` | `AuthenticationError` | Token invalid, missing, or expired. Check `KAWACH_API_TOKEN`. |
| `403` | `PermissionDeniedError` | Token lacks the required OAuth scope for this tool. |
| `404` | `NotFoundError` | Entity does not exist, or belongs to a different project (cross-project isolation). |
| `409` | `ConflictError` | State conflict (e.g. run already in progress, duplicate name). |
| `422` | `ValidationError` | Request arguments failed Pydantic validation (e.g. invalid SHA format). |
| `429` | `RateLimitError` | Rate limit exceeded. Server automatically retries with backoff. |
| `5xx` | `BackendUnavailableError`| Backend service error or network unreachable. |
