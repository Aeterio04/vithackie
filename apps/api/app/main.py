"""Compatibility shim forwarding to kawach.main."""

import time

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
