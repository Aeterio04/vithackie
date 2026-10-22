# Autonomous AI QA Engineer — Run Report

**Run ID:** `20261018-020000-a1b2`
**Target URL:** `http://localhost:4000`
**Stage:** `done` (Execution Complete)

## Summary
- **Tests Planned & Approved:** 11
- **Passed:** 3
- **Assertion Failures:** 9
- **Test Errors:** 1
- **Confirmed Bugs (3/3 replays):** 8
- **Flaky Bugs (1-2/3 replays):** 1
- **Not Reproduced (0/3 replays):** 1

## Verified Defects Table

| Bug ID | Test ID | Severity | Category | Status | Summary |
| --- | --- | --- | --- | --- | --- |
| B01 | T02 | medium | validation | confirmed (3/3) | Signup accepts an invalid email |
| B02 | T03 | medium | validation | confirmed (3/3) | Signup accepts passwords shorter than 8 |
| B03 | T05 | high | auth | confirmed (3/3) | Wrong password shows no error message |
| B04 | T06 | high | auth | confirmed (3/3) | Login fails when email has capital letters |
| B05 | T08 | medium | validation | confirmed (3/3) | Dashboard accepts an empty item title |
| B06 | T09 | high | data | confirmed (3/3) | Delete removes first item instead of clicked |
| B07 | T11 | high | auth | confirmed (3/3) | After logout, Back shows cached dashboard |
| B08 | T10 | low | console | not_reproduced (0/3) | Settings page console TypeError |
| B09 | T10 | medium | network | flaky (2/3) | Every second settings save returns 500 |
| B10 | X02 | medium | other | confirmed (3/3) | Unhandled 500 on special character probe |

## Performance & Metrics
- **Wall Clock Time:** 84.2 s
- **Parallel Speedup:** 2.44x (4 workers vs 1 worker)
- **Spec Coverage:** 11/11 (100%)
- **LLM Cost:** $0.14
