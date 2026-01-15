"""Notification service for PRDForge.

Provides centralized notification management with support for
in-app notifications and webhook delivery.
"""

import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from src.db.models import (
    Notification,
    NotificationChannel,
    NotificationConfig,
    NotificationEventType,
    NotificationPriority,
    WebhookDelivery,
)
from src.db.notification_repository import (
    NotificationConfigRepository,
    NotificationRepository,
    WebhookDeliveryRepository,
)

if TYPE_CHECKING:
    from src.db import Database

logger = logging.getLogger(__name__)


# Default event messages
EVENT_MESSAGES = {
    NotificationEventType.RUN_STARTED: ("Run Started", "A new run has started: {run_id}"),
    NotificationEventType.RUN_COMPLETED: ("Run Completed", "Run {run_id} completed successfully"),
    NotificationEventType.RUN_FAILED: ("Run Failed", "Run {run_id} failed: {error}"),
    NotificationEventType.RUN_PAUSED: ("Run Paused", "Run {run_id} has been paused"),
    NotificationEventType.RUN_RESUMED: ("Run Resumed", "Run {run_id} has been resumed"),
    NotificationEventType.RUN_CANCELLED: ("Run Cancelled", "Run {run_id} was cancelled"),
    NotificationEventType.TASK_STARTED: ("Task Started", "Task {task_id} has started"),
    NotificationEventType.TASK_COMPLETED: ("Task Completed", "Task {task_id} completed"),
    NotificationEventType.TASK_FAILED: ("Task Failed", "Task {task_id} failed: {error}"),
    NotificationEventType.BUDGET_WARNING: ("Budget Warning", "Budget at {percent}% - ${current} of ${limit}"),
    NotificationEventType.BUDGET_EXCEEDED: ("Budget Exceeded", "Budget exceeded: ${current} of ${limit}"),
    NotificationEventType.QUALITY_GATES_PASSED: ("Quality Gates Passed", "All quality gates passed"),
    NotificationEventType.QUALITY_GATES_FAILED: ("Quality Gates Failed", "{failed_count} quality gate(s) failed"),
    NotificationEventType.SYSTEM_ERROR: ("System Error", "{error}"),
    NotificationEventType.WEBHOOK_FAILURE: ("Webhook Failed", "Webhook delivery failed: {url}"),
}


@dataclass
class NotificationEvent:
    """A notification event to be processed.

    Attributes:
        event_type: Type of notification event.
        project_id: Project that triggered the event.
        data: Additional event data.
        priority: Priority level.
        user_ids: Specific users to notify (None for all project users).
    """

    event_type: NotificationEventType
    project_id: int
    data: dict[str, Any] | None = None
    priority: NotificationPriority = NotificationPriority.NORMAL
    user_ids: list[int] | None = None


