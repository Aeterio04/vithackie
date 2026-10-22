"""Generate consistent, valid contract sample files for contracts/samples."""

import base64
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import (
    AppMap,
    AppMapStats,
    Benchmark,
    BenchmarkMatch,
    Bug,
    BugReplay,
    BugsFile,
    Budgets,
    ButtonInfo,
    Catalog,
    Evidence,
    Feature,
    FieldInfo,
    FormInfo,
    HeadingInfo,
    LinkInfo,
    LlmUsage,
    LoginInfo,
    Metrics,
    MetricsBugs,
    MetricsCoverage,
    MetricsSafety,
    MetricsTests,
    PageInfo,
    ParallelTiming,
    Progress,
    Results,
    ResultsSummary,
    ReviewDecision,
    ReviewLog,
    Run,
    RunInput,
    RunListItem,
    RunListItemCounts,
    RunView,
    SpecItem,
    StageTime,
    Step,
    TestCase,
    TestResult,
    Verification,
    VerificationAttempt,
)

SAMPLES_DIR = REPO_ROOT / "packages" / "contracts" / "samples"
FILES_DIR = SAMPLES_DIR / "files"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(parents=True, exist_ok=True)

RUN_ID = "20261018-020000-a1b2"

SPEC_ITEMS = [
    SpecItem(id="S1", text="Signing up with a valid email and a password of at least 8 characters creates the account and lands the user on the dashboard."),
    SpecItem(id="S2", text='Signing up with an invalid email address (for example "not-an-email") is rejected with the message "Enter a valid email address".'),
    SpecItem(id="S3", text='Signing up with a password shorter than 8 characters is rejected with the message "Password must be at least 8 characters".'),
    SpecItem(id="S4", text="Logging in with a correct email and password lands the user on the dashboard."),
    SpecItem(id="S5", text='Logging in with a wrong password shows the message "Invalid email or password" and the user stays on the login page.'),
    SpecItem(id="S6", text="Logging in is case-insensitive for the email address (QA.Tester@Example.com works the same as qa.tester@example.com)."),
    SpecItem(id="S7", text="On the dashboard, adding an item with a non-empty title shows that item in the list."),
    SpecItem(id="S8", text='On the dashboard, adding an item with an empty title is rejected with the message "Title is required" and no item is added.'),
    SpecItem(id="S9", text="With several items in the list, clicking Delete on an item removes only that item."),
    SpecItem(id="S10", text='On the settings page, saving a display name shows "Settings saved" every time, and the page loads without console errors.'),
    SpecItem(id="S11", text="Logging out returns the user to the login page, and pressing the browser Back button afterwards does not show the dashboard."),
]

BASE_INPUT = RunInput(
    runId=RUN_ID,
    createdAt="2026-10-18T02:00:00Z",
    targetUrl="http://localhost:4000",
    prompt="TaskBoard is a collaboration to-do app with auth, items list, and profile settings.",
    specRaw="\n".join(f"{s.id}: {s.text}" for s in SPEC_ITEMS),
    spec=SPEC_ITEMS,
    username="qa.tester@example.com",
    mode="autonomous",
    budgets=Budgets(maxPages=10, exploreSeconds=90, maxTests=12, testTimeoutMs=30000),
)

