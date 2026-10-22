"""Managed artifact store driver for physical storage of execution evidence, traces, and media."""

import hashlib
import mimetypes
from pathlib import Path
import shutil
from typing import Optional, Tuple, Union
import uuid

from kawach.core.config import settings


class ArtifactStore:
    """Storage manager storing physical files under ARTIFACTS_DIR with content hashing."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or settings.artifacts_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, relative_uri: str) -> Path:
        """Resolve URI securely ensuring no traversal escapes the artifact root."""
        clean_rel = relative_uri.replace("\\", "/").lstrip("/")
        resolved = (self.root_dir / clean_rel).resolve()
        if not str(resolved).startswith(str(self.root_dir.resolve())):
            raise ValueError(f"Path traversal detected: {relative_uri}")
        return resolved

    def save_bytes(
        self,
        data: Union[bytes, str],
        project_id: str,
        kind: str,
        filename: str,
        run_id: Optional[str] = None,
        mime: Optional[str] = None,
    ) -> Tuple[str, str, int, str]:
        """Save raw bytes or text to managed storage and compute size and SHA256.

        Returns:
            Tuple of (artifact_id, relative_uri, size_bytes, sha256)
        """
        raw_bytes = data.encode("utf-8") if isinstance(data, str) else data
        size_bytes = len(raw_bytes)
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        artifact_id = str(uuid.uuid4())

        # Construct relative directory: projects/<project_id>/runs/<run_id>/<kind>/<uuid>_<filename>
        run_part = f"runs/{run_id}" if run_id else "global"
        rel_dir = Path("projects") / project_id / run_part / kind
        target_dir = self.root_dir / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / f"{artifact_id[:8]}_{filename}"
        with open(target_file, "wb") as f:
            f.write(raw_bytes)

        rel_uri = str(target_file.relative_to(self.root_dir)).replace("\\", "/")
        return artifact_id, rel_uri, size_bytes, sha256

    def copy_file(
        self,
        src_path: Path,
        project_id: str,
        kind: str,
        run_id: Optional[str] = None,
    ) -> Tuple[str, str, int, str]:
        """Copy existing file on disk into artifact store.

        Returns:
            Tuple of (artifact_id, relative_uri, size_bytes, sha256)
        """
        if not src_path.exists():
            raise FileNotFoundError(f"Source file {src_path} not found")

        with open(src_path, "rb") as f:
            data = f.read()

        return self.save_bytes(
            data=data,
            project_id=project_id,
            kind=kind,
            filename=src_path.name,
            run_id=run_id,
        )

    def get_path(self, relative_uri: str) -> Path:
        """Resolve physical path from stored URI."""
        return self._safe_path(relative_uri)

    def read_bytes(self, relative_uri: str) -> bytes:
        """Read artifact file contents."""
        path = self.get_path(relative_uri)
        with open(path, "rb") as f:
            return f.read()

    def delete_file(self, relative_uri: str) -> bool:
        """Delete physical artifact file."""
        try:
            path = self.get_path(relative_uri)
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def infer_mime(filename: str) -> str:
        """Guess MIME type from filename extension."""
        mime, _ = mimetypes.guess_type(filename)
        return mime or "application/octet-stream"


artifact_store = ArtifactStore()
