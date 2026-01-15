"""Repository classes for data access."""

import json
from datetime import datetime
from typing import TYPE_CHECKING

from .models import (
    LogEntry,
    LogLevel,
    Project,
    Run,
    RunStatus,
    Task,
    TaskExecution,
    TaskStatus,
)

if TYPE_CHECKING:
    from .database import Database


class ProjectRepository:
    """Repository for project data access."""

    def __init__(self, database: "Database"):
        self.db = database

    def create(self, project: Project) -> int:
        """Create a new project.

        Args:
            project: Project to create.

        Returns:
            ID of created project.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (name, path, project_type, config_json, is_active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project.name,
                    project.path,
                    project.project_type,
                    project.config_json,
                    project.is_active,
                ),
            )
            return cursor.lastrowid

    def get_by_id(self, project_id: int) -> Project | None:
        """Get project by ID.

        Args:
            project_id: Project ID.

        Returns:
            Project or None if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            return self._row_to_project(row) if row else None

    def get_by_name(self, name: str) -> Project | None:
        """Get project by name.

        Args:
            name: Project name.

        Returns:
            Project or None if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()
            return self._row_to_project(row) if row else None

    def list_all(self, active_only: bool = True) -> list[Project]:
        """List all projects.

        Args:
            active_only: If True, only return active projects.

        Returns:
            List of projects.
        """
        with self.db.connection() as conn:
            if active_only:
                cursor = conn.execute(
                    "SELECT * FROM projects WHERE is_active = 1 ORDER BY name"
                )
            else:
                cursor = conn.execute("SELECT * FROM projects ORDER BY name")
            return [self._row_to_project(row) for row in cursor.fetchall()]

    def update(self, project: Project) -> None:
        """Update a project.

        Args:
            project: Project to update (must have id set).
        """
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE projects
                SET name = ?, path = ?, project_type = ?, config_json = ?,
                    is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    project.name,
                    project.path,
                    project.project_type,
                    project.config_json,
                    project.is_active,
                    datetime.utcnow(),
                    project.id,
                ),
            )

    def delete(self, project_id: int) -> None:
        """Delete a project.

        Args:
            project_id: ID of project to delete.
        """
        with self.db.connection() as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def _row_to_project(self, row) -> Project:
        """Convert database row to Project."""
        return Project(
            id=row["id"],
            name=row["name"],
            path=row["path"],
            project_type=row["project_type"],
            config_json=row["config_json"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            is_active=bool(row["is_active"]),
        )


class RunRepository:
    """Repository for run data access."""

    def __init__(self, database: "Database"):
        self.db = database

    def create(self, run: Run) -> int:
        """Create a new run.

        Args:
            run: Run to create.

        Returns:
            ID of created run.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (
                    run_id, project_id, prd_path, status, base_branch, run_branch,
                    executor, started_at, total_tasks, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.project_id,
                    run.prd_path,
                    run.status.value,
                    run.base_branch,
                    run.run_branch,
                    run.executor,
                    run.started_at,
                    run.total_tasks,
                    run.metadata_json,
                ),
            )
            return cursor.lastrowid

    def get_by_id(self, run_db_id: int) -> Run | None:
        """Get run by database ID.

        Args:
            run_db_id: Database ID.

        Returns:
            Run or None if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_db_id,),
            )
            row = cursor.fetchone()
            return self._row_to_run(row) if row else None

    def get_by_run_id(self, run_id: str) -> Run | None:
        """Get run by external run ID.

        Args:
            run_id: External run ID (UUID string).

        Returns:
            Run or None if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (run_id,),
            )
            row = cursor.fetchone()
            return self._row_to_run(row) if row else None

    def list_by_project(
        self,
        project_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Run]:
        """List runs for a project.

        Args:
            project_id: Project ID.
            limit: Maximum results.
            offset: Result offset.

        Returns:
            List of runs.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM runs
                WHERE project_id = ?
                ORDER BY started_at DESC
                LIMIT ? OFFSET ?
                """,
                (project_id, limit, offset),
            )
            return [self._row_to_run(row) for row in cursor.fetchall()]

    def list_active(self) -> list[Run]:
        """List all active (running or paused) runs.

        Returns:
            List of active runs.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM runs
                WHERE status IN ('running', 'paused')
                ORDER BY started_at DESC
                """,
            )
            return [self._row_to_run(row) for row in cursor.fetchall()]

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        completed_at: datetime | None = None,
    ) -> None:
        """Update run status.

        Args:
            run_id: External run ID.
            status: New status.
            completed_at: Completion timestamp.
        """
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, completed_at = ?
                WHERE run_id = ?
                """,
                (status.value, completed_at, run_id),
            )

    def update_progress(
        self,
        run_id: str,
        completed_tasks: int,
        failed_tasks: int,
    ) -> None:
        """Update run progress.

        Args:
            run_id: External run ID.
            completed_tasks: Number of completed tasks.
            failed_tasks: Number of failed tasks.
        """
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE runs
                SET completed_tasks = ?, failed_tasks = ?
                WHERE run_id = ?
                """,
                (completed_tasks, failed_tasks, run_id),
            )

    def delete(self, run_id: str) -> None:
        """Delete a run and all related data.

        Args:
            run_id: External run ID.
        """
        with self.db.connection() as conn:
            conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    def _row_to_run(self, row) -> Run:
        """Convert database row to Run."""
        return Run(
            id=row["id"],
            run_id=row["run_id"],
            project_id=row["project_id"],
            prd_path=row["prd_path"],
            status=RunStatus(row["status"]),
            base_branch=row["base_branch"],
            run_branch=row["run_branch"],
            executor=row["executor"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            total_tasks=row["total_tasks"],
            completed_tasks=row["completed_tasks"],
            failed_tasks=row["failed_tasks"],
            metadata_json=row["metadata_json"],
        )


class TaskRepository:
    """Repository for task data access."""

    def __init__(self, database: "Database"):
        self.db = database

    def create(self, task: Task) -> int:
        """Create a new task.

        Args:
            task: Task to create.

        Returns:
            ID of created task.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks (
                    run_id, task_id, phase, category, description,
                    steps_json, blocked_by_json, order_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.run_id,
                    task.task_id,
                    task.phase,
                    task.category,
                    task.description,
                    task.steps_json,
                    task.blocked_by_json,
                    task.order_index,
                ),
            )
            return cursor.lastrowid

    def create_many(self, tasks: list[Task]) -> None:
        """Create multiple tasks.

        Args:
            tasks: List of tasks to create.
        """
        with self.db.connection() as conn:
            conn.executemany(
                """
                INSERT INTO tasks (
                    run_id, task_id, phase, category, description,
                    steps_json, blocked_by_json, order_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        t.run_id,
                        t.task_id,
                        t.phase,
                        t.category,
                        t.description,
                        t.steps_json,
                        t.blocked_by_json,
                        t.order_index,
                    )
                    for t in tasks
                ],
            )

    def get_by_id(self, task_db_id: int) -> Task | None:
        """Get task by database ID.

        Args:
            task_db_id: Database ID.

        Returns:
            Task or None if not found.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_db_id,),
            )
            row = cursor.fetchone()
            return self._row_to_task(row) if row else None

    def list_by_run(self, run_db_id: int) -> list[Task]:
        """List all tasks for a run.

        Args:
            run_db_id: Database ID of run.

        Returns:
            List of tasks ordered by order_index.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM tasks
                WHERE run_id = ?
                ORDER BY order_index
                """,
                (run_db_id,),
            )
            return [self._row_to_task(row) for row in cursor.fetchall()]

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task."""
        return Task(
            id=row["id"],
            run_id=row["run_id"],
            task_id=row["task_id"],
            phase=row["phase"],
            category=row["category"],
            description=row["description"],
            steps_json=row["steps_json"],
            blocked_by_json=row["blocked_by_json"],
            order_index=row["order_index"],
        )

    def create_execution(self, execution: TaskExecution) -> int:
        """Create a task execution record.

        Args:
            execution: TaskExecution to create.

        Returns:
            ID of created execution.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO task_executions (
                    task_id, run_id, status, attempt, started_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    execution.task_id,
                    execution.run_id,
                    execution.status.value,
                    execution.attempt,
                    execution.started_at,
                ),
            )
            return cursor.lastrowid

    def update_execution(self, execution: TaskExecution) -> None:
        """Update a task execution.

        Args:
            execution: TaskExecution to update (must have id set).
        """
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE task_executions
                SET status = ?, completed_at = ?, duration_seconds = ?,
                    output = ?, error = ?, files_changed_json = ?
                WHERE id = ?
                """,
                (
                    execution.status.value,
                    execution.completed_at,
                    execution.duration_seconds,
                    execution.output,
                    execution.error,
                    execution.files_changed_json,
                    execution.id,
                ),
            )

    def get_latest_execution(self, task_db_id: int) -> TaskExecution | None:
        """Get the latest execution for a task.

        Args:
            task_db_id: Database ID of task.

        Returns:
            Latest TaskExecution or None.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM task_executions
                WHERE task_id = ?
                ORDER BY attempt DESC
                LIMIT 1
                """,
                (task_db_id,),
            )
            row = cursor.fetchone()
            return self._row_to_execution(row) if row else None

    def list_executions_by_run(self, run_db_id: int) -> list[TaskExecution]:
        """List all executions for a run.

        Args:
            run_db_id: Database ID of run.

        Returns:
            List of task executions.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM task_executions
                WHERE run_id = ?
                ORDER BY started_at
                """,
                (run_db_id,),
            )
            return [self._row_to_execution(row) for row in cursor.fetchall()]

    def _row_to_execution(self, row) -> TaskExecution:
        """Convert database row to TaskExecution."""
        return TaskExecution(
            id=row["id"],
            task_id=row["task_id"],
            run_id=row["run_id"],
            status=TaskStatus(row["status"]),
            attempt=row["attempt"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration_seconds=row["duration_seconds"],
            output=row["output"],
            error=row["error"],
            files_changed_json=row["files_changed_json"],
        )


class LogRepository:
    """Repository for log entry data access."""

    def __init__(self, database: "Database"):
        self.db = database

    def create(self, entry: LogEntry) -> int:
        """Create a log entry.

        Args:
            entry: LogEntry to create.

        Returns:
            ID of created entry.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO logs (run_id, task_id, level, message, context_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.run_id,
                    entry.task_id,
                    entry.level.value,
                    entry.message,
                    entry.context_json,
                    entry.timestamp or datetime.utcnow(),
                ),
            )
            return cursor.lastrowid

    def list_by_run(
        self,
        run_db_id: int,
        level: LogLevel | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[LogEntry]:
        """List log entries for a run.

        Args:
            run_db_id: Database ID of run.
            level: Optional minimum log level filter.
            limit: Maximum results.
            offset: Result offset.

        Returns:
            List of log entries.
        """
        with self.db.connection() as conn:
            if level:
                cursor = conn.execute(
                    """
                    SELECT * FROM logs
                    WHERE run_id = ? AND level = ?
                    ORDER BY timestamp
                    LIMIT ? OFFSET ?
                    """,
                    (run_db_id, level.value, limit, offset),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM logs
                    WHERE run_id = ?
                    ORDER BY timestamp
                    LIMIT ? OFFSET ?
                    """,
                    (run_db_id, limit, offset),
                )
            return [self._row_to_entry(row) for row in cursor.fetchall()]

    def list_by_task(self, task_db_id: int) -> list[LogEntry]:
        """List log entries for a specific task.

        Args:
            task_db_id: Database ID of task.

        Returns:
            List of log entries.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM logs
                WHERE task_id = ?
                ORDER BY timestamp
                """,
                (task_db_id,),
            )
            return [self._row_to_entry(row) for row in cursor.fetchall()]

    def delete_by_run(self, run_db_id: int) -> int:
        """Delete all logs for a run.

        Args:
            run_db_id: Database ID of run.

        Returns:
            Number of deleted entries.
        """
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM logs WHERE run_id = ?",
                (run_db_id,),
            )
            return cursor.rowcount

    def _row_to_entry(self, row) -> LogEntry:
        """Convert database row to LogEntry."""
        return LogEntry(
            id=row["id"],
            run_id=row["run_id"],
            task_id=row["task_id"],
            level=LogLevel(row["level"]),
            message=row["message"],
            context_json=row["context_json"],
            timestamp=row["timestamp"],
        )
