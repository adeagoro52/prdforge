"""Run manager for orchestrating PRD execution."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import ExecutionConfig, RunState, RunStatus, TaskStatus
from .git_manager import GitManager
from .logging import logger
from .prd_executor import BaseExecutor, DryRunExecutor, PRDExecutor, Task


class RunManager:
    """Orchestrates the execution of PRD runs.

    The RunManager is responsible for:
    - Creating and managing run state
    - Setting up git branches for runs
    - Coordinating task execution via PRDExecutor
    - Handling pause/resume/cancel operations
    - Persisting run state (foundation for SQLite in phase1-007)
    """

    def __init__(
        self,
        config: ExecutionConfig,
        executor: BaseExecutor | None = None,
    ) -> None:
        """Initialize the RunManager.

        Args:
            config: Execution configuration.
            executor: AI executor to use. Defaults to DryRunExecutor if dry_run=True.
        """
        self.config = config
        self.git_manager = GitManager(config.project_path)

        # Use DryRunExecutor if dry_run mode or no executor provided
        if config.dry_run or executor is None:
            self.executor = DryRunExecutor()
        else:
            self.executor = executor

        self.state: RunState | None = None
        self._paused = False
        self._cancelled = False
        self._on_task_complete: list[Callable[[str, TaskStatus], None]] = []
        self._on_status_change: list[Callable[[RunStatus], None]] = []

    def on_task_complete(self, callback: Callable[[str, TaskStatus], None]) -> None:
        """Register a callback for task completion events.

        Args:
            callback: Function called with (task_id, status) on completion.
        """
        self._on_task_complete.append(callback)

    def on_status_change(self, callback: Callable[[RunStatus], None]) -> None:
        """Register a callback for run status changes.

        Args:
            callback: Function called with new status on change.
        """
        self._on_status_change.append(callback)

    def _notify_task_complete(self, task_id: str, status: TaskStatus) -> None:
        """Notify listeners of task completion."""
        for callback in self._on_task_complete:
            try:
                callback(task_id, status)
            except Exception as e:
                logger.error(f"Task completion callback error: {e}")

    def _notify_status_change(self, status: RunStatus) -> None:
        """Notify listeners of status change."""
        for callback in self._on_status_change:
            try:
                callback(status)
            except Exception as e:
                logger.error(f"Status change callback error: {e}")

    def _set_status(self, status: RunStatus) -> None:
        """Update run status and notify listeners."""
        if self.state:
            self.state.status = status
            self._notify_status_change(status)

    def _generate_run_id(self) -> str:
        """Generate a unique run identifier."""
        return str(uuid.uuid4())

    def _generate_run_branch_name(self, run_id: str) -> str:
        """Generate a branch name for the run.

        Args:
            run_id: The run identifier.

        Returns:
            Branch name in format: prdforge/run/<timestamp>-<short_id>
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        short_id = run_id[:8]
        return f"prdforge/run/{timestamp}-{short_id}"

    def load_prd_tasks(self) -> list[Task]:
        """Load tasks from the PRD file.

        Returns:
            List of Task objects from the PRD.

        Raises:
            ValueError: If PRD file cannot be parsed.
        """
        prd_path = self.config.prd_path

        with open(prd_path) as f:
            prd_data = json.load(f)

        tasks = []
        for task_data in prd_data.get("tasks", []):
            task = Task(
                id=task_data["id"],
                phase=task_data.get("phase", 1),
                category=task_data.get("category", "general"),
                description=task_data.get("description", ""),
                steps=task_data.get("steps", []),
                passes=task_data.get("passes", False),
                test_coverage=task_data.get("test_coverage", "none"),
                blocked_by=task_data.get("blocked_by", []),
            )
            tasks.append(task)

        logger.info(f"Loaded {len(tasks)} tasks from PRD")
        return tasks

    def create_run(self) -> RunState:
        """Create a new run.

        Returns:
            The initialized RunState.
        """
        run_id = self._generate_run_id()

        # Generate run branch name if not specified
        run_branch = self.config.run_branch or self._generate_run_branch_name(run_id)

        self.state = RunState(
            run_id=run_id,
            config=self.config,
            status=RunStatus.PENDING,
            metadata={
                "run_branch": run_branch,
                "executor": self.executor.name,
                "created_at": datetime.now().isoformat(),
            },
        )

        logger.info(f"Created run: {run_id}")
        return self.state

    def setup_run_branch(self) -> bool:
        """Set up the git branch for this run.

        Returns:
            True if branch setup succeeded.
        """
        if not self.state:
            logger.error("No run state - call create_run() first")
            return False

        run_branch = self.state.metadata.get("run_branch")
        if not run_branch:
            logger.error("No run branch in state")
            return False

        # Check for uncommitted changes
        if self.git_manager.has_uncommitted_changes():
            logger.warning("Uncommitted changes detected, stashing...")
            self.git_manager.stash(f"PRDForge auto-stash for run {self.state.run_id}")

        # Checkout base branch
        base_result = self.git_manager.checkout(self.config.base_branch)
        if not base_result.success:
            logger.error(f"Failed to checkout base branch: {base_result.error}")
            return False

        # Create run branch
        branch_result = self.git_manager.create_branch(run_branch)
        if not branch_result.success:
            logger.error(f"Failed to create run branch: {branch_result.error}")
            return False

        logger.info(f"Set up run branch: {run_branch}")
        return True

    def start(self) -> RunState:
        """Start the run execution.

        Returns:
            Final RunState after execution completes.
        """
        if not self.state:
            self.create_run()

        assert self.state is not None

        self._paused = False
        self._cancelled = False

        # Set up git branch
        if not self.config.dry_run:
            if not self.setup_run_branch():
                self._set_status(RunStatus.FAILED)
                return self.state

        # Load tasks
        try:
            tasks = self.load_prd_tasks()
        except Exception as e:
            logger.error(f"Failed to load PRD: {e}")
            self._set_status(RunStatus.FAILED)
            return self.state

        # Start execution
        self.state.started_at = datetime.now()
        self._set_status(RunStatus.RUNNING)

        config_summary = {
            "project_path": str(self.config.project_path),
            "prd_path": str(self.config.prd_path),
            "executor": self.executor.name,
            "total_tasks": len(tasks),
        }
        logger.run_started(self.state.run_id, config_summary)

        # Create PRD executor
        prd_executor = PRDExecutor(
            config=self.config,
            executor=self.executor,
            git_manager=self.git_manager,
        )

        # Execute tasks
        try:
            self._execute_tasks(prd_executor, tasks)
        except Exception as e:
            logger.error(f"Run execution error: {e}")
            self._set_status(RunStatus.FAILED)
            self.state.completed_at = datetime.now()
            logger.run_failed(self.state.run_id, str(e))
            return self.state

        # Determine final status
        self.state.completed_at = datetime.now()

        if self._cancelled:
            self._set_status(RunStatus.CANCELLED)
        elif self.state.tasks_failed > 0:
            self._set_status(RunStatus.FAILED)
        else:
            self._set_status(RunStatus.COMPLETED)

        summary = {
            "completed": self.state.tasks_completed,
            "failed": self.state.tasks_failed,
            "duration_seconds": self.state.duration_seconds,
        }
        logger.run_completed(self.state.run_id, summary)

        return self.state

    def _execute_tasks(self, prd_executor: PRDExecutor, tasks: list[Task]) -> None:
        """Execute tasks with pause/cancel support.

        Args:
            prd_executor: The PRDExecutor instance.
            tasks: List of tasks to execute.
        """
        assert self.state is not None

        # Get executable tasks
        executable = prd_executor.get_executable_tasks(tasks)
        task_map = {t.id: t for t in tasks}
        remaining = set(t.id for t in executable)

        while remaining and not self._cancelled:
            # Check for pause
            if self._paused:
                self._set_status(RunStatus.PAUSED)
                logger.info("Run paused, waiting for resume...")
                while self._paused and not self._cancelled:
                    import time
                    time.sleep(0.5)
                if not self._cancelled:
                    self._set_status(RunStatus.RUNNING)
                    logger.info("Run resumed")

            if self._cancelled:
                break

            # Find next executable task
            next_task = None
            for task_id in list(remaining):
                task = task_map[task_id]
                if prd_executor.can_execute(task):
                    next_task = task
                    break

            if not next_task:
                # No more executable tasks
                break

            # Execute task
            self.state.current_task_id = next_task.id
            result = prd_executor.execute_task(next_task)
            self.state.task_results[next_task.id] = result
            self.state.current_task_id = None

            # Notify listeners
            self._notify_task_complete(next_task.id, result.status)

            # Remove from remaining
            remaining.discard(next_task.id)

            # Check for newly unblocked tasks
            if result.status == TaskStatus.COMPLETED:
                for task in tasks:
                    if task.id not in remaining and task.id not in self.state.task_results:
                        if prd_executor.can_execute(task):
                            remaining.add(task.id)

            # Stop on failure
            if result.status == TaskStatus.FAILED:
                logger.warning(f"Stopping due to failed task: {next_task.id}")
                break

    def pause(self) -> None:
        """Pause the running execution."""
        if self.state and self.state.status == RunStatus.RUNNING:
            self._paused = True
            logger.info("Pause requested")

    def resume(self) -> None:
        """Resume a paused execution."""
        if self.state and self.state.status == RunStatus.PAUSED:
            self._paused = False
            logger.info("Resume requested")

    def cancel(self) -> None:
        """Cancel the running execution."""
        self._cancelled = True
        self._paused = False  # Unblock if paused
        logger.info("Cancel requested")

    def get_progress(self) -> dict[str, Any]:
        """Get current run progress.

        Returns:
            Dict with progress information.
        """
        if not self.state:
            return {"status": "no_run"}

        return {
            "run_id": self.state.run_id,
            "status": self.state.status.value,
            "current_task": self.state.current_task_id,
            "tasks_completed": self.state.tasks_completed,
            "tasks_failed": self.state.tasks_failed,
            "tasks_total": len(self.state.task_results),
            "duration_seconds": self.state.duration_seconds,
        }

    def save_state(self, path: Path | None = None) -> Path:
        """Save run state to a JSON file.

        This is a temporary solution until SQLite is implemented in phase1-007.

        Args:
            path: Optional path to save to. Defaults to project/.prdforge/runs/<run_id>.json

        Returns:
            Path where state was saved.
        """
        if not self.state:
            raise ValueError("No run state to save")

        if path is None:
            runs_dir = self.config.project_path / ".prdforge" / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            path = runs_dir / f"{self.state.run_id}.json"

        # Convert state to serializable dict
        state_dict = {
            "run_id": self.state.run_id,
            "status": self.state.status.value,
            "started_at": self.state.started_at.isoformat() if self.state.started_at else None,
            "completed_at": self.state.completed_at.isoformat() if self.state.completed_at else None,
            "current_task_id": self.state.current_task_id,
            "metadata": self.state.metadata,
            "config": {
                "project_path": str(self.config.project_path),
                "prd_path": str(self.config.prd_path),
                "base_branch": self.config.base_branch,
                "executor": self.config.executor,
            },
            "task_results": {
                task_id: {
                    "task_id": result.task_id,
                    "status": result.status.value,
                    "started_at": result.started_at.isoformat(),
                    "completed_at": result.completed_at.isoformat() if result.completed_at else None,
                    "output": result.output,
                    "error": result.error,
                    "retries": result.retries,
                    "files_changed": result.files_changed,
                }
                for task_id, result in self.state.task_results.items()
            },
        }

        with open(path, "w") as f:
            json.dump(state_dict, f, indent=2)

        logger.info(f"Saved run state to: {path}")
        return path
