"""Dry run executor for testing without actual AI calls.

This module provides a mock executor for testing the execution flow.
"""

import random
import time
from typing import Any

from src.engine.logging import logger

from .base import ExecutionResult, ExecutorConfig, TaskContext
from .plugin import ExecutorPlugin, PluginConfigField, PluginSchema


class DryRunExecutor(ExecutorPlugin):
    """Executor that simulates task execution without making changes.

    Useful for testing the execution flow without actual AI calls.
    """

    @classmethod
    def get_plugin_info(cls) -> dict[str, Any]:
        """Get plugin metadata."""
        return {
            "name": "dry-run",
            "display_name": "Dry Run",
            "description": "Simulates task execution without making changes. "
            "Useful for testing the execution flow.",
            "version": "1.0.0",
            "author": "PRDForge",
        }

    @classmethod
    def get_config_schema(cls) -> PluginSchema:
        """Get the configuration schema for this plugin."""
        return PluginSchema(
            fields=[
                PluginConfigField(
                    name="delay",
                    type="number",
                    description="Simulated execution delay in seconds",
                    required=False,
                    default=0.0,
                    min_value=0.0,
                    max_value=60.0,
                ),
                PluginConfigField(
                    name="fail_rate",
                    type="number",
                    description="Probability of simulated failure (0.0-1.0)",
                    required=False,
                    default=0.0,
                    min_value=0.0,
                    max_value=1.0,
                ),
            ]
        )

    @classmethod
    def get_capabilities(cls) -> list[str]:
        """Get list of capabilities (all simulated)."""
        return ["code_generation", "simulation"]

    @property
    def name(self) -> str:
        return "dry-run"

    @property
    def version(self) -> str:
        return "1.0.0"

    def _execute_impl(self, context: TaskContext) -> ExecutionResult:
        """Simulate task execution.

        Args:
            context: Task execution context.

        Returns:
            ExecutionResult indicating simulated success.
        """
        logger.info(f"[DRY RUN] Simulating execution of task: {context.task_id}")
        logger.debug(f"[DRY RUN] Description: {context.description}")
        logger.debug(f"[DRY RUN] Steps: {len(context.steps)}")

        # Simulate delay if configured
        delay = self.config.extra.get("delay", 0.0)
        if delay > 0:
            time.sleep(delay)

        # Simulate failure if configured
        fail_rate = self.config.extra.get("fail_rate", 0.0)
        if fail_rate > 0 and random.random() < fail_rate:
            return ExecutionResult(
                success=False,
                output="[DRY RUN] Simulated failure",
                error="Simulated random failure",
                metadata={"simulated": True, "simulated_failure": True},
            )

        return ExecutionResult(
            success=True,
            output=f"[DRY RUN] Task {context.task_id} simulated successfully.\n"
            f"Description: {context.description}\n"
            f"Steps: {len(context.steps)}",
            metadata={
                "simulated": True,
                "steps_count": len(context.steps),
            },
        )
