"""Artifact file serving, video range streaming, and app-map visualization endpoints."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from kawach.api.deps import (
    get_current_user,
    get_db,
    get_owned_artifact,
    get_owned_run,
    get_user_scope,
    require_scope,
)
from kawach.core.clock import now_iso
from kawach.db.models.artifacts import Artifact
from kawach.db.models.identity import User
from kawach.db.models.runs import Run as DbRun
from kawach.schemas import AppMap, Run
from kawach.storage import artifacts as storage
from kawach.storage.artifact_store import ArtifactStore
from kawach.storage.file_storage import (
    delete_artifact_file,
    delete_test_artifact_files,
    get_file_path,
    save_artifact_file,
)

router = APIRouter(tags=["artifacts"])


def stream_file_with_range(
    target_file: Path,
    request: Request,
    media_type: str = "application/octet-stream",
) -> Response:
    """Serve file with HTTP 206 Partial Content support for seeking in video/audio players."""
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    file_size = target_file.stat().st_size
    range_header = request.headers.get("range")

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": media_type,
    }

    if not range_header or not range_header.startswith("bytes="):
        headers["Content-Length"] = str(file_size)
        return FileResponse(target_file, media_type=media_type, headers={"Accept-Ranges": "bytes"})

    range_val = range_header.replace("bytes=", "").strip()
    parts = range_val.split("-")
    start_str = parts[0]
    end_str = parts[1] if len(parts) > 1 else ""

    try:
        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str:
            start = int(start_str)
            end = file_size - 1
        elif end_str:
            length = int(end_str)
            start = max(0, file_size - length)
            end = file_size - 1
        else:
            start = 0
            end = file_size - 1
    except ValueError:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    if start < 0 or start >= file_size or end >= file_size or start > end:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = end - start + 1
    headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    headers["Content-Length"] = str(chunk_size)

    def file_chunk_generator():
        with open(target_file, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            buf_size = 64 * 1024
            while remaining > 0:
                to_read = min(buf_size, remaining)
                chunk = f.read(to_read)
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        file_chunk_generator(),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        headers=headers,
    )


def _resolve_artifact_path(artifact: Artifact) -> Path:
    """Resolve physical disk path from artifact metadata safely."""
    rel_path = artifact.relative_path or artifact.uri
    if rel_path:
        try:
            p = get_file_path(rel_path)
            if p.exists() and p.is_file():
                return p
        except Exception:
            pass

    if artifact.uri:
        try:
            store = ArtifactStore()
            p = store.get_path(artifact.uri)
            if p.exists() and p.is_file():
                return p
        except Exception:
            pass

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file missing")


@router.post("/artifacts/upload", status_code=status.HTTP_201_CREATED)
@router.post("/storage/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    test_id: str = Form(...),
    file_type: str = Form("screenshot"),
    project_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload and persist test evidence/video/screenshot to disk with DB metadata."""
    content = await file.read()
    ext = Path(file.filename or "").suffix.lstrip(".") if file.filename else None

    artifact = save_artifact_file(
        user_id=current_user.id,
        test_id=test_id,
        data=content,
        file_type=file_type,
        ext=ext,
        mime_type=file.content_type,
        project_id=project_id,
        db=db,
    )
    db.commit()

    return {
        "id": artifact.id,
        "user_id": artifact.user_id,
        "test_id": artifact.test_id,
        "type": artifact.type,
        "relative_path": artifact.relative_path,
        "size": artifact.size,
        "mime_type": artifact.mime_type,
        "created_at": artifact.created_at.isoformat() if hasattr(artifact.created_at, "isoformat") else str(artifact.created_at),
    }


@router.get("/artifacts/{artifact_id}")
@router.get("/storage/files/{artifact_id}")
def get_artifact(
    artifact_id: str,
    request: Request,
    artifact: Artifact = Depends(get_owned_artifact),
):
    """Serve physical artifact evidence with strict multi-tenant ownership check and range streaming."""
    file_path = _resolve_artifact_path(artifact)
    mime = artifact.mime_type or artifact.mime or "application/octet-stream"
    return stream_file_with_range(file_path, request, media_type=mime)


