"""Notification repositories for PRDForge.

Provides data access for notification-related entities.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from .models import (
    Notification,
    NotificationChannel,
    NotificationConfig,
    NotificationEventType,
    NotificationPriority,
    WebhookDelivery,
)

if TYPE_CHECKING:
    from .database import Database


class NotificationConfigRepository:
    """Repository for notification configuration operations."""

    def __init__(self, database: "Database"):
        """Initialize repository.

        Args:
            database: Database instance.
        """
        self.db = database

    def get_by_project(self, project_id: int) -> NotificationConfig | None:
        """Get notification config for a project.

        Args:
            project_id: Project ID.

        Returns:
            NotificationConfig if found, None otherwise.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, events_json, channels_json,
                       webhook_url, webhook_secret, is_enabled,
                       created_at, updated_at
                FROM notification_configs
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()

        if not row:
            return None

        return NotificationConfig(
            id=row["id"],
            project_id=row["project_id"],
            events_json=row["events_json"],
            channels_json=row["channels_json"],
            webhook_url=row["webhook_url"],
            webhook_secret=row["webhook_secret"],
            is_enabled=bool(row["is_enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(self, config: NotificationConfig) -> int:
        """Create a new notification config.

        Args:
            config: NotificationConfig to create.

        Returns:
            ID of created config.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notification_configs
                    (project_id, events_json, channels_json, webhook_url,
                     webhook_secret, is_enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config.project_id,
                    config.events_json,
                    config.channels_json,
                    config.webhook_url,
                    config.webhook_secret,
                    config.is_enabled,
                    datetime.utcnow(),
                    datetime.utcnow(),
                ),
            )
            return cursor.lastrowid

    def update(self, config: NotificationConfig) -> bool:
        """Update an existing notification config.

        Args:
            config: NotificationConfig to update.

        Returns:
            True if updated, False if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE notification_configs
                SET events_json = ?, channels_json = ?, webhook_url = ?,
                    webhook_secret = ?, is_enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    config.events_json,
                    config.channels_json,
                    config.webhook_url,
                    config.webhook_secret,
                    config.is_enabled,
                    datetime.utcnow(),
                    config.id,
                ),
            )
            return cursor.rowcount > 0

    def upsert(self, config: NotificationConfig) -> int:
        """Create or update notification config.

        Args:
            config: NotificationConfig to upsert.

        Returns:
            ID of the config.
        """
        existing = self.get_by_project(config.project_id)
        if existing:
            config.id = existing.id
            self.update(config)
            return existing.id
        return self.create(config)

    def delete(self, project_id: int) -> bool:
        """Delete notification config for a project.

        Args:
            project_id: Project ID.

        Returns:
            True if deleted, False if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM notification_configs WHERE project_id = ?",
                (project_id,),
            )
            return cursor.rowcount > 0

    def list_enabled(self) -> list[NotificationConfig]:
        """List all enabled notification configs.

        Returns:
            List of enabled NotificationConfig objects.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, events_json, channels_json,
                       webhook_url, webhook_secret, is_enabled,
                       created_at, updated_at
                FROM notification_configs
                WHERE is_enabled = 1
                """
            ).fetchall()

        return [
            NotificationConfig(
                id=row["id"],
                project_id=row["project_id"],
                events_json=row["events_json"],
                channels_json=row["channels_json"],
                webhook_url=row["webhook_url"],
                webhook_secret=row["webhook_secret"],
                is_enabled=bool(row["is_enabled"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


class NotificationRepository:
    """Repository for notification operations."""

    def __init__(self, database: "Database"):
        """Initialize repository.

        Args:
            database: Database instance.
        """
        self.db = database

    def create(self, notification: Notification) -> int:
        """Create a new notification.

        Args:
            notification: Notification to create.

        Returns:
            ID of created notification.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notifications
                    (user_id, project_id, event_type, channel, priority,
                     title, message, data_json, is_read, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notification.user_id,
                    notification.project_id,
                    notification.event_type.value,
                    notification.channel.value,
                    notification.priority.value,
                    notification.title,
                    notification.message,
                    notification.data_json,
                    notification.is_read,
                    datetime.utcnow(),
                ),
            )
            return cursor.lastrowid

    def get_by_id(self, notification_id: int) -> Notification | None:
        """Get notification by ID.

        Args:
            notification_id: Notification ID.

        Returns:
            Notification if found, None otherwise.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, project_id, event_type, channel, priority,
                       title, message, data_json, is_read, read_at, created_at
                FROM notifications
                WHERE id = ?
                """,
                (notification_id,),
            ).fetchone()

        if not row:
            return None

        return self._row_to_notification(row)

    def list_for_user(
        self,
        user_id: int,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications for a user.

        Args:
            user_id: User ID.
            unread_only: Only return unread notifications.
            limit: Maximum notifications to return.
            offset: Number to skip.

        Returns:
            List of Notification objects.
        """
        query = """
            SELECT id, user_id, project_id, event_type, channel, priority,
                   title, message, data_json, is_read, read_at, created_at
            FROM notifications
            WHERE user_id = ?
        """
        params: list = [user_id]

        if unread_only:
            query += " AND is_read = 0"

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_notification(row) for row in rows]

    def list_for_project(
        self,
        project_id: int,
        limit: int = 50,
    ) -> list[Notification]:
        """List notifications for a project.

        Args:
            project_id: Project ID.
            limit: Maximum notifications to return.

        Returns:
            List of Notification objects.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, project_id, event_type, channel, priority,
                       title, message, data_json, is_read, read_at, created_at
                FROM notifications
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()

        return [self._row_to_notification(row) for row in rows]

    def mark_as_read(self, notification_id: int) -> bool:
        """Mark a notification as read.

        Args:
            notification_id: Notification ID.

        Returns:
            True if marked, False if not found or already read.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE notifications
                SET is_read = 1, read_at = ?
                WHERE id = ? AND is_read = 0
                """,
                (datetime.utcnow(), notification_id),
            )
            return cursor.rowcount > 0

    def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read for a user.

        Args:
            user_id: User ID.

        Returns:
            Number of notifications marked as read.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE notifications
                SET is_read = 1, read_at = ?
                WHERE user_id = ? AND is_read = 0
                """,
                (datetime.utcnow(), user_id),
            )
            return cursor.rowcount

    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user.

        Args:
            user_id: User ID.

        Returns:
            Number of unread notifications.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND is_read = 0",
                (user_id,),
            ).fetchone()
            return row["count"] if row else 0

    def delete(self, notification_id: int) -> bool:
        """Delete a notification.

        Args:
            notification_id: Notification ID.

        Returns:
            True if deleted, False if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM notifications WHERE id = ?",
                (notification_id,),
            )
            return cursor.rowcount > 0

    def delete_old(self, days: int = 30) -> int:
        """Delete notifications older than specified days.

        Args:
            days: Age threshold in days.

        Returns:
            Number of notifications deleted.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM notifications
                WHERE created_at < datetime('now', '-' || ? || ' days')
                """,
                (days,),
            )
            return cursor.rowcount

    def _row_to_notification(self, row) -> Notification:
        """Convert a database row to Notification object."""
        return Notification(
            id=row["id"],
            user_id=row["user_id"],
            project_id=row["project_id"],
            event_type=NotificationEventType(row["event_type"]),
            channel=NotificationChannel(row["channel"]),
            priority=NotificationPriority(row["priority"]),
            title=row["title"],
            message=row["message"],
            data_json=row["data_json"],
            is_read=bool(row["is_read"]),
            read_at=row["read_at"],
            created_at=row["created_at"],
        )


