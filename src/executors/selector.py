"""Executor selection and fallback logic.

This module provides intelligent executor selection based on:
- Health status
- Configuration
- Task requirements
- Cost optimization
- Rate limiting
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.engine.logging import logger

from .base import ExecutorStatus, TaskContext
from .plugin import ExecutorPlugin, ExecutorSelection, PluginManager


class SelectionStrategy(Enum):
    """Strategy for selecting executors."""

    PRIMARY_ONLY = "primary_only"  # Use only the primary executor
    FALLBACK = "fallback"  # Try primary, fall back to secondary
    ROUND_ROBIN = "round_robin"  # Rotate between available executors
    COST_OPTIMIZED = "cost_optimized"  # Select cheapest available executor
    CAPABILITY_MATCH = "capability_match"  # Select based on required capabilities


@dataclass
class SelectionResult:
    """Result of executor selection."""

    executor: ExecutorPlugin | None
    executor_name: str
    reason: str
    alternatives: list[str] = field(default_factory=list)
    fallback_used: bool = False


@dataclass
class ExecutorHealth:
    """Health tracking for an executor."""

    name: str
    healthy: bool = True
    consecutive_failures: int = 0
    last_success_time: float | None = None
    last_failure_time: float | None = None
    rate_limited_until: float | None = None


class ExecutorSelector:
    """Intelligent executor selection with fallback support.

    Features:
    - Primary/fallback executor pattern
    - Health monitoring and tracking
    - Task-specific executor override
    - Cost-based selection
    - Rate limiting coordination
    """

    # Threshold for marking executor as unhealthy
    FAILURE_THRESHOLD = 3

    # Default executor order for fallback
    DEFAULT_FALLBACK_ORDER = ["claude-cli", "claude-api", "openai", "gemini", "dry-run"]

    def __init__(
        self,
        plugin_manager: PluginManager | None = None,
        selection: ExecutorSelection | None = None,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> None:
        """Initialize the selector.

        Args:
            plugin_manager: Plugin manager for creating executors.
            selection: Project-level executor selection settings.
            strategy: Selection strategy to use.
        """
        self.plugin_manager = plugin_manager or PluginManager()
        self.selection = selection or ExecutorSelection()
        self.strategy = strategy

        # Health tracking per executor
        self._health: dict[str, ExecutorHealth] = {}

        # Round-robin index for rotation strategy
        self._round_robin_index = 0

    def select(
        self,
        context: TaskContext | None = None,
        task_config: dict[str, Any] | None = None,
        required_capabilities: list[str] | None = None,
    ) -> SelectionResult:
        """Select the best executor for a task.

        Resolution order:
        1. Task-specific executor (from task_config or context.extra_context)
        2. Project default executor (from self.selection)
        3. Strategy-based selection from available executors

        Args:
            context: Task execution context.
            task_config: Task-specific configuration.
            required_capabilities: Required executor capabilities.

        Returns:
            SelectionResult with the selected executor.
        """
        # Check for task-specific executor override
        task_executor = None
        if task_config:
            task_executor = task_config.get("executor")
        if not task_executor and context and context.extra_context:
            task_executor = context.extra_context.get("executor")

        if task_executor:
            return self._try_select_executor(
                task_executor,
                reason="Task-specific executor",
            )

        # Check for project default
        if self.selection.default_executor:
            result = self._try_select_executor(
                self.selection.default_executor,
                reason="Project default executor",
            )
            if result.executor:
                return result

        # Strategy-based selection
        return self._select_by_strategy(required_capabilities)

    def _try_select_executor(
        self,
        name: str,
        reason: str,
        config: dict[str, Any] | None = None,
    ) -> SelectionResult:
        """Try to select a specific executor.

        Args:
            name: Executor name.
            reason: Reason for selection.
            config: Optional executor configuration.

        Returns:
            SelectionResult (executor may be None if unavailable).
        """
        # Check if executor is enabled
        if not self.selection.is_enabled(name):
            return SelectionResult(
                executor=None,
                executor_name=name,
                reason=f"{name} is disabled",
                alternatives=self._get_alternatives(name),
            )

        # Check health
        health = self._get_health(name)
        if not health.healthy:
            return SelectionResult(
                executor=None,
                executor_name=name,
                reason=f"{name} is unhealthy ({health.consecutive_failures} failures)",
                alternatives=self._get_alternatives(name),
            )

        # Check rate limiting
        if health.rate_limited_until:
            import time
            if time.time() < health.rate_limited_until:
                return SelectionResult(
                    executor=None,
                    executor_name=name,
                    reason=f"{name} is rate limited",
                    alternatives=self._get_alternatives(name),
                )

        # Try to create the executor
        try:
            merged_config = self.selection.get_config(name)
            if config:
                merged_config.update(config)

            executor = self.plugin_manager.create_executor(
                name,
                config=merged_config or None,
                selection=self.selection,
            )

            # Quick health check
            if not executor.health_check():
                return SelectionResult(
                    executor=None,
                    executor_name=name,
                    reason=f"{name} failed health check",
                    alternatives=self._get_alternatives(name),
                )

            return SelectionResult(
                executor=executor,
                executor_name=name,
                reason=reason,
            )

        except ValueError as e:
            return SelectionResult(
                executor=None,
                executor_name=name,
                reason=str(e),
                alternatives=self._get_alternatives(name),
            )

    def _select_by_strategy(
        self,
        required_capabilities: list[str] | None = None,
    ) -> SelectionResult:
        """Select executor based on configured strategy.

        Args:
            required_capabilities: Required executor capabilities.

        Returns:
            SelectionResult with selected executor.
        """
        if self.strategy == SelectionStrategy.PRIMARY_ONLY:
            return self._select_primary()
        elif self.strategy == SelectionStrategy.FALLBACK:
            return self._select_with_fallback()
        elif self.strategy == SelectionStrategy.ROUND_ROBIN:
            return self._select_round_robin()
        elif self.strategy == SelectionStrategy.COST_OPTIMIZED:
            return self._select_cost_optimized()
        elif self.strategy == SelectionStrategy.CAPABILITY_MATCH:
            return self._select_by_capability(required_capabilities or [])
        else:
            return self._select_with_fallback()

    def _select_primary(self) -> SelectionResult:
        """Select only the primary executor."""
        primary = self.selection.default_executor or self.DEFAULT_FALLBACK_ORDER[0]
        return self._try_select_executor(primary, "Primary executor")

    def _select_with_fallback(self) -> SelectionResult:
        """Select with fallback to alternatives."""
        # Build ordered list: default first, then fallback, then others
        ordered = []

        if self.selection.default_executor:
            ordered.append(self.selection.default_executor)

        if self.selection.fallback_executor:
            if self.selection.fallback_executor not in ordered:
                ordered.append(self.selection.fallback_executor)

        for name in self.DEFAULT_FALLBACK_ORDER:
            if name not in ordered:
                ordered.append(name)

        # Try each executor in order
        for i, name in enumerate(ordered):
            result = self._try_select_executor(
                name,
                reason=f"Fallback executor (#{i+1})",
            )
            if result.executor:
                result.fallback_used = (i > 0)
                return result

        # No executor available
        return SelectionResult(
            executor=None,
            executor_name="none",
            reason="No executors available",
        )

    def _select_round_robin(self) -> SelectionResult:
        """Select using round-robin rotation."""
        available = self._get_available_executors()
        if not available:
            return SelectionResult(
                executor=None,
                executor_name="none",
                reason="No executors available for round-robin",
            )

        # Select next executor in rotation
        name = available[self._round_robin_index % len(available)]
        self._round_robin_index += 1

        return self._try_select_executor(
            name,
            reason=f"Round-robin selection (index {self._round_robin_index})",
        )

    def _select_cost_optimized(self) -> SelectionResult:
        """Select the cheapest available executor."""
        # Cost ranking (lower is better, rough estimates)
        cost_ranking = {
            "dry-run": 0,
            "gemini": 1,  # Generally cheapest paid option
            "openai": 2,  # GPT-4o-mini is cheap
            "claude-cli": 3,
            "claude-api": 3,
        }

        available = self._get_available_executors()
        if not available:
            return SelectionResult(
                executor=None,
                executor_name="none",
                reason="No executors available for cost optimization",
            )

        # Sort by cost
        sorted_executors = sorted(
            available,
            key=lambda x: cost_ranking.get(x, 100)
        )

        for name in sorted_executors:
            result = self._try_select_executor(
                name,
                reason="Cost-optimized selection",
            )
            if result.executor:
                return result

        return SelectionResult(
            executor=None,
            executor_name="none",
            reason="No cost-effective executors available",
        )

    def _select_by_capability(
        self,
        required_capabilities: list[str],
    ) -> SelectionResult:
        """Select executor matching required capabilities.

        Args:
            required_capabilities: List of required capabilities.

        Returns:
            SelectionResult with matching executor.
        """
        if not required_capabilities:
            return self._select_with_fallback()

        # Get all plugins and check capabilities
        self.plugin_manager.refresh()
        plugins = self.plugin_manager.get_available_plugins()

        matching = []
        for p in plugins:
            if self.selection.is_enabled(p["name"]):
                caps = set(p.get("capabilities", []))
                if set(required_capabilities).issubset(caps):
                    matching.append(p["name"])

        if not matching:
            return SelectionResult(
                executor=None,
                executor_name="none",
                reason=f"No executors match capabilities: {required_capabilities}",
            )

        for name in matching:
            result = self._try_select_executor(
                name,
                reason=f"Capability match: {required_capabilities}",
            )
            if result.executor:
                return result

        return SelectionResult(
            executor=None,
            executor_name="none",
            reason="Matching executors unavailable",
        )

    def _get_available_executors(self) -> list[str]:
        """Get list of available (enabled + healthy) executors.

        Returns:
            List of executor names.
        """
        self.plugin_manager.refresh()
        plugins = self.plugin_manager.get_available_plugins()

        available = []
        for p in plugins:
            name = p["name"]
            if self.selection.is_enabled(name):
                health = self._get_health(name)
                if health.healthy:
                    available.append(name)

        return available

    def _get_alternatives(self, exclude: str) -> list[str]:
        """Get list of alternative executors.

        Args:
            exclude: Executor name to exclude.

        Returns:
            List of alternative executor names.
        """
        available = self._get_available_executors()
        return [name for name in available if name != exclude]

    def _get_health(self, name: str) -> ExecutorHealth:
        """Get or create health tracking for an executor.

        Args:
            name: Executor name.

        Returns:
            ExecutorHealth instance.
        """
        if name not in self._health:
            self._health[name] = ExecutorHealth(name=name)
        return self._health[name]

    def report_success(self, name: str) -> None:
        """Report successful execution for health tracking.

        Args:
            name: Executor name.
        """
        import time
        health = self._get_health(name)
        health.consecutive_failures = 0
        health.last_success_time = time.time()
        health.healthy = True
        health.rate_limited_until = None

        logger.debug(f"Executor {name} success reported, health restored")

    def report_failure(self, name: str, is_rate_limited: bool = False) -> None:
        """Report failed execution for health tracking.

        Args:
            name: Executor name.
            is_rate_limited: Whether the failure was due to rate limiting.
        """
        import time
        health = self._get_health(name)
        health.consecutive_failures += 1
        health.last_failure_time = time.time()

        if is_rate_limited:
            # Back off for 60 seconds on rate limit
            health.rate_limited_until = time.time() + 60
            logger.warning(f"Executor {name} rate limited, backing off 60s")

        if health.consecutive_failures >= self.FAILURE_THRESHOLD:
            health.healthy = False
            logger.warning(
                f"Executor {name} marked unhealthy after "
                f"{health.consecutive_failures} consecutive failures"
            )

    def reset_health(self, name: str | None = None) -> None:
        """Reset health tracking for executor(s).

        Args:
            name: Executor name, or None to reset all.
        """
        if name:
            if name in self._health:
                self._health[name] = ExecutorHealth(name=name)
        else:
            self._health.clear()

    def get_health_summary(self) -> dict[str, dict[str, Any]]:
        """Get health summary for all tracked executors.

        Returns:
            Dict mapping executor names to health info.
        """
        return {
            name: {
                "healthy": h.healthy,
                "consecutive_failures": h.consecutive_failures,
                "rate_limited": h.rate_limited_until is not None,
            }
            for name, h in self._health.items()
        }
