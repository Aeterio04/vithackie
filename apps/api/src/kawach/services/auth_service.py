"""Authentication and session management service.

Handles user registration, authentication, JWT issuing/verification,
and secure refresh token rotation in accordance with Section 7.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from typing import Any, Dict, Optional, Tuple

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.core.config import settings
from kawach.core.security import hash_password, verify_password
from kawach.db.base import utc_now
from kawach.db.models.identity import RefreshToken, User
from kawach.repositories.audit_repo import AuditRepository

logger = logging.getLogger("kawach.services.auth")


class AuthService:
    """Authentication and identity provider service."""

    def __init__(self, db: Session):
        self.db = db
        self.audit_repo = AuditRepository(db)

    def create_access_token(self, user_id: str, email: str) -> str:
        """Create a signed JWT access token for an authenticated user."""
        expire = utc_now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        payload: Dict[str, Any] = {
            "sub": user_id,
            "email": email,
            "exp": expire,
            "iat": utc_now(),
            "iss": "kawach",
        }
        token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        return token

    def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT access token. Return None if expired or invalid."""
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
                issuer="kawach",
            )
            return payload
        except (jwt.PyJWTError, Exception) as e:
            logger.debug(f"Invalid access token: {e}")
            return None

    def create_refresh_token(self, user_id: str) -> str:
        """Generate a cryptographically secure refresh token and persist its hash."""
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = utc_now() + timedelta(days=30)

        record = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(record)
        self.db.commit()
        return raw_token

    def rotate_refresh_token(self, raw_token: str) -> Tuple[User, str, str]:
        """Verify and rotate an active refresh token, issuing a new access and refresh token.

        Raises:
            ValueError: If token is revoked, expired, or invalid.
        """
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = utc_now()

        record = self.db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
        if not record:
            raise ValueError("Invalid or expired refresh token")

        # Revoke old token
        record.revoked_at = now

        # Get user
        user = self.db.get(User, record.user_id)
        if not user or not user.is_active:
            self.db.commit()
            raise ValueError("User account inactive or not found")

        # Create new tokens
        new_access_token = self.create_access_token(user.id, user.email)
        new_refresh_token = self.create_refresh_token(user.id)
        self.db.commit()

        return user, new_access_token, new_refresh_token

    def revoke_refresh_token(self, raw_token: str) -> None:
        """Revoke an active refresh token on logout."""
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        record = self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if record and not record.revoked_at:
            record.revoked_at = utc_now()
            self.db.commit()

    def register_user(
        self,
        email: str,
        password: str,
        display_name: Optional[str] = None,
    ) -> User:
        """Register a new user account.

        Raises:
            ValueError: If signups are disabled, email is taken, or password too short.
        """
        if not settings.ALLOW_SIGNUP:
            raise ValueError("Registration is currently disabled")

        clean_email = email.strip().lower()
        if not clean_email or "@" not in clean_email:
            raise ValueError("Valid email address is required")

        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        existing = self.db.scalar(select(User).where(User.email == clean_email))
        if existing:
            raise ValueError("An account with this email already exists")

        user = User(
            email=clean_email,
            password_hash=hash_password(password),
            display_name=display_name or clean_email.split("@")[0],
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        self.audit_repo.record(
            action="user_register",
            user_id=user.id,
            details={"email": clean_email},
        )
        return user

    def authenticate(self, email: str, password: str) -> User:
        """Authenticate user by email and password.

        Raises:
            ValueError: If credentials are invalid or account is disabled.
        """
        clean_email = email.strip().lower()
        user = self.db.scalar(select(User).where(User.email == clean_email))
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")

        if not user.is_active:
            raise ValueError("Account is disabled")

        user.last_login_at = utc_now()
        self.db.commit()

        self.audit_repo.record(
            action="login",
            user_id=user.id,
            details={"email": clean_email},
        )
        return user
