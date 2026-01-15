"""Authentication service for PRDForge.

Provides authentication and authorization functionality.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.db.models import AuditAction, Session, User, UserRole
from src.db.user_repository import (
    AuditLogRepository,
    SessionRepository,
    UserRepository,
)

if TYPE_CHECKING:
    from src.db.database import Database


@dataclass
class AuthResult:
    """Result of an authentication attempt.

    Attributes:
        success: Whether authentication succeeded.
        user: Authenticated user (if success).
        session: Created session (if success).
        error: Error message (if failure).
    """

    success: bool
    user: User | None = None
    session: Session | None = None
    error: str | None = None


@dataclass
class CurrentUser:
    """Current authenticated user context.

    Attributes:
        user: The authenticated user.
        session: Active session.
        is_admin: Whether user has admin role.
        is_viewer: Whether user has viewer role (read-only).
    """

    user: User
    session: Session

    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.user.role == UserRole.ADMIN

    @property
    def is_viewer(self) -> bool:
        """Check if user is viewer (read-only)."""
        return self.user.role == UserRole.VIEWER

    @property
    def can_write(self) -> bool:
        """Check if user can perform write operations."""
        return self.user.role in [UserRole.ADMIN, UserRole.USER]


class AuthService:
    """Service for authentication and authorization.

    Features:
    - User authentication (login/logout)
    - Session management
    - Role-based access control
    - Audit logging
    """

    def __init__(self, db: "Database"):
        """Initialize authentication service.

        Args:
            db: Database instance.
        """
        self.db = db
        self.user_repo = UserRepository(db)
        self.session_repo = SessionRepository(db)
        self.audit_repo = AuditLogRepository(db)

    def login(
        self,
        username: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuthResult:
        """Authenticate a user and create a session.

        Args:
            username: Username or email.
            password: Password.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            AuthResult with success status and session.
        """
        user = self.user_repo.authenticate(username, password)

        if not user:
            self.audit_repo.log(
                action=AuditAction.USER_LOGIN,
                details={"username": username, "success": False},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return AuthResult(success=False, error="Invalid username or password")

        # Create session
        session = self.session_repo.create(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.audit_repo.log(
            action=AuditAction.USER_LOGIN,
            resource_type="user",
            resource_id=str(user.id),
            user_id=user.id,
            details={"username": user.username, "success": True},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return AuthResult(success=True, user=user, session=session)

    def logout(
        self,
        token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Log out a user by invalidating their session.

        Args:
            token: Session token.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            True if logout successful.
        """
        session = self.session_repo.get_by_token(token)
        if not session:
            return False

        self.audit_repo.log(
            action=AuditAction.USER_LOGOUT,
            resource_type="user",
            resource_id=str(session.user_id),
            user_id=session.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return self.session_repo.delete_by_token(token)

    def logout_all_sessions(self, user_id: int) -> int:
        """Log out all sessions for a user.

        Args:
            user_id: User ID.

        Returns:
            Number of sessions invalidated.
        """
        return self.session_repo.delete_user_sessions(user_id)

    def validate_session(self, token: str) -> CurrentUser | None:
        """Validate a session token and get current user.

        Args:
            token: Session token.

        Returns:
            CurrentUser if valid, None otherwise.
        """
        session = self.session_repo.get_by_token(token)
        if not session:
            return None

        user = self.user_repo.get_by_id(session.user_id)
        if not user or not user.is_active:
            # Invalidate session if user is deactivated
            self.session_repo.delete(session.id)
            return None

        return CurrentUser(user=user, session=session)

    def extend_session(self, token: str, hours: int = 24) -> bool:
        """Extend a session's expiration.

        Args:
            token: Session token.
            hours: Additional hours.

        Returns:
            True if extended.
        """
        session = self.session_repo.get_by_token(token)
        if not session:
            return False
        return self.session_repo.extend(session.id, hours)

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        role: UserRole = UserRole.USER,
        display_name: str | None = None,
        created_by_user_id: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User | None:
        """Create a new user.

        Args:
            username: Unique username.
            email: Email address.
            password: Password.
            role: User role.
            display_name: Display name.
            created_by_user_id: ID of user creating this account.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            Created user or None if failed.
        """
        # Check for existing username or email
        if self.user_repo.get_by_username(username):
            return None
        if self.user_repo.get_by_email(email):
            return None

        user = User(
            id=None,
            username=username,
            email=email,
            password_hash="",  # Will be set by repository
            role=role,
            display_name=display_name or username,
        )

        user_id = self.user_repo.create(user, password)
        created_user = self.user_repo.get_by_id(user_id)

        self.audit_repo.log(
            action=AuditAction.USER_CREATE,
            resource_type="user",
            resource_id=str(user_id),
            user_id=created_by_user_id,
            details={"username": username, "email": email, "role": role.value},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return created_user

    def update_user(
        self,
        user: User,
        updated_by_user_id: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Update a user.

        Args:
            user: User with updated values.
            updated_by_user_id: ID of user performing update.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            True if updated.
        """
        result = self.user_repo.update(user)

        if result:
            self.audit_repo.log(
                action=AuditAction.USER_UPDATE,
                resource_type="user",
                resource_id=str(user.id),
                user_id=updated_by_user_id,
                details={"username": user.username},
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return result

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Change a user's password.

        Args:
            user_id: User ID.
            current_password: Current password for verification.
            new_password: New password.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            True if changed.
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            return False

        # Verify current password
        if not self.user_repo.authenticate(user.username, current_password):
            return False

        result = self.user_repo.update_password(user_id, new_password)

        if result:
            # Invalidate all other sessions
            self.session_repo.delete_user_sessions(user_id)

            self.audit_repo.log(
                action=AuditAction.USER_UPDATE,
                resource_type="user",
                resource_id=str(user_id),
                user_id=user_id,
                details={"action": "password_change"},
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return result

    def reset_password(
        self,
        user_id: int,
        new_password: str,
        admin_user_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Admin reset of a user's password.

        Args:
            user_id: User ID.
            new_password: New password.
            admin_user_id: Admin performing the reset.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            True if reset.
        """
        result = self.user_repo.update_password(user_id, new_password)

        if result:
            # Invalidate all sessions
            self.session_repo.delete_user_sessions(user_id)

            self.audit_repo.log(
                action=AuditAction.USER_UPDATE,
                resource_type="user",
                resource_id=str(user_id),
                user_id=admin_user_id,
                details={"action": "password_reset"},
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return result

    def deactivate_user(
        self,
        user_id: int,
        deactivated_by_user_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Deactivate a user account.

        Args:
            user_id: User ID to deactivate.
            deactivated_by_user_id: Admin performing deactivation.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            True if deactivated.
        """
        result = self.user_repo.deactivate(user_id)

        if result:
            # Invalidate all sessions
            self.session_repo.delete_user_sessions(user_id)

            self.audit_repo.log(
                action=AuditAction.USER_DELETE,
                resource_type="user",
                resource_id=str(user_id),
                user_id=deactivated_by_user_id,
                details={"action": "deactivate"},
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return result

    def update_settings(
        self,
        user_id: int,
        settings: dict,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Update user settings/preferences.

        Args:
            user_id: User ID.
            settings: Settings dict.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            True if updated.
        """
        result = self.user_repo.update_settings(user_id, json.dumps(settings))

        if result:
            self.audit_repo.log(
                action=AuditAction.SETTINGS_UPDATE,
                resource_type="user",
                resource_id=str(user_id),
                user_id=user_id,
                details={"settings_keys": list(settings.keys())},
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return result

    def get_user_settings(self, user_id: int) -> dict:
        """Get user settings.

        Args:
            user_id: User ID.

        Returns:
            Settings dict.
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            return {}
        return user.settings

    def check_permission(self, current_user: CurrentUser, action: str) -> bool:
        """Check if user has permission for an action.

        Args:
            current_user: Current user context.
            action: Action to check (e.g., 'project.create', 'user.admin').

        Returns:
            True if permitted.
        """
        # Admin has all permissions
        if current_user.is_admin:
            return True

        # Viewer can only read
        if current_user.is_viewer:
            return action.startswith("read") or action.endswith(".view")

        # Regular user permissions
        allowed_actions = [
            "project.create",
            "project.update",
            "run.start",
            "run.pause",
            "run.resume",
            "run.cancel",
            "settings.update",
            "read",
        ]

        for allowed in allowed_actions:
            if action.startswith(allowed) or action == allowed:
                return True

        return False

    def cleanup(self) -> dict:
        """Cleanup expired sessions and old audit logs.

        Returns:
            Cleanup statistics.
        """
        sessions_deleted = self.session_repo.cleanup_expired()
        logs_deleted = self.audit_repo.cleanup_old(days=90)

        return {
            "sessions_deleted": sessions_deleted,
            "audit_logs_deleted": logs_deleted,
        }


def get_auth_service(db: "Database") -> AuthService:
    """Get an AuthService instance.

    Args:
        db: Database instance.

    Returns:
        AuthService instance.
    """
    return AuthService(db)
