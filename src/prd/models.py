"""PRD data models - unified representation for all PRD formats."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskCategory(Enum):
    """Category of a PRD task."""

    BACKEND = "backend"
    FRONTEND = "frontend"
    CONFIG = "config"
    DOCS = "docs"
    TEST = "test"
    INFRA = "infra"
    OTHER = "other"

    @classmethod
    def from_string(cls, value: str) -> "TaskCategory":
        """Convert string to TaskCategory, defaulting to OTHER."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.OTHER


class TestCoverage(Enum):
    """Test coverage level for a task."""

    NONE = "none"
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    MANUAL = "manual"

    @classmethod
    def from_string(cls, value: str) -> "TestCoverage":
        """Convert string to TestCoverage, defaulting to NONE."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.NONE


@dataclass
class PRDTask:
    """A single task within a PRD.

    Attributes:
        id: Unique identifier for the task.
        phase: Phase number this task belongs to.
        category: Category of the task (backend, frontend, etc.).
        description: Human-readable description of what to do.
        steps: List of implementation steps.
        passes: Whether this task has been completed.
        test_coverage: Required test coverage level.
        blocked_by: List of task IDs that must complete first.
        acceptance_criteria: Optional acceptance criteria.
        metadata: Additional task-specific metadata.
    """

    id: str
    phase: int
    category: TaskCategory
    description: str
    steps: list[str] = field(default_factory=list)
    passes: bool = False
    test_coverage: TestCoverage = TestCoverage.NONE
    blocked_by: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_blocked(self, completed_task_ids: set[str]) -> bool:
        """Check if this task is blocked by incomplete dependencies."""
        return any(dep not in completed_task_ids for dep in self.blocked_by)


@dataclass
class Phase:
    """A phase grouping within a PRD.

    Attributes:
        phase: Phase number.
        name: Human-readable phase name.
        description: What this phase accomplishes.
        estimated_tasks: Expected number of tasks in this phase.
    """

    phase: int
    name: str
    description: str = ""
    estimated_tasks: int = 0


@dataclass
class PRDMeta:
    """Metadata about the PRD itself.

    Attributes:
        feature_name: Name of the feature being built.
        feature_slug: URL-safe identifier.
        description: Detailed description of the feature.
        created_at: When the PRD was created.
        project_name: Name of the project.
        priority: Priority level (strategic, high, medium, low).
        wave: Release wave or milestone.
        tech_stack: Technology stack decisions.
        deployment: Deployment strategy.
        storage: Storage solution.
    """

    feature_name: str
    feature_slug: str = ""
    description: str = ""
    created_at: datetime | None = None
    project_name: str = ""
    priority: str = "medium"
    wave: str = ""
    tech_stack: str = ""
    deployment: str = ""
    storage: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PRD:
    """Complete PRD representation.

    This is the unified format that all parsers produce,
    enabling format-agnostic processing downstream.

    Attributes:
        meta: PRD metadata.
        phases: List of phases in order.
        tasks: List of all tasks.
        source_format: Original format (json, markdown).
        source_path: Path to the source file if loaded from disk.
    """

    meta: PRDMeta
    phases: list[Phase] = field(default_factory=list)
    tasks: list[PRDTask] = field(default_factory=list)
    source_format: str = "unknown"
    source_path: str | None = None

    def get_tasks_by_phase(self, phase_num: int) -> list[PRDTask]:
        """Get all tasks for a specific phase."""
        return [t for t in self.tasks if t.phase == phase_num]

    def get_pending_tasks(self) -> list[PRDTask]:
        """Get all tasks not yet completed."""
        return [t for t in self.tasks if not t.passes]

    def get_completed_tasks(self) -> list[PRDTask]:
        """Get all completed tasks."""
        return [t for t in self.tasks if t.passes]

    def get_task_by_id(self, task_id: str) -> PRDTask | None:
        """Find a task by its ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_executable_tasks(self) -> list[PRDTask]:
        """Get tasks that can be executed (not blocked, not completed)."""
        completed_ids = {t.id for t in self.get_completed_tasks()}
        return [
            t
            for t in self.get_pending_tasks()
            if not t.is_blocked(completed_ids)
        ]

    @property
    def total_tasks(self) -> int:
        """Total number of tasks."""
        return len(self.tasks)

    @property
    def completed_count(self) -> int:
        """Number of completed tasks."""
        return len(self.get_completed_tasks())

    @property
    def progress_percent(self) -> float:
        """Completion percentage."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_count / self.total_tasks) * 100
