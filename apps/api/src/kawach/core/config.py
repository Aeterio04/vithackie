"""Configuration settings for Autonomous AI QA Engineer (KAWACH).

Grouped settings management powered by pydantic-settings.
"""

from pathlib import Path
from typing import List, Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Root of the repository is 6 directories above apps/api/src/kawach/core/config.py
REPO_ROOT = Path(__file__).resolve().parents[5]


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
    JWT_SECRET: str = "dev-secret-change-in-production-must-be-32-chars-long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ALLOW_SIGNUP: bool = True
    ALLOW_SYSTEM_USER_FALLBACK: bool = False

    # 4. Storage & Persistence
    RUNS_DIR: str = "runs"
    ARTIFACTS_DIR: str = "data/artifacts"

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

    _repo_root: Optional[Path] = None
    _runs_dir: Optional[Path] = None
    _artifacts_dir: Optional[Path] = None

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
    def resolved_database_url(self) -> str:
        """Resolve SQLite relative path to absolute repository root path."""
        if self.DATABASE_URL.startswith("sqlite:///") and not self.DATABASE_URL.startswith("sqlite:////") and ":memory:" not in self.DATABASE_URL:
            rel = self.DATABASE_URL.replace("sqlite:///", "")
            target_path = (self.repo_root / rel).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{target_path.as_posix()}"
        return self.DATABASE_URL


settings = Settings()
