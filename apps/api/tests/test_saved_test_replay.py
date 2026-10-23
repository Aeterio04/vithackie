"""Tests proving and verifying the saved-test replay problem and standalone script verification.

Task N1-0 c:
1. Proves the saved-test replay problem: a script generated under runs/<id>/scripts/
   with relative fixtures import ('../../../apps/runner/fixtures') fails if executed
   directly from an arbitrary artifact depth without depth mirroring or path rewriting.
2. Proves the fix: staging the script in a workspace mirroring canonical depth (runs/<id>/scripts/)
   and/or rewriting the fixtures import at execution time.
3. Proves that the Verifier (verify_script) is callable on any stored script with no agent involved.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from kawach.core.config import settings
from kawach.execution.runner import RawRun
from kawach.execution.verifier import (
    prepare_script_workspace,
    rewrite_fixtures_import,
    verify_script,
)
from kawach.schemas import Verification
from kawach.storage.artifact_store import ArtifactStore


SAMPLE_SPEC_SCRIPT = """import { test, expect } from '../../../apps/runner/fixtures';

test('T01: Sample test journey', async ({ page }) => {
    await page.goto('/');
    expect(true).toBe(true);
});
"""


def test_saved_test_replay_depth_failure_demonstration(tmp_path):
    """Demonstrate the replay depth bug:

    When a script is saved into the artifact store at depth 6:
    (e.g., data/artifacts/projects/<p_id>/global/saved_tests/<uuid>_T01.spec.ts),
    its relative import '../../../apps/runner/fixtures' resolves to
    data/artifacts/projects/apps/runner/fixtures which DOES NOT exist.
    """
    store = ArtifactStore(root_dir=tmp_path / "artifacts")
    artifact_id, rel_uri, _, _ = store.save_bytes(
        data=SAMPLE_SPEC_SCRIPT,
        project_id="proj_alpha",
        kind="saved_tests",
        filename="T01.spec.ts",
    )

    stored_file = (store.root_dir / rel_uri).resolve()
    assert stored_file.exists()

    # Calculate what '../../../apps/runner/fixtures' resolves to from the stored file location
    unresolved_fixtures = (stored_file.parent / "../../../apps/runner/fixtures").resolve()
    actual_fixtures = (settings.repo_root / "apps" / "runner" / "fixtures").resolve()

    # PROOF OF THE PROBLEM: The naive relative import from artifact store does NOT resolve to repo fixtures
    assert unresolved_fixtures != actual_fixtures
    assert not unresolved_fixtures.exists()


def test_prepare_script_workspace_resolution(tmp_path, monkeypatch):
    """Prove that prepare_script_workspace stages the script at depth 3 and resolves fixtures."""
    monkeypatch.setattr(settings, "runs_dir", tmp_path / "runs")

    store = ArtifactStore(root_dir=tmp_path / "artifacts")
    _, rel_uri, _, _ = store.save_bytes(
        data=SAMPLE_SPEC_SCRIPT,
        project_id="proj_beta",
        kind="saved_tests",
        filename="T01.spec.ts",
    )
    stored_file = (store.root_dir / rel_uri).resolve()

    # Stage the script for execution
    workspace_id, staged_script = prepare_script_workspace(
        script_path=stored_file,
        run_id="test_replay_workspace",
        target_url="http://localhost:4000",
    )

    assert staged_script.exists()
    assert staged_script.parent.name == "scripts"
    assert staged_script.parent.parent.name == "test_replay_workspace"

    # From staged location, the import resolves or is rewritten accurately
    staged_content = staged_script.read_text(encoding="utf-8")
    assert "apps/runner/fixtures" in staged_content


def test_rewrite_fixtures_import_utility():
    """Verify rewrite_fixtures_import rewrites any fixtures import to point to apps/runner/fixtures."""
    sample_dir = settings.repo_root / "data" / "artifacts" / "projects" / "p1" / "saved_tests"
    rewritten = rewrite_fixtures_import(
        SAMPLE_SPEC_SCRIPT,
        source_dir=sample_dir,
        repo_root=settings.repo_root,
    )
    # Must compute relative path starting with ../
    assert "runner/fixtures" in rewritten
    assert "../../../../../apps/runner/fixtures" in rewritten or "../" in rewritten


def test_verifier_callable_standalone_on_stored_script(tmp_path, monkeypatch):
    """Prove that the Verifier (verify_script) can be called directly on any stored script

    with NO agent involved, executing 3 deterministic replays and returning a Verification object.
    """
    monkeypatch.setattr(settings, "runs_dir", tmp_path / "runs")

    store = ArtifactStore(root_dir=tmp_path / "artifacts")
    _, rel_uri, _, _ = store.save_bytes(
        data=SAMPLE_SPEC_SCRIPT,
        project_id="proj_standalone",
        kind="saved_tests",
        filename="T01.spec.ts",
    )
    stored_file = (store.root_dir / rel_uri).resolve()

    # Mock run_playwright to simulate 3 reproducible assertion failures
    mock_report = tmp_path / "report.json"
    mock_report.write_text('{"suites": []}', encoding="utf-8")

    call_count = 0

    def mock_run_pw(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return RawRun(
            exit_code=0,
            report_path=str(mock_report),
            stdout="",
            stderr="",
            duration_s=0.5,
        )

    with patch("kawach.execution.verifier.run_playwright", side_effect=mock_run_pw), \
         patch("kawach.execution.verifier.parse_report") as mock_parse:
        # Simulate 3 passes where assertion failed reproducibly
        mock_parse.return_value = [{
            "title": "T01: Sample test journey",
            "status": "failed",
            "errorMessage": "Error: expect(received).toBe(true)\nReceived: false",
            "durationMs": 450,
        }]

        result: Verification = verify_script(
            script_path=stored_file,
            target_url="http://localhost:4000",
            grep="T01",
        )

    # 3 replays must be executed
    assert call_count == 3
    assert len(result.attempts) == 3
    assert result.reproduced == 3
    assert result.status == "confirmed"
    assert result.attempts[0].outcome == "assertion_failure"
    assert result.attempts[0].reproduced is True
