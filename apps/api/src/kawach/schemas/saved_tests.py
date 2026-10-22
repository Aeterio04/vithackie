# SCAFFOLD: not implemented
"""Pydantic wire models for saved test library and regression selection.

Scaffolded schemas supporting Section 8 / Appendix A product flow.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SavedTestCreate(BaseModel):
    """Payload to save an executed test case to a project's regression library."""

    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(description="Run ID from which the test originated")
    test_id: str = Field(description="Test case ID (e.g. T01)")
    name: Optional[str] = Field(default=None, description="Optional custom name for saved test")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")


class SavedTestRead(BaseModel):
    """Saved test model returned to clients."""

    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    origin_run_id: Optional[str] = None
    origin_test_case_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    script_path: str
    tags: List[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class SavedTestCoverageItem(BaseModel):
    """Mapping between a saved test and the application page/component it exercises."""

    model_config = ConfigDict(extra="ignore")

    saved_test_id: str
    page_url_pattern: str
    component_name: Optional[str] = None


class RunSelectedTestsRequest(BaseModel):
    """Request to trigger execution for a subset of saved tests."""

    model_config = ConfigDict(extra="ignore")

    test_ids: List[str] = Field(default_factory=list, description="Explicit test IDs or empty for diff-selected")
    commit_sha: Optional[str] = Field(default=None, description="Commit SHA triggering the regression")


class RunSelectedTestsResponse(BaseModel):
    """Response initiating a regression test run."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    selected_test_count: int
    selection_strategy: str  # diff_aware | full_suite | explicit
