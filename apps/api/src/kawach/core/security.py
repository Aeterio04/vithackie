"""Security utilities: encryption at rest, secret storage, and password hashing."""

import base64
import hashlib
import hmac
import logging
import os
from typing import Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet

from kawach.core.config import settings

logger = logging.getLogger("kawach.security")


class SecretStore:
    """Fernet-based symmetric encryption store for credentials and tokens at rest."""

    def __init__(self, key: Optional[str] = None):
        raw_key = key or settings.SECRET_ENCRYPTION_KEY
        if not raw_key:
            # For development & testing convenience, derive stable key from JWT_SECRET
            salt = b"kawach_secret_salt_2026"
            derived = hashlib.pbkdf2_hmac("sha256", settings.secret_store_basis.encode(), salt, 100_000)
            self._fernet = Fernet(base64.urlsafe_b64encode(derived[:32]))
            if settings.ENV == "production":
                logger.error("CRITICAL: SECRET_ENCRYPTION_KEY not set in production!")
        else:
            try:
                self._fernet = Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)
            except Exception as e:
                logger.error(f"Invalid SECRET_ENCRYPTION_KEY: {e}. Falling back to derived key.")
                salt = b"kawach_secret_salt_2026"
                derived = hashlib.pbkdf2_hmac("sha256", settings.secret_store_basis.encode(), salt, 100_000)
                self._fernet = Fernet(base64.urlsafe_b64encode(derived[:32]))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string into base64 ciphertext string."""
        if not plaintext:
            return ""
        encrypted_bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64 ciphertext string into plaintext string."""
        if not ciphertext:
            return ""
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}") from e

    @staticmethod
    def mask_token(token: Optional[str]) -> str:
        """Mask token returning only the last 4 characters for API responses."""
        if not token:
            return ""
        if len(token) <= 4:
            return "****"
        return f"...{token[-4:]}"

def mask_token(token: Optional[str]) -> str:
    """Mask token returning only the last 4 characters for API responses."""
    return SecretStore.mask_token(token)


secret_store = SecretStore()


def constant_time_compare(val1: str, val2: str) -> bool:
    """Constant-time string comparison preventing timing attacks."""
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))


_ph = PasswordHasher()  # argon2id with the library's recommended parameters
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Hash a password with argon2id (random salt, self-describing parameters)."""
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password. Understands argon2 hashes and the legacy PBKDF2 `salt:key` format."""
    if not hashed:
        return False
    if hashed.startswith("$argon2"):
        try:
            return _ph.verify(hashed, password)
        except (VerifyMismatchError, InvalidHashError, VerificationError):
            return False
    if ":" in hashed:  # legacy PBKDF2-HMAC-SHA256, kept so existing accounts can still log in
        try:
            salt_hex, key_hex = hashed.split(":", 1)
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 100_000)
            return hmac.compare_digest(bytes.fromhex(key_hex), candidate)
        except Exception:
            return False
    return False


def password_needs_rehash(hashed: str) -> bool:
    """True for legacy hashes or argon2 hashes with outdated parameters (upgrade on next login)."""
    if not hashed or not hashed.startswith("$argon2"):
        return True
    try:
        return _ph.check_needs_rehash(hashed)
    except Exception:
        return True
