"""PRD task executor for PRDForge."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from .config import ExecutionConfig, TaskResult, TaskStatus
from .git_manager import GitManager
from .logging import logger


@dataclass
class Task:
    """Represents a task from a PRD.

    Attributes:
        id: Unique task identifier.
        phase: Phase number this task belongs to.
        category: Task category (backend, frontend, config, etc.).
        description: Human-readable task description.
        steps: List of steps to complete the task.
        passes: Whether the task is already completed.
        test_coverage: Type of test coverage required.
        blocked_by: List of task IDs this task depends on.
    """

    id: str
    phase: int
    category: str
    description: str
    steps: list[str] = field(default_factory=list)
    passes: bool = False
    test_coverage: str = "none"
    blocked_by: list[str] = field(default_factory=list)


class ExecutorProtocol(Protocol):
    """Protocol that AI executors must implement.

    This will be fully implemented in phase1-004 (AI executor abstraction).
    For now, it defines the interface that PRDExecutor expects.
    """

    def execute(self, task: Task, config: ExecutionConfig) -> TaskResult:
        """Execute a task and return the result.

        Args:
            task: The task to execute.
            config: Execution configuration.

        Returns:
            TaskResult with execution outcome.
        """
        ...


class BaseExecutor(ABC):
    """Abstract base class for AI executors.

    Concrete implementations (ClaudeCLI, Codex, Gemini) will be
    created in phase1-004.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the executor name."""
        ...

    @abstractmethod
    def execute(self, task: Task, config: ExecutionConfig) -> TaskResult:
        """Execute a task.

        Args:
            task: The task to execute.
            config: Execution configuration.

        Returns:
            TaskResult with execution outcome.
        """
        ...

    def build_prompt(self, task: Task, config: ExecutionConfig) -> str:
        """Build the prompt for task execution.

        Args:
            task: The task to execute.
            config: Execution configuration.

        Returns:
            Formatted prompt string.
        """
        steps_text = "\n".join(f"  - {step}" for step in task.steps)

        return f"""Execute the following task from the PRD:

Task ID: {task.id}
Phase: {task.phase}
Category: {task.category}
Description: {task.description}

Steps to complete:
{steps_text}

Project path: {config.project_path}
PRD file: {config.prd_path}

