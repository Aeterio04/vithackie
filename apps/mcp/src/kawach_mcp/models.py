"""Data models for Kawach MCP Server."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class AuthMeInfo(BaseModel):
    """Token scope introspection response model."""
    user_id: Optional[str] = None
    email: Optional[str] = None
    client_type: str = "mcp"
    scopes: List[str] = Field(default_factory=list)
    is_session: bool = False
    token_id: Optional[str] = None
