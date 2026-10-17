"""Pytest configuration for backend test suite."""

from app.models import TestCase

# Instruct pytest not to treat the TestCase Pydantic model as a test suite class
TestCase.__test__ = False
