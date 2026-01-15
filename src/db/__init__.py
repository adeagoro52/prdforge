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
from .models import LogEntry, Project, Run, Task, TaskExecution
from .repositories import (
    LogRepository,
    ProjectRepository,
    RunRepository,
    TaskRepository,
)

__all__ = [
    # Core
    "Database",
    "MigrationManager",
    # Models
    "Project",
    "Run",
    "Task",
    "TaskExecution",
    "LogEntry",
    # Repositories
    "ProjectRepository",
    "RunRepository",
    "TaskRepository",
    "LogRepository",
]
