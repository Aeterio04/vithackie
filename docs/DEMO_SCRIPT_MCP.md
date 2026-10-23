# Kawach MCP Terminal Demo Walkthrough (`docs/DEMO_SCRIPT_MCP.md`)

This walkthrough demonstrates how an AI coding assistant (e.g. Cursor, Claude Code, Windsurf) or terminal developer interacts with the **Kawach MCP Server** (`apps/mcp`) to autonomously discover, triage, localize, and suggest fixes for web application regressions.

---

## Prerequisites & Setup

Ensure the demo environment is running:

```powershell
# 1. Target Web App (Runs on http://localhost:4000)
cd examples/target-app
npm start

# 2. Kawach Backend API (Runs on http://localhost:8000)
uvicorn app.main:app --port 8000

# 3. Kawach API Token
$env:KAWACH_API_URL = "http://localhost:8000"
$env:KAWACH_API_TOKEN = "kw_live_0123456789abcdef0123456789abcdef"
$env:KAWACH_ALLOW_WRITE_TOOLS = "true"
```

---

## Step 1: Health & Scope Introspection (`get_server_status`)

Before issuing commands, the IDE agent inspects the MCP connection and verifies its active scopes:

```json
// Tool Call: get_server_status {}
```

**MCP Response**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "backend_url": "http://localhost:8000",
  "latency_ms": 8.5,
  "authenticated": true,
  "active_scopes": [
    "projects:read",
    "projects:write",
    "runs:read",
    "runs:trigger",
    "analysis:read",
    "analysis:run",
    "tests:read",
    "tests:write"
  ]
}
```

---

## Step 2: Start an Autonomous QA Run (`start_run`)

The developer asks: *"Run autonomous QA testing on the current commit."*

```json
// Tool Call: start_run
{
  "project_id": "proj_demo_target_app",
  "commit_sha": "a1b2c3d4e5f678901234567890abcdef12345678",
  "branch": "main"
}
```

**MCP Response**:
```json
{
  "run_id": "run_01928374-demo",
  "project_id": "proj_demo_target_app",
  "status": "pending",
  "message": "Autonomous QA run started successfully."
}
```

---

## Step 3: Wait for Completion (`wait_for_run`)

The IDE agent invokes the bounded polling tool to monitor the run without flooding the context:

```json
// Tool Call: wait_for_run
{
  "run_id": "run_01928374-demo",
  "timeout_seconds": 120,
  "poll_interval_seconds": 3
}
```

**MCP Response**:
```json
{
  "run_id": "run_01928374-demo",
  "status": "completed",
  "tests_total": 8,
  "tests_passed": 7,
  "tests_failed": 1,
  "tests_flaky": 0,
  "duration_seconds": 24.3
}
```

---

## Step 4: Inspect Verified Failures (`list_failures`)

The agent lists the failures discovered during the run. Note how untrusted DOM text is automatically sandboxed:

```json
// Tool Call: list_failures
{
  "run_id": "run_01928374-demo"
}
```

**MCP Response**:
```json
{
  "run_id": "run_01928374-demo",
  "failures": [
    {
      "failure_id": "fail_checkout_coupon_discount",
      "test_name": "Checkout Flow: Apply 20% Promo Code",
      "error_type": "AssertionError",
      "error_message": "<untrusted_content>Expected cart total to be $80.00, but DOM showed $100.00</untrusted_content>",
      "verified": true,
      "reproduced": true
    }
  ]
}
```

---

## Step 5: Root-Cause & Code Localization (`get_failure_analysis`)

The agent dives into the failure to inspect suspect files and lines:

```json
// Tool Call: get_failure_analysis
{
  "failure_id": "fail_checkout_coupon_discount"
}
```

**MCP Response**:
```json
{
  "failure_id": "fail_checkout_coupon_discount",
  "root_cause": "The applyCoupon handler ignores the percentage discount rate and returns unadjusted order total.",
  "confidence": 0.95,
  "suspect_files": [
    {
      "path": "server.js",
      "line_range": [72, 85],
      "reason": "applyCoupon function calculates discountAmount but never subtracts it from subtotal before returning."
    }
  ],
  "repro_script": "<untrusted_content>import requests\n\ndef test_repro():\n    r = requests.post('http://localhost:4000/api/cart/apply-coupon', json={'code': 'SAVE20'})\n    assert r.json()['discount'] == 20\n</untrusted_content>"
}
```

---

## Step 6: Inspect Fix Suggestion (`get_fix_suggestion`)

The agent retrieves the suggested patch. The unified diff is wrapped in `<untrusted_content>`:

```json
// Tool Call: get_fix_suggestion
{
  "failure_id": "fail_checkout_coupon_discount"
}
```

**MCP Response**:
```json
{
  "failure_id": "fail_checkout_coupon_discount",
  "target_file": "server.js",
  "explanation": "Subtract discountAmount from orderTotal before returning cart response.",
  "diff": "<untrusted_content>--- a/server.js\n+++ b/server.js\n@@ -79,2 +79,2 @@\n-  const finalTotal = subtotal;\n+  const finalTotal = Math.max(0, subtotal - discountAmount);\n</untrusted_content>"
}
```

---

## Step 7: Two-Step Write Confirmation (`save_test`)

The developer decides to save the generated reproduction test to the permanent regression test suite.

### Step 7A: Confirmation Request (confirm=false)
```json
// Tool Call: save_test
{
  "project_id": "proj_demo_target_app",
  "name": "Regression: Cart Coupon Percentage Discount",
  "script_content": "test('applies percentage coupon', async ({ page }) => { ... });",
  "confirm": false
}
```

**MCP Response**:
```json
{
  "status": "confirmation_required",
  "message": "Action 'save_test' requires confirmation. Call again with confirm=true and confirmation_token.",
  "confirmation_token": "8f4a13c9e782b54d1938562140abde...",
  "expires_in_seconds": 300,
  "payload_summary": {
    "project_id": "proj_demo_target_app",
    "name": "Regression: Cart Coupon Percentage Discount"
  }
}
```

### Step 7B: Confirmed Execution (confirm=true)
The agent executes the mutation with the exact same payload and confirmation token:

```json
// Tool Call: save_test
{
  "project_id": "proj_demo_target_app",
  "name": "Regression: Cart Coupon Percentage Discount",
  "script_content": "test('applies percentage coupon', async ({ page }) => { ... });",
  "confirm": true,
  "confirmation_token": "8f4a13c9e782b54d1938562140abde..."
}
```

**MCP Response**:
```json
{
  "status": "success",
  "test_id": "saved_test_9921",
  "name": "Regression: Cart Coupon Percentage Discount",
  "message": "Test successfully persisted to permanent regression suite."
}
```

---

## Conclusion: The 3rd Front Door in Action

This session completes an entire QA lifecycle:
1. **Triggered** from IDE agent via JSON-RPC.
2. **Executed** by the Kawach backend agentic engine in real browsers.
3. **Triaged & Localized** directly to `server.js:72-85`.
4. **Patched & Verified** with cryptographically confirmed test persistence.
5. **Completely Sandboxed**: zero secret leaks, zero injection vulnerability.
