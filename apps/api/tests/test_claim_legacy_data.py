"""scripts/claim_legacy_data.py: dry run by default, ownership moves on --apply, nothing is deleted."""

import importlib.util
import sqlite3
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kawach.db.base import Base
from kawach.db.models.artifacts import Artifact
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.db.models.runs import Run

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "claim_legacy_data.py"
spec = importlib.util.spec_from_file_location("claim_legacy_data", SCRIPT)
claim_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(claim_mod)


@pytest.fixture
def world(tmp_path):
    db_file = tmp_path / "k.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    old_id, new_id = str(uuid.uuid4()), str(uuid.uuid4())
    storage = tmp_path / "storage"
    (storage / "users" / old_id / "tests").mkdir(parents=True)
    (storage / "users" / old_id / "tests" / "a.png").write_bytes(b"png")
    with sessionmaker(bind=engine)() as db:
        db.add_all([User(id=old_id, email="tester@example.com", password_hash="x", display_name="QA Engineer"),
                    User(id=new_id, email="me@example.com", password_hash="x", display_name="Me")])
        db.flush()
        db.add(Project(id="p1", owner_id=old_id, name="P", slug="p", target_url="http://localhost:4000"))
        db.flush()
        db.add(Run(id="r1", project_id="p1", created_by=old_id, stage="done", mode="manual", progress={}))
        db.add(Artifact(id="a1", project_id="p1", run_id="r1", kind="screenshot", uri=f"users/{old_id}/tests/a.png",
                        size_bytes=3, sha256="0", mime="image/png", user_id=old_id,
                        relative_path=f"users/{old_id}/tests/a.png"))
        db.commit()
    return db_file, storage, old_id, new_id


def owners(db_file):
    c = sqlite3.connect(db_file)
    row = (c.execute("select owner_id from projects").fetchone()[0], c.execute("select created_by from runs").fetchone()[0],
           c.execute("select user_id, relative_path, uri from artifacts").fetchone())
    c.close()
    return row


def test_dry_run_changes_nothing(world):
    db_file, storage, old_id, new_id = world
    res = claim_mod.claim(db_file, storage, "tester@example.com", "me@example.com", apply=False, log=lambda m: None)
    assert res["applied"] is False and res["counts"]["projects.owner_id"] == 1 and res["counts"]["runs.created_by"] == 1
    assert owners(db_file)[0] == old_id and not (storage / "users" / new_id).exists()
    assert not list(db_file.parent.glob("*.bak*"))


def test_apply_moves_ownership_copies_files_and_keeps_originals(world):
    db_file, storage, old_id, new_id = world
    claim_mod.claim(db_file, storage, "QA Engineer", "ME@example.com", apply=True, log=lambda m: None)
    owner, created_by, (art_user, rel, uri) = owners(db_file)
    assert owner == created_by == art_user == new_id
    assert rel == uri == f"users/{new_id}/tests/a.png"
    assert (storage / "users" / new_id / "tests" / "a.png").read_bytes() == b"png"
    assert (storage / "users" / old_id / "tests" / "a.png").exists()  # nothing deleted
    assert len(list(db_file.parent.glob("k.db.bak-*"))) == 1
    sqlite3.connect(db_file).execute("select count(*) from users").fetchone()  # old user row still there
    claim_mod.claim(db_file, storage, "tester@example.com", "me@example.com", apply=True, log=lambda m: None)
    assert len(list(db_file.parent.glob("k.db.bak-*"))) == 2  # second backup does not overwrite the first


@pytest.mark.parametrize("source,dest,msg", [("nobody", "me@example.com", "No user matches"),
                                             ("tester@example.com", "ghost@example.com", "No user matches"),
                                             ("me@example.com", "me@example.com", "same account")])
def test_bad_inputs_are_errors(world, source, dest, msg):
    db_file, storage, *_ = world
    with pytest.raises(claim_mod.ClaimError, match=msg):
        claim_mod.claim(db_file, storage, source, dest, apply=True, log=lambda m: None)
