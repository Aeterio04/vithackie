import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import runner_client, storage, verifier
from app.models import Bug, BugsFile, Evidence, Run, RunInput


def main():
    # 1. Reset target-app ONCE
    req = urllib.request.Request("http://localhost:4000/__reset", method="POST")
    with urllib.request.urlopen(req) as resp:
        print("Reset response:", resp.read().decode())

    run_id = "_verify_demo"
    r_dir = storage.run_dir(run_id)
    scripts_dir = r_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # 2. Write scripts
    # Note: clicking button:has-text("Save settings") clicks the form button, not the nav logout button
    flaky_spec = (
        "import { test, expect, unique } from '../../../runner/fixtures';\n\n"
        "test('T_flaky: Settings save succeeds', async ({ page }) => {\n"
        "  await page.goto('/login');\n"
        "  await page.fill('#email', 'qa.tester@example.com');\n"
        "  await page.fill('#password', 'Passw0rd!23');\n"
        "  await page.click('button:has-text(\"Log in\")');\n"
        "  await expect(page.locator('h1')).toHaveText('Dashboard');\n\n"
        "  await page.goto('/settings');\n"
        "  await page.fill('#displayName', unique('User'));\n"
        "  await page.click('button:has-text(\"Save settings\")');\n"
        "  await expect(page.locator('p[role=\"status\"]')).toHaveText('Settings saved');\n"
        "});\n"
    )
    (scripts_dir / "T_flaky.spec.ts").write_text(flaky_spec, encoding="utf-8")

    conf_spec = (
        "import { test, expect } from '../../../runner/fixtures';\n\n"
        "test('T_confirmed: Empty title rejected', async ({ page }) => {\n"
        "  await page.goto('/login');\n"
        "  await page.fill('#email', 'qa.tester@example.com');\n"
        "  await page.fill('#password', 'Passw0rd!23');\n"
        "  await page.click('button:has-text(\"Log in\")');\n"
        "  await expect(page.locator('h1')).toHaveText('Dashboard');\n\n"
        "  await page.fill('#title', '');\n"
        "  await page.click('button:has-text(\"Add item\")');\n"
        "  await expect(page.locator('p[role=\"alert\"]')).toHaveText('Title is required');\n"
        "});\n"
    )
    (scripts_dir / "T_confirmed.spec.ts").write_text(conf_spec, encoding="utf-8")

    # 3. Models
    storage.save_model(
        run_id,
        "input.json",
        RunInput(
            runId=run_id,
            createdAt="2026-10-18T00:00:00Z",
            targetUrl="http://localhost:4000",
            specRaw="S10: Settings\nS8: Empty title",
            username="qa.tester@example.com",
        ),
    )
    storage.save_model(
        run_id,
        "run.json",
        Run(
            runId=run_id,
            createdAt="2026-10-18T00:00:00Z",
            updatedAt="2026-10-18T00:00:00Z",
            targetUrl="http://localhost:4000",
        ),
    )

    flaky_err = 'Error: expect(locator).toHaveText(expected) failed\nLocator: locator(\'p[role="status"]\')\nExpected: "Settings saved"'
    conf_err = 'Error: expect(locator).toHaveText(expected) failed\nLocator: locator(\'p[role="alert"]\')\nExpected: "Title is required"'

    bug_flaky = Bug(
        id="B09",
        testId="T_flaky",
        source="planned",
        title="T_flaky: Settings save succeeds",
        grep="T_flaky:",
        file="scripts/T_flaky.spec.ts",
        category="other",
        severity="medium",
        specRef=["S10"],
        steps=["Save settings"],
        expected="Settings saved",
        actual="Internal Server Error",
        errorMessage=flaky_err,
        signature=runner_client.signature(flaky_err),
        duplicates=[],
        evidence=Evidence(),
        status="candidate",
    )

    bug_conf = Bug(
        id="B05",
        testId="T_confirmed",
        source="planned",
        title="T_confirmed: Empty title rejected",
        grep="T_confirmed:",
        file="scripts/T_confirmed.spec.ts",
        category="other",
        severity="medium",
        specRef=["S8"],
        steps=["Add empty title"],
        expected="Title is required",
        actual="Title accepted",
        errorMessage=conf_err,
        signature=runner_client.signature(conf_err),
        duplicates=[],
        evidence=Evidence(),
        status="candidate",
    )

    storage.save_model(run_id, "bugs.json", BugsFile(runId=run_id, bugs=[bug_flaky, bug_conf]))

    print("--- Running verify_bug on B09 (settings flaky) ---")
    v_flaky = verifier.verify_bug(run_id, "B09")
    print("B09 status:", v_flaky.status, "reproduced:", v_flaky.reproduced)
    print("B09 verification JSON:\n", v_flaky.model_dump_json(indent=2))

    print("\n--- Running verify_bug on B05 (empty title confirmed) ---")
    v_conf = verifier.verify_bug(run_id, "B05")
    print("B05 status:", v_conf.status, "reproduced:", v_conf.reproduced)
    print("B05 verification JSON:\n", v_conf.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
