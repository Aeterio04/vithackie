"""Domain exceptions and standardized error response formatting."""

from typing import Any, Dict, Optional


class KawachError(Exception):
    """Base exception for all domain and platform errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: Optional[Any] = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details


class NotFoundError(KawachError):
    """Raised when a requested resource is not found."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message, code="NOT_FOUND", details=details)


class ConflictError(KawachError):
    """Raised on invalid stage transitions or concurrent conflicts."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message, code="CONFLICT", details=details)


class ValidationError(KawachError):
    """Raised on semantic validation failures."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class SecurityError(KawachError):
    """Raised on path traversal or forbidden access attempts."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message, code="FORBIDDEN", details=details)


class StageTransitionError(ConflictError):
    """Raised when a run cannot transition from current stage to target stage."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Cannot transition from {current} to {target}", details={"from": current, "to": target})


class RunnerError(KawachError):
    """Raised when the execution runner client fails."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message, code="RUNNER_ERROR", details=details)


class LLMError(KawachError):
    """Raised on LLM provider or parsing failures."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message, code="LLM_ERROR", details=details)


def error_envelope(code: str, message: str, details: Optional[Any] = None) -> Dict[str, Any]:
    """Build a uniform error envelope matching Section 4."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
