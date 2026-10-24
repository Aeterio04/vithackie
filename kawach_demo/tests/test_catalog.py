"""Offline tests ensuring bug catalog matches the patch files."""

import json
from pathlib import Path


def test_catalog_matches_patches():
    demo_root = Path(__file__).resolve().parent.parent
    bugs_dir = demo_root / "bugs"
    catalog_path = bugs_dir / "catalog.json"

    assert catalog_path.is_file(), "catalog.json must exist in bugs/"

    catalog_data = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert len(catalog_data) >= 3, "Catalog must define at least 3 bugs"

    required_fields = ["id", "title", "commit_message", "difficulty", "files_touched", "causal_file"]

    for bug in catalog_data:
        for field in required_fields:
            assert field in bug, f"Field '{field}' missing in bug {bug.get('id')}"

        bug_id = bug["id"]
        patch_file = bugs_dir / f"{bug_id}.patch"
        assert patch_file.is_file(), f"Missing patch file for {bug_id}: {patch_file}"

        patch_text = patch_file.read_text(encoding="utf-8")
        assert len(bug["files_touched"]) == 3, f"{bug_id} must touch exactly 3 files"
        assert bug["causal_file"] in bug["files_touched"], f"Causal file must be in files_touched for {bug_id}"

        # Assert every touched file is referenced in the patch
        for touched in bug["files_touched"]:
            assert touched in patch_text, f"Touched file {touched} not found in {bug_id}.patch"
