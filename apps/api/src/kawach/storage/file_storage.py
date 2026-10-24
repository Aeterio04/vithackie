"""Secure local disk file storage helper for test artifacts, screenshots, and screen recordings.

Implements directory structure:
    storage/users/<user_id>/tests/<test_id>/<uuid>.<ext>
"""

import mimetypes
from pathlib import Path
import shutil
from typing import Optional, Union
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.core.config import settings
from kawach.db.models.artifacts import Artifact


def guess_mime_and_ext(
    file_type: str,
    ext: Optional[str] = None,
    mime_type: Optional[str] = None,
) -> tuple[str, str]:
    """Resolve normalized extension (without dot) and MIME type."""
    type_ext_map = {
        "screenshot": ("png", "image/png"),
        "screen_recording": ("webm", "video/webm"),
        "video": ("webm", "video/webm"),
        "trace": ("zip", "application/zip"),
        "log": ("log", "text/plain"),
        "console": ("json", "application/json"),
        "network": ("json", "application/json"),
    }

    if file_type in type_ext_map:
        default_ext, default_mime = type_ext_map[file_type]
    else:
        default_ext, default_mime = ("bin", "application/octet-stream")

    final_ext = (ext or default_ext).lstrip(".").lower()
    if not mime_type:
        guessed_mime, _ = mimetypes.guess_type(f"file.{final_ext}")
        final_mime = guessed_mime or default_mime
    else:
        final_mime = mime_type

    return final_ext, final_mime


def get_file_path(relative_path: str) -> Path:
    """Resolve physical disk path while strictly preventing directory traversal.
    
    Raises ValueError if path traversal or path outside storage root is attempted.
    """
    clean = relative_path.replace("\\", "/").strip()
    if clean.startswith("storage/"):
        clean = clean[len("storage/"):]
    clean = clean.lstrip("/")

    parts = clean.split("/")
    if ".." in parts or any(p.startswith("..") for p in parts) or ":" in clean:
        raise ValueError(f"Path traversal detected: {relative_path}")

    storage_root = settings.storage_dir.resolve()
    target_path = (storage_root / clean).resolve()

    try:
        target_path.relative_to(storage_root)
    except ValueError:
        raise ValueError(f"Path traversal detected: {relative_path}")

    return target_path


def save_artifact_file(
    user_id: str,
    test_id: str,
    data: Union[bytes, str],
    file_type: str,
    ext: Optional[str] = None,
    mime_type: Optional[str] = None,
    project_id: Optional[str] = None,
    run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Artifact:
    """Save file content to local disk under storage/users/<user_id>/tests/<test_id>/<uuid>.<ext>
    and persist metadata record in the database.
    """
    final_ext, final_mime = guess_mime_and_ext(file_type, ext, mime_type)
    artifact_id = str(uuid.uuid4())
    filename = f"{artifact_id}.{final_ext}"

    rel_dir = Path("users") / user_id / "tests" / test_id
    abs_target_dir = settings.storage_dir / rel_dir
    abs_target_dir.mkdir(parents=True, exist_ok=True)

    abs_target_file = abs_target_dir / filename
    raw_bytes = data.encode("utf-8") if isinstance(data, str) else data

    with open(abs_target_file, "wb") as f:
        f.write(raw_bytes)

    rel_path_str = str(rel_dir / filename).replace("\\", "/")

    artifact = Artifact(
        id=artifact_id,
        user_id=user_id,
        test_id=test_id,
        project_id=project_id,
        run_id=run_id or test_id,
        type=file_type,
        relative_path=rel_path_str,
        size=len(raw_bytes),
        mime_type=final_mime,
    )

    if db is not None:
        db.add(artifact)
        db.flush()

    return artifact


def save_artifact_file_from_disk(
    user_id: str,
    test_id: str,
    src_path: Union[str, Path],
    file_type: str,
    ext: Optional[str] = None,
    mime_type: Optional[str] = None,
    project_id: Optional[str] = None,
    run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Artifact:
    """Read existing file on disk and save into user's storage structure."""
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"Source file {src} not found")

    if not ext and src.suffix:
        ext = src.suffix.lstrip(".")

    data = src.read_bytes()
    return save_artifact_file(
        user_id=user_id,
        test_id=test_id,
        data=data,
        file_type=file_type,
        ext=ext,
        mime_type=mime_type,
        project_id=project_id,
        run_id=run_id,
        db=db,
    )


def delete_artifact_file(artifact: Artifact, db: Optional[Session] = None) -> bool:
    """Delete artifact file from disk and remove its database record."""
    rel = artifact.relative_path or artifact.uri
    if rel:
        try:
            path = get_file_path(rel)
            if path.exists() and path.is_file():
                path.unlink(missing_ok=True)
        except Exception:
            pass

    if db is not None:
        db.delete(artifact)
        db.commit()

    return True


def delete_test_artifact_files(user_id: str, test_id: str, db: Optional[Session] = None) -> int:
    """Delete all files and directory for a specific test and purge associated artifact records."""
    test_dir = settings.storage_dir / "users" / user_id / "tests" / test_id
    if test_dir.exists():
        shutil.rmtree(test_dir, ignore_errors=True)

    deleted_count = 0
    if db is not None:
        stmt = select(Artifact).where(Artifact.user_id == user_id, Artifact.test_id == test_id)
        artifacts = list(db.scalars(stmt).all())
        deleted_count = len(artifacts)
        for art in artifacts:
            db.delete(art)
        db.commit()

    return deleted_count

