"""Pydantic schemas for API token authentication and management."""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

ApiClient = Literal["web", "github", "mcp"]


class ApiTokenCreate(BaseModel):
    """Payload to create a new scoped API token."""
    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., min_length=1, max_length=100, description="Descriptive token label")
    scopes: List[str] = Field(default_factory=lambda: ["read", "write"], description="Authorized access scopes")
    expires_in_days: Optional[int] = Field(default=30, ge=1, le=365, description="Token validity duration in days")


class ApiTokenRead(BaseModel):
    """Public metadata for an API token (hash never exposed)."""
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    token_prefix: str
    scopes: List[str]
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None
    last_used_at: Optional[str] = None
    created_at: str


class ApiTokenCreated(ApiTokenRead):
    """Returned once upon token creation; contains plaintext bearer secret."""
    token_secret: str = Field(..., description="Full bearer token secret; displayed once and cannot be recovered")
