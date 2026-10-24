# KAWACH + Antigravity demo (3 to 4 minutes)

**Before you start (2 minutes, off stage):** backend running (`http://localhost:8000`), the example app running
(`cd examples/target-app && npm start`, port 4000), you registered on the website, the MCP block is pasted into Antigravity with the
same email/password, and the website is open on **Projects** in a second window. Open the demo app's code folder
(`examples/target-app`) as the Antigravity workspace so the agent can edit it.

Replace `SPEC` below with the absolute path of `examples/target-app/spec.md`.

| # | Time | Type into the Antigravity chat | Tools the agent should call | What the audience sees |
|---|---|---|---|---|
| 1 | 0:00 | *"Check that KAWACH is up, which account you are using, and list my projects."* | `health_check`, `whoami`, `list_projects` | Backend `active`, **your email** (the same one on the website), the project list that matches the website |
| 2 | 0:25 | *"Run QA on http://localhost:4000 with the spec at SPEC in manual review mode. Create a project first if I do not have one."* (or use the `qa_full_run` prompt) | `check_target`, `create_project`, `run_qa_pipeline` (manual) | Progress messages (exploring, planning). It stops at **awaiting_review** and says how many tests await review. Refresh the website: the run is there |
| 3 | 1:00 | *"Review the plan before anything runs. Reject duplicates or anything out of scope, tell me why, and wait for my OK."* (the `review_catalog` prompt) | `get_catalog(include_steps=True)` | A proposal: tests to approve, tests to reject with reasons, missing scenarios. The agent **waits** |
| 4 | 1:30 | *"Looks good. Reject the one you flagged, approve the rest, and run it."* | `review_tests` (rejection with reason), `approve_all_and_resume`, `wait_for_run` | Approving starts execution (no separate resume step). Live stage updates, run goes to `done` in well under a minute on the sample app |
| 5 | 2:00 | *"Summarise the run. How many bugs are really confirmed?"* | `get_run_summary`, `list_bugs` | **Confirmed: 8, flaky: 1, not reproduced: 1**, each confirmed bug marked `3/3 reproduced`, flaky ones explicitly NOT counted. Point at the website's Results page showing the same |
| 6 | 2:25 | *"Show me the evidence for the most severe bug."* | `get_bug` (with the run id) | The 3-trial timeline (`Trial 1: reproduced (failed) 420ms`, ...), steps, expected vs actual, evidence links |
| 7 | 2:50 | *"Fix that bug in this codebase, save the repro test, and show me what you changed."* (the `triage_and_fix` prompt) | `get_bug_fix_context`, (edits files), `save_repro_script` | The agent reads the fix brief, finds the route in `server.js`, edits it, writes `tests/kawach/B0x-....spec.ts`. It **asks before** retesting |
| 8 | 3:20 | *"Yes, retest."* | `retest_after_fix`, `compare_runs` | New run, then **"N fixed, 0 new, M persisting"** and the pass-rate change. Website: two runs side by side |

Tips: say "run id" explicitly if the agent drifts. Step 7 fixes one bug, so expect `1 fixed, 0 new, 7 persisting`: that is the honest result and a good point to make.

## Short on time: autonomous fallback (about 90 seconds)

*"Run a full autonomous QA on http://localhost:4000 with the spec at SPEC, then summarise it and explain the confirmed bugs in plain language."*
Tools: `run_qa_pipeline` (autonomous, no review gate), `wait_for_run`, `get_run_summary`, `explain_run`. The sample app finishes in about 10 seconds.
If you have time for one more beat: *"Fix the highest severity bug and retest"* (steps 7 and 8).

## What if something goes wrong

| Symptom | Likely cause | Quick fix |
|---|---|---|
| Agent says `unreachable` | Backend not running | Start it, then *"try again"* (the server needs no restart) |
| `Authentication failed` | Wrong password in the MCP config, or too many tries (locked for 1 minute) | Fix the config, click **Refresh**, wait a minute if rate limited |
| `Target not allowed` | URL not in the backend's allowed hosts | Use `http://localhost:4000`, or add the host to `ALLOWED_HOSTS` |
| Run stays `still_running` | Slow machine or a long run | *"Keep waiting"* (calls `wait_for_run` again); it never errors on timeout |
| Agent tries to review a finished run | Gate only opens at `awaiting_review` | Ask for `get_run_summary` instead, or start a new manual run |
| Agent has no confirmed bugs to fix | Fixed already, or the run found only flaky candidates | Say so honestly: flaky candidates are not proven bugs |
| `retest_after_fix` asks for the spec | The API cannot return the old spec | Give it `spec_file_path` (SPEC) |
| Tools missing in Antigravity | Bad JSON or wrong Python path | **View raw config**, fix, **Refresh**; run `kawach-mcp --check` in a terminal |
| Saved repro test will not run in your repo | It imports the KAWACH runner fixtures | Adjust the import (the tool's `note` says so) |
