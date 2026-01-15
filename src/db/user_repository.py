"""User repository for PRDForge.

Provides database operations for users, sessions, and audit logs.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .models import AuditAction, AuditLog, Session, User, UserRole

if TYPE_CHECKING:
    from .database import Database


def _hash_password(password: str, salt: str | None = None) -> str:
    """Hash a password using SHA-256 with salt.

    Args:
        password: Plain text password.
        salt: Optional salt (generated if not provided).

    Returns:
        Hashed password string in format "salt:hash".
    """
    if salt is None:
        salt = secrets.token_hex(16)
    hash_value = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{hash_value}"


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash.

    Args:
        password: Plain text password to verify.
        password_hash: Stored hash in format "salt:hash".

    Returns:
        True if password matches.
    """
    if ":" not in password_hash:
        return False
    salt = password_hash.split(":")[0]
    return _hash_password(password, salt) == password_hash


class UserRepository:
    """Repository for user CRUD operations."""

    def __init__(self, db: "Database"):
        """Initialize repository.

        Args:
            db: Database instance.
        """
        self.db = db

    def create(self, user: User, password: str) -> int:
        """Create a new user.

        Args:
            user: User object to create (password_hash will be set).
            password: Plain text password to hash.

        Returns:
            Created user ID.
        """
        user.password_hash = _hash_password(password)
        user.created_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()

        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (username, email, password_hash, role, display_name,
                                   is_active, settings_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.username,
                    user.email,
                    user.password_hash,
                    user.role.value,
                    user.display_name,
                    user.is_active,
                    user.settings_json,
                    user.created_at,
                    user.updated_at,
                ),
            )
            return cursor.lastrowid

    def get_by_id(self, user_id: int) -> User | None:
        """Get a user by ID.

        Args:
            user_id: User ID.

        Returns:
            User or None if not found.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()

            if row:
                return self._row_to_user(row)
            return None

    def get_by_username(self, username: str) -> User | None:
        """Get a user by username.

        Args:
            username: Username to lookup.

        Returns:
            User or None if not found.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

            if row:
                return self._row_to_user(row)
            return None

    def get_by_email(self, email: str) -> User | None:
        """Get a user by email.

        Args:
            email: Email to lookup.

        Returns:
            User or None if not found.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()

            if row:
                return self._row_to_user(row)
            return None

    def authenticate(self, username: str, password: str) -> User | None:
        """Authenticate a user.

        Args:
            username: Username or email.
            password: Plain text password.

        Returns:
            User if authentication successful, None otherwise.
        """
        # Try username first, then email
        user = self.get_by_username(username)
        if not user:
            user = self.get_by_email(username)

        if not user:
            return None

        if not user.is_active:
            return None

        if _verify_password(password, user.password_hash):
            # Update last login time
            self.update_last_login(user.id)
            return user

        return None

    def update(self, user: User) -> bool:
        """Update a user.

        Args:
            user: User with updated values.

        Returns:
            True if updated.
        """
        user.updated_at = datetime.utcnow()
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE users
                SET email = ?, role = ?, display_name = ?, is_active = ?,
                    settings_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    user.email,
                    user.role.value,
                    user.display_name,
                    user.is_active,
                    user.settings_json,
                    user.updated_at,
                    user.id,
                ),
            )
            return cursor.rowcount > 0

    def update_password(self, user_id: int, new_password: str) -> bool:
        """Update a user's password.

        Args:
            user_id: User ID.
            new_password: New plain text password.

        Returns:
            True if updated.
        """
        password_hash = _hash_password(new_password)
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE users
                SET password_hash = ?, updated_at = ?
                WHERE id = ?
                """,
                (password_hash, datetime.utcnow(), user_id),
            )
            return cursor.rowcount > 0

    def update_last_login(self, user_id: int) -> None:
        """Update last login timestamp.

        Args:
            user_id: User ID.
        """
        with self.db.connection() as conn:
            conn.execute(
                "UPDATE users SET last_login_at = ? WHERE id = ?",
                (datetime.utcnow(), user_id),
            )

    def update_settings(self, user_id: int, settings_json: str) -> bool:
        """Update user settings.

        Args:
            user_id: User ID.
            settings_json: JSON-encoded settings.

        Returns:
            True if updated.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE users
                SET settings_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (settings_json, datetime.utcnow(), user_id),
            )
            return cursor.rowcount > 0

    def delete(self, user_id: int) -> bool:
        """Delete a user.

        Args:
            user_id: User ID.

        Returns:
            True if deleted.
        """
        with self.db.connection() as conn:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cursor.rowcount > 0

    def deactivate(self, user_id: int) -> bool:
        """Deactivate a user (soft delete).

        Args:
            user_id: User ID.

        Returns:
            True if deactivated.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
                (datetime.utcnow(), user_id),
            )
            return cursor.rowcount > 0

    def list_all(self, active_only: bool = True) -> list[User]:
        """List all users.

        Args:
            active_only: Only include active users.

        Returns:
            List of users.
        """
        with self.db.connection() as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM users WHERE is_active = 1 ORDER BY username"
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()

            return [self._row_to_user(row) for row in rows]

    def count(self, active_only: bool = True) -> int:
        """Count users.

        Args:
            active_only: Only count active users.

        Returns:
            User count.
        """
        with self.db.connection() as conn:
            if active_only:
                return conn.execute(
                    "SELECT COUNT(*) FROM users WHERE is_active = 1"
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def _row_to_user(self, row) -> User:
        """Convert database row to User object."""
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=UserRole(row["role"]),
            display_name=row["display_name"],
            is_active=bool(row["is_active"]),
            settings_json=row["settings_json"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login_at=row["last_login_at"],
        )


class SessionRepository:
    """Repository for session management."""

    DEFAULT_SESSION_HOURS = 24

    def __init__(self, db: "Database"):
        """Initialize repository.

        Args:
            db: Database instance.
        """
        self.db = db

    def create(
        self,
        user_id: int,
        hours: int = DEFAULT_SESSION_HOURS,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Session:
        """Create a new session.

        Args:
            user_id: User ID.
            hours: Session duration in hours.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            Created session.
        """
        token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=hours)

        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sessions (user_id, token, expires_at, created_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, token, expires_at, now, ip_address, user_agent),
            )

            return Session(
                id=cursor.lastrowid,
                user_id=user_id,
                token=token,
                expires_at=expires_at,
                created_at=now,
                ip_address=ip_address,
                user_agent=user_agent,
            )

    def get_by_token(self, token: str) -> Session | None:
        """Get a session by token.

        Args:
            token: Session token.

        Returns:
            Session or None if not found or expired.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token = ?", (token,)
            ).fetchone()

            if not row:
                return None

            session = Session(
                id=row["id"],
                user_id=row["user_id"],
                token=row["token"],
                expires_at=row["expires_at"],
                created_at=row["created_at"],
                ip_address=row["ip_address"],
                user_agent=row["user_agent"],
            )

            # Check if expired
            if session.expires_at < datetime.utcnow():
                self.delete(session.id)
                return None

            return session

    def delete(self, session_id: int) -> bool:
        """Delete a session.

        Args:
            session_id: Session ID.

        Returns:
            True if deleted.
        """
        with self.db.connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    def delete_by_token(self, token: str) -> bool:
        """Delete a session by token.

        Args:
            token: Session token.

        Returns:
            True if deleted.
        """
        with self.db.connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return cursor.rowcount > 0

    def delete_user_sessions(self, user_id: int) -> int:
        """Delete all sessions for a user.

        Args:
            user_id: User ID.

        Returns:
            Number of sessions deleted.
        """
        with self.db.connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            return cursor.rowcount

    def cleanup_expired(self) -> int:
        """Delete all expired sessions.

        Returns:
            Number of sessions deleted.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?", (datetime.utcnow(),)
            )
            return cursor.rowcount

    def extend(self, session_id: int, hours: int = DEFAULT_SESSION_HOURS) -> bool:
        """Extend a session's expiration.

        Args:
            session_id: Session ID.
            hours: Additional hours.

        Returns:
            True if extended.
        """
        new_expires = datetime.utcnow() + timedelta(hours=hours)
        with self.db.connection() as conn:
            cursor = conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE id = ?",
                (new_expires, session_id),
            )
            return cursor.rowcount > 0


