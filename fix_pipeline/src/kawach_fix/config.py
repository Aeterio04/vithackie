"""Configuration settings and constants for Kawach GitHub Fix Pipeline."""

import os
from pathlib import Path
from typing import Set

# Directory where pipeline execution artifacts are saved
DEFAULT_RUNS_DIR = Path(os.environ.get("KAWACH_FIX_RUNS_DIR", "./fix_runs")).resolve()

# Git and PR Conventions
BRANCH_PREFIX = "kawach/fix-"
COMMIT_MSG_PREFIX = "fix(kawach):"
PR_FOOTER = "\n\n---\n*Generated autonomously by Kawach GitHub Fix Pipeline.*"

# File filtering patterns
LOCKFILES: Set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "poetry.lock",
    "Pipfile.lock",
    "requirements.txt.lock",
    "composer.lock",
    "Cargo.lock",
    "go.sum",
}

BINARY_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".7z",
    ".pdf", ".exe", ".bin", ".wasm", ".dll", ".so", ".dylib",
    ".pyc", ".pyo", ".pyd", ".db", ".sqlite",
}

GENERATED_PATH_SNIPPETS: Set[str] = {
    ".min.js",
    ".min.css",
    ".map",
    "/dist/",
    "/build/",
    "/.next/",
    "/out/",
    "/node_modules/",
    "/__pycache__/",
    "/coverage/",
    ".tsbuildinfo",
}
