"""Repository for user database operations.

Data Access Layer for User management.

Pattern:
- All database queries go through repositories
- Endpoints/services call repositories (never SessionLocal directly)
- Repositories handle session management and error handling
- Makes testing easier with repository mocking
"""
from datetime import datetime
from typing import Optional
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.database import SessionLocal
from app.db_models_users import User
from app.utils.logging import logger


class UserRepository:
    """Repository for user database operations.

    Encapsulates all database access for users.
    Provides clean interface for CRUD operations.

    Usage:
        user_repo = UserRepository()
        user_repo.get_user(user_id)
        user_repo.create_user(...)
    """

    @contextmanager
    def _get_session(self) -> Session:
        """Context manager for database sessions.

        Ensures sessions are properly closed even on errors.

        Yields:
            Session: SQLAlchemy database session
        """
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID.

        Args:
            user_id: User ID (Clerk ID)

        Returns:
            User object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(User).filter(User.id == user_id).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get user: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                return None

    def create_user(
        self,
        user_id: str,
        org_id: str,
        email: str,
        tier: str = "free",
        pages_limit: int = 100,
        total_pages_processed: int = 0,
        pages_this_month: int = 0
    ) -> Optional[User]:
        """Create a new user.

        Args:
            user_id: User ID (Clerk ID)
            email: User email address
            tier: Subscription tier (default: "free")
            pages_limit: Page processing limit (default: 100)
            total_pages_processed: Total pages processed (default: 0)
            pages_this_month: Pages processed this month (default: 0)

        Returns:
            User object if successful, None on error (including duplicate)
        """
        with self._get_session() as db:
            try:
                user = User(
                    id=user_id,
                    org_id=org_id,
                    email=email,
                    tier=tier,
                    pages_limit=pages_limit,
                    total_pages_processed=total_pages_processed,
                    pages_this_month=pages_this_month
                )
                db.add(user)
                db.commit()
                db.refresh(user)

                logger.info(
                    f"Created user: {user_id}",
                    extra={"user_id": user_id, "org_id": org_id, "email": email, "tier": tier}
                )

                return user

            except IntegrityError:
                # User already exists (race condition)
                db.rollback()
                logger.debug(
                    f"User {user_id} already exists (IntegrityError)",
                    extra={"user_id": user_id}
                )
                return None
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create user: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                db.rollback()
                return None

    def update_last_login(self, user_id: str) -> bool:
        """Update user's last login timestamp.

        Args:
            user_id: User ID

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    logger.warning(
                        f"User not found for last_login update: {user_id}",
                        extra={"user_id": user_id}
                    )
                    return False

                user.last_login = datetime.now()
                db.commit()

                logger.debug(
                    f"Updated last_login for user {user_id}",
                    extra={"user_id": user_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update last_login: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                db.rollback()
                return False

    def get_or_create_user(
        self,
        user_id: str,
        org_id: str,
        email: str,
        tier: str = "free",
        pages_limit: int = 100
    ) -> Optional[User]:
        """Get existing user or create new one.

        Handles race conditions by attempting to get the user first,
        then creating if not found, then retrying get if creation fails.

        Args:
            user_id: User ID (Clerk ID)
            email: User email address
            tier: Subscription tier (default: "free")
            pages_limit: Page processing limit (default: 100)

        Returns:
            User object, None only on unexpected errors
        """
        # Try to get existing user
        user = self.get_user(user_id)
        if user:
            # Update org_id if changed
            if user.org_id != org_id:
                try:
                    with self._get_session() as db:
                        db_user = db.query(User).filter(User.id == user_id).first()
                        if db_user:
                            db_user.org_id = org_id
                            db.commit()
                except SQLAlchemyError as e:
                    logger.error(
                        "Failed to update user org_id",
                        extra={"user_id": user_id, "org_id": org_id, "error": str(e)}
                    )
            # Update last login and return
            self.update_last_login(user_id)
            return user

        # User doesn't exist - try to create
        user = self.create_user(
            user_id=user_id,
            org_id=org_id,
            email=email,
            tier=tier,
            pages_limit=pages_limit,
            total_pages_processed=0,
            pages_this_month=0
        )

        if user:
            return user

        # Creation failed (likely race condition) - retry get
        logger.warning(
            f"User creation failed, retrying get (race condition): {user_id}",
            extra={"user_id": user_id}
        )
        user = self.get_user(user_id)
        if user:
            self.update_last_login(user_id)
            return user

        # This shouldn't happen - both create and get failed
        logger.error(
            f"Failed to get or create user: {user_id}",
            extra={"user_id": user_id}
        )
        return None

    def update_page_usage(
        self,
        user_id: str,
        pages_to_add: int,
        update_monthly: bool = True
    ) -> bool:
        """Update user's page usage counters.

        Args:
            user_id: User ID
            pages_to_add: Number of pages to add to counters
            update_monthly: Whether to update monthly counter (default: True)

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    logger.warning(
                        f"User not found for page usage update: {user_id}",
                        extra={"user_id": user_id}
                    )
                    return False

                # Update total pages
                user.total_pages_processed = (user.total_pages_processed or 0) + pages_to_add

                # Update monthly pages if requested
                if update_monthly:
                    user.pages_this_month = (user.pages_this_month or 0) + pages_to_add

                db.commit()

                logger.debug(
                    f"Updated page usage for user {user_id}: +{pages_to_add} pages",
                    extra={
                        "user_id": user_id,
                        "pages_added": pages_to_add,
                        "total": user.total_pages_processed,
                        "monthly": user.pages_this_month
                    }
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update page usage: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                db.rollback()
                return False
