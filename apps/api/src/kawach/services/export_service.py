"""Export service for bundling runs and standalone test suites into ZIP archives."""

import io
from pathlib import Path
import zipfile
from typing import Optional

from kawach.core.config import settings
from kawach.schemas import Results, Run
from kawach.storage import artifacts as storage


def export_run_zip(run_id: str) -> io.BytesIO:
    """Create a ZIP archive of all run artifacts, excluding temporary and cache files."""
    run_dir = storage.run_dir(run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory for {run_id} not found")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in Path(run_dir).walk():
            for f in files:
                if f.endswith(".tmp") or ".tmp." in f or f == "secrets.json":
                    continue
                file_path = root / f
                rel_path = file_path.relative_to(run_dir)
                zf.write(file_path, arcname=str(rel_path).replace("\\", "/"))

    zip_buffer.seek(0)
    return zip_buffer


def export_scripts_zip(run_id: str) -> io.BytesIO:
    """Create a standalone executable Playwright project containing passing test scripts."""
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise FileNotFoundError(f"Run {run_id} not found")

    results = storage.load_model(run_id, "results.json", Results)
    if not results:
        raise FileNotFoundError(f"Results for run {run_id} not found")

    passed_tests = [t for t in results.tests if t.outcome == "passed"]
    if not passed_tests:
        raise ValueError("No passed tests to export")

    run_dir = storage.run_dir(run_id)
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add passing scripts with rewritten imports
        for pt in passed_tests:
            script_path = run_dir / (pt.file if pt.file else f"scripts/{pt.testId}.spec.ts")
            if script_path.exists():
                content = script_path.read_text(encoding="utf-8")
                content = content.replace("../../../apps/runner/fixtures", "./fixtures")
                content = content.replace("../../../runner/fixtures", "./fixtures")
                zf.writestr(f"scripts/{pt.testId}.spec.ts", content)

        # 2. Add fixtures.ts
        fixtures_source = settings.repo_root / "apps" / "runner" / "fixtures.ts"
        if not fixtures_source.exists():
            fixtures_source = settings.repo_root / "runner" / "fixtures.ts"
        if fixtures_source.exists():
            zf.write(fixtures_source, arcname="fixtures.ts")
            zf.write(fixtures_source, arcname="scripts/fixtures.ts")
        else:
            minimal_fixtures = """import { test as base, expect } from '@playwright/test';
export const test = base;
export { expect };
export const unique = (prefix: string) => `${prefix}-${Date.now()}`;
"""
            zf.writestr("fixtures.ts", minimal_fixtures)
            zf.writestr("scripts/fixtures.ts", minimal_fixtures)

        # 3. Add playwright.config.ts
        base_url = run.targetUrl or "http://localhost:4000"
        cfg_content = f"""import {{ defineConfig, devices }} from '@playwright/test';

export default defineConfig({{
  testDir: './scripts',
  timeout: 30000,
  use: {{
    baseURL: process.env.BASE_URL ?? '{base_url}',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  }},
  projects: [
    {{
      name: 'chromium',
      use: {{ ...devices['Desktop Chrome'] }},
    }},
  ],
}});
"""
        zf.writestr("playwright.config.ts", cfg_content)

        # 4. Add package.json
        pkg_content = """{
  "name": "qa-exported-tests",
  "private": true,
  "scripts": {
    "test": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "^1.49.0"
  }
}
"""
        zf.writestr("package.json", pkg_content)

        # 5. Add README.md
        readme_content = """# Exported QA Tests

## Setup & Execution
1. Install dependencies:
   ```bash
   npm install
   npx playwright install chromium
   ```
2. Configure credentials in environment:
   ```bash
   export TEST_USERNAME="<user@example.com>"
   export TEST_PASSWORD="<password>"
   ```
3. Run tests:
   ```bash
   npx playwright test
   ```
"""
        zf.writestr("README.md", readme_content)

        # 6. Add QA verification report files (PDF, Markdown, HTML)
        for report_name in ["report.md", "report.html", "report.pdf"]:
            report_file = run_dir / report_name
            if report_file.exists():
                zf.write(report_file, arcname=f"reports/{report_name}")

    zip_buffer.seek(0)
    return zip_buffer
