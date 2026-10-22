"""Base repository definition and multi-tenant user Scope abstraction."""

from dataclasses import dataclass
from typing import Optional
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Scope:
    """Multi-user ownership scope.

    Enforces that queries only access resources owned by the user,
    or allows system bypass when is_system=True.
    """
    user_id: Optional[str] = None
    is_system: bool = False

    @classmethod
    def system(cls) -> "Scope":
        """Factory for system background tasks or migrations."""
        return cls(user_id=None, is_system=True)

    @classmethod
    def user(cls, user_id: str) -> "Scope":
        """Factory for authenticated user requests."""
        return cls(user_id=user_id, is_system=False)


class BaseRepository:
    """Base repository holding database session."""

    def __init__(self, db: Session):
        self.db = db
