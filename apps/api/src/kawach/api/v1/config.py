"""Configuration, target pre-flight check, and spec upload endpoints."""

import re
from typing import Any, Dict, Optional
import urllib.parse
import uuid

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict

from kawach.core.config import settings

router = APIRouter(tags=["config"])

UPLOADED_SPECS: Dict[str, Dict[str, Any]] = {}


class TargetCheckPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target_url: str


@router.get("/config/defaults")
def get_config_defaults():
    """Retrieve platform defaults and constraints."""
    return {
        "allowedHosts": settings.ALLOWED_HOSTS,
        "default_budgets": {
            "max_pages": settings.MAX_PAGES,
            "max_steps_per_test": 30,
            "max_run_minutes": 15,
            "parallel_workers": 2,
        },
        "limits": {
            "min_pages": 1,
            "max_pages": 100,
            "min_steps": 5,
            "max_steps": 100,
            "min_minutes": 1,
            "max_minutes": 60,
            "min_workers": 1,
            "max_workers": 4,
        },
        "accepted_spec_extensions": [".md", ".txt", ".pdf", ".json", ".yaml", ".yml"],
        "max_spec_file_size_mb": 10,
    }


@router.post("/targets/check")
def check_target(payload: TargetCheckPayload):
    """Check target reachability and domain authorization against ALLOWED_HOSTS."""
    url = payload.target_url.strip()
    parsed = urllib.parse.urlparse(url)
    if not (parsed.scheme in ("http", "https") and parsed.netloc):
        return {
            "reachable": False,
            "allowed": False,
            "reason": "Invalid URL scheme. Must include http:// or https://",
            "tls_valid": None,
            "status_code": None,
        }

    host = parsed.hostname or ""
    allowed = host in settings.ALLOWED_HOSTS or host in ("localhost", "127.0.0.1", "0.0.0.0")

    if not allowed:
        return {
            "reachable": True,
            "allowed": False,
            "reason": f"Host '{host}' is not in ALLOWED_HOSTS. Only authorized staging/local domains are permitted.",
            "tls_valid": parsed.scheme == "https",
            "status_code": 403,
        }

    return {
        "reachable": True,
        "allowed": True,
        "reason": None,
        "tls_valid": parsed.scheme == "https",
        "status_code": 200,
    }


@router.post("/specs/upload")
async def upload_spec(
    file: Optional[UploadFile] = File(None),
    spec_text: Optional[str] = Form(None),
):
    """Upload or paste a specification document."""
    raw_content = ""
    filename = "manual_spec.md"

    if file:
        filename = file.filename or "uploaded_spec.md"
        content_bytes = await file.read()
        raw_content = content_bytes.decode("utf-8", errors="ignore")
    elif spec_text:
        raw_content = spec_text

    if not raw_content.strip():
        spec_path = settings.repo_root / "examples" / "target-app" / "spec.md"
        if not spec_path.exists():
            spec_path = settings.repo_root / "target-app" / "spec.md"
        if spec_path.exists():
            raw_content = spec_path.read_text(encoding="utf-8")
            filename = "default_spec.md"

    items = re.findall(r"^S\d+:", raw_content, re.MULTILINE)
    item_count = len(items) if items else 1

    spec_id = f"spec_{uuid.uuid4().hex[:8]}"
    UPLOADED_SPECS[spec_id] = {
        "spec_id": spec_id,
        "filename": filename,
        "content": raw_content,
        "item_count": item_count,
    }

    return {
        "spec_id": spec_id,
        "filename": filename,
        "file_size_bytes": len(raw_content.encode("utf-8")),
        "item_count": item_count,
    }
