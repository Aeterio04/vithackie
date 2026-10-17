# QA Report: http://localhost:4000
**Run ID:** `sample-run` | **Mode:** `autonomous` | **Date:** `2026-10-18T02:00:00Z`
**Verdict:** 8 confirmed, 1 flaky, 1 not reproduced bugs

## Summary
- **Tests:** 13 executed | 3 passed | 9 assertion failures | 1 test errors
- **Wall-clock execution time:** 360.0s
- **Application map coverage:** 4/4 pages, 4/4 forms
- **Specification requirements covered:** 11 of 11 items
- **LLM usage:** 0 calls | 0 input tokens | 0 output tokens | $0.00

## Confirmed bugs
### B03 · high · auth: T05: Wrong password shows no error message
- **Replay:** reproduced 3 of 3.
- **Spec:** S5
- **Steps:**
  1. Navigate to /login
  2. Enter valid email
  3. Enter wrong password
  4. Click Log in
- **Expected:** Shows message "Invalid email or password"
- **Actual:** Page remains blank with no alert or message
```text
expect(received).toBeVisible()
Expected: visible alert
```

### B04 · high · auth: T06: Login fails when the email has capital letters
- **Replay:** reproduced 3 of 3.
- **Spec:** S6
- **Steps:**
  1. Navigate to /login
  2. Enter email with uppercase letters
  3. Enter correct password
  4. Submit
- **Expected:** Successful login lands on dashboard
- **Actual:** Login rejected with error
```text
expect(received).toHaveURL(expected)
```

### B06 · high · data: T09: Delete removes the first item instead of clicked one
- **Replay:** reproduced 3 of 3.
- **Spec:** S9
- **Steps:**
  1. Create two items
  2. Click Delete on second item
- **Expected:** Second item is deleted
- **Actual:** First item in the list is deleted instead
```text
expect(items.first()).toHaveText(expected)
```

### B07 · high · auth: T11: After logout, Back shows cached dashboard
- **Replay:** reproduced 3 of 3.
- **Spec:** S11
- **Steps:**
  1. Log in to dashboard
  2. Log out
  3. Press browser Back button
- **Expected:** Redirected to login or 401 unauthenticated
- **Actual:** Cached dashboard displays sensitive task data
```text
expect(received).toHaveURL(expected)
```

### B01 · medium · validation: T02: Signup accepts an invalid email
- **Replay:** reproduced 3 of 3.
- **Spec:** S2
- **Steps:**
  1. Navigate to /signup
  2. Enter invalid email 'not-an-email'
  3. Enter password
  4. Submit
- **Expected:** Rejected with message "Enter a valid email address"
- **Actual:** Account created and user redirected to dashboard
- **Evidence:** [screenshot](evidence/T02/screenshot.png) | [video](evidence/T02/video.webm) | [console](evidence/T02/console.json) | [network](evidence/T02/network.json) | [script](scripts/T02.spec.ts)
```text
expect(received).toHaveText(expected)
Expected: "Enter a valid email address"
```

### B02 · medium · validation: T03: Signup accepts passwords shorter than 8 characters
- **Replay:** reproduced 3 of 3.
- **Spec:** S3
- **Steps:**
  1. Navigate to /signup
  2. Enter valid email
  3. Enter 7-character password '1234567'
  4. Submit
- **Expected:** Rejected with message "Password must be at least 8 characters"
- **Actual:** Account created successfully
```text
expect(received).toHaveText(expected)
Expected: "Password must be at least 8 characters"
```

### B05 · medium · validation: T08: Dashboard accepts an empty item title
- **Replay:** reproduced 3 of 3.
- **Spec:** S8
- **Steps:**
  1. Open /dashboard
  2. Submit empty title form
- **Expected:** Rejected with message "Title is required"
- **Actual:** Empty item added to task list
```text
expect(received).toHaveText(expected)
Expected: "Title is required"
```

### B10 · medium · other: X02: Unhandled 500 Internal Server Error on special character input
- **Replay:** reproduced 3 of 3.
- **Spec:** S7
- **Steps:**
  1. Submit probe payload into dashboard search
- **Expected:** Handled with 400 or graceful validation error
- **Actual:** Server crashes with HTTP 500
- **Note:** Exploratory finding
```text
expect(response.status()).not.toBe(500)
```

## Flaky bugs
### B09 · medium · network: T10: Every second settings save fails with HTTP 500
- **Replay:** reproduced 2 of 3 replays.
- **Spec:** S10
- **Steps:**
  1. Open /settings
  2. Save display name consecutively
