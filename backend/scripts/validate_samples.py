"""Validate all contract sample JSON files against Pydantic models and contract rules."""

import json
import sys
from pathlib import Path
from pydantic import BaseModel, TypeAdapter

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import (
    AppMap,
    BugsFile,
    Catalog,
    Metrics,
    Results,
    ReviewLog,
    RunListItem,
    RunView,
    Verification,
)

SAMPLES_DIR = REPO_ROOT / "contracts" / "samples"
FILES_DIR = SAMPLES_DIR / "files"

VALID_SPEC_REFS = {f"S{i}" for i in range(1, 12)}


def validate_all_samples() -> bool:
    all_ok = True
    print(f"Validating samples in {SAMPLES_DIR.relative_to(REPO_ROOT)}...\n")

    # Mapping of filename patterns to models
    sample_files = list(SAMPLES_DIR.glob("*.json"))
    if not sample_files:
        print("FAIL: No sample JSON files found!")
        return False

    for json_file in sorted(sample_files):
        rel_name = json_file.name
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if rel_name.startswith("run_view."):
                model_obj = RunView.model_validate(data)
                # If done sample, perform extra deep checks
                if "done" in rel_name:
                    _check_done_sample(model_obj)
            elif rel_name == "runs_list.sample.json":
                adapter = TypeAdapter(list[RunListItem])
                adapter.validate_python(data)
            elif rel_name == "app_map.sample.json":
                AppMap.model_validate(data)
            elif rel_name == "catalog.sample.json":
                cat = Catalog.model_validate(data)
                for t in cat.tests:
                    for s in t.specRef:
                        if s not in VALID_SPEC_REFS:
                            raise ValueError(f"Invalid specRef {s} in test {t.id}")
            elif rel_name == "review_log.sample.json":
                ReviewLog.model_validate(data)
            elif rel_name == "results.sample.json":
                Results.model_validate(data)
            elif rel_name == "bugs.sample.json":
                bugs_file = BugsFile.model_validate(data)
                for b in bugs_file.bugs:
                    for s in b.specRef:
                        if s not in VALID_SPEC_REFS:
                            raise ValueError(f"Invalid specRef {s} in bug {b.id}")
            elif rel_name == "metrics.sample.json":
                Metrics.model_validate(data)
            elif rel_name.startswith("verification."):
                Verification.model_validate(data)
            else:
                print(f"WARN: Unknown sample schema for {rel_name}")

            print(f"  OK: {rel_name}")
        except Exception as e:
            print(f"FAIL: {rel_name} -> {e}")
            all_ok = False

    return all_ok


def _check_done_sample(rv: RunView) -> None:
    # 1. Check specRefs in catalog
    if rv.catalog:
        for t in rv.catalog.tests:
            for s in t.specRef:
                if s not in VALID_SPEC_REFS:
                    raise ValueError(f"Invalid specRef {s} in test {t.id}")

    # 2. Check result testIds
    result_test_ids = set()
    if rv.results:
        result_test_ids = {tr.testId for tr in rv.results.tests}

    # 3. Check bugs
    for b in rv.bugs:
        for s in b.specRef:
            if s not in VALID_SPEC_REFS:
                raise ValueError(f"Invalid specRef {s} in bug {b.id}")
        if result_test_ids and b.testId not in result_test_ids:
            raise ValueError(f"bug.testId '{b.testId}' not found in results.tests")

        # 4. Check evidence paths
        ev = b.evidence
        for attr in ("screenshot", "video", "trace", "console", "network"):
            val = getattr(ev, attr, None)
            if val:
                ev_path = FILES_DIR / val
                if not ev_path.exists():
                    if attr == "video":
                        print(f"    [WARN] Video evidence file missing (optional): {val}")
                    else:
                        raise FileNotFoundError(f"Referenced evidence file missing: {val} (expected at {ev_path})")


if __name__ == "__main__":
    success = validate_all_samples()
    print("\nSummary:")
    if success:
        print("ALL SAMPLES OK")
        sys.exit(0)
    else:
        print("SOME SAMPLES FAILED VALIDATION")
        sys.exit(1)
