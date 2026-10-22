"""Authentication endpoints for user registration, login, token refresh, and session logout."""

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from kawach.api.deps import get_current_user
from kawach.db.models.identity import User
from kawach.db.session import get_db
from kawach.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: str
    password: str
    displayName: Optional[str] = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: Optional[str] = None
    username_or_email: Optional[str] = None
    password: str


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    refreshToken: Optional[str] = None


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set secure httpOnly authentication cookies."""
    for cookie_name in ("auth_token", "access_token", "token", "kawach_session", "session"):
        response.set_cookie(
            key=cookie_name,
            value=access_token,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=86400,
        )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=30 * 86400,
    )


def clear_auth_cookies(response: Response) -> None:
    """Clear all authentication cookies on logout."""
    for cookie_name in ("auth_token", "access_token", "token", "kawach_session", "session", "refresh_token"):
        response.delete_cookie(cookie_name, path="/")


@router.post("/auth/register")
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    """Register a new user account with email and password."""
    auth_service = AuthService(db)
    try:
        user = auth_service.register_user(
            email=payload.email,
            password=payload.password,
            display_name=payload.displayName,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    access_token = auth_service.create_access_token(user.id, user.email)
    refresh_token = auth_service.create_refresh_token(user.id)
    set_auth_cookies(response, access_token, refresh_token)

    return {
        "id": user.id,
        "email": user.email,
        "displayName": user.display_name,
        "name": user.display_name,
        "token": access_token,
        "refreshToken": refresh_token,
    }


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Log in with email/password and obtain JWT session and refresh tokens."""
    auth_service = AuthService(db)
    email_cand = payload.email or payload.username_or_email or ""
    if not email_cand:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")

    try:
        user = auth_service.authenticate(email_cand, payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    access_token = auth_service.create_access_token(user.id, user.email)
    refresh_token = auth_service.create_refresh_token(user.id)
    set_auth_cookies(response, access_token, refresh_token)

    return {
        "id": user.id,
        "email": user.email,
        "displayName": user.display_name,
        "name": user.display_name,
        "username": user.email.split("@")[0],
        "token": access_token,
        "refreshToken": refresh_token,
    }


@router.post("/auth/refresh")
def refresh_session(
    payload: Optional[RefreshRequest] = None,
    cookie_token: Optional[str] = Cookie(None, alias="refresh_token"),
    response: Response = None,
    db: Session = Depends(get_db),
):
    """Rotate active refresh token and issue a fresh access token."""
    raw_token = (payload and payload.refreshToken) or cookie_token
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token required")

    auth_service = AuthService(db)
    try:
        user, new_access, new_refresh = auth_service.rotate_refresh_token(raw_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    set_auth_cookies(response, new_access, new_refresh)
    return {
        "token": new_access,
        "refreshToken": new_refresh,
        "user": {
            "id": user.id,
            "email": user.email,
            "displayName": user.display_name,
        },
    }


@router.get("/auth/me")
def auth_me(current_user: User = Depends(get_current_user)):
    """Retrieve current authenticated user profile."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "displayName": current_user.display_name,
        "name": current_user.display_name or current_user.email.split("@")[0],
        "username": current_user.email.split("@")[0],
        "role": "qa_engineer",
        "isActive": current_user.is_active,
    }


@router.post("/auth/logout")
def logout(
    payload: Optional[RefreshRequest] = None,
    cookie_token: Optional[str] = Cookie(None, alias="refresh_token"),
    response: Response = None,
    db: Session = Depends(get_db),
):
    """Log out current user, revoke active refresh token, and clear cookies."""
    raw_token = (payload and payload.refreshToken) or cookie_token
    if raw_token:
        AuthService(db).revoke_refresh_token(raw_token)
    clear_auth_cookies(response)
    return {"ok": True}
