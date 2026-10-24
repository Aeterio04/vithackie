#!/usr/bin/env python3
"""Reassign the data of an old/demo account to a real registered account.

Moves ownership of projects, runs, saved tests, review decisions and artifacts from one user to another so
nothing is lost when moving off a shared/demo login. Nothing is deleted: the old user row stays, files are
COPIED (never moved or overwritten), and a SQLite backup is written before any change.

DRY RUN BY DEFAULT. Nothing is modified unless you pass --apply.

Examples (from the repository root):
    # 1. Register the destination account on the website first, then preview:
    python scripts/claim_legacy_data.py --from tester@example.com --to-email you@example.com
    # 2. Apply:
    python scripts/claim_legacy_data.py --from tester@example.com --to-email you@example.com --apply

`--from` accepts the old user's id, email or display name. Stop the backend before --apply.
Uses only the standard library.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

# (table, column) pairs holding a user id that represents ownership of the data
OWNERSHIP_COLUMNS: List[Tuple[str, str]] = [
    ("projects", "owner_id"),
    ("projects", "user_id"),
    ("runs", "created_by"),
    ("saved_tests", "created_by"),
    ("review_decisions", "reviewer_user_id"),
    ("artifacts", "user_id"),
]


class ClaimError(Exception):
    pass


def _table_has(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def find_user(conn: sqlite3.Connection, ref: str, label: str) -> sqlite3.Row:
    ref = ref.strip()
    rows = conn.execute(
        "SELECT id, email, display_name FROM users WHERE id = ? OR lower(email) = lower(?) OR display_name = ?",
        (ref, ref, ref)).fetchall()
    if not rows:
        raise ClaimError(f"No user matches {label} {ref!r}.")
    if len(rows) > 1:
        listing = "\n".join(f"  {r['id']}  {r['email']}  ({r['display_name']})" for r in rows)
        raise ClaimError(f"{label} {ref!r} is ambiguous, use the id or the exact email:\n{listing}")
    return rows[0]


def plan(conn: sqlite3.Connection, old_id: str) -> List[Tuple[str, str, int]]:
    out = []
    for table, col in OWNERSHIP_COLUMNS:
        if _table_has(conn, table, col):
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (old_id,)).fetchone()[0]
            out.append((table, col, n))
    return out


def copy_user_files(storage_dir: Path, old_id: str, new_id: str, apply: bool) -> Tuple[int, int]:
    """Copy storage/users/<old>/** to storage/users/<new>/** without overwriting. Returns (copied, skipped)."""
    src = storage_dir / "users" / old_id
    dst = storage_dir / "users" / new_id
    copied = skipped = 0
    if not src.is_dir():
        return 0, 0
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        target = dst / f.relative_to(src)
        if target.exists():
            skipped += 1
            continue
        copied += 1
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
    return copied, skipped


def claim(db_path: Path, storage_dir: Path, source: str, to_email: str, apply: bool,
          log=lambda m: print(m)) -> dict:
    if not db_path.exists():
        raise ClaimError(f"Database not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        old = find_user(conn, source, "--from")
        new = find_user(conn, to_email, "--to-email")
        if old["id"] == new["id"]:
            raise ClaimError("--from and --to-email are the same account.")
        if "@" not in new["email"] or new["email"].endswith("@kawach.local"):
            raise ClaimError("The destination must be a real registered account.")

        log(f"From: {old['email']} ({old['id']})")
        log(f"To:   {new['email']} ({new['id']})")
        log(f"Mode: {'APPLY' if apply else 'DRY RUN (nothing will be changed)'}")
        counts = plan(conn, old["id"])
        log("\nRows that would change owner:" if not apply else "\nRows changing owner:")
        for table, col, n in counts:
            log(f"  {table + '.' + col:<32}{n:>6}")
        art_paths = conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE relative_path LIKE ? OR uri LIKE ?",
            (f"users/{old['id']}/%", f"users/{old['id']}/%")).fetchone()[0]
        log(f"  {'artifacts (path prefix rewrite)':<32}{art_paths:>6}")
        copied, skipped = copy_user_files(storage_dir, old["id"], new["id"], apply=False)
        log(f"\nFiles under storage/users/{old['id']}/: {copied} to copy, {skipped} already present at the destination")

        result = {"old": old["id"], "new": new["id"], "counts": {f"{t}.{c}": n for t, c, n in counts},
                  "artifact_paths": art_paths, "files_to_copy": copied, "applied": False}
        if not apply:
            log("\nDry run only. Re-run with --apply to make these changes (stop the backend first).")
            return result

        backup = db_path.with_name(f"{db_path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        n = 1
        while backup.exists():  # never overwrite an earlier backup
            backup = db_path.with_name(f"{db_path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}-{n}")
            n += 1
        with sqlite3.connect(str(backup)) as dest:
            conn.backup(dest)
        log(f"\nBackup written: {backup}")

        copied, skipped = copy_user_files(storage_dir, old["id"], new["id"], apply=True)
        log(f"Copied {copied} file(s) (skipped {skipped} existing). Originals were left in place.")

        try:
            conn.execute("BEGIN")
            for table, col, _ in counts:
                conn.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", (new["id"], old["id"]))
            old_prefix, new_prefix = f"users/{old['id']}/", f"users/{new['id']}/"
            for col in ("relative_path", "uri"):
                if _table_has(conn, "artifacts", col):
                    conn.execute(
                        f"UPDATE artifacts SET {col} = ? || substr({col}, ?) WHERE {col} LIKE ?",
                        (new_prefix, len(old_prefix) + 1, old_prefix + "%"))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        result["applied"] = True
        log("Done. Refresh the website while signed in as the destination account.")
        return result
    finally:
        conn.close()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Reassign an old/demo account's data to a real account (dry run by default).")
    ap.add_argument("--from", dest="source", required=True, help="old user id, email or display name")
    ap.add_argument("--to-email", required=True, help="email of the registered destination account")
    ap.add_argument("--db", default=str(REPO_ROOT / "data" / "kawach.db"), help="SQLite file (default: data/kawach.db)")
    ap.add_argument("--storage", default=str(REPO_ROOT / "storage"), help="storage dir (default: storage)")
    ap.add_argument("--apply", action="store_true", help="actually modify the database (default is a dry run)")
    args = ap.parse_args(argv)
    try:
        claim(Path(args.db), Path(args.storage), args.source, args.to_email, args.apply)
    except ClaimError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
