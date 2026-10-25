"""Compatibility shim forwarding to kawach.main."""

from pathlib import Path
import sys
import time

# Ensure src/ and fix_pipeline/src are on python path
_src_dir = Path(__file__).resolve().parent.parent / "src"
if _src_dir.exists() and str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

_fix_dir = Path(__file__).resolve().parent.parent.parent / "fix_pipeline" / "src"
if _fix_dir.exists() and str(_fix_dir) not in sys.path:
    sys.path.insert(0, str(_fix_dir))

from kawach.api.legacy import (
    _start_execute_background,
    _start_pipeline_background,
)
from kawach.main import app, create_app, lifespan
from kawach.services.spec_parser import parse_spec_text

__all__ = [
    "app",
    "create_app",
    "lifespan",
    "time",
    "parse_spec_text",
    "_start_pipeline_background",
    "_start_execute_background",
]