APP_MAP = AppMap(
    baseUrl="http://localhost:4000",
    generatedAt="2026-10-18T02:01:30Z",
    login=LoginInfo(attempted=True, success=True, url="http://localhost:4000/login", note="Authenticated as qa.tester@example.com"),
    pages=[
        PageInfo(
            url="http://localhost:4000/login",
            path="/login",
            title="Log in - TaskBoard",
            status=200,
            requiresAuth=False,
            headings=[HeadingInfo(level=1, text="Log in")],
            links=[LinkInfo(text="Sign up", href="/signup")],
            buttons=[ButtonInfo(text="Log in")],
            forms=[
                FormInfo(
                    id="/login#form0",
                    action="/login",
                    method="POST",
                    submitText="Log in",
                    fields=[
                        FieldInfo(role="textbox", label="Email", type="email", name="email", required=True),
                        FieldInfo(role="textbox", label="Password", type="password", name="password", required=True),
                    ],
                )
            ],
            consoleErrors=[],
        ),
        PageInfo(
            url="http://localhost:4000/signup",
            path="/signup",
            title="Sign up - TaskBoard",
            status=200,
            requiresAuth=False,
            headings=[HeadingInfo(level=1, text="Create Account")],
            links=[LinkInfo(text="Log in", href="/login")],
            buttons=[ButtonInfo(text="Sign up")],
            forms=[
                FormInfo(
                    id="/signup#form0",
                    action="/signup",
                    method="POST",
                    submitText="Sign up",
                    fields=[
                        FieldInfo(role="textbox", label="Email", type="email", name="email", required=True),
                        FieldInfo(role="textbox", label="Password", type="password", name="password", required=True),
                    ],
                )
            ],
            consoleErrors=[],
        ),
        PageInfo(
            url="http://localhost:4000/dashboard",
            path="/dashboard",
            title="Dashboard - TaskBoard",
            status=200,
            requiresAuth=True,
            headings=[HeadingInfo(level=1, text="Dashboard"), HeadingInfo(level=2, text="Your Tasks")],
            links=[LinkInfo(text="Settings", href="/settings"), LinkInfo(text="Log out", href="/logout")],
            buttons=[ButtonInfo(text="Add item"), ButtonInfo(text="Delete")],
            forms=[
                FormInfo(
                    id="/dashboard#form0",
                    action="/dashboard/items",
                    method="POST",
                    submitText="Add item",
                    fields=[
                        FieldInfo(role="textbox", label="Item title", type="text", name="title", required=True),
                    ],
                )
            ],
            consoleErrors=[],
        ),
        PageInfo(
            url="http://localhost:4000/settings",
            path="/settings",
            title="Settings - TaskBoard",
            status=200,
            requiresAuth=True,
            headings=[HeadingInfo(level=1, text="Account Settings")],
            links=[LinkInfo(text="Dashboard", href="/dashboard"), LinkInfo(text="Log out", href="/logout")],
            buttons=[ButtonInfo(text="Save settings")],
            forms=[
                FormInfo(
                    id="/settings#form0",
                    action="/settings",
                    method="POST",
                    submitText="Save settings",
                    fields=[
                        FieldInfo(role="textbox", label="Display name", type="text", name="displayName", required=True),
                    ],
                )
            ],
            consoleErrors=["TypeError: Cannot read properties of undefined (reading 'theme')"],
        ),
    ],
    summary="TaskBoard is a streamlined task management application with user registration, authentication, dashboard task CRUD, and profile customization.",
    features=[
        Feature(name="Authentication", description="User registration and session management", pages=["/login", "/signup", "/logout"]),
        Feature(name="Task Management", description="Adding, viewing and deleting tasks", pages=["/dashboard"]),
        Feature(name="User Settings", description="Updating display name and preferences", pages=["/settings"]),
    ],
    stats=AppMapStats(pagesVisited=4, durationSeconds=12.4, budgetHit=None),
    error=None,
)

