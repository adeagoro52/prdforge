"""Database models for PRDForge.

These are simple dataclasses representing database entities.
They are not ORM models - just plain Python objects for data transfer.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RunStatus(Enum):
    """Status of a PRD run."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """Status of a task execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class LogLevel(Enum):
    """Log entry severity level."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Project:
    """A registered project.

    Attributes:
        id: Unique project identifier.
        name: Human-readable project name.
        path: Local path or git URL.
        project_type: Type (local or git).
        config_json: JSON-encoded project configuration.
        created_at: When the project was registered.
        updated_at: When the project was last updated.
        is_active: Whether the project is active.
    """

    id: int | None
    name: str
    path: str
    project_type: str = "local"
    config_json: str = "{}"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_active: bool = True


@dataclass
class Run:
    """A PRD execution run.

    Attributes:
        id: Unique run identifier.
        run_id: External run ID (UUID string).
        project_id: Foreign key to project.
        prd_path: Path to the PRD file.
        status: Current run status.
        base_branch: Git base branch.
        run_branch: Git run branch.
        executor: Executor used for this run.
        started_at: When the run started.
        completed_at: When the run completed.
        total_tasks: Total number of tasks.
        completed_tasks: Number of completed tasks.
        failed_tasks: Number of failed tasks.
        metadata_json: JSON-encoded metadata.
    """

    id: int | None
    run_id: str
    project_id: int
    prd_path: str
    status: RunStatus = RunStatus.PENDING
    base_branch: str = "develop"
    run_branch: str | None = None
    executor: str = "claude-cli"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    metadata_json: str = "{}"


@dataclass
class Task:
    """A task within a PRD (static definition).

    Attributes:
        id: Unique task identifier.
        run_id: Foreign key to run.
        task_id: Task ID from PRD (e.g., "phase1-001").
        phase: Phase number.
        category: Task category.
        description: Task description.
        steps_json: JSON-encoded steps list.
        blocked_by_json: JSON-encoded blocked_by list.
        order_index: Execution order index.
    """

    id: int | None
    run_id: int
    task_id: str
    phase: int
    category: str
    description: str
    steps_json: str = "[]"
    blocked_by_json: str = "[]"
    order_index: int = 0


@dataclass
class TaskExecution:
    """An execution attempt for a task.

    Attributes:
        id: Unique execution identifier.
        task_id: Foreign key to task.
        run_id: Foreign key to run.
        status: Execution status.
        attempt: Attempt number (1-based).
        started_at: When execution started.
        completed_at: When execution completed.
        duration_seconds: Execution duration.
        output: Raw output from executor.
        error: Error message if failed.
        files_changed_json: JSON-encoded list of changed files.
    """

    id: int | None
    task_id: int
    run_id: int
    status: TaskStatus = TaskStatus.PENDING
    attempt: int = 1
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    output: str = ""
    error: str | None = None
    files_changed_json: str = "[]"


@dataclass
class LogEntry:
    """A log entry for a run or task.

    Attributes:
        id: Unique log identifier.
        run_id: Foreign key to run.
        task_id: Optional foreign key to task.
        level: Log level.
        message: Log message.
        context_json: JSON-encoded context.
        timestamp: When the log was created.
    """

    id: int | None
    run_id: int
    task_id: int | None = None
    level: LogLevel = LogLevel.INFO
    message: str = ""
    context_json: str = "{}"
    timestamp: datetime | None = None
