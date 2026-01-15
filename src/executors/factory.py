"""Executor factory for instantiating AI executors.

This module provides the ExecutorFactory class for creating executor
instances based on configuration.
"""

from typing import Any

from src.engine.logging import logger

from .base import BaseExecutor, ExecutorConfig
from .dry_run import DryRunExecutor


class ExecutorRegistry:
    """Registry for executor implementations.

    Provides a centralized place to register and lookup executor classes.
    """

    _executors: dict[str, type[BaseExecutor]] = {}

    @classmethod
    def register(cls, name: str, executor_class: type[BaseExecutor]) -> None:
        """Register an executor class.

        Args:
            name: Executor name (e.g., 'claude-cli').
            executor_class: The executor class to register.
        """
        cls._executors[name] = executor_class
        logger.debug(f"Registered executor: {name}")

    @classmethod
    def get(cls, name: str) -> type[BaseExecutor] | None:
        """Get an executor class by name.

        Args:
            name: Executor name.

        Returns:
            Executor class or None if not found.
        """
        return cls._executors.get(name)

    @classmethod
    def list_executors(cls) -> list[str]:
        """List all registered executor names.

        Returns:
            List of executor names.
        """
        return list(cls._executors.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered executors."""
        cls._executors.clear()


class ExecutorFactory:
    """Factory for creating executor instances.

    This factory handles:
    - Executor instantiation based on name
    - Configuration injection
    - Default executor selection
    """

    # Default executor to use if none specified
    DEFAULT_EXECUTOR = "claude-cli"

    def __init__(self) -> None:
        """Initialize the factory and register built-in executors."""
        self._register_builtin_executors()

    def _register_builtin_executors(self) -> None:
        """Register built-in executor implementations."""
        # Import here to avoid circular imports
        from .claude_cli import ClaudeCLIExecutor

        ExecutorRegistry.register("claude-cli", ClaudeCLIExecutor)
        ExecutorRegistry.register("dry-run", DryRunExecutor)

    def create(
        self,
        name: str | None = None,
        config: ExecutorConfig | dict[str, Any] | None = None,
    ) -> BaseExecutor:
        """Create an executor instance.

        Args:
            name: Executor name. Uses DEFAULT_EXECUTOR if not specified.
            config: Executor configuration (ExecutorConfig or dict).

        Returns:
            Executor instance.

        Raises:
            ValueError: If executor name is not registered.
        """
        name = name or self.DEFAULT_EXECUTOR

        executor_class = ExecutorRegistry.get(name)
        if not executor_class:
            available = ExecutorRegistry.list_executors()
            raise ValueError(
                f"Unknown executor: {name}. Available: {available}"
            )

        # Handle config
        if config is None:
            executor_config = None
        elif isinstance(config, dict):
            executor_config = ExecutorConfig(**config)
        else:
            executor_config = config

        executor = executor_class(executor_config)
        logger.info(f"Created executor: {name} (version: {executor.version})")

        return executor

    def create_for_task(
        self,
        task_config: dict[str, Any] | None = None,
        project_config: dict[str, Any] | None = None,
    ) -> BaseExecutor:
        """Create an executor based on task and project configuration.

        Resolution order:
        1. Task-specific executor setting
        2. Project-level executor setting
        3. Default executor

        Args:
            task_config: Task-specific configuration.
            project_config: Project-level configuration.

        Returns:
            Executor instance.
        """
        # Determine executor name
        executor_name = None

        if task_config:
            executor_name = task_config.get("executor")

        if not executor_name and project_config:
            executor_name = project_config.get("default_executor")

        if not executor_name:
            executor_name = self.DEFAULT_EXECUTOR

        # Merge configs (task config overrides project config)
        merged_config: dict[str, Any] = {}

        if project_config and "executor_config" in project_config:
            merged_config.update(project_config["executor_config"])

        if task_config and "executor_config" in task_config:
            merged_config.update(task_config["executor_config"])

        return self.create(executor_name, merged_config or None)

    def list_available(self) -> list[dict[str, Any]]:
        """List all available executors with their info.

        Returns:
            List of executor info dicts.
        """
        result = []
        for name in ExecutorRegistry.list_executors():
            executor_class = ExecutorRegistry.get(name)
            if executor_class:
                # Create temporary instance to get info
                try:
                    instance = executor_class()
                    info = instance.get_info()
                    info["available"] = instance.health_check()
                    result.append(info)
                except Exception as e:
                    result.append({
                        "name": name,
                        "available": False,
                        "error": str(e),
                    })

        return result


# Global factory instance
executor_factory = ExecutorFactory()