TEST_SPECS = [
    ("T01", "T01: Signing up with valid credentials lands on dashboard", "Verify valid account creation flow", ["S1"], "high", [
        Step(n=1, action="Navigate to /signup", expected=None),
        Step(n=2, action="Fill Email with unique('user')@example.com", expected=None),
        Step(n=3, action="Fill Password with 'Passw0rd!123'", expected=None),
        Step(n=4, action="Click 'Sign up' button", expected="User lands on /dashboard"),
    ]),
    ("T02", "T02: Signing up with invalid email is rejected", "Verify rejection of malformed email address", ["S2"], "medium", [
        Step(n=1, action="Navigate to /signup", expected=None),
        Step(n=2, action="Fill Email with 'not-an-email'", expected=None),
        Step(n=3, action="Fill Password with 'ValidPass123'", expected=None),
        Step(n=4, action="Click 'Sign up' button", expected='Shows message "Enter a valid email address"'),
    ]),
    ("T03", "T03: Signing up with short password is rejected", "Verify password length validation (< 8 characters)", ["S3"], "medium", [
        Step(n=1, action="Navigate to /signup", expected=None),
        Step(n=2, action="Fill Email with unique('user')@example.com", expected=None),
        Step(n=3, action="Fill Password with '1234567'", expected=None),
        Step(n=4, action="Click 'Sign up' button", expected='Shows message "Password must be at least 8 characters"'),
    ]),
    ("T04", "T04: Logging in with valid credentials lands on dashboard", "Verify happy path login", ["S4"], "high", [
        Step(n=1, action="Navigate to /login", expected=None),
        Step(n=2, action="Fill Email with 'qa.tester@example.com'", expected=None),
        Step(n=3, action="Fill Password with 'Passw0rd!23'", expected=None),
        Step(n=4, action="Click 'Log in' button", expected="User lands on /dashboard"),
    ]),
    ("T05", "T05: Logging in with wrong password shows error", "Verify rejection of incorrect password", ["S5"], "high", [
        Step(n=1, action="Navigate to /login", expected=None),
        Step(n=2, action="Fill Email with 'qa.tester@example.com'", expected=None),
        Step(n=3, action="Fill Password with 'WrongPassword!'", expected=None),
        Step(n=4, action="Click 'Log in' button", expected='Shows message "Invalid email or password" and remains on /login'),
    ]),
    ("T06", "T06: Logging in email is case-insensitive", "Verify uppercase email login", ["S6"], "high", [
        Step(n=1, action="Navigate to /login", expected=None),
        Step(n=2, action="Fill Email with 'QA.Tester@Example.com'", expected=None),
        Step(n=3, action="Fill Password with 'Passw0rd!23'", expected=None),
        Step(n=4, action="Click 'Log in' button", expected="User lands on /dashboard"),
    ]),
    ("T07", "T07: Adding item with non-empty title shows in list", "Verify task addition", ["S7"], "high", [
        Step(n=1, action="Log in as qa.tester@example.com and open /dashboard", expected=None),
        Step(n=2, action="Fill Item title with unique('Task')", expected=None),
        Step(n=3, action="Click 'Add item' button", expected="Item appears in task list"),
    ]),
    ("T08", "T08: Adding item with empty title is rejected", "Verify title required validation", ["S8"], "medium", [
        Step(n=1, action="Log in as qa.tester@example.com and open /dashboard", expected=None),
        Step(n=2, action="Clear Item title", expected=None),
        Step(n=3, action="Click 'Add item' button", expected='Shows message "Title is required" and no item is added'),
    ]),
    ("T09", "T09: Deleting an item removes only that item", "Verify item deletion target", ["S9"], "high", [
        Step(n=1, action="Log in and ensure two distinct items exist on /dashboard", expected=None),
        Step(n=2, action="Click 'Delete' on the second item", expected="Only the second item is removed; first remains"),
    ]),
    ("T10", "T10: Saving display name shows success and page has no errors", "Verify settings save and console health", ["S10"], "medium", [
        Step(n=1, action="Log in and navigate to /settings", expected="Page loads without console errors"),
        Step(n=2, action="Fill Display name with 'Quality Tester'", expected=None),
        Step(n=3, action="Click 'Save settings'", expected='Shows status "Settings saved"'),
    ]),
    ("T11", "T11: Logging out returns to login and Back does not show dashboard", "Verify logout and cache invalidation", ["S11"], "high", [
        Step(n=1, action="Log in and navigate to /dashboard", expected=None),
        Step(n=2, action="Click 'Log out'", expected="Navigates to /login"),
        Step(n=3, action="Click browser Back button", expected="Dashboard is not displayed; redirected to /login"),
    ]),
]

PROPOSED_TESTS = [
    TestCase(
        id=tid,
        title=title,
        description=desc,
        specRef=spec_ref,
        priority=pri,
        steps=steps,
        status="proposed",
        origin="planner",
        script=None,
        scriptStatus="pending",
        scriptError=None,
    )
    for tid, title, desc, spec_ref, pri, steps in TEST_SPECS
]

APPROVED_TESTS = [
    TestCase(
        id=tid,
        title=title,
        description=desc,
        specRef=spec_ref,
        priority=pri,
        steps=steps,
        status="approved",
        origin="planner",
        script=f"scripts/{tid}.spec.ts",
        scriptStatus="ok",
        scriptError=None,
    )
    for tid, title, desc, spec_ref, pri, steps in TEST_SPECS
]

CATALOG_PROPOSED = Catalog(runId=RUN_ID, generatedAt="2026-10-18T02:02:15Z", tests=PROPOSED_TESTS)
CATALOG_APPROVED = Catalog(runId=RUN_ID, generatedAt="2026-10-18T02:03:00Z", tests=APPROVED_TESTS)

REVIEW_LOG = ReviewLog(
    runId=RUN_ID,
    reviewedAt="2026-10-18T02:02:45Z",
    decisions=[
        ReviewDecision(testId=t.id, decision="approve", reason=f"Valid test verifying spec requirement {', '.join(t.specRef)}")
        for t in PROPOSED_TESTS
    ],
)

