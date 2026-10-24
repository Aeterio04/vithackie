"""Configuration loading and validation for Kawach Demo Harness."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import SecretStr

from kawach_fix.schemas import normalize_github_repo


def find_and_load_dotenv():
    """Find and load .env from demo folder, workspace root, or current directory."""
    here = Path(__file__).resolve()
    candidate_paths = [
        Path.cwd() / ".env",
        here.parent.parent.parent / ".env",  # kawach_demo/.env
        here.parent.parent.parent.parent / ".env",  # repo root .env
    ]
    for p in candidate_paths:
        if p.is_file():
            load_dotenv(p, override=False)


find_and_load_dotenv()


@dataclass
class DemoConfig:
    """Settings required for running the demo harness."""

    github_pat: SecretStr
    demo_repo: str
    app_clone_path: Path
    target_url: str = "http://localhost:3000"
    groq_api_key: Optional[SecretStr] = None
    gemini_api_key: Optional[SecretStr] = None
    runs_dir: Path = Path("./fix_runs")

    @property
    def secrets_list(self) -> List[SecretStr]:
        """Return all active secrets for redaction filters."""
        res = [self.github_pat]
        if self.groq_api_key:
            res.append(self.groq_api_key)
        if self.gemini_api_key:
            res.append(self.gemini_api_key)
        return res


def load_config() -> DemoConfig:
    """Load and validate demo configuration from environment."""
    find_and_load_dotenv()

    pat_val = os.environ.get("GITHUB_PAT", "").strip()
    if not pat_val:
        raise ValueError("Missing GITHUB_PAT environment variable in .env.")

    repo_val = os.environ.get("DEMO_REPO", "").strip()
    if not repo_val:
        raise ValueError("Missing DEMO_REPO environment variable in .env (e.g. 'owner/kawach-demo-shop').")
    normalized_repo = normalize_github_repo(repo_val)

    clone_str = os.environ.get("APP_CLONE_PATH", "").strip()
    if not clone_str:
        # Default fallback if APP_CLONE_PATH not explicitly set
        candidate_clone = Path("C:/projects/target-app/kawach-demo-shop")
        if candidate_clone.exists():
            clone_path = candidate_clone.resolve()
        else:
            raise ValueError("Missing APP_CLONE_PATH environment variable in .env.")
    else:
        clone_path = Path(clone_str).resolve()

    target_url = os.environ.get("TARGET_URL", "http://localhost:3000").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    runs_dir_str = os.environ.get("KAWACH_FIX_RUNS_DIR", "./fix_runs").strip()

    return DemoConfig(
        github_pat=SecretStr(pat_val),
        demo_repo=normalized_repo,
        app_clone_path=clone_path,
        target_url=target_url,
        groq_api_key=SecretStr(groq_key) if groq_key else None,
        gemini_api_key=SecretStr(gemini_key) if gemini_key else None,
        runs_dir=Path(runs_dir_str).resolve(),
    )
