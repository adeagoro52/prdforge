"""Configuration dataclasses for PRDForge execution engine."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
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
    """Status of an individual task."""

    PENDING = "pending"
    BLOCKED = "blocked"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ExecutionConfig:
    """Configuration for a PRD execution run.

    Attributes:
        project_path: Path to the project root directory.
        prd_path: Path to the PRD file to execute.
        base_branch: Git branch to use as base for the run.
        run_branch: Git branch name for this run (auto-generated if not provided).
        executor: Name of the AI executor to use (e.g., 'claude-cli').
        skip_completed: Whether to skip tasks already marked as completed.
        auto_commit: Whether to auto-commit after each task.
        auto_push: Whether to push to remote after commits.
        max_retries: Maximum retries for failed tasks.
        timeout_seconds: Timeout for each task execution.
        dry_run: If True, simulate execution without making changes.
    """

    project_path: Path
    prd_path: Path
    base_branch: str = "develop"
    run_branch: str | None = None
    executor: str = "claude-cli"
    skip_completed: bool = True
    auto_commit: bool = True
    auto_push: bool = False
    max_retries: int = 2
    timeout_seconds: int = 600
    dry_run: bool = False

    def __post_init__(self) -> None:
        """Validate and normalize paths."""
        self.project_path = Path(self.project_path).resolve()
        self.prd_path = Path(self.prd_path).resolve()

        if not self.project_path.is_dir():
            raise ValueError(f"Project path does not exist: {self.project_path}")

        if not self.prd_path.is_file():
            raise ValueError(f"PRD file does not exist: {self.prd_path}")


@dataclass
class TaskResult:
    """Result of executing a single task.

    Attributes:
        task_id: Identifier of the task.
        status: Final status of the task.
        started_at: When execution started.
        completed_at: When execution completed.
        output: Raw output from the executor.
        error: Error message if failed.
        retries: Number of retry attempts made.
        files_changed: List of files modified by this task.
    """

    task_id: str
    status: TaskStatus
    started_at: datetime
    completed_at: datetime | None = None
    output: str = ""
    error: str | None = None
    retries: int = 0
    files_changed: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        """Calculate execution duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class RunState:
    """State of an entire PRD run.

    Attributes:
        run_id: Unique identifier for this run.
        config: The execution configuration.
        status: Current status of the run.
        started_at: When the run started.
        completed_at: When the run completed.
        current_task_id: ID of the currently executing task.
        task_results: Results for each executed task.
        metadata: Additional run metadata.
    """

    run_id: str
    config: ExecutionConfig
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    current_task_id: str | None = None
    task_results: dict[str, TaskResult] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def tasks_completed(self) -> int:
        """Count of completed tasks."""
        return sum(
            1 for r in self.task_results.values() if r.status == TaskStatus.COMPLETED
        )

    @property
    def tasks_failed(self) -> int:
        """Count of failed tasks."""
        return sum(
            1 for r in self.task_results.values() if r.status == TaskStatus.FAILED
        )

    @property
    def duration_seconds(self) -> float | None:
        """Calculate total run duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