@router.get("/storage/files/by-path/{relative_path:path}")
def get_file_by_path(
    relative_path: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Serve file by relative path securely ensuring owner isolation and blocking path traversal."""
    try:
        target_file = get_file_path(relative_path)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Multi-tenant check: user can only access files in their own folder (users/<user_id>/...)
    clean_rel = relative_path.replace("\\", "/").strip().lstrip("/")
    if clean_rel.startswith("storage/"):
        clean_rel = clean_rel[len("storage/"):]
    parts = clean_rel.split("/")
    # Only the caller's own folder is reachable; anything else (other users, shared roots) is a 404.
    if len(parts) < 2 or parts[0] != "users" or parts[1] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    ext = target_file.suffix.lower()
    media_map = {
        ".png": "image/png",
        ".webm": "video/webm",
        ".mp4": "video/mp4",
        ".zip": "application/zip",
        ".json": "application/json",
        ".ts": "text/plain",
        ".md": "text/markdown",
        ".log": "text/plain",
    }
    media_type = media_map.get(ext, "application/octet-stream")
    return stream_file_with_range(target_file, request, media_type=media_type)


@router.delete("/artifacts/{artifact_id}")
@router.delete("/storage/files/{artifact_id}")
def delete_file(
    artifact_id: str,
    artifact: Artifact = Depends(get_owned_artifact),
    db: Session = Depends(get_db),
):
    """Delete an artifact file from disk and remove its database metadata record."""
    delete_artifact_file(artifact, db)
    db.commit()
    return {"ok": True, "id": artifact_id}


@router.delete("/storage/tests/{test_id}")
def delete_test_files(
    test_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete all files and storage folder for a test owned by current user."""
    count = delete_test_artifact_files(user_id=current_user.id, test_id=test_id, db=db)
    db.commit()
    return {"ok": True, "test_id": test_id, "deleted_count": count}


@router.get("/runs/{run_id}/files/{path:path}")
def get_run_file(
    run_id: str,
    path: str,
    request: Request,
    _run: DbRun = Depends(get_owned_run),
):
    """Serve generated screenshots, videos, trace files, and scripts securely with range request support."""
    rdir = storage.run_dir(run_id).resolve()
    target_file = (rdir / path).resolve()

    # Block path traversal outside run folder
    try:
        target_file.relative_to(rdir)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Path traversal blocked")

    # Guard secrets and raw inputs
    if target_file.name in ("secrets.json", "input.json"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not target_file.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    ext = target_file.suffix.lower()
    media_map = {
        ".png": "image/png",
        ".webm": "video/webm",
        ".mp4": "video/mp4",
        ".zip": "application/zip",
        ".json": "application/json",
        ".ts": "text/plain",
        ".md": "text/markdown",
    }
    media_type = media_map.get(ext, "application/octet-stream")
    return stream_file_with_range(target_file, request, media_type=media_type)


@router.get("/runs/{run_id}/app-map")
def get_app_map(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
) -> dict:
    """Retrieve application map node graph and crawled pages."""
    app_map = storage.load_model(run_id, "app_map.json", AppMap)
    run = storage.load_model(run_id, "run.json", Run)
    root_url = run.targetUrl if run else "http://localhost:4000"

    pages_list = []
    nodes_list = []
    if app_map and app_map.pages:
        for idx, p in enumerate(app_map.pages, 1):
            forms_count = len(p.forms) if p.forms else 0
            buttons_count = len(p.buttons) if p.buttons else 0
            links_count = len(p.links) if p.links else 0
            interactive_elems = getattr(p, "interactiveElements", None) or []
            interactive_count = len(interactive_elems) if interactive_elems else (buttons_count + links_count)

            pages_list.append({
                "id": f"page_{idx}",
                "url": p.url,
                "title": p.title or p.url,
                "status_code": getattr(p, "status", 200),
                "depth": 1 if p.url == root_url else 2,
                "forms_count": forms_count,
                "interactive_elements": interactive_count,
            })

            actions = []
            if interactive_elems:
                actions = [f"{getattr(e, 'tag', 'element')} {getattr(e, 'name', '') or getattr(e, 'selector', '')}".strip() for e in interactive_elems[:5]]
            else:
                actions = [f"button {b.text}" for b in (p.buttons or [])[:3]] + [f"link {l.text}" for l in (p.links or [])[:2]]

            nodes_list.append({
                "id": f"node_{idx}",
                "url": p.url,
                "title": p.title or p.url,
                "status_code": getattr(p, "status", 200),
                "actions_found": actions,
                "children": [],
            })

    return {
        "run_id": run_id,
        "root_url": root_url,
        "crawled_at": app_map.generatedAt if app_map else now_iso(),
        "total_pages": len(pages_list),
        "pages": pages_list,
        "nodes": nodes_list,
    }
