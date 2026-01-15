"""Configuration validation with helpful error messages."""

from dataclasses import dataclass, field
from pathlib import Path

from .models import PRDForgeConfig, ProjectConfig, ProjectType


class ConfigValidationError(Exception):
    """Raised when configuration validation fails.

    Attributes:
        errors: List of validation error messages.
        config_path: Path to the config file being validated.
    """

    def __init__(
        self,
        errors: list[str],
        config_path: str | None = None,
    ):
        self.errors = errors
        self.config_path = config_path
        message = self._format_message()
        super().__init__(message)

    def _format_message(self) -> str:
        """Format validation errors into a readable message."""
        lines = ["Configuration validation failed:"]
        if self.config_path:
            lines.append(f"  File: {self.config_path}")
        lines.append("")
        for error in self.errors:
            lines.append(f"  • {error}")
        return "\n".join(lines)


@dataclass
class ValidationResult:
    """Result of validation with errors and warnings."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add an error and mark as invalid."""
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning (doesn't affect validity)."""
        self.warnings.append(message)

    def merge(self, other: "ValidationResult") -> None:
        """Merge another result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if not other.valid:
            self.valid = False


class ConfigValidator:
    """Validates PRDForge configuration with helpful error messages."""

    # Valid executor names
    VALID_EXECUTORS = {"claude-cli", "codex", "gemini", "dry-run"}

    # Valid log levels
    VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    # Valid log formats
    VALID_LOG_FORMATS = {"json", "pretty"}

    def validate(
        self,
        config: PRDForgeConfig,
        config_path: str | None = None,
    ) -> ValidationResult:
        """Validate a PRDForge configuration.

        Args:
            config: The configuration to validate.
            config_path: Optional path to config file (for error messages).

        Returns:
            ValidationResult with errors and warnings.
        """
        result = ValidationResult()

        # Validate global settings
        self._validate_global_settings(config, result)

        # Validate each project
        for i, project in enumerate(config.projects):
            project_result = self.validate_project(project, index=i)
            result.merge(project_result)

        # Check for duplicate project names
        names = [p.name for p in config.projects]
        duplicates = [n for n in set(names) if names.count(n) > 1]
        if duplicates:
            result.add_error(
                f"Duplicate project names: {', '.join(duplicates)}"
            )

        # Validate default_project reference
        if config.default_project:
            if config.default_project not in names:
                result.add_error(
                    f"default_project '{config.default_project}' not found in projects"
                )

        return result

    def validate_project(
        self,
        project: ProjectConfig,
        index: int | None = None,
    ) -> ValidationResult:
        """Validate a single project configuration.

        Args:
            project: The project configuration to validate.
            index: Optional index for error messages.

        Returns:
            ValidationResult with errors and warnings.
        """
        result = ValidationResult()
        prefix = f"projects[{index}]" if index is not None else f"project '{project.name}'"

        # Required fields
        if not project.name:
            result.add_error(f"{prefix}: 'name' is required")

        if not project.path:
            result.add_error(f"{prefix}: 'path' is required")

        # Validate path based on type
        if project.path:
            if project.project_type == ProjectType.LOCAL:
                path = Path(project.path).expanduser()
                if not path.exists():
                    result.add_warning(
                        f"{prefix}: Local path does not exist: {project.path}"
                    )
                elif not path.is_dir():
                    result.add_error(
                        f"{prefix}: Path is not a directory: {project.path}"
                    )
            elif project.project_type == ProjectType.GIT:
                if not self._is_valid_git_url(project.path):
                    result.add_error(
                        f"{prefix}: Invalid git URL: {project.path}"
                    )

        # Validate PRD patterns
        if not project.prd_patterns:
            result.add_warning(
                f"{prefix}: No PRD patterns specified, using defaults"
            )

        # Validate executor settings
        self._validate_executor_settings(project, prefix, result)

        # Validate git settings
        self._validate_git_settings(project, prefix, result)

        return result

    def _validate_global_settings(
        self,
        config: PRDForgeConfig,
        result: ValidationResult,
    ) -> None:
        """Validate global configuration settings."""
        # Log level
        if config.log_level.upper() not in self.VALID_LOG_LEVELS:
            result.add_error(
                f"Invalid log_level '{config.log_level}'. "
                f"Must be one of: {', '.join(self.VALID_LOG_LEVELS)}"
            )

        # Log format
        if config.log_format.lower() not in self.VALID_LOG_FORMATS:
            result.add_error(
                f"Invalid log_format '{config.log_format}'. "
                f"Must be one of: {', '.join(self.VALID_LOG_FORMATS)}"
            )

        # Workspace dir
        workspace = Path(config.workspace_dir).expanduser()
        if workspace.exists() and not workspace.is_dir():
            result.add_error(
                f"workspace_dir exists but is not a directory: {config.workspace_dir}"
            )

        # Database path parent
        db_path = Path(config.database_path).expanduser()
        if not db_path.parent.exists():
            result.add_warning(
                f"Database parent directory does not exist: {db_path.parent}"
            )

    def _validate_executor_settings(
        self,
        project: ProjectConfig,
        prefix: str,
        result: ValidationResult,
    ) -> None:
        """Validate executor settings."""
        executor = project.executor

        if executor.default_executor not in self.VALID_EXECUTORS:
            result.add_error(
                f"{prefix}.executor.default_executor: Invalid executor "
                f"'{executor.default_executor}'. "
                f"Must be one of: {', '.join(self.VALID_EXECUTORS)}"
            )

        if executor.max_retries < 0:
            result.add_error(
                f"{prefix}.executor.max_retries: Cannot be negative"
            )

        if executor.timeout_seconds <= 0:
            result.add_error(
                f"{prefix}.executor.timeout_seconds: Must be positive"
            )

        if executor.claude_cli_path:
            path = Path(executor.claude_cli_path)
            if not path.exists():
                result.add_warning(
                    f"{prefix}.executor.claude_cli_path: "
                    f"Path does not exist: {executor.claude_cli_path}"
                )

    def _validate_git_settings(
        self,
        project: ProjectConfig,
        prefix: str,
        result: ValidationResult,
    ) -> None:
        """Validate git settings."""
        git = project.git

        if not git.default_branch:
            result.add_error(
                f"{prefix}.git.default_branch: Cannot be empty"
            )

        if not git.run_branch_prefix:
            result.add_warning(
                f"{prefix}.git.run_branch_prefix: Empty prefix may cause issues"
            )

        # Validate commit template has required placeholders
        template = git.commit_template
        if "{task_id}" not in template and "{description}" not in template:
            result.add_warning(
                f"{prefix}.git.commit_template: Template should contain "
                "{{task_id}} or {{description}} placeholders"
            )

    def _is_valid_git_url(self, url: str) -> bool:
        """Check if URL is a valid git URL."""
        url_lower = url.lower()
        return (
            url_lower.startswith("git@")
            or url_lower.startswith("https://")
            or url_lower.startswith("http://")
            or url_lower.startswith("ssh://")
        )

    def validate_and_raise(
        self,
        config: PRDForgeConfig,
        config_path: str | None = None,
    ) -> None:
        """Validate configuration and raise if invalid.

        Args:
            config: The configuration to validate.
            config_path: Optional path to config file.

        Raises:
            ConfigValidationError: If validation fails.
        """
        result = self.validate(config, config_path)
        if not result.valid:
            raise ConfigValidationError(result.errors, config_path)
