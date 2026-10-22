"""HTTP Request logging middleware (protects credentials by never logging bodies)."""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("kawach.api")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log incoming HTTP request method, path, response code, and latency."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 1)
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)"
        )
        return response
