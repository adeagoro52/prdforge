"""Configuration management for PRDForge.

This module provides:
- ProjectConfig: Configuration for individual projects
- ConfigLoader: Load config from files, env vars, and CLI args
- ConfigValidator: Validate configuration with helpful errors

Example usage:
    from config import ProjectConfig, load_project_config

    # Load from file with env var overrides
    config = load_project_config("prdforge.yaml")

    # Or create directly
    config = ProjectConfig(
        name="my-project",
        path="/path/to/project",
        prd_patterns=["docs/prds/*.json"],
    )
"""

from .loader import ConfigLoader, load_project_config
from .models import (
    ExecutorSettings,
    GitSettings,
    PRDForgeConfig,
    ProjectConfig,
)
from .validator import ConfigValidationError, ConfigValidator

__all__ = [
    "ProjectConfig",
    "PRDForgeConfig",
    "ExecutorSettings",
    "GitSettings",
    "ConfigLoader",
    "ConfigValidator",
    "ConfigValidationError",
    "load_project_config",
]
