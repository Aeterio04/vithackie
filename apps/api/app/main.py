"""Compatibility shim forwarding to kawach.main."""

from pathlib import Path
import sys
import time

# Ensure src/ is on python path so kawach is importable
_src_dir = Path(__file__).resolve().parent.parent / "src"
if _src_dir.exists() and str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

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
