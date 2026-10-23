"""Configuration settings for Kawach MCP Server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_token_from_file(explicit_path: Optional[str] = None) -> Optional[str]:
    """Attempt to load token from a 0600-permissioned file.
    
    Checks explicit_path, then ~/.kawach/token, then ~/.config/kawach/token.
    Enforces 0600 permissions on POSIX systems.
    """
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    candidates.append(Path.home() / ".kawach" / "token")
    candidates.append(Path.home() / ".config" / "kawach" / "token")

    for path in candidates:
        if path.is_file():
            # Check POSIX permissions (owner read/write only: 0600 or 0400)
            if os.name != "nt":
                mode = path.stat().st_mode
                if (mode & 0o077) != 0:
                    raise PermissionError(
                        f"Insecure permissions on token file {path}: must be 0600 (owner only)."
                    )
            token = path.read_text(encoding="utf-8").strip()
            if token:
                return token
    return None


class Settings(BaseSettings):
    """MCP Server Settings loaded from environment or secure config file."""

    model_config = SettingsConfigDict(
        env_prefix="KAWACH_",
        case_sensitive=False,
        extra="ignore",
    )

    api_url: str = Field(default="http://localhost:8000", description="Base URL of Kawach HTTP API")
    api_token: Optional[str] = Field(default=None, description="Kawach API Bearer Token (kw_live_...)")
    token_file: Optional[str] = Field(default=None, description="Path to 0600-permissioned file containing API token")
    default_project: Optional[str] = Field(default=None, description="Default project ID or slug for convenience")
    max_response_chars: int = Field(default=4000, description="Max character length for tool and resource responses")
    allow_write_tools: bool = Field(default=False, description="Enable write/mutating tools (save_test, auto_fix, etc.)")
    request_timeout_seconds: float = Field(default=30.0, description="HTTP request timeout in seconds")
    max_retries: int = Field(default=3, description="Max retries for transient HTTP errors (429, 502, 503, 504)")

    # HTTP transport settings
    mcp_transport: str = Field(default="stdio", description="MCP Transport protocol: 'stdio' or 'http'")
    mcp_host: str = Field(default="127.0.0.1", description="Host to bind for HTTP transport")
    mcp_port: int = Field(default=8765, description="Port to bind for HTTP transport")
    mcp_path: str = Field(default="/mcp", description="Path for MCP streamable HTTP endpoint")
    mcp_public_url: Optional[str] = Field(default=None, description="Informational public URL from MCP_PUBLIC_URL")
    allowed_origins: str = Field(default="", description="Comma-separated allowed Origin headers for HTTP mode")
    max_request_body_size: int = Field(default=1048576, description="Max request body size in bytes (1MB)")
    per_caller_concurrency_limit: int = Field(default=10, description="Max concurrent requests per caller token")
    per_request_timeout_seconds: float = Field(default=30.0, description="Per-request execution timeout in HTTP mode")

    def get_effective_token(self) -> Optional[str]:
        """Return token from environment or fallback to secure file."""
        if self.api_token:
            return self.api_token
        return _resolve_token_from_file(self.token_file)

    @property
    def clean_api_url(self) -> str:
        """Normalized API URL without trailing slash."""
        return self.api_url.rstrip("/")

    @property
    def effective_public_url(self) -> Optional[str]:
        """Return MCP public URL from settings or MCP_PUBLIC_URL environment variable."""
        return self.mcp_public_url or os.environ.get("MCP_PUBLIC_URL")

    @property
    def get_allowed_origins(self) -> list[str]:
        """Parsed list of allowed origins from KAWACH_ALLOWED_ORIGINS."""
        raw = self.allowed_origins or os.environ.get("KAWACH_ALLOWED_ORIGINS", "")
        if not raw:
            return []
        return [o.strip() for o in raw.split(",") if o.strip()]


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton getter for application settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def reset_settings() -> None:
    """Reset singleton instance (useful in testing)."""
    global _settings_instance
    _settings_instance = None
