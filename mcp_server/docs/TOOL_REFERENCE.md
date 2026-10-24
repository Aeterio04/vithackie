# kawach-qa tool reference

Generated from the live server schema by `scripts/gen_tool_reference.py` (kawach-mcp 0.1.0). 58 tools, 5 prompts, 5 resources. Do not edit by hand.

## Tools

### `add_test`

Ask the planner to add a custom test to the catalog (only while awaiting_review).

The backend generates the final test from a prompt, so your steps guide it rather than being copied
verbatim. Returns the generated test id. New tests start as proposed.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `title` | string | yes |  |  |
| `category` | string | yes |  | e.g. functional, security, validation, ui |
| `priority` | string | yes |  | critical, high, medium or low |
| `page_path` | string | yes |  | Page the test targets, e.g. /login |
| `steps` | list[object] | yes |  | At least 2 steps: [{"action": "...", "expected": "..."}] |
| `spec_ref` | string | no | `None` | Spec item this test covers, e.g. S3 |

### `approve_all_and_resume`

Approve every proposed test in one review call and let execution start (run must be awaiting_review).

Use when the user trusts the whole catalog. Rejected tests stay rejected. Returns
{ok, approved, already_approved, stage}. Next: wait_for_run.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `reason` | string | no | `'Approved via MCP'` | Audit reason recorded with the decision |

### `cancel_run`  (DESTRUCTIVE (needs confirm=true), idempotent)

Cancel an active run. Destructive: ask the user first, then call with confirm=true.

Without confirm=true nothing happens.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `confirm` | boolean | no | `False` | Must be true to actually cancel |

### `check_target`  (read-only, idempotent)

Check whether a target URL may be tested (SSRF/allow-list policy) before using it.

Use before create_project or start_run (both also run this check themselves). Returns
{allowed, reachable, host, status_code, reason, verdict}; verdict is one of "OK to test",
"Blocked by SSRF policy", "Unreachable, is the app running?", "Invalid target URL".

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `target_url` | string | yes |  | Full URL of the app to test, e.g. http://localhost:3000 |

### `compare_runs`  (read-only, idempotent)

Diff the verified bugs of two runs: which were fixed, which are new, which persist.