TEST_RESULTS = [
    TestResult(testId="T01", title=TEST_SPECS[0][1], file="scripts/T01.spec.ts", source="planned", outcome="passed", durationMs=1200, errorMessage=None, evidenceDir=None),
    TestResult(testId="T02", title=TEST_SPECS[1][1], file="scripts/T02.spec.ts", source="planned", outcome="assertion_failure", durationMs=950, errorMessage='expect(received).toHaveText(expected)\nExpected: "Enter a valid email address"\nReceived: "Welcome to dashboard"', evidenceDir="evidence/T02"),
    TestResult(testId="T03", title=TEST_SPECS[2][1], file="scripts/T03.spec.ts", source="planned", outcome="assertion_failure", durationMs=850, errorMessage='expect(received).toHaveText(expected)\nExpected: "Password must be at least 8 characters"\nReceived: "Welcome to dashboard"', evidenceDir=None),
    TestResult(testId="T04", title=TEST_SPECS[3][1], file="scripts/T04.spec.ts", source="planned", outcome="passed", durationMs=1100, errorMessage=None, evidenceDir=None),
    TestResult(testId="T05", title=TEST_SPECS[4][1], file="scripts/T05.spec.ts", source="planned", outcome="assertion_failure", durationMs=900, errorMessage='expect(received).toBeVisible()\nExpected: visible alert\nReceived: not visible', evidenceDir=None),
    TestResult(testId="T06", title=TEST_SPECS[5][1], file="scripts/T06.spec.ts", source="planned", outcome="assertion_failure", durationMs=920, errorMessage='expect(received).toHaveURL(expected)\nExpected: /dashboard\nReceived: /login?error=invalid_user', evidenceDir=None),
    TestResult(testId="T07", title=TEST_SPECS[6][1], file="scripts/T07.spec.ts", source="planned", outcome="passed", durationMs=1400, errorMessage=None, evidenceDir=None),
    TestResult(testId="T08", title=TEST_SPECS[7][1], file="scripts/T08.spec.ts", source="planned", outcome="assertion_failure", durationMs=880, errorMessage='expect(received).toHaveText(expected)\nExpected: "Title is required"\nReceived: item created successfully', evidenceDir=None),
    TestResult(testId="T09", title=TEST_SPECS[8][1], file="scripts/T09.spec.ts", source="planned", outcome="assertion_failure", durationMs=1300, errorMessage='expect(items.first()).toHaveText(expected)\nExpected: "Task Alpha"\nReceived: "Task Beta"', evidenceDir=None),
    TestResult(testId="T10", title=TEST_SPECS[9][1], file="scripts/T10.spec.ts", source="planned", outcome="assertion_failure", durationMs=1050, errorMessage='expect(consoleErrors).toHaveLength(0)\nExpected: 0 errors\nReceived: 1 error (TypeError)', evidenceDir=None),
    TestResult(testId="T11", title=TEST_SPECS[10][1], file="scripts/T11.spec.ts", source="planned", outcome="assertion_failure", durationMs=1600, errorMessage='expect(received).toHaveURL(expected)\nExpected: /login\nReceived: /dashboard (cached page)', evidenceDir=None),
    TestResult(testId="T12", title="T12: External navigation test", file="scripts/T12.spec.ts", source="planned", outcome="test_error", durationMs=5200, errorMessage="page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:9999", evidenceDir=None),
    TestResult(testId="X02", title="X02: Exploratory SQL injection probe on search input", file="scripts/probes/X02.spec.ts", source="exploratory", outcome="assertion_failure", durationMs=780, errorMessage="expect(response.status()).not.toBe(500)\nExpected: not 500\nReceived: 500 Internal Server Error", evidenceDir=None),
]

RESULTS = Results(
    runId=RUN_ID,
    startedAt="2026-10-18T02:04:00Z",
    durationSeconds=18.5,
    workers=4,
    tests=TEST_RESULTS,
    summary=ResultsSummary(total=13, passed=3, assertionFailures=9, testErrors=1),
)