Complete all steps and ensure the implementation is correct.
After completing the task, the 'passes' field should be set to true in the PRD.
"""


class DryRunExecutor(BaseExecutor):
    """Executor that simulates task execution without making changes.

    Useful for testing the execution flow without actual AI calls.
    """

    @property
    def name(self) -> str:
        return "dry-run"

    def execute(self, task: Task, config: ExecutionConfig) -> TaskResult:
        """Simulate task execution.

        Args:
            task: The task to execute.
            config: Execution configuration.

        Returns:
            TaskResult indicating simulated success.
        """
        logger.info(f"[DRY RUN] Would execute task: {task.id}")
        logger.debug(f"[DRY RUN] Prompt:\n{self.build_prompt(task, config)}")

        return TaskResult(
            task_id=task.id,
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output="[DRY RUN] Task simulated successfully",
        )


class PRDExecutor:
    """Executes tasks from a PRD using configured AI executor.

    This class handles:
    - Task dependency resolution
    - Task execution with retries
    - Git operations around task execution
    - Result tracking and logging
    """

    def __init__(
        self,
        config: ExecutionConfig,
        executor: BaseExecutor,
        git_manager: GitManager | None = None,
    ) -> None:
        """Initialize the PRD executor.

        Args:
            config: Execution configuration.
            executor: AI executor to use for task execution.
            git_manager: Optional GitManager for git operations.
        """
        self.config = config
        self.executor = executor
        self.git_manager = git_manager or GitManager(config.project_path)
        self._completed_tasks: set[str] = set()

    def can_execute(self, task: Task, completed_tasks: set[str] | None = None) -> bool:
        """Check if a task can be executed based on dependencies.

        Args:
            task: The task to check.
            completed_tasks: Set of completed task IDs (uses internal tracking if None).

        Returns:
            True if all dependencies are satisfied.
        """
        if completed_tasks is None:
            completed_tasks = self._completed_tasks

        # Skip if already completed and skip_completed is enabled
        if task.passes and self.config.skip_completed:
            return False

        # Check all dependencies are satisfied
        for dep_id in task.blocked_by:
            if dep_id not in completed_tasks:
                return False

        return True

    def execute_task(self, task: Task) -> TaskResult:
        """Execute a single task.

        Args:
            task: The task to execute.

        Returns:
            TaskResult with execution outcome.
        """
        logger.task_started(task.id, task.description)
        start_time = datetime.now()

        # Check if task can be executed
        if not self.can_execute(task):
            blocked_by = [
                dep for dep in task.blocked_by if dep not in self._completed_tasks
            ]
            logger.warning(f"Task {task.id} blocked by: {blocked_by}")
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.BLOCKED,
                started_at=start_time,
                completed_at=datetime.now(),
                error=f"Blocked by unfinished tasks: {blocked_by}",
            )

        # Execute with retries
        last_result: TaskResult | None = None
        for attempt in range(self.config.max_retries + 1):
            if attempt > 0:
                logger.info(f"Retry attempt {attempt} for task {task.id}")

            try:
                result = self.executor.execute(task, self.config)
                result.retries = attempt

                if result.status == TaskStatus.COMPLETED:
                    self._completed_tasks.add(task.id)

                    # Auto-commit if enabled and there are changes
                    if self.config.auto_commit and self.git_manager.has_uncommitted_changes():
                        self._auto_commit(task)

                    duration = (datetime.now() - start_time).total_seconds()
                    logger.task_completed(task.id, duration)
                    return result

                last_result = result

            except Exception as e:
                logger.error(f"Task execution error: {e}")
                last_result = TaskResult(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    started_at=start_time,
                    completed_at=datetime.now(),
                    error=str(e),
                    retries=attempt,
                )

        # All retries exhausted
        if last_result:
            logger.task_failed(task.id, last_result.error or "Unknown error")
            return last_result

        return TaskResult(
            task_id=task.id,
            status=TaskStatus.FAILED,
            started_at=start_time,
            completed_at=datetime.now(),
            error="All retry attempts exhausted",
        )

    def _auto_commit(self, task: Task) -> None:
        """Create an automatic commit for task changes.

        Args:
            task: The completed task.
        """
        commit_message = f"[PRDForge] {task.id}: {task.description}\n\nPhase {task.phase}, Category: {task.category}"

        self.git_manager.add(".")
        result = self.git_manager.commit(commit_message)

        if result.success and self.config.auto_push:
            branch = self.git_manager.get_current_branch()
            if branch:
                self.git_manager.push(branch=branch, set_upstream=True)

    def get_executable_tasks(self, tasks: list[Task]) -> list[Task]:
        """Get list of tasks that can be executed now.

        Args:
            tasks: All tasks from the PRD.

        Returns:
            List of tasks with satisfied dependencies.
        """
        # First, mark already-passed tasks as completed
        for task in tasks:
            if task.passes:
                self._completed_tasks.add(task.id)

        return [task for task in tasks if self.can_execute(task)]

    def execute_tasks(self, tasks: list[Task]) -> dict[str, TaskResult]:
        """Execute multiple tasks in dependency order.

        Args:
            tasks: List of tasks to execute.

        Returns:
            Dict mapping task IDs to their results.
        """
        results: dict[str, TaskResult] = {}

        # Build execution order respecting dependencies
        remaining = list(tasks)
        max_iterations = len(tasks) * 2  # Prevent infinite loops

        for _ in range(max_iterations):
            if not remaining:
                break

            # Find tasks that can be executed
            executable = [t for t in remaining if self.can_execute(t)]

            if not executable:
                # No more tasks can be executed
                for task in remaining:
                    results[task.id] = TaskResult(
                        task_id=task.id,
                        status=TaskStatus.BLOCKED,
                        started_at=datetime.now(),
                        completed_at=datetime.now(),
                        error="Blocked by unfinished dependencies",
                    )
                break

            # Execute the first executable task
            task = executable[0]
            result = self.execute_task(task)
            results[task.id] = result
            remaining.remove(task)

            # Stop on failure if not skipping
            if result.status == TaskStatus.FAILED:
                logger.warning(f"Stopping execution due to failed task: {task.id}")
                break

        return results