Bugs are matched by (test id, normalised title), falling back to title alone (noted in matching_note). ONLY
confirmed (3/3) bugs count toward fixed/new/persisting; flaky ones appear in still_flaky. Returns
{fixed, new, persisting, still_flaky, verdict, metrics_delta}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_a` | string | yes |  | Earlier run (before the fix) |
| `run_b` | string | yes |  | Later run (after the fix) |

### `create_project`

Create a project for a target app. Runs the target safety check first.

Blocks creation if the target is disallowed by the SSRF/allow-list policy; an unreachable app only
produces a warning. Returns {project, target_check, next_step_hint}. Next: set_project_credentials
if the app needs a login, then start_run(project_id=...).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | yes |  | Project name |
| `target_url` | string | yes |  | URL of the app under test, e.g. http://localhost:3000 |
| `description` | string | no | `None` | Short description |
| `default_mode` | string | no | `'manual'` | manual (human approves the catalog) or autonomous |
| `budgets` | object | no | `None` | Optional budgets, e.g. {"max_pages": 10, "max_steps_per_test": 30, "max_run_minutes": 15, "parallel_workers": 2}. Ranges come from get_defaults. |
| `github_url` | string | no | `None` | GitHub repo URL for commit/regression features |

### `delete_project`  (DESTRUCTIVE (needs confirm=true), idempotent)

Delete (archive) a project. Destructive: ask the user first, then call with confirm=true.

Without confirm=true nothing happens. Returns {ok, archived}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |
| `confirm` | boolean | no | `False` | Must be true to actually delete |

### `delete_run`  (DESTRUCTIVE (needs confirm=true), idempotent)

Permanently delete a run, including its artifacts, logs and evidence. Destructive: confirm first.

Without confirm=true nothing happens.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `confirm` | boolean | no | `False` | Must be true to actually delete |

### `delete_saved_test`  (DESTRUCTIVE (needs confirm=true), idempotent)

Remove a test from the project's regression library. Destructive: confirm with the user first.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |
| `test_id` | string | yes |  | Saved test id from list_saved_tests |
| `confirm` | boolean | no | `False` | Must be true to actually delete |

### `download_artifact`

Download an artifact (screenshot, video, trace, script) from the backend to the local download folder.

Saves under KAWACH_DOWNLOAD_DIR/artifacts/, never overwriting. Returns {path, size_bytes, content_type}.
Only the configured backend host is allowed.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `artifact_id_or_url` | string | yes |  | Artifact id, or a backend file URL/path from get_bug evidence |
| `filename` | string | no | `None` | Optional name to save as (sanitized) |

### `export_catalog`

Save the run's test catalog to disk as JSON or CSV and return the path.

Built from the catalog API (the backend has no catalog export route).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `format` | string | no | `'json'` | json or csv |

### `export_playwright_scripts`

Download the passing Playwright test scripts (a standalone project) as a zip, optionally extracting it.

Extraction is zip-slip safe, capped at 200 MB and never overwrites files. Returns {path, size_bytes}
plus {extracted_to, files} when extract_to is given.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `extract_to` | string | no | `None` | Optional sub-folder name under the download dir to extract into |

### `export_report_markdown`

Download the full markdown report (report.md) to KAWACH_DOWNLOAD_DIR/<run_id>/.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |

### `export_run_archive`

Download the run's export zip to KAWACH_DOWNLOAD_DIR/<run_id>/run_<id>.zip.

The backend's export route returns the passing tests as a runnable Playwright project, or the whole run
folder (secrets excluded) when no test passed. Returns {path, size_bytes, content_type}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |

### `get_app_map`  (read-only, idempotent)

Show what the explorer learned about the app: pages, forms, features.

Returns base URL, summary text, features, page count, total forms and the page list. Empty until the
exploring stage has produced a map.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `detail` | string | no | `'summary'` | summary (first 15 pages) or full (up to 40 pages with actions) |

### `get_bug`  (read-only, idempotent)

Get the full bug card: steps, expected vs actual, evidence links and the 3-replay verification timeline.

Pass run_id so the right run's bug is used. Evidence URLs are absolute (download with download_artifact). Never includes binary data. The Playwright
reproduction script is included up to 6,000 characters (a full copy can be saved with save_repro_script
in a later release). Next: fix the code, then retest.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `bug_id` | string | yes |  | Bug id from list_bugs |
| `run_id` | string | no | `None` | Run the bug belongs to. Strongly recommended: ids like B01 exist in every run |

### `get_bug_fix_context`  (read-only, idempotent)

Build a self-contained markdown FIX BRIEF for one bug so you can fix the code without more lookups.

Refuses bugs that are not confirmed (3/3 replays) unless allow_unconfirmed=True. The brief has the title,
severity and verification line, the page, spec ref, steps to reproduce, expected vs actual, error and console
output, the full Playwright repro script and fix guidance. Returns {bug_id, run_id, severity, status,
verification, page_path, brief}. Next: fix the code in this repository, save_repro_script, retest_after_fix.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `bug_id` | string | yes |  | Bug id from list_bugs, e.g. B01 |
| `allow_unconfirmed` | boolean | no | `False` | Allow a brief for a flaky/not-reproduced/unverified bug (marked with a warning) |

### `get_catalog`  (read-only, idempotent)

Show the test catalog the planner proposed for a run (works in any stage).

Returns compact tests {id, title, category, priority, status, specRef, pagePath, step_count}, plus
counts by status/priority and spec_coverage. Statuses: proposed (awaiting decision), approved, rejected.
Next: review_tests / approve_all_and_resume while the run is awaiting_review.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `status` | string | no | `None` | Only tests with this status: proposed, approved, rejected |
| `priority` | string | no | `None` | Only this priority: critical, high, medium, low |
| `category` | string | no | `None` | Only this category (the backend does not report categories yet) |
| `include_steps` | boolean | no | `False` | Include steps and expected results (first 25 tests only) |

### `get_defaults`  (read-only, idempotent)

Get the platform's default test budgets, allowed ranges and spec upload rules.

Use before creating a project or starting a run with custom budgets, or before upload_spec.
Returns {default_budgets, limits, accepted_spec_extensions, max_spec_file_size_mb, allowed_hosts}.

_No parameters._

### `get_events`  (read-only, idempotent)

Timeline of milestone events (stage changes, catalog ready, test results, completion, errors).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `limit` | integer | no | `50` |  |

### `get_execution`  (read-only, idempotent)

Snapshot of the workers and test queue right now: who runs what, test statuses, budget used.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |

### `get_logs`  (read-only, idempotent)

Read the run's pipeline log lines ("[source] message"), newest by default.

The backend returns the full log (last 500 lines kept), so paging happens here. Returns
{lines, total, showing}. Use after a failure to see why.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `limit` | integer | no | `50` |  |
| `offset` | integer | no | `0` | With tail=True: newest lines to skip; otherwise lines from the start |
| `level` | string | no | `None` | Only this level: info, warn, error, debug |
| `tail` | boolean | no | `True` | Show the newest lines (default) instead of the oldest |

### `get_metrics`  (read-only, idempotent)

Run metrics: wall clock, test totals, pass rate, bug funnel, coverage, LLM token usage and cost.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |

### `get_project`  (read-only, idempotent)

Get one project in full: URL, mode, budgets, GitHub link, saved test count.

Secrets are never returned (the GitHub token is shown masked only). Next: list_runs(project_id=...)
or start_run(project_id=...).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |

### `get_project_credentials`  (read-only, idempotent)

Check whether login credentials are stored for the project's target app. Never returns the password.

Returns {has_secret, username, updated_at}. updated_at is null because the backend does not report it.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |

### `get_project_overview`  (read-only, idempotent)

One-call summary of a project: details, its latest runs and saved-test health.

The backend has no overview route, so this combines get_project, the project's runs and its saved tests.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |

### `get_report`  (read-only, idempotent)

Read the run's markdown executive report (summary, bugs, coverage), truncated if long.

Only meaningful once the run has reached reporting/done. Returns {report, truncated}. For the whole
file call export_report_markdown. Next: list_bugs for evidence on each defect.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `max_chars` | integer | no | `12000` | Max characters of report text to return |

### `get_review_log`  (read-only, idempotent)

Show the audit trail of review decisions (who approved/rejected which test, and why).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |

### `get_run`  (read-only, idempotent)

Get the full state of one run: stage (with a plain-language meaning), progress, metrics, budgets.

Use it to follow a run or decide the next action. The backend reports progress as a percentage;
current_step is filled in best-effort from the live execution state.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |

### `get_run_summary`  (read-only, idempotent)

One-call digest of a run: stage, metrics, verified bug counts and the top confirmed bugs.

Use this instead of calling get_run, get_metrics and list_bugs separately. Bugs are counted confirmed ONLY
with 3/3 reproductions in the real verification record; flaky, not-reproduced and unverified candidates are
reported separately. Early in a run, metrics/bugs are zero with available=false. Returns
{run_id, target_url, stage, mode, progress, metrics, bugs{confirmed, flaky, not_reproduced, unverified},
top_confirmed_bugs (max 5, critical first), recommended_next_action, next_step_hint}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |

### `get_stats`  (read-only, idempotent)

Get platform-wide counters: total runs, confirmed bugs, flaky bugs, pending reviews.

Note: the backend computes these across all stored runs, not just this account's. For one run
use get_run. Returns {total_runs, confirmed_bugs, flaky_bugs, pending_reviews}.

_No parameters._

### `get_test`  (read-only, idempotent)

Get one catalog test with its full steps and expected result.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `test_id` | string | yes |  | Test id, e.g. T01 |

### `health_check`  (read-only, idempotent)

Check whether the KAWACH backend is up and how busy it is.

Use this first when anything seems wrong, or before starting a run. Returns
{status, workers_up, queue_depth, message, backend_url}. If the backend cannot be reached this
returns status "unreachable" instead of failing. Next: whoami, then list_projects.

_No parameters._

### `list_bugs`  (read-only, idempotent)

List defects found in a run, with the verification evidence next to each one.

A bug is CONFIRMED only when 3 of 3 replays reproduce it; 1/3 or 2/3 is FLAKY; 0/3 is NOT REPRODUCED.
The status is re-derived from the replays, never copied blindly. Rows are ordered confirmed, flaky,
not_reproduced. Returns {bugs, summary{confirmed, flaky, not_reproduced, total}, by_severity (confirmed
only), honesty_note}. summary.total excludes not_reproduced. Next: get_bug for the full card.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `status` | string | no | `None` | confirmed, flaky or not_reproduced |
| `severity` | string | no | `None` | critical, high, medium or low |

### `list_commits`  (read-only, idempotent)

List commit events recorded for a project (commits that triggered or could trigger regression runs).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |
| `limit` | integer | no | `20` |  |

### `list_github_commits`  (read-only, idempotent)

List recent commits from the project's linked GitHub repo (uses the stored GitHub link and token).

Returns {configured, message, commits}. configured=false means no valid GitHub URL is set; fix it with
update_project(github_url=...).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |

### `list_projects`  (read-only, idempotent)

List the projects (test targets) in this account.

Returns compact rows {id, name, target_url, default_mode, saved_test_count, last_run_status,
github_url}. Next: get_project for details, start_run(project_id=...) to test one, or create_project.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `limit` | integer | no | `50` | Max projects to return |

### `list_runs`  (read-only, idempotent)

List test runs, newest first, optionally for one project or stage.

Returns compact rows {run_id, target_url, stage, mode, created_at, progress_percent, metrics}.
Next: get_run for one run; use stage="awaiting_review" to find runs that need approval.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | no | `None` | Only runs of this project |
| `stage` | string | no | `None` | Only runs in this stage: created, exploring, planning, awaiting_review, scripting, running, verifying, reporting, done, failed, cancelled |
| `limit` | integer | no | `20` | Max runs to return |

### `list_saved_tests`  (read-only, idempotent)

List a project's saved regression tests (verified tests kept for re-running).

Returns rows {id, name, tags, last_result, origin_run_id, origin_test_id}. Next: run_saved_tests.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |
| `tag` | string | no | `None` | Only tests with this tag |
| `limit` | integer | no | `50` |  |

### `read_run_file`  (read-only, idempotent)

Read a generated text file from the run folder (report.md, bugs.json, app_map.json, ...).

The name must be a plain file name: no slashes, '..' or absolute paths. The backend refuses secrets.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `filename` | string | yes |  | Plain file name in the run folder, e.g. report.md, bugs.json, app_map.json |
| `max_chars` | integer | no | `8000` |  |

### `reject_tests`

Reject catalog tests in one review call, without starting the run (run must be awaiting_review).

Refuses if any other test is already approved, because the backend would then start executing
immediately; use review_tests with resume=True in that case.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `test_ids` | list[string] | yes |  | Tests to reject |
| `reason` | string | yes |  | Why they are rejected (required) |

### `resume_run`

Low-level: force a run in awaiting_review into scripting/execution WITHOUT recording any approvals.

Prefer review_tests or approve_all_and_resume: in this backend approving tests already starts execution, so
no separate resume is needed, and resume_run skips the audit trail. Only valid while awaiting_review.
Returns {run_id, stage, next_step_hint}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |

### `retest_after_fix`

Re-run QA against the same target after a fix and compare with the previous run.

Recovers target URL, project and page budget from the previous run. The spec text and app credentials cannot
be read back from the API, so if the previous run used a spec you must pass spec_file_path/spec_id (or
allow_default_spec=True); the tool says exactly what is missing and never guesses. If the new run is still going
it returns {still_running, new_run_id}; call wait_for_run then compare_runs. When done it includes the comparison.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `previous_run_id` | string | yes |  | The run whose bugs you just fixed |
| `review_mode` | string | no | `'autonomous'` | autonomous (default, no human step) or manual |
| `wait_seconds` | integer | no | `100` |  |
| `spec_file_path` | string | no | `None` | Spec to use again (the API cannot return the old run's spec) |
| `spec_id` | string | no | `None` | Id from upload_spec |
| `allow_default_spec` | boolean | no | `False` | Proceed without a spec even though the previous run used one (backend default spec) |
| `username` | string | no | `None` | App login username, if the app needs one |
| `password` | string | no | `None` | App login password, if the app needs one |

### `retry_run`

Retry a run that failed or was cancelled, re-running execution from its current artifacts.

Only meaningful for stage failed or cancelled; for other stages an explanatory error is returned.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |

### `review_tests`

Approve or reject catalog tests at the review gate (run must be awaiting_review).

Everything is validated before any call: known ids, no duplicates, reasons on rejects. IMPORTANT: the
backend starts executing as soon as at least one test is approved after a review call, so if the result
leaves any test approved you must pass resume=True to confirm. Tests already in the requested state are
reported as unchanged. Rejections are sent first, approvals last. Returns
{ok, decisions_count, approved, rejected, unchanged, stage}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `decisions` | list[object] | yes |  | [{"test_id": "T01", "decision": "approve"\|"reject", "reason": "..."}]; reason required for rejects |
| `resume` | boolean | no | `False` | Must be true to allow execution to start (backend auto-starts once any test is approved) |

### `run_project_regression`

Run a project's saved regression tests, wait, and return the same digest as get_run_summary plus failures.

Wraps POST /projects/{id}/saved-tests/run-all (see run_saved_tests). Save tests first with
save_test_to_project. Returns {run_id, stage, still_running, summary, failures[{test, error}]}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project whose saved regression tests should run |
| `wait_seconds` | integer | no | `100` |  |

### `run_qa_pipeline`

Run the whole QA flow in one call: health check, target check, optional spec upload, start, wait, summary.

Aborts with a clear message if the backend is unreachable or the target is not allowed. In manual mode it
stops at awaiting_review and says how many tests await review (approving them starts execution). If the run
is still going after wait_seconds it returns still_running=true: call wait_for_run, then get_run_summary.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `target_url` | string | no | `None` | App URL to test; optional if project_id is given |
| `project_id` | string | no | `None` | Project to run against |
| `spec_file_path` | string | no | `None` | Local spec file to upload first |
| `prompt` | string | no | `None` | Natural-language testing focus |
| `review_mode` | string | no | `'manual'` | manual (stops at awaiting_review) or autonomous |
| `budgets` | object | no | `None` | Optional budgets, see get_defaults |
| `username` | string | no | `None` | Login username for the app under test |
| `password` | string | no | `None` | Login password for the app under test |
| `wait_seconds` | integer | no | `100` | How long to wait before returning (max 600) |

### `run_saved_tests`

Re-run saved regression tests for a project (all of them, or one by test_id) as a background run.

Returns the backend's run info. Poll get_run / list_runs(project_id=...) to follow it.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |
| `test_id` | string | no | `None` | Run just this saved test; omit to run all |

### `save_repro_script`

Save a bug's full Playwright repro script into the workspace so it can guard against regressions.

Paths resolve against the server's working directory and must stay inside it. Never overwrites unless
overwrite=True (otherwise a numeric suffix is added). Returns {path, relative_path, size_bytes}. Next: run it
with `npx playwright test <path>`.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `bug_id` | string | yes |  | Bug id from list_bugs, e.g. B01 |
| `dest_dir` | string | no | `'tests/kawach'` | Folder inside the current working directory (default tests/kawach) |
| `filename` | string | no | `None` | File name; default <bug_id>-<slug>.spec.ts |
| `overwrite` | boolean | no | `False` | Replace an existing file with the same name |

### `save_test_to_project`

Save an executed test from a run into the project's permanent regression library.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |
| `run_id` | string | yes |  | Run the test came from |
| `test_id` | string | yes |  | Test case id inside that run, e.g. T01 |
| `name` | string | no | `None` |  |
| `tags` | list[string] | no | `None` |  |

### `set_project_credentials`  (idempotent)

Store login credentials for the app under test, encrypted at rest and write-only.

Note: the backend does not auto-apply stored credentials when a run starts; also pass username and
password to start_run for apps that need a login. Returns {ok, stored_encrypted, username}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |
| `username` | string | yes |  | Login username/email for the target app |
| `password` | string | yes |  | Login password for the target app (stored encrypted, write-only) |

### `start_run`

Start a QA run: the platform explores the app, plans tests, runs them and verifies bugs.

Needs target_url or project_id. Provide at most one of spec_id, spec_text, spec_file_path. If the app
needs a login pass username and password (stored project credentials are NOT applied by the backend).
The target is safety-checked first and the run is aborted if disallowed. Returns
{run_id, stage, mode, target_url, next_step_hint}. In manual mode the run stops at awaiting_review.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `target_url` | string | no | `None` | App URL to test; optional if project_id is given |
| `project_id` | string | no | `None` | Project to run against (uses its URL and default mode) |
| `review_mode` | string | no | `None` | manual (stop at awaiting_review for approval) or autonomous. Default: the project's mode, else manual |
| `prompt` | string | no | `None` | Natural-language focus for the testing, e.g. 'focus on checkout' |
| `spec_id` | string | no | `None` | Id from upload_spec |
| `spec_text` | string | no | `None` | Inline spec/requirements text |
| `spec_file_path` | string | no | `None` | Local spec file to upload first |
| `budgets` | object | no | `None` | Optional budgets, see get_defaults for ranges |
| `username` | string | no | `None` | Login username for the app under test |
| `password` | string | no | `None` | Login password for the app under test |

### `tail_run_stream`  (read-only, idempotent)

Listen to a run's live event stream for a few seconds and summarize what happened.

Bounded by time and event count, stops early at run.done, and always closes the connection. The
backend replays existing log history first, so use a larger max_events to reach live events.
Returns {logs, stage_changes, tests, budget, workers, run_done, events_seen}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `seconds` | integer | no | `10` | Max seconds to listen (hard max 30) |
| `max_events` | integer | no | `40` | Max events to collect (hard max 200) |

### `update_project`  (idempotent)

Partially update a project; only the fields you pass change. At least one field is required.

A new target_url goes through the same safety check as create_project. Returns the updated project.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes |  | Project id, from list_projects |
| `name` | string | no | `None` |  |
| `target_url` | string | no | `None` |  |
| `description` | string | no | `None` |  |
| `default_mode` | string | no | `None` | manual or autonomous |
| `budgets` | object | no | `None` | Optional budgets, e.g. {"max_pages": 10, "max_steps_per_test": 30, "max_run_minutes": 15, "parallel_workers": 2}. Ranges come from get_defaults. |
| `github_url` | string | no | `None` |  |

### `update_test`

Edit one catalog test: its priority, title, expected result, steps, or its review status.

Field edits use the catalog PATCH route. A status change goes through the review route (only valid in
awaiting_review); NOTE the backend starts executing as soon as any test is approved. Rejecting needs a
reason. At least one field is required. Returns the updated test.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `test_id` | string | yes |  | Test id, e.g. T01 |
| `status` | string | no | `None` | approved or rejected (proposed cannot be restored). Approving starts execution |
| `priority` | string | no | `None` | critical, high, medium or low |
| `title` | string | no | `None` |  |
| `description` | string | no | `None` | The expected result text |
| `steps` | list[string] | no | `None` | Replacement step list, plain-language strings |
| `reason` | string | no | `None` | Required when status=rejected |

### `upload_spec`

Upload a local spec/requirements file so a run can generate spec-driven tests.

Validates the file exists, has an accepted extension and is under the size limit, then uploads it.
Returns {spec_id, filename, items_count, preview}. Next: start_run with spec_id (or pass
spec_file_path to start_run directly). The backend keeps specs in memory only, so use the
spec_id soon and re-upload after a backend restart.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `file_path` | string | yes |  | Path to a local spec file (.md .txt .pdf .json .yaml .yml) |

### `wait_for_run`  (read-only, idempotent)

Wait (with live progress) until a run reaches a stage you care about, or the timeout passes.

Use after start_run or a review call instead of polling get_run. Never errors on timeout: it returns
still_running=true and you simply call it again (clients cap tool-call time). On awaiting_review it
returns catalog counts; on done a digest of metrics and bug counts; on failed the error text.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `run_id` | string | yes |  | Run id, from list_runs or start_run |
| `until_stages` | list[string] | no | `['awaiting_review', 'done', 'failed', 'cancelled']` | Return when the run reaches any of these stages |
| `timeout_seconds` | integer | no | `120` | Max seconds to wait (hard max 600) |
| `poll_seconds` | integer | no | `3` | Seconds between polls |

### `whoami`  (read-only, idempotent)

Show how this MCP server authenticates and who it is acting as. Never shows secrets.

Returns {auth_mode (token|login|guest), authenticated, email, user, backend_url, download_dir, note}.
`email` is the KAWACH account everything you do is stored under: it is the same account whose dashboard you
see on the website after signing in with that email.
Use it to debug "authentication failed" or to confirm which account owns the data you see.

_No parameters._

## Prompts

- **`explain_run`**(run_id): A short plain-language briefing of a run for a non-technical stakeholder.
- **`qa_full_run`**(target_url, spec_path, mode?): Run QA on an app end to end and explain the verified results.
- **`regression_check`**(previous_run_id): Re-run QA after changes and report what got fixed, what is new and what persists.
- **`review_catalog`**(run_id): Review a run's test plan and propose approvals/rejections for the user's go-ahead.
- **`triage_and_fix`**(run_id): Fix the confirmed bugs of a run in the user's code, save repro tests, then offer a retest.

## Resources

- `kawach://projects`: All projects in this account (compact).
- `kawach://runs/{run_id}/report`: Markdown executive report for a run.
- `kawach://runs/{run_id}/catalog`: Test catalog for a run, with steps.
- `kawach://runs/{run_id}/bugs`: Bugs for a run, confirmed first, each with its verification result.
- `kawach://runs/{run_id}/app-map`: Summary of the app map discovered during exploration.