- **Expected:** Status 200 and 'Settings saved' every time
- **Actual:** Second save attempt returns HTTP 500

## Not reproduced
| Bug ID | Title | Test ID |
| --- | --- | --- |
| B08 | T10: The settings page throws an uncaught TypeError on load | T10 |

*These failed once but not on replay. Treat as unconfirmed.*

## Test results
| ID | Title | Spec Items | Outcome | Duration (s) |
| --- | --- | --- | --- | --- |
| T01 | T01: Signing up with valid credentials lands on dashboard | S1 | ✅ Passed | 1.20 |
| T02 | T02: Signing up with invalid email is rejected | S2 | ❌ Bug (Assertion Failure) | 0.95 |
| T03 | T03: Signing up with short password is rejected | S3 | ❌ Bug (Assertion Failure) | 0.85 |
| T04 | T04: Logging in with valid credentials lands on dashboard | S4 | ✅ Passed | 1.10 |
| T05 | T05: Logging in with wrong password shows error | S5 | ❌ Bug (Assertion Failure) | 0.90 |
| T06 | T06: Logging in email is case-insensitive | S6 | ❌ Bug (Assertion Failure) | 0.92 |
| T07 | T07: Adding item with non-empty title shows in list | S7 | ✅ Passed | 1.40 |
| T08 | T08: Adding item with empty title is rejected | S8 | ❌ Bug (Assertion Failure) | 0.88 |
| T09 | T09: Deleting an item removes only that item | S9 | ❌ Bug (Assertion Failure) | 1.30 |
| T10 | T10: Saving display name shows success and page has no errors | S10 | ❌ Bug (Assertion Failure) | 1.05 |
| T11 | T11: Logging out returns to login and Back does not show dashboard | S11 | ❌ Bug (Assertion Failure) | 1.60 |
| T12 | T12: External navigation test | exploratory | ⚠️ Test Error | 5.20 |
| X02 | X02: Exploratory SQL injection probe on search input | exploratory | ❌ Bug (Assertion Failure) | 0.78 |

### Test Errors
- **T12:** `page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:9999`

## Coverage
| Spec ID | Requirement | Tests | Result |
| --- | --- | --- | --- |
| S1 | Signing up with a valid email and a password of at least 8 characters creates th... | T01 | Covered & Passed |
| S2 | Signing up with an invalid email address (for example "not-an-email") is rejecte... | T02 | Bug Found |
| S3 | Signing up with a password shorter than 8 characters is rejected with the messag... | T03 | Bug Found |
| S4 | Logging in with a correct email and password lands the user on the dashboard. | T04 | Covered & Passed |
| S5 | Logging in with a wrong password shows the message "Invalid email or password" a... | T05 | Bug Found |
| S6 | Logging in is case-insensitive for the email address (QA.Tester@Example.com work... | T06 | Bug Found |
| S7 | On the dashboard, adding an item with a non-empty title shows that item in the l... | T07 | Bug Found |
| S8 | On the dashboard, adding an item with an empty title is rejected with the messag... | T08 | Bug Found |
| S9 | With several items in the list, clicking Delete on an item removes only that ite... | T09 | Bug Found |
| S10 | On the settings page, saving a display name shows "Settings saved" every time, a... | T10 | Bug Found |
| S11 | Logging out returns the user to the login page, and pressing the browser Back bu... | T11 | Bug Found |

## Timings
| Stage | Duration (s) |
| --- | --- |
| created | 5.0 |
| exploring | 85.0 |
| planning | 50.0 |
| awaiting_review | 25.0 |
| scripting | 60.0 |
| running | 45.0 |
| verifying | 70.0 |
| reporting | 20.0 |
| done | 0.0 |
| **Total (Wall Clock)** | **360.0** |

## Safety
No off-domain requests were attempted.

## Review log
| Test ID | Decision | Reason |
| --- | --- | --- |
| T01 | approve | Valid test verifying spec requirement S1 |
| T02 | approve | Valid test verifying spec requirement S2 |
| T03 | approve | Valid test verifying spec requirement S3 |
| T04 | approve | Valid test verifying spec requirement S4 |
| T05 | approve | Valid test verifying spec requirement S5 |
| T06 | approve | Valid test verifying spec requirement S6 |
| T07 | approve | Valid test verifying spec requirement S7 |
| T08 | approve | Valid test verifying spec requirement S8 |
| T09 | approve | Valid test verifying spec requirement S9 |
| T10 | approve | Valid test verifying spec requirement S10 |
| T11 | approve | Valid test verifying spec requirement S11 |