class WebhookDeliveryRepository:
    """Repository for webhook delivery operations."""

    def __init__(self, database: "Database"):
        """Initialize repository.

        Args:
            database: Database instance.
        """
        self.db = database

    def create(self, delivery: WebhookDelivery) -> int:
        """Create a webhook delivery record.

        Args:
            delivery: WebhookDelivery to create.

        Returns:
            ID of created delivery.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO webhook_deliveries
                    (project_id, notification_id, event_type, url,
                     payload_json, response_status, response_body,
                     success, attempt, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery.project_id,
                    delivery.notification_id,
                    delivery.event_type.value,
                    delivery.url,
                    delivery.payload_json,
                    delivery.response_status,
                    delivery.response_body,
                    delivery.success,
                    delivery.attempt,
                    datetime.utcnow(),
                ),
            )
            return cursor.lastrowid

    def list_for_project(
        self,
        project_id: int,
        limit: int = 50,
        success_only: bool | None = None,
    ) -> list[WebhookDelivery]:
        """List webhook deliveries for a project.

        Args:
            project_id: Project ID.
            limit: Maximum deliveries to return.
            success_only: Filter by success status (None for all).

        Returns:
            List of WebhookDelivery objects.
        """
        query = """
            SELECT id, project_id, notification_id, event_type, url,
                   payload_json, response_status, response_body,
                   success, attempt, created_at
            FROM webhook_deliveries
            WHERE project_id = ?
        """
        params: list = [project_id]

        if success_only is not None:
            query += " AND success = ?"
            params.append(success_only)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_delivery(row) for row in rows]

    def list_failed_recent(self, hours: int = 24) -> list[WebhookDelivery]:
        """List recent failed deliveries for retry.

        Args:
            hours: How far back to look.

        Returns:
            List of failed WebhookDelivery objects.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, notification_id, event_type, url,
                       payload_json, response_status, response_body,
                       success, attempt, created_at
                FROM webhook_deliveries
                WHERE success = 0
                  AND created_at > datetime('now', '-' || ? || ' hours')
                ORDER BY created_at DESC
                """,
                (hours,),
            ).fetchall()

        return [self._row_to_delivery(row) for row in rows]

    def get_delivery_stats(
        self,
        project_id: int,
        days: int = 7,
    ) -> dict:
        """Get delivery statistics for a project.

        Args:
            project_id: Project ID.
            days: Number of days to include.

        Returns:
            Dictionary with delivery statistics.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed
                FROM webhook_deliveries
                WHERE project_id = ?
                  AND created_at > datetime('now', '-' || ? || ' days')
                """,
                (project_id, days),
            ).fetchone()

        return {
            "total": row["total"] or 0,
            "successful": row["successful"] or 0,
            "failed": row["failed"] or 0,
            "success_rate": (
                (row["successful"] / row["total"] * 100)
                if row["total"] > 0
                else 100.0
            ),
        }

    def delete_old(self, days: int = 30) -> int:
        """Delete webhook deliveries older than specified days.

        Args:
            days: Age threshold in days.

        Returns:
            Number of deliveries deleted.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM webhook_deliveries
                WHERE created_at < datetime('now', '-' || ? || ' days')
                """,
                (days,),
            )
            return cursor.rowcount

    def _row_to_delivery(self, row) -> WebhookDelivery:
        """Convert a database row to WebhookDelivery object."""
        return WebhookDelivery(
            id=row["id"],
            project_id=row["project_id"],
            notification_id=row["notification_id"],
            event_type=NotificationEventType(row["event_type"]),
            url=row["url"],
            payload_json=row["payload_json"],
            response_status=row["response_status"],
            response_body=row["response_body"],
            success=bool(row["success"]),
            attempt=row["attempt"],
            created_at=row["created_at"],
        )
