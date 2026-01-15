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


class ProjectHealth(Enum):
    """Health status of a project based on recent runs."""

    HEALTHY = "healthy"  # Last run succeeded
    WARNING = "warning"  # Last run had failures but completed
    FAILING = "failing"  # Last run failed
    INACTIVE = "inactive"  # No recent runs
    UNKNOWN = "unknown"  # Never run


@dataclass
class Project:
    """A registered project.

    Attributes:
        id: Unique project identifier.
        name: Human-readable project name.
        path: Local path or git URL.
        project_type: Type (local or git).
        config_json: JSON-encoded project configuration.
        tags_json: JSON-encoded list of tags for grouping.
        created_at: When the project was registered.
        updated_at: When the project was last updated.
        archived_at: When the project was archived (None if active).
        is_active: Whether the project is active.
    """

    id: int | None
    name: str
    path: str
    project_type: str = "local"
    config_json: str = "{}"
    tags_json: str = "[]"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None
    is_active: bool = True

    @property
    def tags(self) -> list[str]:
        """Get tags as a list."""
        import json
        try:
            return json.loads(self.tags_json)
        except (json.JSONDecodeError, TypeError):
            return []

    @tags.setter
    def tags(self, value: list[str]) -> None:
        """Set tags from a list (sorted and deduplicated)."""
        import json
        self.tags_json = json.dumps(sorted(set(value)))

    @property
    def is_archived(self) -> bool:
        """Check if project is archived."""
        return self.archived_at is not None


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


class AlertType(Enum):
    """Type of cost alert."""

    DAILY_THRESHOLD = "daily_threshold"
    MONTHLY_THRESHOLD = "monthly_threshold"
    TOTAL_THRESHOLD = "total_threshold"
    DAILY_EXCEEDED = "daily_exceeded"
    MONTHLY_EXCEEDED = "monthly_exceeded"
    TOTAL_EXCEEDED = "total_exceeded"


@dataclass
class CostRecord:
    """A cost record for a task execution.

    Attributes:
        id: Unique record identifier.
        project_id: Foreign key to project.
        run_id: Optional foreign key to run.
        task_execution_id: Optional foreign key to task execution.
        executor: Executor name used.
        model: Model identifier used.
        prompt_tokens: Number of input tokens.
        completion_tokens: Number of output tokens.
        total_tokens: Total tokens (prompt + completion).
        cost_usd: Estimated cost in USD.
        created_at: When the record was created.
        metadata_json: JSON-encoded additional metadata.
    """

    id: int | None
    project_id: int
    executor: str
    model: str
    run_id: int | None = None
    task_execution_id: int | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime | None = None
    metadata_json: str = "{}"

    @property
    def metadata(self) -> dict[str, Any]:
        """Get metadata as a dict."""
        import json
        try:
            return json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return {}


@dataclass
class CostBudget:
    """A cost budget for a project.

    Attributes:
        id: Unique budget identifier.
        project_id: Foreign key to project.
        daily_budget_usd: Daily budget limit.
        monthly_budget_usd: Monthly budget limit.
        total_budget_usd: Total (all-time) budget limit.
        alert_threshold_percent: Threshold for triggering alerts (0-100).
        is_hard_limit: Whether to block execution when budget exceeded.
        created_at: When the budget was created.
        updated_at: When the budget was last updated.
    """

    id: int | None
    project_id: int
    daily_budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    total_budget_usd: float | None = None
    alert_threshold_percent: float = 80.0
    is_hard_limit: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class CostAlert:
    """A cost alert triggered by budget threshold.

    Attributes:
        id: Unique alert identifier.
        project_id: Foreign key to project.
        alert_type: Type of alert.
        message: Alert message.
        budget_amount_usd: Budget amount that triggered alert.
        current_amount_usd: Current spending amount.
        threshold_percent: Threshold percentage reached.
        acknowledged: Whether alert has been acknowledged.
        acknowledged_at: When the alert was acknowledged.
        created_at: When the alert was created.
    """

    id: int | None
    project_id: int
    alert_type: AlertType
    message: str
    budget_amount_usd: float | None = None
    current_amount_usd: float | None = None
    threshold_percent: float | None = None
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    created_at: datetime | None = None


class UserRole(Enum):
    """User role for access control."""

    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


@dataclass
class User:
    """A user account.

    Attributes:
        id: Unique user identifier.
        username: Unique username for login.
        email: User email address.
        password_hash: Hashed password.
        role: User role for access control.
        display_name: Human-readable display name.
        is_active: Whether the account is active.
        settings_json: JSON-encoded user settings/preferences.
        created_at: When the account was created.
        updated_at: When the account was last updated.
        last_login_at: When the user last logged in.
    """

    id: int | None
    username: str
    email: str
    password_hash: str
    role: UserRole = UserRole.USER
    display_name: str | None = None
    is_active: bool = True
    settings_json: str = "{}"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None

    @property
    def settings(self) -> dict[str, Any]:
        """Get settings as a dict."""
        import json
        try:
            return json.loads(self.settings_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @settings.setter
    def settings(self, value: dict[str, Any]) -> None:
        """Set settings from a dict."""
        import json
        self.settings_json = json.dumps(value)


@dataclass
class Session:
    """A user session for authentication.

    Attributes:
        id: Unique session identifier.
        user_id: Foreign key to user.
        token: Session token (secure random string).
        expires_at: When the session expires.
        created_at: When the session was created.
        ip_address: Client IP address.
        user_agent: Client user agent string.
    """

    id: int | None
    user_id: int
    token: str
    expires_at: datetime
    created_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class AuditAction(Enum):
    """Type of audited action."""

    # User actions
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"

    # Project actions
    PROJECT_CREATE = "project_create"
    PROJECT_UPDATE = "project_update"
    PROJECT_DELETE = "project_delete"
    PROJECT_ARCHIVE = "project_archive"

    # Run actions
    RUN_START = "run_start"
    RUN_PAUSE = "run_pause"
    RUN_RESUME = "run_resume"
    RUN_CANCEL = "run_cancel"
    RUN_COMPLETE = "run_complete"

    # Settings actions
    SETTINGS_UPDATE = "settings_update"
    BUDGET_UPDATE = "budget_update"

    # Generic
    OTHER = "other"


@dataclass
class AuditLog:
    """Audit log entry for tracking user actions.

    Attributes:
        id: Unique log identifier.
        user_id: Foreign key to user (None for system actions).
        action: Type of action performed.
        resource_type: Type of resource affected.
        resource_id: ID of resource affected.
        details_json: JSON-encoded action details.
        ip_address: Client IP address.
        user_agent: Client user agent string.
        created_at: When the action occurred.
    """

    id: int | None
    action: AuditAction
    resource_type: str | None = None
    resource_id: str | None = None
    user_id: int | None = None
    details_json: str = "{}"
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime | None = None

    @property
    def details(self) -> dict[str, Any]:
        """Get details as a dict."""
        import json
        try:
            return json.loads(self.details_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @details.setter
    def details(self, value: dict[str, Any]) -> None:
        """Set details from a dict."""
        import json
        self.details_json = json.dumps(value)