BUGS = [
    Bug(
        id="B01",
        testId="T02",
        source="planned",
        title="T02: Signup accepts an invalid email",
        grep="T02:",
        file="scripts/T02.spec.ts",
        category="validation",
        severity="medium",
        specRef=["S2"],
        steps=["Navigate to /signup", "Enter invalid email 'not-an-email'", "Enter password", "Submit"],
        expected='Rejected with message "Enter a valid email address"',
        actual="Account created and user redirected to dashboard",
        errorMessage='expect(received).toHaveText(expected)\nExpected: "Enter a valid email address"',
        signature="a1b2c3d4e5",
        duplicates=[],
        evidence=Evidence(screenshot="evidence/T02/screenshot.png", video="evidence/T02/video.webm", trace=None, console="evidence/T02/console.json", network="evidence/T02/network.json"),
        status="confirmed",
        replay=BugReplay(reproduced=3, attempts=3),
    ),
    Bug(
        id="B02",
        testId="T03",
        source="planned",
        title="T03: Signup accepts passwords shorter than 8 characters",
        grep="T03:",
        file="scripts/T03.spec.ts",
        category="validation",
        severity="medium",
        specRef=["S3"],
        steps=["Navigate to /signup", "Enter valid email", "Enter 7-character password '1234567'", "Submit"],
        expected='Rejected with message "Password must be at least 8 characters"',
        actual="Account created successfully",
        errorMessage='expect(received).toHaveText(expected)\nExpected: "Password must be at least 8 characters"',
        signature="b2c3d4e5f6",
        duplicates=[],
        evidence=Evidence(),
        status="confirmed",
        replay=BugReplay(reproduced=3, attempts=3),
    ),
    Bug(
        id="B03",
        testId="T05",
        source="planned",
        title="T05: Wrong password shows no error message",
        grep="T05:",
        file="scripts/T05.spec.ts",
        category="auth",
        severity="high",
        specRef=["S5"],
        steps=["Navigate to /login", "Enter valid email", "Enter wrong password", "Click Log in"],
        expected='Shows message "Invalid email or password"',
        actual="Page remains blank with no alert or message",
        errorMessage='expect(received).toBeVisible()\nExpected: visible alert',
        signature="c3d4e5f6a1",
        duplicates=[],
        evidence=Evidence(),
        status="confirmed",
        replay=BugReplay(reproduced=3, attempts=3),
    ),
    Bug(
        id="B04",
        testId="T06",
        source="planned",
        title="T06: Login fails when the email has capital letters",
        grep="T06:",
        file="scripts/T06.spec.ts",
        category="auth",
        severity="high",
        specRef=["S6"],
        steps=["Navigate to /login", "Enter email with uppercase letters", "Enter correct password", "Submit"],
        expected="Successful login lands on dashboard",
        actual="Login rejected with error",
        errorMessage="expect(received).toHaveURL(expected)",
        signature="d4e5f6a1b2",
        duplicates=[],
        evidence=Evidence(),
        status="confirmed",
        replay=BugReplay(reproduced=3, attempts=3),
    ),
    Bug(
        id="B05",
        testId="T08",
        source="planned",
        title="T08: Dashboard accepts an empty item title",
        grep="T08:",
        file="scripts/T08.spec.ts",
        category="validation",
        severity="medium",
        specRef=["S8"],
        steps=["Open /dashboard", "Submit empty title form"],
        expected='Rejected with message "Title is required"',
        actual="Empty item added to task list",
        errorMessage='expect(received).toHaveText(expected)\nExpected: "Title is required"',
        signature="e5f6a1b2c3",
        duplicates=[],
        evidence=Evidence(),
        status="confirmed",
        replay=BugReplay(reproduced=3, attempts=3),
    ),
    Bug(
        id="B06",
        testId="T09",
        source="planned",
        title="T09: Delete removes the first item instead of clicked one",
        grep="T09:",
        file="scripts/T09.spec.ts",
        category="data",
        severity="high",
        specRef=["S9"],
        steps=["Create two items", "Click Delete on second item"],
        expected="Second item is deleted",
        actual="First item in the list is deleted instead",
        errorMessage="expect(items.first()).toHaveText(expected)",
        signature="f6a1b2c3d4",
        duplicates=[],
        evidence=Evidence(),
        status="confirmed",
        replay=BugReplay(reproduced=3, attempts=3),
    ),
    Bug(
        id="B07",
        testId="T11",
        source="planned",
        title="T11: After logout, Back shows cached dashboard",
        grep="T11:",
        file="scripts/T11.spec.ts",
        category="auth",
        severity="high",
        specRef=["S11"],
        steps=["Log in to dashboard", "Log out", "Press browser Back button"],
        expected="Redirected to login or 401 unauthenticated",
        actual="Cached dashboard displays sensitive task data",
        errorMessage="expect(received).toHaveURL(expected)",
        signature="a2b3c4d5e6",
        duplicates=[],
        evidence=Evidence(),
        status="confirmed",
        replay=BugReplay(reproduced=3, attempts=3),
    ),
    Bug(
        id="B08",
        testId="T10",
        source="planned",
        title="T10: The settings page throws an uncaught TypeError on load",
        grep="T10:",
        file="scripts/T10.spec.ts",
        category="console",
        severity="low",
        specRef=["S10"],
        steps=["Navigate to /settings"],
        expected="Loads without console errors",
        actual="Throws TypeError: Cannot read properties of undefined (reading 'theme')",
        errorMessage="expect(consoleErrors).toHaveLength(0)",
        signature="b3c4d5e6f7",
        duplicates=[],
        evidence=Evidence(),
        status="not_reproduced",
        replay=BugReplay(reproduced=0, attempts=3),
    ),
    Bug(
        id="B09",
        testId="T10",
        source="planned",
        title="T10: Every second settings save fails with HTTP 500",
        grep="T10:",
        file="scripts/T10.spec.ts",
        category="network",
        severity="medium",
        specRef=["S10"],
        steps=["Open /settings", "Save display name consecutively"],
        expected="Status 200 and 'Settings saved' every time",
        actual="Second save attempt returns HTTP 500",
        errorMessage="expect(response.status()).toBe(200)",
        signature="c4d5e6f7a2",
        duplicates=[],
        evidence=Evidence(),
        status="flaky",
        replay=BugReplay(reproduced=2, attempts=3),
    ),
    Bug(
        id="B10",
        testId="X02",
        source="exploratory",
        title="X02: Unhandled 500 Internal Server Error on special character input",
        grep="X02:",
        file="scripts/probes/X02.spec.ts",
        category="other",
        severity="medium",
        specRef=["S7"],
        steps=["Submit probe payload into dashboard search"],
        expected="Handled with 400 or graceful validation error",
        actual="Server crashes with HTTP 500",
        errorMessage="expect(response.status()).not.toBe(500)",
        signature="d5e6f7a2b3",
        duplicates=[],
        evidence=Evidence(),
        status="confirmed",
        replay=BugReplay(reproduced=3, attempts=3),
    ),
]

