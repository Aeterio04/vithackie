"""Authentication endpoints: registration, login (JWT), refresh, session info and logout.

The JWT is returned in the JSON body (for API clients such as the MCP server, sent back as
`Authorization: Bearer <token>`) and also set as an httpOnly cookie (for the website). Protected routes accept either.
"""

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from kawach.api.deps import get_current_user
from kawach.core.config import settings
from kawach.core.ratelimit import FailureLimiter
from kawach.db.models.identity import User
from kawach.db.session import get_db
from kawach.services.auth_service import (INVALID_CREDENTIALS, AuthService, DuplicateEmailError, normalize_email)

router = APIRouter(tags=["auth"])

# Failed-login throttling: tight per email, looser per client IP (shared NATs / test clients).
email_limiter = FailureLimiter(settings.LOGIN_MAX_FAILURES, settings.LOGIN_WINDOW_SECONDS)
ip_limiter = FailureLimiter(settings.LOGIN_MAX_FAILURES * 4, settings.LOGIN_WINDOW_SECONDS)

COOKIE_NAMES = ("auth_token", "access_token", "token", "kawach_session", "session")


def reset_login_limits() -> None:
    """Clear throttling state (used by tests and admin tooling)."""
    email_limiter.clear()
    ip_limiter.clear()


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: str
    password: str
    displayName: Optional[str] = None
    name: Optional[str] = None
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: Optional[str] = None
    username_or_email: Optional[str] = None
    password: str


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    refreshToken: Optional[str] = None


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly, SameSite=Lax session cookies (Secure outside dev)."""
    secure = settings.cookie_secure
    for cookie_name in COOKIE_NAMES:
        response.set_cookie(key=cookie_name, value=access_token, httponly=True, samesite="lax", secure=secure,
                            path="/", max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, samesite="lax", secure=secure,
                        path="/", max_age=30 * 86400)


def clear_auth_cookies(response: Response) -> None:
    for cookie_name in (*COOKIE_NAMES, "refresh_token"):
        response.delete_cookie(cookie_name, path="/")


def user_view(user: User) -> dict:
    """Public user object. Never includes the password hash."""
    return {
        "id": user.id,
        "email": user.email,
        "displayName": user.display_name,
        "name": user.display_name or user.email.split("@")[0],
        "username": user.email.split("@")[0],
        "isActive": user.is_active,
        "createdAt": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
    }


def session_payload(user: User, access_token: str, refresh_token: str) -> dict:
    view = user_view(user)
    return {**view, "user": view, "token": access_token, "access_token": access_token, "token_type": "bearer",
            "refreshToken": refresh_token}


@router.post("/auth/register")
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    """Create an account and sign it in. 409 if the email is taken (case-insensitive)."""
    auth_service = AuthService(db)
    name = payload.displayName or payload.name or payload.display_name
    try:
        user = auth_service.register_user(email=payload.email, password=payload.password, display_name=name)
    except DuplicateEmailError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        code = status.HTTP_403_FORBIDDEN if "disabled" in str(e) else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(status_code=code, detail=str(e))

    access_token = auth_service.create_access_token(user.id, user.email)
    refresh_token = auth_service.create_refresh_token(user.id)
    set_auth_cookies(response, access_token, refresh_token)
    return session_payload(user, access_token, refresh_token)


@router.post("/auth/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Sign in with email + password. Unknown email and wrong password give the same 401."""
    email = normalize_email(payload.email or payload.username_or_email or "")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")

    ip = request.client.host if request.client else "unknown"
    wait = max(email_limiter.retry_after(f"e:{email}") or 0, ip_limiter.retry_after(f"i:{ip}") or 0)
    if wait:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Too many failed sign-in attempts. Try again in {wait} seconds.",
                            headers={"Retry-After": str(wait)})

    auth_service = AuthService(db)
    try:
        user = auth_service.authenticate(email, payload.password)
    except ValueError:
        email_limiter.record_failure(f"e:{email}")
        ip_limiter.record_failure(f"i:{ip}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    email_limiter.reset(f"e:{email}")
    access_token = auth_service.create_access_token(user.id, user.email)
    refresh_token = auth_service.create_refresh_token(user.id)
    set_auth_cookies(response, access_token, refresh_token)
    return session_payload(user, access_token, refresh_token)


@router.post("/auth/refresh")
def refresh_session(
    payload: Optional[RefreshRequest] = None,
    cookie_token: Optional[str] = Cookie(None, alias="refresh_token"),
    response: Response = None,
    db: Session = Depends(get_db),
):
    """Rotate the refresh token and issue a fresh access token."""
    raw_token = (payload and payload.refreshToken) or cookie_token
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token required")

    auth_service = AuthService(db)
    try:
        user, new_access, new_refresh = auth_service.rotate_refresh_token(raw_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    set_auth_cookies(response, new_access, new_refresh)
    return {"token": new_access, "access_token": new_access, "token_type": "bearer", "refreshToken": new_refresh,
            "user": user_view(user)}


@router.get("/auth/me")
def auth_me(current_user: User = Depends(get_current_user)):
    """The signed-in account (cookie or Bearer)."""
    return {**user_view(current_user), "role": "qa_engineer"}


@router.post("/auth/logout")
def logout(
    payload: Optional[RefreshRequest] = None,
    cookie_token: Optional[str] = Cookie(None, alias="refresh_token"),
    response: Response = None,
    db: Session = Depends(get_db),
):
    """Revoke the refresh token and clear the session cookies."""
    raw_token = (payload and payload.refreshToken) or cookie_token
    if raw_token:
        AuthService(db).revoke_refresh_token(raw_token)
    clear_auth_cookies(response)
    return {"ok": True, "message": "Signed out"}
