"""Base skill definitions for PRDForge.

This module provides the abstract base class and supporting types
for implementing skills.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class SkillSource(Enum):
    """Source/origin of a skill definition."""

    PACKAGE = "package"  # Built into PRDForge
    USER = "user"  # User-level ~/.prdforge/skills/
    PROJECT = "project"  # Project-level .prdforge/skills/


class SkillStatus(Enum):
    """Execution status of a skill."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SkillConfig:
    """Configuration for a skill instance.

    Attributes:
        enabled: Whether the skill is enabled.
        timeout: Maximum execution time in seconds.
        retry_count: Number of retries on failure.
        env: Environment variables to set.
        options: Skill-specific options.
    """

    enabled: bool = True
    timeout: int = 300  # 5 minutes default
    retry_count: int = 0
    env: dict[str, str] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillConfig":
        """Create config from dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            SkillConfig instance.
        """
        return cls(
            enabled=data.get("enabled", True),
            timeout=data.get("timeout", 300),
            retry_count=data.get("retry_count", 0),
            env=data.get("env", {}),
            options=data.get("options", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary.

        Returns:
            Configuration as dictionary.
        """
        return {
            "enabled": self.enabled,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "env": self.env,
            "options": self.options,
        }


@dataclass
class SkillResult:
    """Result of a skill execution.

    Attributes:
        status: Execution status.
        output: Output from the skill (stdout/logs).
        error: Error message if failed.
        duration: Execution duration in seconds.
        metadata: Additional metadata from execution.
    """

    status: SkillStatus
    output: str = ""
    error: Optional[str] = None
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == SkillStatus.SUCCESS

    @property
    def failed(self) -> bool:
        """Check if execution failed."""
        return self.status == SkillStatus.FAILED


class SkillError(Exception):
    """Error raised during skill execution."""

    def __init__(self, message: str, skill_name: str = "", output: str = ""):
        """Initialize skill error.

        Args:
            message: Error message.
            skill_name: Name of the skill that failed.
            output: Output/logs from the skill.
        """
        super().__init__(message)
        self.skill_name = skill_name
        self.output = output


class Skill(ABC):
    """Abstract base class for skills.

    Skills are reusable automation tasks that can be executed
    during PRD runs or independently. They support:
    - Configuration via SkillConfig
    - Multiple execution contexts (CLI, API)
    - Output capture and error handling

    Example implementation::

        class MySkill(Skill):
            name = "my-skill"
            description = "Does something useful"

            def execute(self, context: SkillContext) -> SkillResult:
                # Implementation
                return SkillResult(status=SkillStatus.SUCCESS)
    """

    # Class-level attributes to be overridden
    name: str = ""
    description: str = ""
    category: str = "general"

    def __init__(
        self,
        config: Optional[SkillConfig] = None,
        source: SkillSource = SkillSource.PACKAGE,
    ):
        """Initialize skill.

        Args:
            config: Skill configuration.
            source: Origin of the skill definition.
        """
        self.config = config or SkillConfig()
        self.source = source

    @abstractmethod
    def execute(self, context: "SkillContext") -> SkillResult:
        """Execute the skill.

        Args:
            context: Execution context with project path, etc.

        Returns:
            Result of the execution.
        """
        pass

    def validate(self) -> list[str]:
        """Validate skill configuration.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []

        if not self.name:
            errors.append("Skill name is required")

        if self.config.timeout < 0:
            errors.append("Timeout must be non-negative")

        if self.config.retry_count < 0:
            errors.append("Retry count must be non-negative")

        return errors

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, source={self.source.value})"


@dataclass
class SkillContext:
    """Execution context for skills.

    Attributes:
        project_path: Path to the project directory.
        working_dir: Working directory for execution.
        task_id: Optional task ID if running as part of a task.
        run_id: Optional run ID if running as part of a run.
        dry_run: If True, don't make actual changes.
        files: Optional list of files to operate on.
        env: Additional environment variables.
    """

    project_path: Path
    working_dir: Optional[Path] = None
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    dry_run: bool = False
    files: list[Path] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Set defaults after initialization."""
        if self.working_dir is None:
            self.working_dir = self.project_path
