"""Configuration, target pre-flight check, and spec upload endpoints."""

import re
from typing import Any, Dict, Optional
import urllib.parse
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile

from kawach.api.deps import get_current_user
from kawach.db.models.identity import User
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
def check_target(payload: TargetCheckPayload, _user: User = Depends(get_current_user)):
    """Check target reachability and domain authorization against SSRF policy and shared target fetch rules."""
    from kawach.core.target_fetch import check_target_reachability

    res = check_target_reachability(payload.target_url)
    return {
        "reachable": res.reachable,
        "allowed": res.allowed,
        "reason": res.reason,
        "tls_valid": res.tls_valid,
        "status_code": res.status_code,
        "final_url": res.final_url,
        "server": res.server,
        "origin": res.origin,
    }


@router.post("/specs/upload")
async def upload_spec(
    file: Optional[UploadFile] = File(None),
    spec_text: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
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

    from kawach.services.spec_parser import parse_spec_raw
    parsed_items = parse_spec_raw(raw_content)
    item_count = len(parsed_items) if parsed_items else 1

    spec_id = f"spec_{uuid.uuid4().hex[:8]}"
    UPLOADED_SPECS[spec_id] = {
        "spec_id": spec_id,
        "owner_id": current_user.id,
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
