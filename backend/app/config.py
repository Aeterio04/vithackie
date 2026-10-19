"""Configuration settings for Autonomous AI QA Engineer backend."""

import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Root of the repository is two directories above backend/app
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOTENV_PATH = REPO_ROOT / ".env"
load_dotenv(DOTENV_PATH)


class Settings:
    """Parsed application settings matching CONTRACTS section 2."""

    def __init__(self) -> None:
        self.repo_root: Path = REPO_ROOT

        runs_name = os.getenv("RUNS_DIR", "runs")
        self.runs_dir: Path = (REPO_ROOT / runs_name).resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)

        self.LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
        self.LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
        self.ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

        self.LLM_PRICE_IN_PER_MTOK: float = float(os.getenv("LLM_PRICE_IN_PER_MTOK", "0"))
        self.LLM_PRICE_OUT_PER_MTOK: float = float(os.getenv("LLM_PRICE_OUT_PER_MTOK", "0"))
        self.LLM_CACHE: str = os.getenv("LLM_CACHE", "on")

        allowed_raw = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1")
        self.ALLOWED_HOSTS: List[str] = [h.strip() for h in allowed_raw.split(",") if h.strip()]

        self.MAX_PAGES: int = int(os.getenv("MAX_PAGES", "10"))
        self.EXPLORE_SECONDS: int = int(os.getenv("EXPLORE_SECONDS", "90"))
        self.MAX_TESTS: int = int(os.getenv("MAX_TESTS", "12"))
        self.TEST_TIMEOUT_MS: int = int(os.getenv("TEST_TIMEOUT_MS", "30000"))
        self.RUNS_DIR: str = runs_name
        self.STUB_MODE: int = int(os.getenv("STUB_MODE", "0"))
        self.VERIFY_PARALLEL: int = int(os.getenv("VERIFY_PARALLEL", "1"))
        self.BUGS_OFF: str = os.getenv("BUGS_OFF", "")


settings = Settings()