BUGS_FILE = BugsFile(runId=RUN_ID, bugs=BUGS)

VERIFICATIONS = [
    Verification(
        bugId=b.id,
        verifiedAt="2026-10-18T02:05:30Z",
        attempts=[
            VerificationAttempt(
                attempt=i + 1,
                reproduced=(i < (b.replay.reproduced if b.replay else 0)),
                outcome="assertion_failure" if (i < (b.replay.reproduced if b.replay else 0)) else "passed",
                errorMessage=b.errorMessage if (i < (b.replay.reproduced if b.replay else 0)) else None,
                durationMs=920,
            )
            for i in range(3)
        ],
        reproduced=b.replay.reproduced if b.replay else 0,
        status=b.status,
    )
    for b in BUGS
]

METRICS = Metrics(
    runId=RUN_ID,
    wallClockSeconds=84.2,
    stageSeconds={
        "exploring": 14.5,
        "planning": 10.2,
        "awaiting_review": 5.0,
        "scripting": 22.1,
        "running": 18.5,
        "verifying": 11.4,
        "reporting": 2.5,
    },
    tests=MetricsTests(planned=11, approved=11, passed=3, failed=9, errored=1),
    bugs=MetricsBugs(candidates=10, confirmed=8, flaky=1, notReproduced=1),
    coverage=MetricsCoverage(
        pagesInMap=4,
        pagesExercised=4,
        formsInMap=4,
        formsExercised=4,
        specItems=11,
        specItemsCovered=11,
    ),
    llm=LlmUsage(calls=14, cacheHits=6, inputTokens=24500, outputTokens=4800, costUsd=0.14),
    parallel=ParallelTiming(workers1Seconds=45.2, workers4Seconds=18.5, speedup=2.44),
    safety=MetricsSafety(blockedRequests=0),
)


def write_sample(filename: str, obj: BaseModel) -> None:
    path = SAMPLES_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj.model_dump(by_alias=True, mode="json"), f, indent=2, ensure_ascii=False)
    print(f"Wrote sample: {path.name}")


