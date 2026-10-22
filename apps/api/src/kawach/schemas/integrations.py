# SCAFFOLD: not implemented
"""Pydantic wire models for external integrations (GitHub, Webhooks).

Scaffolded schemas supporting Section 8 / Appendix A product flow.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class GitHubIntegrationCreate(BaseModel):
    """Configuration to connect a GitHub repository with KAWACH."""

    model_config = ConfigDict(extra="ignore")

    repo_url: str = Field(description="Full GitHub repository URL (e.g. https://github.com/org/repo)")
    default_branch: str = Field(default="main", description="Target primary branch")
    github_token: str = Field(description="Fine-grained Personal Access Token with repo read / pull_request write")
    webhook_secret: Optional[str] = Field(default=None, description="Optional custom webhook secret")


class GitHubIntegrationRead(BaseModel):
    """Metadata response for configured GitHub integration."""

    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    provider: str = "github"
    repo_url: str
    default_branch: str
    webhook_active: bool
    created_at: datetime
    updated_at: datetime


class GitHubWebhookPayload(BaseModel):
    """Partial representation of GitHub push / PR webhook payload."""

    model_config = ConfigDict(extra="ignore")

    ref: Optional[str] = None
    before: Optional[str] = None
    after: Optional[str] = None
    repository: Optional[Dict[str, Any]] = None
    pusher: Optional[Dict[str, Any]] = None
    commits: Optional[list] = None
    head_commit: Optional[Dict[str, Any]] = None
