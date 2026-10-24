"""Artifact file serving and app-map visualization endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from kawach.api.deps import get_owned_artifact, get_owned_run
from kawach.core.clock import now_iso
from kawach.db.models.artifacts import Artifact
from kawach.db.models.runs import Run as DbRun
from kawach.schemas import AppMap, Run
from kawach.storage import artifacts as storage
from kawach.storage.artifact_store import ArtifactStore

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts/{artifact_id}")
def get_artifact(
    artifact_id: str,
    artifact: Artifact = Depends(get_owned_artifact),
):
    """Serve physical artifact evidence with strict multi-tenant ownership check.
    
    Returns 404 if artifact does not exist or is owned by another user.
    """
    store = ArtifactStore()
    try:
        file_path = store.get_path(artifact.uri)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file missing")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file not found")

    mime = artifact.mime or "application/octet-stream"
    return FileResponse(file_path, media_type=mime, filename=file_path.name)


@router.get("/runs/{run_id}/files/{path:path}")
def get_run_file(run_id: str, path: str):
    """Serve generated screenshots, videos, trace files, and scripts securely."""
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
        ".zip": "application/zip",
        ".json": "application/json",
        ".ts": "text/plain",
        ".md": "text/markdown",
    }
    media_type = media_map.get(ext, "application/octet-stream")
    return FileResponse(target_file, media_type=media_type)


@router.get("/runs/{run_id}/app-map")
def get_app_map(run_id: str) -> dict:
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
