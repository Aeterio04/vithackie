"""Filesystem safety for everything the MCP server writes to disk."""

from __future__ import annotations

import re
import stat
import zipfile
from pathlib import Path
from typing import Optional

from .errors import KawachError

MAX_EXTRACT_BYTES = 200 * 1024 * 1024
MAX_NAME_LEN = 100
_BAD = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(name: Optional[str], default: str = "file") -> str:
    """Keep [A-Za-z0-9._-], replace the rest, strip leading dots, cap the length."""
    base = (name or "").replace("\\", "/").split("/")[-1]
    clean = _BAD.sub("_", base).lstrip(".")[:MAX_NAME_LEN]
    return clean or default


def ensure_inside(base: Path, target: Path) -> Path:
    base_r, target_r = base.resolve(), target.resolve()
    if not target_r.is_relative_to(base_r):
        raise KawachError("Refusing to write outside the download directory.")
    return target_r


def unique_path(path: Path) -> Path:
    """Never overwrite: append _1, _2, ... before the extension if the file exists."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(1, 10_000):
        cand = path.with_name(f"{stem}_{i}{suffix}")
        if not cand.exists():
            return cand
    raise KawachError("Too many files with the same name in the download directory.")


def safe_dest(base: Path, *folders: str, filename: str) -> Path:
    """Build base/<sanitized folders>/<sanitized filename>, inside base, unique, parents created."""
    base.mkdir(parents=True, exist_ok=True)
    target = base.joinpath(*[sanitize_filename(f, "dir") for f in folders], sanitize_filename(filename))
    target = unique_path(ensure_inside(base, target))
    target.parent.mkdir(parents=True, exist_ok=True)
    return ensure_inside(base, target)


def plain_filename(name: str) -> str:
    """Validate a user-supplied file name: no slashes, no .., not absolute. Returns it unchanged."""
    if (not name or "/" in name or "\\" in name or ".." in name or name.startswith(".")
            or re.match(r"^[A-Za-z]:", name) or "\x00" in name):
        raise KawachError("filename must be a plain file name like 'report.md' (no slashes, '..' or absolute paths).")
    return name


def safe_extract_zip(zip_path: Path, dest_dir: Path, max_total: int = MAX_EXTRACT_BYTES) -> dict:
    """Extract a zip defensively (zip-slip, absolute paths, symlinks, size bomb). Returns {files, bytes}."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    root = dest_dir.resolve()
    total = files = 0
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if sum(i.file_size for i in infos) > max_total:
            raise KawachError(f"Archive would extract to more than {max_total // (1024 * 1024)} MB; refusing.")
        plan = []
        for info in infos:  # validate everything first so nothing is written for a bad archive
            name = info.filename.replace("\\", "/")
            parts = [p for p in name.split("/") if p not in ("", ".")]
            if name.startswith("/") or ".." in parts or (parts and re.match(r"^[A-Za-z]:", parts[0])):
                raise KawachError(f"Unsafe path in archive: {info.filename!r}; refusing to extract.")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise KawachError(f"Archive contains a symlink ({info.filename!r}); refusing to extract.")
            target = (root / Path(*parts)) if parts else root
            if not target.resolve().is_relative_to(root):
                raise KawachError(f"Unsafe path in archive: {info.filename!r}; refusing to extract.")
            plan.append((info, target))
        for info, target in plan:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target = unique_path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                while chunk := src.read(65536):
                    total += len(chunk)
                    if total > max_total:
                        raise KawachError("Archive exceeded the extraction size limit; stopped.")
                    out.write(chunk)
            files += 1
    return {"files": files, "bytes": total}
