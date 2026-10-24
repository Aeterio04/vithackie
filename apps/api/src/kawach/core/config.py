"""Configuration settings for Autonomous AI QA Engineer (KAWACH).

Grouped settings management powered by pydantic-settings.
"""

import logging
import os
import secrets
from pathlib import Path
from typing import List, Optional, Union

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Root of the repository is 6 directories above apps/api/src/kawach/core/config.py
REPO_ROOT = Path(__file__).resolve().parents[5]

# The historical default JWT secret. It is NOT accepted as a signing secret any more; it is kept only so the
# credential vault can still decrypt secrets that were encrypted with the key derived from it (dev installs
# that never set JWT_SECRET / SECRET_ENCRYPTION_KEY).
LEGACY_DEV_SECRET = "dev-secret-change-in-production-must-be-32-chars-long"
DEV_ENVS = ("dev", "development", "test", "testing", "local")
_log = logging.getLogger("kawach.config")


class Settings(BaseSettings):
    """Application settings grouped according to Section 11 specifications."""

    model_config = SettingsConfigDict(
        env_file=(
            str(REPO_ROOT / ".env"),
            str(REPO_ROOT / "apps" / "api" / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 1. App Configuration
    ENV: str = "development"
    DEBUG: bool = True
    LEGACY_ROUTES: bool = True

    # 2. Database
    DATABASE_URL: str = "sqlite:///data/kawach.db"

    # 3. Authentication & Sessions
    JWT_SECRET: str = ""  # required outside dev; in dev an unset value is generated and persisted
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ALLOW_SIGNUP: bool = True
    ALLOW_SYSTEM_USER_FALLBACK: bool = False  # DEPRECATED and ignored: unauthenticated requests are always 401
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_WINDOW_SECONDS: int = 60
    COOKIE_SECURE: Optional[bool] = None  # default: secure cookies outside dev

    # 4. Storage & Persistence
    RUNS_DIR: str = "runs"
    ARTIFACTS_DIR: str = "data/artifacts"
    STORAGE_BASE_DIR: str = "storage"

    # 5. Security & Network Sandboxing
    SECRET_ENCRYPTION_KEY: str = ""
    ALLOWED_HOSTS: Union[List[str], str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )

    # 6. LLM Engine & Provider
    LLM_PROVIDER: str = "groq"
    LLM_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_DEFAULT_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_FALLBACK_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_API_KEY: str = ""
    GROQ_RPM_LIMIT: int = 30
    GROQ_TPM_LIMIT: int = 6000
    GROQ_MIN_INTERVAL: float = 2.0
    GROQ_DEFAULT_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_FALLBACK_MODEL: str = "llama-3.1-8b-instant"
    GEMINI_API_KEY: str = ""
    GEMINI_DEFAULT_MODEL: str = "gemini-3.8-flash"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_PRICE_IN_PER_MTOK: float = 0.0
    LLM_PRICE_OUT_PER_MTOK: float = 0.0
    LLM_CACHE: str = "on"
    STUB_MODE: int = 0

    # 7. Runner & Exploration Limits
    MAX_PAGES: int = 10
    EXPLORE_SECONDS: int = 90
    MAX_TESTS: int = 12
    TEST_TIMEOUT_MS: int = 30000
    VERIFY_PARALLEL: int = 1
    BUGS_OFF: str = ""

    # 8. GitHub Integration & Webhooks
    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # 9. Automated Fix Policies
    FIX_POLICY_MAX_FILES: int = 1
    FIX_POLICY_MAX_LINES: int = 20
    FIX_POLICY_FORBIDDEN_PATHS: Union[List[str], str] = Field(
        default_factory=lambda: ["auth", "payment", "migrations"]
    )

    @field_validator("ALLOWED_HOSTS", mode="after")
    @classmethod
    def _parse_allowed_hosts(cls, val: Union[List[str], str]) -> List[str]:
        if isinstance(val, str):
            return [h.strip() for h in val.split(",") if h.strip()]
        return val

    @field_validator("FIX_POLICY_FORBIDDEN_PATHS", mode="after")
    @classmethod
    def _parse_forbidden_paths(cls, val: Union[List[str], str]) -> List[str]:
        if isinstance(val, str):
            return [p.strip() for p in val.split(",") if p.strip()]
        return val

    @model_validator(mode="after")
    def _ensure_jwt_secret(self) -> "Settings":
        """Never sign tokens with a well-known secret. Refuse to start outside dev; generate one in dev."""
        self._secret_was_explicit = bool(self.JWT_SECRET) and self.JWT_SECRET != LEGACY_DEV_SECRET
        if self._secret_was_explicit:
            if len(self.JWT_SECRET) < 32 and self.ENV.lower() not in DEV_ENVS:
                raise ValueError("JWT_SECRET must be at least 32 characters outside dev.")
            return self
        if self.ENV.lower() not in DEV_ENVS:
            raise ValueError("JWT_SECRET is required when ENV is not a dev environment. "
                             "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
        # dev: persist a generated secret so tokens survive restarts (file is under the git-ignored data/ dir)
        path = REPO_ROOT / "data" / ".jwt_secret"
        try:
            if path.exists() and len(path.read_text().strip()) >= 32:
                self.JWT_SECRET = path.read_text().strip()
            else:
                self.JWT_SECRET = secrets.token_urlsafe(48)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(self.JWT_SECRET)
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
        except OSError:
            self.JWT_SECRET = secrets.token_urlsafe(48)
        _log.warning("JWT_SECRET is not set; using a generated development secret (set JWT_SECRET in .env for stable deployments).")
        return self

    @property
    def secret_store_basis(self) -> str:
        """Key material for the credential vault when SECRET_ENCRYPTION_KEY is unset (keeps old secrets readable)."""
        return self.JWT_SECRET if self._secret_was_explicit else LEGACY_DEV_SECRET

    @property
    def cookie_secure(self) -> bool:
        return self.COOKIE_SECURE if self.COOKIE_SECURE is not None else self.ENV.lower() not in DEV_ENVS

    _secret_was_explicit: bool = False
    _repo_root: Optional[Path] = None
    _runs_dir: Optional[Path] = None
    _artifacts_dir: Optional[Path] = None
    _storage_dir: Optional[Path] = None

    @property
    def repo_root(self) -> Path:
        return self._repo_root if self._repo_root is not None else REPO_ROOT

    @repo_root.setter
    def repo_root(self, val: Path) -> None:
        self._repo_root = Path(val).resolve()

    @property
    def runs_dir(self) -> Path:
        if self._runs_dir is not None:
            return self._runs_dir
        p = (self.repo_root / self.RUNS_DIR).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @runs_dir.setter
    def runs_dir(self, val: Path) -> None:
        self._runs_dir = Path(val).resolve()

    @property
    def artifacts_dir(self) -> Path:
        if self._artifacts_dir is not None:
            return self._artifacts_dir
        p = (self.repo_root / self.ARTIFACTS_DIR).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @artifacts_dir.setter
    def artifacts_dir(self, val: Path) -> None:
        self._artifacts_dir = Path(val).resolve()

    @property
    def storage_dir(self) -> Path:
        if self._storage_dir is not None:
            return self._storage_dir
        p = (self.repo_root / self.STORAGE_BASE_DIR).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @storage_dir.setter
    def storage_dir(self, val: Path) -> None:
        self._storage_dir = Path(val).resolve()

    @property
    def resolved_database_url(self) -> str:
        """Resolve SQLite relative path to absolute repository root path."""
        if self.DATABASE_URL.startswith("sqlite:///") and not self.DATABASE_URL.startswith("sqlite:////") and ":memory:" not in self.DATABASE_URL:
            rel = self.DATABASE_URL.replace("sqlite:///", "")
            target_path = (self.repo_root / rel).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{target_path.as_posix()}"
        return self.DATABASE_URL


import os

settings = Settings()

# Propagate LLM and provider keys into os.environ for fix_pipeline clients
if settings.GROQ_API_KEY and not os.environ.get("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = settings.GROQ_API_KEY
if settings.GEMINI_API_KEY and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY
if settings.ANTHROPIC_API_KEY and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY
if settings.OPENAI_API_KEY and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
