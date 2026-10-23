"""API token management routes for MCP and CLI access."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from kawach.api.deps import get_client_type, get_db, require_session_auth
from kawach.db.models.identity import User
from kawach.repositories.base import Scope
from kawach.schemas.tokens import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from kawach.services.token_service import ApiTokenService

router = APIRouter(prefix="/auth/tokens", tags=["auth-tokens"])


@router.post("", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(
    payload: ApiTokenCreate,
    current_user: User = Depends(require_session_auth),
    db: Session = Depends(get_db),
    client_type: str = Depends(get_client_type),
) -> ApiTokenCreated:
    """Create a new personal API token.
    
    The plaintext bearer secret (kw_live_...) is returned ONCE upon creation.
    Only its SHA-256 hash is retained on the server.
    """
    token_svc = ApiTokenService(db)
    scope = Scope(user_id=current_user.id)
    return token_svc.create_token(
        scope=scope,
        name=payload.name,
        scopes=payload.scopes,
        expires_in_days=payload.expires_in_days,
        client_type=client_type,
    )


@router.get("", response_model=List[ApiTokenRead])
def list_tokens(
    current_user: User = Depends(require_session_auth),
    db: Session = Depends(get_db),
) -> List[ApiTokenRead]:
    """List all active and revoked API tokens belonging to the authenticated user."""
    token_svc = ApiTokenService(db)
    scope = Scope(user_id=current_user.id)
    return token_svc.list_tokens(scope)


@router.delete("/{token_id}", response_model=dict)
def revoke_token(
    token_id: str,
    current_user: User = Depends(require_session_auth),
    db: Session = Depends(get_db),
    client_type: str = Depends(get_client_type),
) -> dict:
    """Revoke an existing API token. Immediate and irreversible."""
    token_svc = ApiTokenService(db)
    scope = Scope(user_id=current_user.id)
    success = token_svc.revoke_token(scope, token_id, client_type=client_type)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API token not found or already revoked",
        )
    return {"ok": True, "message": "Token revoked successfully"}
