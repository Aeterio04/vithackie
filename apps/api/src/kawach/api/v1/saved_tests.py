# SCAFFOLD: not implemented
"""Saved test library management endpoints (501 Scaffold).

Per Section 8 / Appendix A specifications:
Allows users to save verified test cases to a project's permanent regression suite.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from kawach.api.deps import get_db, get_owned_project, require_scope
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.schemas.saved_tests import SavedTestCreate, SavedTestRead

router = APIRouter(prefix="/projects/{project_id}/saved-tests", tags=["saved-tests"])


@router.get("", response_model=List[SavedTestRead])
def list_saved_tests(
    project_id: str,
    _user: User = Depends(require_scope("tests:read")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """List all saved tests in the project's regression library."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Saved test library is scaffolded but not implemented in this phase.",
    )


@router.post("", response_model=SavedTestRead, status_code=status.HTTP_201_CREATED)
def save_test(
    project_id: str,
    payload: SavedTestCreate,
    _user: User = Depends(require_scope("tests:write")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Save an executed test case to the project's regression library."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Saving tests to library is scaffolded but not implemented in this phase.",
    )


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_test(
    project_id: str,
    test_id: str,
    _user: User = Depends(require_scope("tests:write")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Remove a test from the project's regression suite."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Deleting saved tests is scaffolded but not implemented in this phase.",
    )