def generate_all():
    # 1. run_view.exploring.sample.json
    run_exploring = Run(
        runId=RUN_ID,
        createdAt="2026-10-18T02:00:00Z",
        updatedAt="2026-10-18T02:00:30Z",
        stage="exploring",
        mode="autonomous",
        targetUrl="http://localhost:4000",
        error=None,
        progress=Progress(step="Crawling /dashboard", done=3, total=10),
        stageTimes={
            "created": StageTime(startedAt="2026-10-18T02:00:00Z", endedAt="2026-10-18T02:00:05Z"),
            "exploring": StageTime(startedAt="2026-10-18T02:00:05Z", endedAt=None),
        },
        golden=False,
    )
    rv_exploring = RunView(
        run=run_exploring,
        input=BASE_INPUT,
        appMap=None,
        catalog=None,
        reviewLog=None,
        results=None,
        bugs=[],
        verifications=[],
        metrics=None,
        hasReport=False,
    )
    write_sample("run_view.exploring.sample.json", rv_exploring)

    # 2. run_view.awaiting_review.sample.json
    run_awaiting = Run(
        runId=RUN_ID,
        createdAt="2026-10-18T02:00:00Z",
        updatedAt="2026-10-18T02:02:20Z",
        stage="awaiting_review",
        mode="manual",
        targetUrl="http://localhost:4000",
        error=None,
        progress=None,
        stageTimes={
            "created": StageTime(startedAt="2026-10-18T02:00:00Z", endedAt="2026-10-18T02:00:05Z"),
            "exploring": StageTime(startedAt="2026-10-18T02:00:05Z", endedAt="2026-10-18T02:01:30Z"),
            "planning": StageTime(startedAt="2026-10-18T02:01:30Z", endedAt="2026-10-18T02:02:20Z"),
            "awaiting_review": StageTime(startedAt="2026-10-18T02:02:20Z", endedAt=None),
        },
        golden=False,
    )
    rv_awaiting = RunView(
        run=run_awaiting,
        input=BASE_INPUT,
        appMap=APP_MAP,
        catalog=CATALOG_PROPOSED,
        reviewLog=None,
        results=None,
        bugs=[],
        verifications=[],
        metrics=None,
        hasReport=False,
    )
    write_sample("run_view.awaiting_review.sample.json", rv_awaiting)

    # 3. run_view.done.sample.json
    run_done = Run(
        runId=RUN_ID,
        createdAt="2026-10-18T02:00:00Z",
        updatedAt="2026-10-18T02:06:00Z",
        stage="done",
        mode="autonomous",
        targetUrl="http://localhost:4000",
        error=None,
        progress=None,
        stageTimes={
            "created": StageTime(startedAt="2026-10-18T02:00:00Z", endedAt="2026-10-18T02:00:05Z"),
            "exploring": StageTime(startedAt="2026-10-18T02:00:05Z", endedAt="2026-10-18T02:01:30Z"),
            "planning": StageTime(startedAt="2026-10-18T02:01:30Z", endedAt="2026-10-18T02:02:20Z"),
            "awaiting_review": StageTime(startedAt="2026-10-18T02:02:20Z", endedAt="2026-10-18T02:02:45Z"),
            "scripting": StageTime(startedAt="2026-10-18T02:02:45Z", endedAt="2026-10-18T02:03:45Z"),
            "running": StageTime(startedAt="2026-10-18T02:03:45Z", endedAt="2026-10-18T02:04:30Z"),
            "verifying": StageTime(startedAt="2026-10-18T02:04:30Z", endedAt="2026-10-18T02:05:40Z"),
            "reporting": StageTime(startedAt="2026-10-18T02:05:40Z", endedAt="2026-10-18T02:06:00Z"),
            "done": StageTime(startedAt="2026-10-18T02:06:00Z", endedAt="2026-10-18T02:06:00Z"),
        },
        golden=True,
    )
    rv_done = RunView(
        run=run_done,
        input=BASE_INPUT,
        appMap=APP_MAP,
        catalog=CATALOG_APPROVED,
        reviewLog=REVIEW_LOG,
        results=RESULTS,
        bugs=BUGS,
        verifications=VERIFICATIONS,
        metrics=METRICS,
        hasReport=True,
    )
    write_sample("run_view.done.sample.json", rv_done)

    # 4. run_view.failed.sample.json
    run_failed = Run(
        runId="20261018-013000-dead",
        createdAt="2026-10-18T01:30:00Z",
        updatedAt="2026-10-18T01:30:45Z",
        stage="failed",
        mode="manual",
        targetUrl="http://localhost:4000",
        error="Target app unreachable at http://localhost:4000 (connection refused after 30s timeout)",
        progress=None,
        stageTimes={
            "created": StageTime(startedAt="2026-10-18T01:30:00Z", endedAt="2026-10-18T01:30:05Z"),
            "exploring": StageTime(startedAt="2026-10-18T01:30:05Z", endedAt="2026-10-18T01:30:45Z"),
            "failed": StageTime(startedAt="2026-10-18T01:30:45Z", endedAt="2026-10-18T01:30:45Z"),
        },
        golden=False,
    )
    input_failed = RunInput(
        runId="20261018-013000-dead",
        createdAt="2026-10-18T01:30:00Z",
        targetUrl="http://localhost:4000",
        prompt="Test run",
        specRaw="S1: Basic sign in",
        spec=[SpecItem(id="S1", text="Basic sign in")],
        username="user@example.com",
        mode="manual",
        budgets=Budgets(),
    )
    rv_failed = RunView(
        run=run_failed,
        input=input_failed,
        appMap=None,
        catalog=None,
        reviewLog=None,
        results=None,
        bugs=[],
        verifications=[],
        metrics=None,
        hasReport=False,
    )
    write_sample("run_view.failed.sample.json", rv_failed)

    # 5. runs_list.sample.json
    runs_list = [
        RunListItem(
            runId=RUN_ID,
            createdAt="2026-10-18T02:00:00Z",
            stage="done",
            mode="autonomous",
            targetUrl="http://localhost:4000",
            counts=RunListItemCounts(tests=11, bugs=10, confirmed=8, flaky=1),
        ),
        RunListItem(
            runId="20261018-014500-b3c4",
            createdAt="2026-10-18T01:45:00Z",
            stage="awaiting_review",
            mode="manual",
            targetUrl="http://localhost:4000",
            counts=RunListItemCounts(tests=11, bugs=0, confirmed=0, flaky=0),
        ),
        RunListItem(
            runId="20261018-013000-dead",
            createdAt="2026-10-18T01:30:00Z",
            stage="failed",
            mode="manual",
            targetUrl="http://localhost:4000",
            counts=RunListItemCounts(tests=0, bugs=0, confirmed=0, flaky=0),
        ),
    ]
    with open(SAMPLES_DIR / "runs_list.sample.json", "w", encoding="utf-8") as f:
        json.dump([item.model_dump(by_alias=True, mode="json") for item in runs_list], f, indent=2)
    print("Wrote sample: runs_list.sample.json")

    # 6. Stand-alone files
    write_sample("app_map.sample.json", APP_MAP)
    write_sample("catalog.sample.json", CATALOG_APPROVED)
    write_sample("review_log.sample.json", REVIEW_LOG)
    write_sample("results.sample.json", RESULTS)
    write_sample("bugs.sample.json", BUGS_FILE)
    write_sample("metrics.sample.json", METRICS)
    write_sample("verification.B01.sample.json", VERIFICATIONS[0])

    # 7. Mirror run files in contracts/samples/files/
    # Tiny valid 1x1 PNG base64
    tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    png_bytes = base64.b64decode(tiny_png_b64)

    t02_dir = FILES_DIR / "evidence" / "T02"
    t02_dir.mkdir(parents=True, exist_ok=True)
    with open(t02_dir / "screenshot.png", "wb") as f:
        f.write(png_bytes)

    # Empty placeholder video.webm
    with open(t02_dir / "video.webm", "wb") as f:
        pass

    # console.json
    with open(t02_dir / "console.json", "w", encoding="utf-8") as f:
        json.dump([{"type": "error", "text": "Validation error: invalid email domain"}], f, indent=2)

    # network.json
    with open(t02_dir / "network.json", "w", encoding="utf-8") as f:
        json.dump([{"url": "http://localhost:4000/signup", "status": 200, "method": "POST"}], f, indent=2)

    # scripts/T02.spec.ts
    scripts_dir = FILES_DIR / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    spec_content = '''import { test, expect, unique } from '../../../apps/runner/fixtures';

test('T02: Signing up with invalid email is rejected', async ({ page }) => {
  await page.goto('/signup');
  await page.getByLabel('Email').fill('not-an-email');
  await page.getByLabel('Password').fill('ValidPass123');
  await page.getByRole('button', { name: 'Sign up' }).click();

  const alert = page.getByRole('alert');
  await expect(alert).toHaveText('Enter a valid email address');
});
'''
    with open(scripts_dir / "T02.spec.ts", "w", encoding="utf-8") as f:
        f.write(spec_content)

    # report.md
    report_content = f"""# Autonomous AI QA Engineer — Run Report

**Run ID:** `{RUN_ID}`
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
"""
    with open(FILES_DIR / "report.md", "w", encoding="utf-8") as f:
        f.write(report_content)

    print("All sample files generated successfully.")


if __name__ == "__main__":
    generate_all()
