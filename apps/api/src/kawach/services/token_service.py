"""Service layer for API token lifecycle management and verification."""

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from kawach.db.models import ApiToken, User
from kawach.repositories.audit_repo import AuditRepository
from kawach.repositories.base import Scope
from kawach.repositories.token_repo import ApiTokenRepository
from kawach.schemas.tokens import ApiTokenCreated, ApiTokenRead


class ApiTokenService:
    """Business logic for creating, hashing, auditing, and validating API tokens."""

    def __init__(self, db: Session):
        self.db = db
        self.token_repo = ApiTokenRepository(db)
        self.audit_repo = AuditRepository(db)

    def create_token(
        self,
        scope: Scope,
        name: str,
        scopes: Optional[List[str]] = None,
        expires_in_days: Optional[int] = 30,
        client_type: str = "web",
    ) -> ApiTokenCreated:
        """Create a new high-entropy API token, store SHA-256 hash at rest, and return secret."""
        effective_scopes = scopes or ["read", "write"]
        scopes_str = ",".join(effective_scopes)

        # Generate cryptographic bearer secret: kw_live_<48 hex chars>
        raw_secret = f"kw_live_{secrets.token_hex(24)}"
        token_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
        token_prefix = f"{raw_secret[:11]}..."

        expires_at: Optional[datetime] = None
        if expires_in_days is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        token_record = self.token_repo.create_token(
            scope=scope,
            name=name,
            token_prefix=token_prefix,
            token_hash=token_hash,
            scopes=scopes_str,
            expires_at=expires_at,
        )

        # Audit log creation
        self.audit_repo.record(
            action="token_create",
            entity_type="api_token",
            entity_id=token_record.id,
            user_id=scope.user_id,
            metadata={"token_name": name, "scopes": effective_scopes},
            client_type=client_type,
        )

        return ApiTokenCreated(
            id=token_record.id,
            name=token_record.name,
            token_prefix=token_record.token_prefix,
            scopes=effective_scopes,
            expires_at=token_record.expires_at.isoformat() if token_record.expires_at else None,
            revoked_at=None,
            last_used_at=None,
            created_at=token_record.created_at.isoformat(),
            token_secret=raw_secret,
        )

    def list_tokens(self, scope: Scope) -> List[ApiTokenRead]:
        """List active and revoked tokens for authenticated user."""
        records = self.token_repo.list_tokens(scope, include_revoked=True)
        return [
            ApiTokenRead(
                id=r.id,
                name=r.name,
                token_prefix=r.token_prefix,
                scopes=[s.strip() for s in r.scopes.split(",") if s.strip()],
                expires_at=r.expires_at.isoformat() if r.expires_at else None,
                revoked_at=r.revoked_at.isoformat() if r.revoked_at else None,
                last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
                created_at=r.created_at.isoformat(),
            )
            for r in records
        ]

    def revoke_token(self, scope: Scope, token_id: str, client_type: str = "web") -> bool:
        """Revoke a token and write audit entry."""
        success = self.token_repo.revoke_token(scope, token_id)
        if success:
            self.audit_repo.record(
                action="token_revoke",
                entity_type="api_token",
                entity_id=token_id,
                user_id=scope.user_id,
                client_type=client_type,
            )
        return success

    def verify_token(self, token_str: str) -> Optional[Tuple[User, List[str], str]]:
        """Verify bearer token against SHA-256 hash. Returns (User, scopes, token_id) or None."""
        if not token_str or not token_str.startswith("kw_"):
            return None

        token_hash = hashlib.sha256(token_str.encode("utf-8")).hexdigest()
        tok = self.token_repo.get_by_hash(token_hash)
        if not tok:
            return None

        user = self.db.get(User, tok.user_id)
        if not user or not user.is_active:
            return None

        self.token_repo.touch_token(tok.id)
        scopes = [s.strip() for s in tok.scopes.split(",") if s.strip()]
        return user, scopes, tok.id
