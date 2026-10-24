"""Supabase Object Storage Driver for execution media, screenshots, traces, and reports."""

import hashlib
import mimetypes
from pathlib import Path
from typing import Optional, Tuple, Union
import uuid

import httpx

from kawach.core.config import settings
from kawach.core.logging import get_logger

logger = get_logger("kawach.storage.supabase")


class SupabaseStorageDriver:
    """Manages uploads, downloads, and URLs for media files stored in Supabase Storage buckets."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ):
        self.url = (supabase_url or settings.SUPABASE_URL or "").rstrip("/")
        self.key = (
            supabase_key
            or settings.SUPABASE_SECRET_KEY
            or settings.SUPABASE_KEY
            or settings.SUPABASE_PUBLISHABLE_KEY
            or ""
        )
        self.bucket = bucket_name or settings.SUPABASE_BUCKET or "aiqa_runs"

    @property
    def is_configured(self) -> bool:
        """Return True if active Supabase credentials are configured."""
        return bool(self.url and self.key)

    def _headers(self, mime: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.key}",
            "apikey": self.key,
            "Content-Type": mime,
            "x-upsert": "true",
        }

    def _object_path(self, run_id: str, relative_path: str) -> str:
        """Normalized object path inside the bucket: runs/<run_id>/<relative_path>."""
        clean_rel = relative_path.replace("\\", "/").lstrip("/")
        return f"runs/{run_id}/{clean_rel}"

    def upload_file(
        self,
        run_id: str,
        path: str,
        content: Union[bytes, str],
        mime: Optional[str] = None,
    ) -> Tuple[str, str, int, str, str]:
        """Upload a file to the Supabase bucket (or fallback to artifacts store).

        Returns:
            Tuple of (artifact_id, storage_path, size_bytes, sha256, public_or_local_url)
        """
        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        size_bytes = len(raw_bytes)
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        artifact_id = str(uuid.uuid4())
        clean_path = self._object_path(run_id, path)

        if not mime:
            mime, _ = mimetypes.guess_type(path)
            mime = mime or "application/octet-stream"

        public_url = ""
        if self.is_configured:
            endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{clean_path}"
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(
                        endpoint,
                        content=raw_bytes,
                        headers=self._headers(mime),
                    )
                    if resp.is_success:
                        public_url = f"{self.url}/storage/v1/object/public/{self.bucket}/{clean_path}"
                        logger.info(f"Uploaded {clean_path} to Supabase bucket '{self.bucket}'.")
                    else:
                        logger.warning(
                            f"Supabase upload returned HTTP {resp.status_code}: {resp.text}. Falling back to disk."
                        )
            except Exception as e:
                logger.error(f"Failed to upload {clean_path} to Supabase: {e}. Falling back to disk.")

        # Local fallback persistence when not configured or upload failed
        local_path = (settings.artifacts_dir / clean_path).resolve()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(local_path, "wb") as f:
                f.write(raw_bytes)
            if not public_url:
                public_url = f"/api/v1/artifacts/media/{clean_path}"
        except Exception as e:
            logger.error(f"Error writing local fallback artifact {local_path}: {e}")

        return artifact_id, clean_path, size_bytes, sha256, public_url

    def get_public_url(self, run_id: str, path: str) -> str:
        """Get public or accessible URL for an object."""
        clean_path = self._object_path(run_id, path)
        if self.is_configured:
            return f"{self.url}/storage/v1/object/public/{self.bucket}/{clean_path}"
        return f"/api/v1/artifacts/media/{clean_path}"

    def download_file(self, run_id: str, path: str) -> Optional[bytes]:
        """Download object bytes from Supabase bucket or local fallback."""
        clean_path = self._object_path(run_id, path)
        if self.is_configured:
            endpoint = f"{self.url}/storage/v1/object/public/{self.bucket}/{clean_path}"
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(endpoint, headers=self._headers("application/octet-stream"))
                    if resp.is_success:
                        return resp.content
            except Exception as e:
                logger.error(f"Failed to download {clean_path} from Supabase: {e}")

        local_path = (settings.artifacts_dir / clean_path).resolve()
        if local_path.exists():
            with open(local_path, "rb") as f:
                return f.read()
        return None

    def delete_file(self, run_id: str, path: str) -> bool:
        """Delete object from Supabase bucket."""
        clean_path = self._object_path(run_id, path)
        deleted = False
        if self.is_configured:
            endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{clean_path}"
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.delete(endpoint, headers=self._headers("application/json"))
                    deleted = resp.is_success
            except Exception:
                pass

        local_path = (settings.artifacts_dir / clean_path).resolve()
        if local_path.exists():
            try:
                local_path.unlink()
                deleted = True
            except Exception:
                pass
        return deleted


supabase_storage = SupabaseStorageDriver()
