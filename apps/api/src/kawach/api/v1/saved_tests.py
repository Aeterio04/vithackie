"""Saved test library management endpoints.

Allows users to save verified test cases to a project's permanent regression suite.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from kawach.api.deps import get_db, get_owned_project, require_scope
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.schemas.saved_tests import SavedTestCreate, SavedTestRead
from kawach.services.saved_test_service import SavedTestService

router = APIRouter(prefix="/projects/{project_id}/saved-tests", tags=["saved-tests"])


@router.get("", response_model=List[SavedTestRead])
def list_saved_tests(
    project_id: str,
    tag: Optional[str] = Query(None, description="Filter tests by tag"),
    _user: User = Depends(require_scope("tests:read")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """List all saved tests in the project's regression library."""
    svc = SavedTestService(db)
    return svc.list_saved_tests(project_id=project_id, tag=tag)


@router.post("", response_model=SavedTestRead, status_code=status.HTTP_201_CREATED)
def save_test(
    project_id: str,
    payload: SavedTestCreate,
    user: User = Depends(require_scope("tests:write")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Save an executed test case to the project's regression library."""
    svc = SavedTestService(db)
    try:
        return svc.save_test(project_id=project_id, payload=payload, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_test(
    project_id: str,
    test_id: str,
    _user: User = Depends(require_scope("tests:write")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Remove a test from the project's regression suite."""
    svc = SavedTestService(db)
    deleted = svc.delete_saved_test(project_id=project_id, test_id=test_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved test {test_id} not found in project {project_id}",
        )
    try:
        from kawach.storage.file_storage import delete_test_artifact_files
        delete_test_artifact_files(user_id=project.owner_id, test_id=test_id, db=db)
    except Exception:
        pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/run-all")
def run_all_saved_tests(
    project_id: str,
    user: User = Depends(require_scope("tests:write")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Run all saved tests for this project on the runner workers."""
    svc = SavedTestService(db)
    try:
        return svc.run_all_saved_tests(project_id=project_id, user_id=user.id, background=True)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{test_id}/run")
def run_single_saved_test(
    project_id: str,
    test_id: str,
    user: User = Depends(require_scope("tests:write")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Run a specific saved test on the runner worker."""
    svc = SavedTestService(db)
    try:
        return svc.run_saved_test(project_id=project_id, test_id=test_id, user_id=user.id, background=True)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