class NotificationService:
    """Service for managing and sending notifications."""

    def __init__(self, database: "Database"):
        """Initialize notification service.

        Args:
            database: Database instance.
        """
        self.db = database
        self.config_repo = NotificationConfigRepository(database)
        self.notification_repo = NotificationRepository(database)
        self.webhook_repo = WebhookDeliveryRepository(database)

        # HTTP client for webhooks
        self._http_client: httpx.Client | None = None

    @property
    def http_client(self) -> httpx.Client:
        """Get HTTP client for webhook delivery."""
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=30.0)
        return self._http_client

    def close(self):
        """Close the notification service and release resources."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None

    # Configuration management
    def get_config(self, project_id: int) -> NotificationConfig | None:
        """Get notification config for a project.

        Args:
            project_id: Project ID.

        Returns:
            NotificationConfig if exists, None otherwise.
        """
        return self.config_repo.get_by_project(project_id)

    def set_config(
        self,
        project_id: int,
        events: list[str] | None = None,
        channels: list[str] | None = None,
        webhook_url: str | None = None,
        is_enabled: bool = True,
        generate_secret: bool = False,
    ) -> NotificationConfig:
        """Set or update notification config for a project.

        Args:
            project_id: Project ID.
            events: List of event types to notify on.
            channels: List of channels to use.
            webhook_url: URL for webhook notifications.
            is_enabled: Whether notifications are enabled.
            generate_secret: Whether to generate a new webhook secret.

        Returns:
            Updated NotificationConfig.
        """
        existing = self.config_repo.get_by_project(project_id)

        config = existing or NotificationConfig(
            id=None,
            project_id=project_id,
        )

        if events is not None:
            config.events = events
        if channels is not None:
            config.channels = channels
        if webhook_url is not None:
            config.webhook_url = webhook_url
        config.is_enabled = is_enabled

        if generate_secret:
            config.webhook_secret = secrets.token_hex(32)

        config.id = self.config_repo.upsert(config)
        return config

    def delete_config(self, project_id: int) -> bool:
        """Delete notification config for a project.

        Args:
            project_id: Project ID.

        Returns:
            True if deleted, False if not found.
        """
        return self.config_repo.delete(project_id)

    # Notification sending
    def send(self, event: NotificationEvent) -> list[int]:
        """Send notifications for an event.

        Args:
            event: NotificationEvent to process.

        Returns:
            List of created notification IDs.
        """
        config = self.config_repo.get_by_project(event.project_id)

        # Check if notifications are enabled and event is configured
        if not config or not config.is_enabled:
            logger.debug(f"Notifications disabled for project {event.project_id}")
            return []

        if event.event_type.value not in config.events:
            logger.debug(f"Event {event.event_type} not enabled for project {event.project_id}")
            return []

        notification_ids = []
        channels = config.channels

        # Create in-app notifications
        if NotificationChannel.IN_APP.value in channels:
            ids = self._send_in_app(event, config)
            notification_ids.extend(ids)

        # Send webhook notifications
        if NotificationChannel.WEBHOOK.value in channels and config.webhook_url:
            self._send_webhook(event, config)

        return notification_ids

    def _send_in_app(
        self,
        event: NotificationEvent,
        config: NotificationConfig,
    ) -> list[int]:
        """Send in-app notifications.

        Args:
            event: NotificationEvent.
            config: NotificationConfig.

        Returns:
            List of created notification IDs.
        """
        title, message_template = EVENT_MESSAGES.get(
            event.event_type,
            ("Notification", "Event occurred"),
        )

        # Format message with event data
        data = event.data or {}
        try:
            message = message_template.format(**data)
        except (KeyError, ValueError):
            message = message_template

        notification_ids = []
        user_ids = event.user_ids or self._get_project_users(event.project_id)

        for user_id in user_ids:
            notification = Notification(
                id=None,
                user_id=user_id,
                project_id=event.project_id,
                event_type=event.event_type,
                channel=NotificationChannel.IN_APP,
                priority=event.priority,
                title=title,
                message=message,
                data_json=json.dumps(data),
            )
            notification_id = self.notification_repo.create(notification)
            notification_ids.append(notification_id)

        return notification_ids

    def _send_webhook(
        self,
        event: NotificationEvent,
        config: NotificationConfig,
    ) -> WebhookDelivery | None:
        """Send webhook notification.

        Args:
            event: NotificationEvent.
            config: NotificationConfig.

        Returns:
            WebhookDelivery record if sent, None otherwise.
        """
        if not config.webhook_url:
            return None

        # Build webhook payload
        payload = {
            "event_type": event.event_type.value,
            "project_id": event.project_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": event.data or {},
            "priority": event.priority.value,
        }

        payload_json = json.dumps(payload)

        # Sign the payload if secret is configured
        headers = {"Content-Type": "application/json"}
        if config.webhook_secret:
            signature = hmac.new(
                config.webhook_secret.encode(),
                payload_json.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-PRDForge-Signature"] = f"sha256={signature}"

        # Attempt delivery
        delivery = WebhookDelivery(
            id=None,
            project_id=event.project_id,
            event_type=event.event_type,
            url=config.webhook_url,
            payload_json=payload_json,
        )

        try:
            response = self.http_client.post(
                config.webhook_url,
                content=payload_json,
                headers=headers,
            )
            delivery.response_status = response.status_code
            delivery.response_body = response.text[:1000] if response.text else None
            delivery.success = 200 <= response.status_code < 300
        except httpx.HTTPError as e:
            logger.error(f"Webhook delivery failed: {e}")
            delivery.response_body = str(e)[:1000]
            delivery.success = False

        # Record delivery
        self.webhook_repo.create(delivery)

        # If delivery failed, create a notification about it
        if not delivery.success:
            self._notify_webhook_failure(config, delivery)

        return delivery

    def _notify_webhook_failure(
        self,
        config: NotificationConfig,
        delivery: WebhookDelivery,
    ) -> None:
        """Create notification about webhook failure.

        Args:
            config: NotificationConfig.
            delivery: Failed WebhookDelivery.
        """
        # Only notify about failures, avoid recursive loop
        if NotificationEventType.WEBHOOK_FAILURE.value in config.events:
            logger.warning("Webhook failure notification skipped to prevent loop")
            return

        # Get admin users to notify
        user_ids = self._get_admin_users()
        if not user_ids:
            return

        for user_id in user_ids:
            notification = Notification(
                id=None,
                user_id=user_id,
                project_id=config.project_id,
                event_type=NotificationEventType.WEBHOOK_FAILURE,
                channel=NotificationChannel.IN_APP,
                priority=NotificationPriority.HIGH,
                title="Webhook Delivery Failed",
                message=f"Failed to deliver webhook to {config.webhook_url}",
                data_json=json.dumps({
                    "url": config.webhook_url,
                    "status": delivery.response_status,
                    "error": delivery.response_body,
                }),
            )
            self.notification_repo.create(notification)

    def _get_project_users(self, project_id: int) -> list[int]:
        """Get user IDs associated with a project.

        For now, returns all active users. In future, this could
        be based on project membership.

        Args:
            project_id: Project ID.

        Returns:
            List of user IDs.
        """
        from src.db.user_repository import UserRepository
        user_repo = UserRepository(self.db)
        users = user_repo.list_all(active_only=True)
        return [u.id for u in users if u.id]

    def _get_admin_users(self) -> list[int]:
        """Get admin user IDs.

        Returns:
            List of admin user IDs.
        """
        from src.db.user_repository import UserRepository
        from src.db.models import UserRole
        user_repo = UserRepository(self.db)
        users = user_repo.list_all(active_only=True)
        return [u.id for u in users if u.id and u.role == UserRole.ADMIN]

    # User notification management
    def get_notifications(
        self,
        user_id: int,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """Get notifications for a user.

        Args:
            user_id: User ID.
            unread_only: Only return unread.
            limit: Maximum to return.

        Returns:
            List of Notification objects.
        """
        return self.notification_repo.list_for_user(user_id, unread_only, limit)

    def get_unread_count(self, user_id: int) -> int:
        """Get unread notification count.

        Args:
            user_id: User ID.

        Returns:
            Unread count.
        """
        return self.notification_repo.get_unread_count(user_id)

    def mark_as_read(self, notification_id: int) -> bool:
        """Mark notification as read.

        Args:
            notification_id: Notification ID.

        Returns:
            True if marked, False otherwise.
        """
        return self.notification_repo.mark_as_read(notification_id)

    def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read.

        Args:
            user_id: User ID.

        Returns:
            Number marked.
        """
        return self.notification_repo.mark_all_as_read(user_id)

    def delete_notification(self, notification_id: int) -> bool:
        """Delete a notification.

        Args:
            notification_id: Notification ID.

        Returns:
            True if deleted, False otherwise.
        """
        return self.notification_repo.delete(notification_id)

    # Webhook delivery management
    def get_webhook_deliveries(
        self,
        project_id: int,
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        """Get webhook deliveries for a project.

        Args:
            project_id: Project ID.
            limit: Maximum to return.

        Returns:
            List of WebhookDelivery objects.
        """
        return self.webhook_repo.list_for_project(project_id, limit)

    def get_webhook_stats(self, project_id: int, days: int = 7) -> dict:
        """Get webhook delivery statistics.

        Args:
            project_id: Project ID.
            days: Number of days.

        Returns:
            Statistics dictionary.
        """
        return self.webhook_repo.get_delivery_stats(project_id, days)

    def retry_failed_webhooks(self, hours: int = 24, max_attempts: int = 3) -> int:
        """Retry recent failed webhook deliveries.

        Args:
            hours: How far back to look.
            max_attempts: Maximum retry attempts.

        Returns:
            Number of retries attempted.
        """
        failed = self.webhook_repo.list_failed_recent(hours)
        retry_count = 0

        for delivery in failed:
            if delivery.attempt >= max_attempts:
                continue

            config = self.config_repo.get_by_project(delivery.project_id)
            if not config or not config.webhook_url:
                continue

            # Create retry event
            event = NotificationEvent(
                event_type=delivery.event_type,
                project_id=delivery.project_id,
                data=delivery.payload,
            )

            # Create new delivery record with incremented attempt
            retry_delivery = WebhookDelivery(
                id=None,
                project_id=delivery.project_id,
                event_type=delivery.event_type,
                url=config.webhook_url,
                payload_json=delivery.payload_json,
                attempt=delivery.attempt + 1,
            )

            try:
                response = self.http_client.post(
                    config.webhook_url,
                    content=delivery.payload_json,
                    headers={"Content-Type": "application/json"},
                )
                retry_delivery.response_status = response.status_code
                retry_delivery.response_body = response.text[:1000] if response.text else None
                retry_delivery.success = 200 <= response.status_code < 300
            except httpx.HTTPError as e:
                retry_delivery.response_body = str(e)[:1000]
                retry_delivery.success = False

            self.webhook_repo.create(retry_delivery)
            retry_count += 1

        return retry_count

    # Cleanup
    def cleanup_old(self, days: int = 30) -> dict[str, int]:
        """Clean up old notifications and deliveries.

        Args:
            days: Age threshold.

        Returns:
            Dictionary with counts deleted.
        """
        notifications_deleted = self.notification_repo.delete_old(days)
        deliveries_deleted = self.webhook_repo.delete_old(days)

        return {
            "notifications": notifications_deleted,
            "webhook_deliveries": deliveries_deleted,
        }


# Convenience functions
_notification_service: NotificationService | None = None


def get_notification_service(database: "Database") -> NotificationService:
    """Get or create notification service instance.

    Args:
        database: Database instance.

    Returns:
        NotificationService instance.
    """
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService(database)
    return _notification_service


def notify(
    database: "Database",
    event_type: NotificationEventType,
    project_id: int,
    data: dict[str, Any] | None = None,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    user_ids: list[int] | None = None,
) -> list[int]:
    """Convenience function to send a notification.

    Args:
        database: Database instance.
        event_type: Type of event.
        project_id: Project ID.
        data: Event data.
        priority: Priority level.
        user_ids: Specific users to notify.

    Returns:
        List of created notification IDs.
    """
    service = get_notification_service(database)
    event = NotificationEvent(
        event_type=event_type,
        project_id=project_id,
        data=data,
        priority=priority,
        user_ids=user_ids,
    )
    return service.send(event)
