"""Unit tests for Playwright Script Writer agent."""

import pytest
from unittest.mock import MagicMock

from app.agents import script_writer
from app.config import settings
from app.models import Catalog, Run, RunInput, Step, TestCase
from app import runner_client
from app import storage


def test_clean_and_sanitize_script_fixes_title_and_imports():
    raw_llm_output = """```typescript
import { test, expect } from '@playwright/test';
import * as path from 'path';

test('Signup rejects an invalid email address', async ({ page }) => {
  await page.goto('/signup');
  await page.getByLabel('Email').fill('invalid');
  await expect(page.getByRole('alert')).toHaveText('Enter a valid email address');
});
```"""

    cleaned = script_writer.clean_and_sanitize_script(
        raw_llm_output,
        test_id="T02",
        test_title="Signup rejects an invalid email address",
    )

    lines = cleaned.splitlines()
    assert lines[0] == "import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';"
    # Verify other imports are stripped
    assert not any("from '@playwright/test'" in l for l in lines)
    assert not any("import * as path" in l for l in lines)

    # Verify title has T02: prefix
    assert "test('T02: Signup rejects an invalid email address'" in cleaned


def test_clean_and_sanitize_script_rejects_forbidden_patterns():
    # waitForTimeout
    bad_code1 = """import { test } from '../../../apps/runner/fixtures';
test('T01: Foo', async ({ page }) => {
  await page.waitForTimeout(500);
});"""
    with pytest.raises(ValueError) as exc1:
        script_writer.clean_and_sanitize_script(bad_code1, "T01", "Foo")
    assert "waitForTimeout is forbidden" in str(exc1.value)

    # process.env
    bad_code2 = """import { test } from '../../../apps/runner/fixtures';
test('T01: Foo', async ({ page }) => {
  const url = process.env.BASE_URL;
});"""
    with pytest.raises(ValueError) as exc2:
        script_writer.clean_and_sanitize_script(bad_code2, "T01", "Foo")
    assert "process.env is forbidden" in str(exc2.value)

    # absolute URL
    bad_code3 = """import { test } from '../../../apps/runner/fixtures';
test('T01: Foo', async ({ page }) => {
  await page.goto('http://google.com');
});"""
    with pytest.raises(ValueError) as exc3:
        script_writer.clean_and_sanitize_script(bad_code3, "T01", "Foo")
    assert "Absolute URLs are forbidden" in str(exc3.value)


@pytest.fixture
def run_fixture(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")

    run_id = "test-script-run-001"
    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        targetUrl="http://localhost:4000",
        prompt="Testing script writer",
        specRaw="S1: Foo\nS2: Bar",
        username="qa.tester@example.com",
    )
    storage.save_model(run_id, "input.json", run_input)

    run_obj = Run(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        updatedAt="2026-10-18T00:00:00Z",
        stage="planning",
        mode="manual",
        targetUrl="http://localhost:4000",
    )
    storage.save_model(run_id, "run.json", run_obj)

    tests = [
        TestCase(
            id="T01",
            title="T01: Approved Test 1",
            description="desc 1",
            specRef=["S1"],
            priority="high",
            steps=[Step(n=1, action="Go to /login", expected="Heading visible")],
            status="approved",
        ),
        TestCase(
            id="T02",
            title="T02: Approved Test 2",
            description="desc 2",
            specRef=["S2"],
            priority="medium",
            steps=[Step(n=1, action="Go to /signup", expected="Alert visible")],
            status="approved",
        ),
        TestCase(
            id="T03",
            title="T03: Approved Test 3",
            description="desc 3",
            specRef=["S1"],
            priority="low",
            steps=[Step(n=1, action="Go to /items", expected=None)],
            status="approved",
        ),
        TestCase(
            id="T04",
            title="T04: Still Proposed Test",
            description="desc 4",
            specRef=["S2"],
            priority="low",
            steps=[Step(n=1, action="Go to /about", expected=None)],
            status="proposed",
        ),
    ]

    catalog = Catalog(runId=run_id, generatedAt="2026-10-18T00:00:00Z", tests=tests)
    storage.save_model(run_id, "catalog.json", catalog)

    return run_id


def test_write_scripts_processes_only_approved_tests(run_fixture, monkeypatch):
    run_id = run_fixture

    # Monkeypatch runner_client.list_tests to succeed
    monkeypatch.setattr(
        runner_client,
        "list_tests",
        MagicMock(return_value=runner_client.ListResult(ok=True)),
    )

    catalog = script_writer.write_scripts(run_id)

    # 3 scripts written, 1 proposed untouched
    assert catalog.tests[0].scriptStatus == "ok"
    assert catalog.tests[0].script == "scripts/T01.spec.ts"
    assert catalog.tests[1].scriptStatus == "ok"
    assert catalog.tests[1].script == "scripts/T02.spec.ts"
    assert catalog.tests[2].scriptStatus == "ok"
    assert catalog.tests[2].script == "scripts/T03.spec.ts"

    assert catalog.tests[3].status == "proposed"
    assert catalog.tests[3].scriptStatus == "pending"
    assert catalog.tests[3].script is None

    # Check files exist on disk
    scripts_dir = storage.run_dir(run_id) / "scripts"
    assert (scripts_dir / "T01.spec.ts").exists()
    assert (scripts_dir / "T02.spec.ts").exists()
    assert (scripts_dir / "T03.spec.ts").exists()
    assert not (scripts_dir / "T04.spec.ts").exists()


def test_write_scripts_auto_healing_retry(run_fixture, monkeypatch):
    run_id = run_fixture
    llm = script_writer.get_llm()

    # Keep only T01 as approved
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    catalog.tests = [catalog.tests[0]]
    storage.save_model(run_id, "catalog.json", catalog)

    # First list_tests fails, second succeeds after LLM retry
    list_mock = MagicMock(side_effect=[
        runner_client.ListResult(ok=False, error="SyntaxError: Unexpected token"),
        runner_client.ListResult(ok=True),
    ])
    monkeypatch.setattr(runner_client, "list_tests", list_mock)

    llm_call_mock = MagicMock(return_value="""import { test, expect } from '../../../apps/runner/fixtures';
test('T01: Fixed', async ({ page }) => { await page.goto('/login'); });""")
    monkeypatch.setattr(llm, "complete_text", llm_call_mock)

    updated_cat = script_writer.write_scripts(run_id)

    assert llm_call_mock.call_count == 2
    assert list_mock.call_count == 2
    assert updated_cat.tests[0].scriptStatus == "ok"
    assert updated_cat.tests[0].scriptError is None


def test_write_scripts_failure_marked_error_and_file_preserved(run_fixture, monkeypatch):
    run_id = run_fixture

    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    catalog.tests = [catalog.tests[0]]
    storage.save_model(run_id, "catalog.json", catalog)

    # Both validation attempts fail
    list_mock = MagicMock(return_value=runner_client.ListResult(ok=False, error="Cannot find module fixtures"))
    monkeypatch.setattr(runner_client, "list_tests", list_mock)

    updated_cat = script_writer.write_scripts(run_id)

    assert updated_cat.tests[0].scriptStatus == "error"
    assert "Cannot find module fixtures" in updated_cat.tests[0].scriptError

    # File still exists on disk
    script_file = storage.run_dir(run_id) / "scripts" / "T01.spec.ts"
    assert script_file.exists()
