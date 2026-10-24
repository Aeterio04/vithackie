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
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kawach.core.config import settings
from kawach.core.security import MIN_PASSWORD_LENGTH, hash_password, password_needs_rehash, verify_password
from kawach.db.base import utc_now
from kawach.db.models.identity import RefreshToken, User
from kawach.repositories.audit_repo import AuditRepository

logger = logging.getLogger("kawach.services.auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESERVED_EMAIL_SUFFIX = "@kawach.local"  # internal/system identities; never registrable, never loggable
INVALID_CREDENTIALS = "Invalid email or password"
_dummy_hash: Optional[str] = None


class DuplicateEmailError(ValueError):
    """An account with this email already exists (maps to HTTP 409)."""


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


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
            DuplicateEmailError: the (case-insensitive) email is already registered.
            ValueError: signups are disabled, or the email/password/name is invalid.
        """
        if not settings.ALLOW_SIGNUP:
            raise ValueError("Registration is currently disabled")

        clean_email = normalize_email(email)
        if not clean_email or len(clean_email) > 255 or not EMAIL_RE.match(clean_email):
            raise ValueError("Enter a valid email address")
        if clean_email.endswith(RESERVED_EMAIL_SUFFIX):
            raise ValueError("This email domain is reserved")
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        if len(password) > 128:
            raise ValueError("Password must be at most 128 characters")
        name = (display_name or "").strip()[:100] or clean_email.split("@")[0]

        if self.db.scalar(select(User).where(User.email == clean_email)):
            raise DuplicateEmailError("An account with this email already exists")

        user = User(email=clean_email, password_hash=hash_password(password), display_name=name, is_active=True)
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as e:  # lost a race with a concurrent registration
            self.db.rollback()
            raise DuplicateEmailError("An account with this email already exists") from e
        self.db.refresh(user)

        self.audit_repo.record(action="user_register", user_id=user.id, details={"email": clean_email})
        return user

    def authenticate(self, email: str, password: str) -> User:
        """Authenticate by email + password.

        Every failure (unknown email, wrong password, disabled or reserved account) raises the SAME message
        so callers cannot tell which emails exist.
        """
        global _dummy_hash
        clean_email = normalize_email(email)
        user = None if clean_email.endswith(RESERVED_EMAIL_SUFFIX) else self.db.scalar(
            select(User).where(User.email == clean_email))
        if user is None:  # spend comparable time so response timing does not reveal unknown emails
            _dummy_hash = _dummy_hash or hash_password("kawach-timing-pad")
            verify_password(password or "", _dummy_hash)
            raise ValueError(INVALID_CREDENTIALS)
        if not verify_password(password or "", user.password_hash) or not user.is_active:
            raise ValueError(INVALID_CREDENTIALS)

        if password_needs_rehash(user.password_hash):  # upgrade legacy PBKDF2 hashes transparently
            user.password_hash = hash_password(password)
        user.last_login_at = utc_now()
        self.db.commit()

        self.audit_repo.record(action="login", user_id=user.id, details={"email": clean_email})
        return user
