"""Security utilities: encryption at rest, secret storage, and password hashing."""

import base64
import hashlib
import hmac
import logging
import os
from typing import Optional, Tuple

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
            derived = hashlib.pbkdf2_hmac("sha256", settings.JWT_SECRET.encode(), salt, 100_000)
            self._fernet = Fernet(base64.urlsafe_b64encode(derived[:32]))
            if settings.ENV == "production":
                logger.error("CRITICAL: SECRET_ENCRYPTION_KEY not set in production!")
        else:
            try:
                self._fernet = Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)
            except Exception as e:
                logger.error(f"Invalid SECRET_ENCRYPTION_KEY: {e}. Falling back to derived key.")
                salt = b"kawach_secret_salt_2026"
                derived = hashlib.pbkdf2_hmac("sha256", settings.JWT_SECRET.encode(), salt, 100_000)
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


def hash_password(password: str) -> str:
    """Secure password hashing using PBKDF2-HMAC-SHA256 with random salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}:{key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored salt:hash string using constant-time comparison."""
    if not hashed or ":" not in hashed:
        return False
    try:
        salt_hex, key_hex = hashed.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        candidate_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(expected_key, candidate_key)
    except Exception:
        return False
