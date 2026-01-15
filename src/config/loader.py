"""Configuration loading from files, environment variables, and CLI args."""

import json
import os
from pathlib import Path
from typing import Any

from .models import (
    ExecutorSettings,
    GitSettings,
    PRDForgeConfig,
    ProjectConfig,
    ProjectType,
)
from .validator import ConfigValidationError, ConfigValidator


# Try to import yaml, but make it optional
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None


class ConfigLoader:
    """Load PRDForge configuration from multiple sources.

    Priority order (highest to lowest):
    1. CLI arguments (passed directly)
    2. Environment variables
    3. Config file
    4. Defaults

    Environment variable mapping:
    - PRDFORGE_LOG_LEVEL -> log_level
    - PRDFORGE_LOG_FORMAT -> log_format
    - PRDFORGE_WORKSPACE_DIR -> workspace_dir
    - PRDFORGE_DATABASE_PATH -> database_path
    - PRDFORGE_DEFAULT_EXECUTOR -> executor.default_executor
    - PRDFORGE_CLAUDE_CLI_PATH -> executor.claude_cli_path
    - PRDFORGE_CLAUDE_MODEL -> executor.claude_model
    - PRDFORGE_GIT_DEFAULT_BRANCH -> git.default_branch
    - PRDFORGE_AUTO_COMMIT -> git.auto_commit
    - PRDFORGE_AUTO_PUSH -> git.auto_push
    """

    # Standard config file names in priority order
    CONFIG_FILE_NAMES = [
        "prdforge.yaml",
        "prdforge.yml",
        "prdforge.json",
        ".prdforge.yaml",
        ".prdforge.yml",
        ".prdforge.json",
    ]

    # Environment variable prefix
    ENV_PREFIX = "PRDFORGE_"

    # Mapping of env vars to config paths
    ENV_MAPPING = {
        "LOG_LEVEL": "log_level",
        "LOG_FORMAT": "log_format",
        "WORKSPACE_DIR": "workspace_dir",
        "DATABASE_PATH": "database_path",
        "DEFAULT_PROJECT": "default_project",
    }

    # Executor-specific env vars
    EXECUTOR_ENV_MAPPING = {
        "DEFAULT_EXECUTOR": "default_executor",
        "MAX_RETRIES": "max_retries",
        "TIMEOUT_SECONDS": "timeout_seconds",
        "CLAUDE_CLI_PATH": "claude_cli_path",
        "CLAUDE_MODEL": "claude_model",
    }

    # Git-specific env vars
    GIT_ENV_MAPPING = {
        "GIT_DEFAULT_BRANCH": "default_branch",
        "AUTO_COMMIT": "auto_commit",
        "AUTO_PUSH": "auto_push",
    }

    def __init__(self, validate: bool = True):
        """Initialize the config loader.

        Args:
            validate: Whether to validate loaded config.
        """
        self.validate = validate
        self.validator = ConfigValidator() if validate else None

    def load(
        self,
        config_path: str | Path | None = None,
        cli_overrides: dict[str, Any] | None = None,
    ) -> PRDForgeConfig:
        """Load configuration from all sources.

        Args:
            config_path: Explicit path to config file.
            cli_overrides: Dictionary of CLI argument overrides.

        Returns:
            Loaded and merged PRDForgeConfig.

        Raises:
            ConfigValidationError: If validation is enabled and fails.
        """
        # Start with defaults
        config_dict: dict[str, Any] = {}

        # Load from file
        file_path = self._find_config_file(config_path)
        if file_path:
            file_config = self._load_file(file_path)
            config_dict = self._deep_merge(config_dict, file_config)

        # Apply environment variable overrides
        env_config = self._load_from_env()
        config_dict = self._deep_merge(config_dict, env_config)

        # Apply CLI overrides
        if cli_overrides:
            config_dict = self._deep_merge(config_dict, cli_overrides)

        # Create config object
        config = PRDForgeConfig(**config_dict) if config_dict else PRDForgeConfig()

        # Validate if enabled
        if self.validate and self.validator:
            self.validator.validate_and_raise(config, str(file_path) if file_path else None)

        return config

    def _find_config_file(self, explicit_path: str | Path | None) -> Path | None:
        """Find the config file to use.

        Args:
            explicit_path: Explicitly specified path.

        Returns:
            Path to config file, or None if not found.
        """
        if explicit_path:
            path = Path(explicit_path)
            if path.exists():
                return path
            raise ConfigValidationError(
                [f"Config file not found: {explicit_path}"],
                config_path=str(explicit_path),
            )

        # Search in current directory and home directory
        search_dirs = [
            Path.cwd(),
            Path.home() / ".prdforge",
            Path.home(),
        ]

        for directory in search_dirs:
            if not directory.exists():
                continue
            for name in self.CONFIG_FILE_NAMES:
                path = directory / name
                if path.exists():
                    return path

        return None

    def _load_file(self, path: Path) -> dict[str, Any]:
        """Load configuration from a file.

        Args:
            path: Path to the config file.

        Returns:
            Configuration dictionary.
        """
        content = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml"):
            if not YAML_AVAILABLE:
                raise ConfigValidationError(
                    ["YAML config files require PyYAML. Install with: pip install pyyaml"],
                    config_path=str(path),
                )
            return yaml.safe_load(content) or {}

        if path.suffix == ".json":
            return json.loads(content)

        # Try to auto-detect format
        content_stripped = content.strip()
        if content_stripped.startswith("{"):
            return json.loads(content)
        if YAML_AVAILABLE:
            return yaml.safe_load(content) or {}

        raise ConfigValidationError(
            [f"Unable to determine config file format: {path}"],
            config_path=str(path),
        )

    def _load_from_env(self) -> dict[str, Any]:
        """Load configuration from environment variables.

        Returns:
            Configuration dictionary from env vars.
        """
        config: dict[str, Any] = {}

        # Global settings
        for env_key, config_key in self.ENV_MAPPING.items():
            full_key = f"{self.ENV_PREFIX}{env_key}"
            value = os.environ.get(full_key)
            if value is not None:
                config[config_key] = value

        # Executor settings (for default project)
        executor_config: dict[str, Any] = {}
        for env_key, config_key in self.EXECUTOR_ENV_MAPPING.items():
            full_key = f"{self.ENV_PREFIX}{env_key}"
            value = os.environ.get(full_key)
            if value is not None:
                # Convert types
                if config_key in ("max_retries", "timeout_seconds"):
                    value = int(value)
                executor_config[config_key] = value

        # Git settings
        git_config: dict[str, Any] = {}
        for env_key, config_key in self.GIT_ENV_MAPPING.items():
            full_key = f"{self.ENV_PREFIX}{env_key}"
            value = os.environ.get(full_key)
            if value is not None:
                # Convert boolean types
                if config_key in ("auto_commit", "auto_push"):
                    value = value.lower() in ("true", "1", "yes")
                git_config[config_key] = value

        # If we have executor or git config, we need to apply it to projects
        # This is stored as metadata to be applied later
        if executor_config or git_config:
            config["_env_executor"] = executor_config
            config["_env_git"] = git_config

        return config

    def _deep_merge(
        self,
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
        """Deep merge two dictionaries.

        Args:
            base: Base dictionary.
            override: Dictionary with values to override.

        Returns:
            Merged dictionary.
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result


def load_project_config(
    config_path: str | Path | None = None,
    project_name: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> ProjectConfig:
    """Load a project configuration.

    Convenience function that loads the PRDForge config and extracts
    a specific project configuration.

    Args:
        config_path: Path to config file.
        project_name: Name of project to load (uses default if None).
        cli_overrides: CLI argument overrides.

    Returns:
        ProjectConfig for the specified project.

    Raises:
        ConfigValidationError: If config is invalid or project not found.
    """
    loader = ConfigLoader()
    config = loader.load(config_path, cli_overrides)

    project = config.get_project(project_name)
    if project is None:
        if project_name:
            raise ConfigValidationError(
                [f"Project '{project_name}' not found in configuration"],
                config_path=str(config_path) if config_path else None,
            )
        if not config.projects:
            raise ConfigValidationError(
                ["No projects defined in configuration"],
                config_path=str(config_path) if config_path else None,
            )
        raise ConfigValidationError(
            ["Multiple projects defined but no default_project set"],
            config_path=str(config_path) if config_path else None,
        )

    return project


def create_default_config(
    project_path: str | Path,
    project_name: str | None = None,
) -> PRDForgeConfig:
    """Create a default configuration for a project.

    Args:
        project_path: Path to the project directory.
        project_name: Name for the project (derived from path if None).

    Returns:
        PRDForgeConfig with a single project configured.
    """
    path = Path(project_path).resolve()

    if project_name is None:
        project_name = path.name

    project = ProjectConfig(
        name=project_name,
        path=str(path),
        project_type=ProjectType.LOCAL,
    )

    return PRDForgeConfig(projects=[project])


def write_config_file(
    config: PRDForgeConfig,
    path: str | Path,
    format: str = "yaml",
) -> None:
    """Write configuration to a file.

    Args:
        config: Configuration to write.
        path: Path to write to.
        format: Output format ('yaml' or 'json').
    """
    path = Path(path)
    config_dict = config.to_dict()

    if format == "yaml":
        if not YAML_AVAILABLE:
            raise RuntimeError(
                "YAML output requires PyYAML. Install with: pip install pyyaml"
            )
        content = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
    elif format == "json":
        content = json.dumps(config_dict, indent=2)
    else:
        raise ValueError(f"Unknown format: {format}")

    path.write_text(content, encoding="utf-8")