class AuditLogRepository:
    """Repository for audit log operations."""

    def __init__(self, db: "Database"):
        """Initialize repository.

        Args:
            db: Database instance.
        """
        self.db = db

    def log(
        self,
        action: AuditAction,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_id: int | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> int:
        """Create an audit log entry.

        Args:
            action: Action type.
            resource_type: Type of resource affected.
            resource_id: ID of resource affected.
            user_id: User who performed action.
            details: Additional details.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            Created log ID.
        """
        import json

        details_json = json.dumps(details or {})

        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_logs (user_id, action, resource_type, resource_id,
                                        details_json, ip_address, user_agent, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    action.value,
                    resource_type,
                    resource_id,
                    details_json,
                    ip_address,
                    user_agent,
                    datetime.utcnow(),
                ),
            )
            return cursor.lastrowid

    def get_by_id(self, log_id: int) -> AuditLog | None:
        """Get an audit log by ID.

        Args:
            log_id: Log ID.

        Returns:
            AuditLog or None.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM audit_logs WHERE id = ?", (log_id,)
            ).fetchone()

            if row:
                return self._row_to_audit_log(row)
            return None

    def list_for_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """List audit logs for a user.

        Args:
            user_id: User ID.
            limit: Max results.
            offset: Result offset.

        Returns:
            List of audit logs.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_logs
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()

            return [self._row_to_audit_log(row) for row in rows]

    def list_for_resource(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 100,
    ) -> list[AuditLog]:
        """List audit logs for a resource.

        Args:
            resource_type: Resource type.
            resource_id: Resource ID.
            limit: Max results.

        Returns:
            List of audit logs.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_logs
                WHERE resource_type = ? AND resource_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (resource_type, resource_id, limit),
            ).fetchall()

            return [self._row_to_audit_log(row) for row in rows]

    def list_by_action(
        self,
        action: AuditAction,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """List audit logs by action type.

        Args:
            action: Action type.
            limit: Max results.
            offset: Result offset.

        Returns:
            List of audit logs.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_logs
                WHERE action = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (action.value, limit, offset),
            ).fetchall()

            return [self._row_to_audit_log(row) for row in rows]

    def list_recent(self, limit: int = 100) -> list[AuditLog]:
        """List recent audit logs.

        Args:
            limit: Max results.

        Returns:
            List of audit logs.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [self._row_to_audit_log(row) for row in rows]

    def count_by_action(self, action: AuditAction, since: datetime | None = None) -> int:
        """Count logs by action type.

        Args:
            action: Action type.
            since: Optional start time.

        Returns:
            Log count.
        """
        with self.db.connection() as conn:
            if since:
                return conn.execute(
                    "SELECT COUNT(*) FROM audit_logs WHERE action = ? AND created_at >= ?",
                    (action.value, since),
                ).fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action = ?", (action.value,)
            ).fetchone()[0]

    def cleanup_old(self, days: int = 90) -> int:
        """Delete audit logs older than specified days.

        Args:
            days: Age threshold in days.

        Returns:
            Number of logs deleted.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM audit_logs WHERE created_at < ?", (cutoff,)
            )
            return cursor.rowcount

    def _row_to_audit_log(self, row) -> AuditLog:
        """Convert database row to AuditLog object."""
        return AuditLog(
            id=row["id"],
            user_id=row["user_id"],
            action=AuditAction(row["action"]),
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            details_json=row["details_json"],
            ip_address=row["ip_address"],
            user_agent=row["user_agent"],
            created_at=row["created_at"],
        )
