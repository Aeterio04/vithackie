"""User repository for accounts and identity authentication."""

from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.db.base import utc_now
from kawach.db.models import User
from kawach.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """User account repository."""

    def create_user(
        self,
        email: str,
        password_hash: str,
        display_name: Optional[str] = None,
    ) -> User:
        """Create a new user."""
        user = User(
            email=email.strip().lower(),
            password_hash=password_hash,
            display_name=display_name,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def get_by_email(self, email: str) -> Optional[User]:
        """Lookup user by lowercased email."""
        stmt = select(User).where(User.email == email.strip().lower())
        return self.db.scalars(stmt).first()

    def get_by_id(self, user_id: str) -> Optional[User]:
        """Lookup user by unique ID."""
        return self.db.get(User, user_id)

    def record_login(self, user_id: str) -> None:
        """Update last login timestamp."""
        user = self.get_by_id(user_id)
        if user:
            user.last_login_at = utc_now()
            self.db.flush()
