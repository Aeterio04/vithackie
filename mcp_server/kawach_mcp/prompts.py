"""MCP prompts: ready-made, step-by-step instructions that name the KAWACH tools and where to stop and ask the user."""

from mcp.server.fastmcp import FastMCP

HONESTY = (
    "Bug honesty rule: a bug is CONFIRMED only when 3 of 3 replays reproduce it (list_bugs shows e.g. '3/3 reproduced'). "
    "Flaky (1/3 or 2/3), not-reproduced (0/3) and unverified candidates are NOT confirmed defects: always report them "
    "separately and never call them bugs you have proven."
)


def register_prompts(mcp: FastMCP) -> list[str]:
    @mcp.prompt(name="qa_full_run", description="Run QA on an app end to end and explain the verified results.")
    def qa_full_run(target_url: str, spec_path: str, mode: str = "manual") -> str:
        return f"""Run a full KAWACH QA pass on {target_url} using the spec at {spec_path} (review mode: {mode}).

1. Call health_check. If status is "unreachable", tell the user to start the KAWACH backend and stop.
2. Call check_target with {target_url}. If it is not allowed, report the verdict and stop.
3. Call upload_spec with {spec_path} (or let run_qa_pipeline upload it through spec_file_path). Report items_count.
4. Call run_qa_pipeline(target_url="{target_url}", spec_file_path="{spec_path}", review_mode="{mode}").
5. If the result says the run is at awaiting_review: call get_catalog and show the user the highlights (counts by priority, any
   spec refs without a test, any suspicious tests). STOP and ask the user whether to review in detail (review_catalog prompt),
   approve everything (approve_all_and_resume) or change something. Do not approve anything yourself without their answer.
6. If still_running is true, call wait_for_run(run_id) repeatedly until the stage is done, failed or cancelled.
7. Call get_run_summary(run_id) and explain the result in plain language.
8. {HONESTY} Say how many bugs are confirmed vs flaky.
9. Offer the next step: triage_and_fix(run_id) if there are confirmed bugs."""

    @mcp.prompt(name="review_catalog", description="Review a run's test plan and propose approvals/rejections for the user's go-ahead.")
    def review_catalog(run_id: str) -> str:
        return f"""Review the test catalog of run {run_id} (it must be at awaiting_review; use wait_for_run first if not).

1. Call get_catalog(run_id="{run_id}", include_steps=True).
2. For each test, judge it against its spec references: is the scenario meaningful, correct and not a duplicate of another test?
   Look for tests that are out of scope, redundant, or untestable. Also look for critical scenarios that are missing.
3. Write a PROPOSAL for the user: the tests you would approve, the tests you would reject (each with a short reason; duplicates and
   out-of-scope tests need a reason), and any test you would add (title, page, steps).
4. STOP. Show the proposal and wait for the user's go-ahead. Do not call any review tool before they answer.
5. After approval: call add_test for each missing scenario the user accepted (the backend's planner writes the final test from
   your description), then call review_tests with the rejections (each needs a reason) and the approvals, with resume=true.
   In this backend approving tests starts execution immediately, so there is no separate resume step afterwards. If everything
   should simply run, approve_all_and_resume does it in one call.
6. Call wait_for_run(run_id) and then get_run_summary(run_id). {HONESTY}"""

    @mcp.prompt(name="triage_and_fix", description="Fix the confirmed bugs of a run in the user's code, save repro tests, then offer a retest.")
    def triage_and_fix(run_id: str) -> str:
        return f"""Triage and fix the verified bugs of run {run_id} in THIS repository.

1. Call get_run_summary(run_id="{run_id}"). {HONESTY}
   Tell the user how many bugs are confirmed vs flaky; do not try to fix flaky or not-reproduced candidates unless the user asks.
2. For each confirmed bug, highest severity first, call get_bug_fix_context(run_id="{run_id}", bug_id=<id>).
3. Read the brief, locate the route/component in this codebase (search for the page path, form labels and button text from the
   steps) and fix the ROOT CAUSE in the application code, not the test. Keep each change small and explain it.
4. Call save_repro_script(run_id="{run_id}", bug_id=<id>) so the failing scenario is kept as a regression test. Note its import
   path may need adjusting to this project's Playwright setup.
5. Summarise what you changed: one line per bug (id, file, what was wrong, what you did).
6. STOP and ask the user before running anything again. Only if they agree, call retest_after_fix(previous_run_id="{run_id}") and
   then explain the compare_runs verdict (fixed / new / persisting)."""

    @mcp.prompt(name="regression_check", description="Re-run QA after changes and report what got fixed, what is new and what persists.")
    def regression_check(previous_run_id: str) -> str:
        return f"""Check for regressions against run {previous_run_id}.

1. Call retest_after_fix(previous_run_id="{previous_run_id}"). If it says the spec or credentials are missing, ask the user for
   spec_file_path (or approval to use the default spec) and any app login, then call it again.
2. If still_running is true, call wait_for_run(new_run_id) until done, then compare_runs("{previous_run_id}", new_run_id).
3. Report the verdict ("N fixed, N new, N persisting") and the metrics change. {HONESTY}
4. List everything that persists or is new, with severity, and the concrete next step for each (get_bug_fix_context)."""

    @mcp.prompt(name="explain_run", description="A short plain-language briefing of a run for a non-technical stakeholder.")
    def explain_run(run_id: str) -> str:
        return f"""Write a short briefing about run {run_id} for a non-technical stakeholder.

1. Call get_run_summary(run_id="{run_id}"), get_report(run_id="{run_id}") and get_app_map(run_id="{run_id}", detail="summary").
2. In plain language, no jargon: what application was tested and what it does (from the app map), how much was tested (tests,
   pass rate, spec coverage), and how long it took.
3. Findings: how many problems are CONFIRMED (proven in 3 of 3 repeat runs) and what they mean for users, most severe first.
   Mention separately any flaky candidates (intermittent, not proven). {HONESTY}
4. End with the recommended next step in one sentence."""

    return ["qa_full_run", "review_catalog", "triage_and_fix", "regression_check", "explain_run"]
