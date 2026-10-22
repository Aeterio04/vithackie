"""Pytest configuration for backend test suite."""

from pathlib import Path
import sys

# Add apps/api and apps/api/src to sys.path
api_root = Path(__file__).resolve().parent.parent
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))
if str(api_root / "src") not in sys.path:
    sys.path.insert(0, str(api_root / "src"))

from app.models import TestCase

# Instruct pytest not to treat the TestCase Pydantic model as a test suite class
TestCase.__test__ = False
