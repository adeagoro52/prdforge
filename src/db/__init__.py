"""Database layer for PRDForge.

This module provides:
- SQLite database management
- Repository pattern for data access
- Migration system for schema evolution

Example usage:
    from db import Database, RunRepository

    # Initialize database
    db = Database("~/.prdforge/prdforge.db")
    db.initialize()

    # Use repositories
    run_repo = RunRepository(db)
    runs = run_repo.list_by_project("my-project")
"""

from .database import Database
from .migrations import MigrationManager
from .models import (
    AlertType,
    AuditAction,
    AuditLog,
    CostAlert,
    CostBudget,
    CostRecord,
    LogEntry,
    Notification,
    NotificationChannel,
    NotificationConfig,
    NotificationEventType,
    NotificationPriority,
    Project,
    ProjectHealth,
    Run,
    Session,
    Task,
    TaskExecution,
    User,
    UserRole,
    WebhookDelivery,
)
from .repositories import (
    LogRepository,
    ProjectRepository,
    RunRepository,
    TaskRepository,
)
from .cost_repository import CostRepository
from .user_repository import (
    AuditLogRepository,
    SessionRepository,
    UserRepository,
)
from .notification_repository import (
    NotificationConfigRepository,
    NotificationRepository,
    WebhookDeliveryRepository,
)

__all__ = [
    # Core
    "Database",
    "MigrationManager",
    # Models
    "Project",
    "ProjectHealth",
    "Run",
    "Task",
    "TaskExecution",
    "LogEntry",
    "CostRecord",
    "CostBudget",
    "CostAlert",
    "AlertType",
    "User",
    "UserRole",
    "Session",
    "AuditLog",
    "AuditAction",
    "Notification",
    "NotificationConfig",
    "NotificationEventType",
    "NotificationChannel",
    "NotificationPriority",
    "WebhookDelivery",
    # Repositories
    "ProjectRepository",
    "RunRepository",
    "TaskRepository",
    "LogRepository",
    "CostRepository",
    "UserRepository",
    "SessionRepository",
    "AuditLogRepository",
    "NotificationConfigRepository",
    "NotificationRepository",
    "WebhookDeliveryRepository",
]
