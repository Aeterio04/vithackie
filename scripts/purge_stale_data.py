#!/usr/bin/env python3
"""Purge stale, orphaned, or mismatched cache/bug records across runs and projects."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

# Add apps/api/src to sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "apps" / "api" / "src"))

from kawach.core.config import settings
from kawach.db.session import SessionLocal
from kawach.db.models.runs import Run as DbRun
from kawach.db.models.project import Project as DbProject


def scan_and_purge(apply: bool = False):
    storage_runs_dir = settings.repo_root / "runs"
    if not storage_runs_dir.exists():
        storage_runs_dir = settings.storage_dir / "runs"

    print("=" * 70)
    print(f"KAWACH DATA CONSISTENCY & PURGE SCAN (Mode: {'APPLY' if apply else 'DRY RUN'})")
    print("=" * 70)

    db = SessionLocal()
    orphaned_run_dirs = []
    mismatched_runs = []
    stale_caches = []

    try:
        db_runs = {r.id: r for r in db.query(DbRun).all()}
        db_projects = {p.id: p for p in db.query(DbProject).all()}

        # 1. Scan filesystem run directories
        if storage_runs_dir.exists():
            for r_dir in storage_runs_dir.iterdir():
                if not r_dir.is_dir():
                    continue
                run_id = r_dir.name
                input_file = r_dir / "input.json"

                if not input_file.exists():
                    orphaned_run_dirs.append((r_dir, "Missing input.json"))
                    continue

                try:
                    data = json.loads(input_file.read_text(encoding="utf-8"))
                    target_url = data.get("targetUrl")
                except Exception as e:
                    orphaned_run_dirs.append((r_dir, f"Corrupted input.json: {e}"))
                    continue

                if run_id in db_runs:
                    db_run = db_runs[run_id]
                    if db_run.project_id and db_run.project_id not in db_projects:
                        mismatched_runs.append((r_dir, f"Project {db_run.project_id} deleted"))
                else:
                    # Run directory on disk but not in DB
                    orphaned_run_dirs.append((r_dir, "Run ID not present in database"))

        # 2. Scan legacy target-app caches
        legacy_cache = settings.repo_root / "apps" / "runner" / "test-results"
        if legacy_cache.exists():
            for item in legacy_cache.iterdir():
                if item.name.startswith("run-") or item.name.startswith("verify"):
                    stale_caches.append(item)

        print(f"Found {len(orphaned_run_dirs)} orphaned run directory/directories on disk.")
        for p, reason in orphaned_run_dirs:
            print(f"  - [ORPHAN] {p.name}: {reason}")

        print(f"Found {len(mismatched_runs)} mismatched run(s).")
        for p, reason in mismatched_runs:
            print(f"  - [MISMATCH] {p.name}: {reason}")

        print(f"Found {len(stale_caches)} stale runner cache folder(s).")
        for p in stale_caches:
            print(f"  - [CACHE] {p.name}")

        if apply:
            print("\nApplying deletions...")
            deleted_count = 0
            for p, _ in orphaned_run_dirs:
                try:
                    shutil.rmtree(p, ignore_errors=True)
                    deleted_count += 1
                except Exception as e:
                    print(f"  Failed to delete {p}: {e}")

            for p, _ in mismatched_runs:
                try:
                    shutil.rmtree(p, ignore_errors=True)
                    deleted_count += 1
                except Exception as e:
                    print(f"  Failed to delete {p}: {e}")

            for p in stale_caches:
                try:
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
                    deleted_count += 1
                except Exception as e:
                    print(f"  Failed to delete cache {p}: {e}")

            print(f"Successfully purged {deleted_count} stale record(s)/directory/directories.")
        else:
            print("\nDry-run complete. To apply changes, execute with --apply.")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Purge stale or orphaned KAWACH data")
    parser.add_argument("--apply", action="store_true", help="Apply deletions (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry-run only (default)")
    args = parser.parse_args()

    scan_and_purge(apply=args.apply)


if __name__ == "__main__":
    main()
