"""LLM Key Pool monitoring and status endpoints."""

from typing import Any, Dict
from fastapi import APIRouter, Depends

from kawach.api.deps import get_current_user
from kawach.db.models.identity import User
from kawach.llm.key_pool import get_key_pool

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/pool-status", response_model=Dict[str, Any])
def get_pool_status(_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve operational status and health metrics for the multi-key pool.
    
    Protected endpoint: requires valid JWT or API bearer token.
    Never returns secret key values.
    """
    pool = get_key_pool()
    return pool.get_pool_status()
