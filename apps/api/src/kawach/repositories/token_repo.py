"""Repository for managing personal API tokens and MCP authentication."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.db.models import ApiToken
from kawach.repositories.base import BaseRepository, Scope


class ApiTokenRepository(BaseRepository):
    """Data access methods for scoped API tokens."""

    def create_token(
        self,
        scope: Scope,
        name: str,
        token_prefix: str,
        token_hash: str,
        scopes: str = "read,write",
        expires_at: Optional[datetime] = None,
    ) -> ApiToken:
        """Create a new API token record owned by scope.user_id."""
        user_id = scope.user_id or "system"
        tok = ApiToken(
            user_id=user_id,
            name=name,
            token_prefix=token_prefix,
            token_hash=token_hash,
            scopes=scopes,
            expires_at=expires_at,
        )
        self.db.add(tok)
        self.db.commit()
        self.db.refresh(tok)
        return tok

    def list_tokens(self, scope: Scope, include_revoked: bool = False) -> List[ApiToken]:
        """List tokens belonging to the authenticated user."""
        stmt = select(ApiToken).where(ApiToken.user_id == scope.user_id)
        if not include_revoked:
            stmt = stmt.where(ApiToken.revoked_at.is_(None))
        stmt = stmt.order_by(ApiToken.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def get_token(self, scope: Scope, token_id: str) -> Optional[ApiToken]:
        """Get a single token owned by user_id."""
        stmt = select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == scope.user_id,
        )
        return self.db.scalar(stmt)

    def get_by_hash(self, token_hash: str) -> Optional[ApiToken]:
        """Lookup active, unrevoked, unexpired token by its SHA-256 hash."""
        now = datetime.now(timezone.utc)
        stmt = select(ApiToken).where(
            ApiToken.token_hash == token_hash,
            ApiToken.revoked_at.is_(None),
        )
        tok = self.db.scalar(stmt)
        if not tok:
            return None

        # Check expiration
        if tok.expires_at:
            exp = tok.expires_at if tok.expires_at.tzinfo else tok.expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return None
        return tok

    def revoke_token(self, scope: Scope, token_id: str) -> bool:
        """Revoke a token owned by user_id."""
        tok = self.get_token(scope, token_id)
        if not tok or tok.revoked_at is not None:
            return False
        tok.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    def touch_token(self, token_id: str) -> None:
        """Record last_used_at timestamp on valid token invocation."""
        tok = self.db.get(ApiToken, token_id)
        if tok:
            tok.last_used_at = datetime.now(timezone.utc)
            self.db.commit()
