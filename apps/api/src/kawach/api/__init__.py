"""API layer package for KAWACH."""

from kawach.api.legacy import router as legacy_router
from kawach.api.v1.router import router as v1_router

__all__ = ["legacy_router", "v1_router"]
