"""Environment-driven settings. Secrets are held as SecretStr and never described."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

AuthMode = Literal["token", "login", "guest"]


class Settings(BaseModel):
    base_url: str = "http://localhost:8000"
    email: Optional[str] = None
    password: Optional[SecretStr] = None
    token: Optional[SecretStr] = None
    timeout_seconds: float = Field(default=30, gt=0)
    download_dir: Path = Path("./kawach_downloads")
    log_level: str = "INFO"

    @property
    def auth_mode(self) -> AuthMode:
        if self.token and self.token.get_secret_value():
            return "token"
        if self.email and self.password and self.password.get_secret_value():
            return "login"
        return "guest"

    def describe(self) -> dict:
        """Safe summary with no secrets."""
        return {
            "base_url": self.base_url,
            "auth_mode": self.auth_mode,
            "email": self.email if self.auth_mode == "login" else None,
            "timeout_seconds": self.timeout_seconds,
            "download_dir": str(self.download_dir),
            "log_level": self.log_level,
        }

    @classmethod
    def from_env(cls) -> "Settings":
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)
        e = os.environ
        return cls(
            base_url=(e.get("KAWACH_BASE_URL") or "http://localhost:8000").strip().rstrip("/"),
            email=(e.get("KAWACH_EMAIL") or None),
            password=SecretStr(e["KAWACH_PASSWORD"]) if e.get("KAWACH_PASSWORD") else None,
            token=SecretStr(e["KAWACH_TOKEN"]) if e.get("KAWACH_TOKEN") else None,
            timeout_seconds=float(e.get("KAWACH_TIMEOUT_SECONDS") or 30),
            download_dir=Path(e.get("KAWACH_DOWNLOAD_DIR") or "./kawach_downloads"),
            log_level=(e.get("KAWACH_LOG_LEVEL") or "INFO").upper(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
