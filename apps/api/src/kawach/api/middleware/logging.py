"""HTTP Request logging middleware (protects credentials by never logging bodies)."""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("kawach.api")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log incoming HTTP request method, path, response code, and latency, attaching X-Request-Id."""

    async def dispatch(self, request: Request, call_next):
        import uuid
        from fastapi.responses import JSONResponse
        from kawach.core.config import settings

        request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id
        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.exception(f"Unhandled exception on {request.method} {request.url.path} [req={request_id}]: {exc}")
            msg = str(exc) if settings.DEBUG else "An unexpected error occurred"
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": msg,
                        "requestId": request_id,
                    }
                },
            )

        response.headers["X-Request-Id"] = request_id
        duration_ms = round((time.time() - start_time) * 1000, 1)
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms) [req={request_id}]"
        )
        return response
