"""Base executor interface for AI backends.

This module defines the abstract base class that all AI executors must implement.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.engine.config import TaskResult, TaskStatus
from src.engine.logging import logger


class ExecutorStatus(Enum):
    """Status of an executor."""

    AVAILABLE = "available"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


@dataclass
class ExecutorConfig:
    """Configuration for an executor.

    Attributes:
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay in seconds between retries.
        timeout: Timeout in seconds for each execution.
        model: Model identifier (executor-specific).
        temperature: Temperature for generation (0.0-1.0).
        max_tokens: Maximum tokens for response.
        extra: Additional executor-specific configuration.
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    timeout: int = 600
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result from an executor run.

    Attributes:
        success: Whether execution succeeded.
        output: Raw output from the executor.
        error: Error message if failed.
        tokens_used: Number of tokens consumed (if available).
        duration_seconds: Execution duration.
        retries: Number of retries attempted.
        metadata: Additional result metadata.
    """

    success: bool
    output: str
    error: str | None = None
    tokens_used: int | None = None
    duration_seconds: float = 0.0
    retries: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContext:
    """Context for task execution.

    Attributes:
        task_id: Unique task identifier.
        description: Human-readable task description.
        steps: List of steps to complete.
        project_path: Path to the project root.
        prd_path: Path to the PRD file.
        phase: Phase number.
        category: Task category.
        extra_context: Additional context for the executor.
    """

    task_id: str
    description: str
    steps: list[str]
    project_path: str
    prd_path: str
    phase: int = 1
    category: str = "general"
    extra_context: dict[str, Any] = field(default_factory=dict)


class BaseExecutor(ABC):
    """Abstract base class for AI executors.

    All AI backend implementations (Claude CLI, Codex, Gemini, etc.)
    must inherit from this class and implement the required methods.
    """

    def __init__(self, config: ExecutorConfig | None = None) -> None:
        """Initialize the executor.

        Args:
            config: Executor configuration. Uses defaults if not provided.
        """
        self.config = config or ExecutorConfig()
        self._status = ExecutorStatus.AVAILABLE
        self._last_error: str | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the executor name (e.g., 'claude-cli', 'codex')."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Return the executor version."""
        ...

    @property
    def status(self) -> ExecutorStatus:
        """Return current executor status."""
        return self._status

    @abstractmethod
    def _execute_impl(self, context: TaskContext) -> ExecutionResult:
        """Implementation-specific execution logic.

        Subclasses must implement this method to perform the actual
        AI execution.

        Args:
            context: Task execution context.

        Returns:
            ExecutionResult with execution outcome.
        """
        ...

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute a task with retry logic.

        This method wraps _execute_impl with retry handling and
        converts the result to a TaskResult.

        Args:
            context: Task execution context.

        Returns:
            TaskResult with execution outcome.
        """
        start_time = datetime.now()
        last_result: ExecutionResult | None = None

        for attempt in range(self.config.max_retries + 1):
            if attempt > 0:
                delay = self._calculate_backoff(attempt)
                logger.info(
                    f"Retry {attempt}/{self.config.max_retries} for {context.task_id}, "
                    f"waiting {delay:.1f}s"
                )
                time.sleep(delay)

            try:
                result = self._execute_impl(context)
                result.retries = attempt

                if result.success:
                    self._status = ExecutorStatus.AVAILABLE
                    return self._to_task_result(context, result, start_time)

                last_result = result

                # Check if we should retry based on error type
                if not self._should_retry(result):
                    break

            except Exception as e:
                logger.error(f"Executor error: {e}")
                last_result = ExecutionResult(
                    success=False,
                    output="",
                    error=str(e),
                    retries=attempt,
                )

                if not self._is_retryable_error(e):
                    break

        # All retries exhausted or non-retryable error
        self._status = ExecutorStatus.ERROR
        self._last_error = last_result.error if last_result else "Unknown error"

        return self._to_task_result(
            context,
            last_result or ExecutionResult(success=False, output="", error="Execution failed"),
            start_time,
        )

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay.

        Args:
            attempt: Current retry attempt (1-based).

        Returns:
            Delay in seconds.
        """
        delay = self.config.base_delay * (2 ** (attempt - 1))
        # Add jitter (±10%)
        import random
        jitter = delay * 0.1 * (random.random() * 2 - 1)
        return min(delay + jitter, self.config.max_delay)

    def _should_retry(self, result: ExecutionResult) -> bool:
        """Determine if execution should be retried based on result.

        Args:
            result: The execution result.

        Returns:
            True if retry is appropriate.
        """
        if result.success:
            return False

        # Retry on rate limiting
        if result.error and "rate" in result.error.lower():
            self._status = ExecutorStatus.RATE_LIMITED
            return True

        # Retry on timeout
        if result.error and "timeout" in result.error.lower():
            return True

        # Retry on transient errors
        transient_errors = ["connection", "network", "temporary", "unavailable"]
        if result.error:
            error_lower = result.error.lower()
            if any(err in error_lower for err in transient_errors):
                return True

        return False

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an exception is retryable.

        Args:
            error: The exception.

        Returns:
            True if retry is appropriate.
        """
        error_str = str(error).lower()
        retryable = ["timeout", "connection", "rate", "temporary", "unavailable"]
        return any(r in error_str for r in retryable)

    def _to_task_result(
        self,
        context: TaskContext,
        result: ExecutionResult,
        start_time: datetime,
    ) -> TaskResult:
        """Convert ExecutionResult to TaskResult.

        Args:
            context: Task context.
            result: Execution result.
            start_time: When execution started.

        Returns:
            TaskResult for the engine.
        """
        end_time = datetime.now()

        return TaskResult(
            task_id=context.task_id,
            status=TaskStatus.COMPLETED if result.success else TaskStatus.FAILED,
            started_at=start_time,
            completed_at=end_time,
            output=result.output,
            error=result.error,
            retries=result.retries,
        )

    def build_prompt(self, context: TaskContext) -> str:
        """Build the prompt for task execution.

        Subclasses can override this to customize prompt generation.

        Args:
            context: Task execution context.

        Returns:
            Formatted prompt string.
        """
        steps_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(context.steps))

        return f"""Execute the following task:

Task ID: {context.task_id}
Phase: {context.phase}
Category: {context.category}

Description:
{context.description}

Steps to complete:
{steps_text}

Project: {context.project_path}

Instructions:
- Complete all steps listed above
- Make necessary code changes to implement the task
- Ensure the implementation is correct and follows project conventions
- After completing, the task should be marked as done
"""

    def health_check(self) -> bool:
        """Check if the executor is healthy and available.

        Subclasses can override for specific health checks.

        Returns:
            True if executor is available.
        """
        return self._status == ExecutorStatus.AVAILABLE

    def get_info(self) -> dict[str, Any]:
        """Get executor information.

        Returns:
            Dict with executor details.
        """
        return {
            "name": self.name,
            "version": self.version,
            "status": self._status.value,
            "last_error": self._last_error,
            "config": {
                "max_retries": self.config.max_retries,
                "timeout": self.config.timeout,
                "model": self.config.model,
            },
        }
