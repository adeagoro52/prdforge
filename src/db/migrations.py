"""Database migration system for PRDForge.

Provides a simple migration system for schema evolution.
Each migration is a versioned SQL script.
"""

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .database import Database


# Migration definitions: (version, description, up_sql)
MIGRATIONS = [
    (
        1,
        "Initial schema",
        """
        -- Schema version tracking
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Projects table
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            path TEXT NOT NULL,
            project_type TEXT NOT NULL DEFAULT 'local',
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
        CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);

        -- Runs table
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE,
            project_id INTEGER NOT NULL,
            prd_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            base_branch TEXT NOT NULL DEFAULT 'develop',
            run_branch TEXT,
            executor TEXT NOT NULL DEFAULT 'claude-cli',
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            total_tasks INTEGER NOT NULL DEFAULT 0,
            completed_tasks INTEGER NOT NULL DEFAULT 0,
            failed_tasks INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
        CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
        CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);

        -- Tasks table (PRD task definitions per run)
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            phase INTEGER NOT NULL,
            category TEXT NOT NULL DEFAULT 'other',
            description TEXT NOT NULL,
            steps_json TEXT NOT NULL DEFAULT '[]',
            blocked_by_json TEXT NOT NULL DEFAULT '[]',
            order_index INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
            UNIQUE(run_id, task_id)
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(run_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase);

        -- Task executions table (actual execution attempts)
        CREATE TABLE IF NOT EXISTS task_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            run_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempt INTEGER NOT NULL DEFAULT 1,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            duration_seconds REAL,
            output TEXT NOT NULL DEFAULT '',
            error TEXT,
            files_changed_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_executions_task ON task_executions(task_id);
        CREATE INDEX IF NOT EXISTS idx_executions_run ON task_executions(run_id);
        CREATE INDEX IF NOT EXISTS idx_executions_status ON task_executions(status);

        -- Log entries table
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            task_id INTEGER,
            level TEXT NOT NULL DEFAULT 'info',
            message TEXT NOT NULL,
            context_json TEXT NOT NULL DEFAULT '{}',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_logs_run ON logs(run_id);
        CREATE INDEX IF NOT EXISTS idx_logs_task ON logs(task_id);
        CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
        CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
        """,
    ),
]


class MigrationManager:
    """Manages database schema migrations."""

    def __init__(self, database: "Database"):
        """Initialize migration manager.

        Args:
            database: Database instance to migrate.
        """
        self.db = database

    def get_current_version(self) -> int:
        """Get the current schema version.

        Returns:
            Current version number, or 0 if not initialized.
        """
        return self.db.get_schema_version()

    def get_pending_migrations(self) -> list[tuple[int, str, str]]:
        """Get list of pending migrations.

        Returns:
            List of (version, description, sql) tuples for pending migrations.
        """
        current = self.get_current_version()
        return [m for m in MIGRATIONS if m[0] > current]

    def run_migrations(self) -> list[int]:
        """Run all pending migrations.

        Returns:
            List of applied migration versions.
        """
        applied = []
        pending = self.get_pending_migrations()

        for version, description, sql in pending:
            self._apply_migration(version, description, sql)
            applied.append(version)

        return applied

    def _apply_migration(self, version: int, description: str, sql: str) -> None:
        """Apply a single migration.

        Args:
            version: Migration version number.
            description: Migration description.
            sql: SQL statements to execute.
        """
        with self.db.connection() as conn:
            # Execute migration SQL
            conn.executescript(sql)

            # Record migration
            conn.execute(
                """
                INSERT INTO schema_version (version, description, applied_at)
                VALUES (?, ?, ?)
                """,
                (version, description, datetime.utcnow()),
            )

    def rollback_to(self, version: int) -> None:
        """Rollback to a specific version.

        Note: This is a placeholder. Full rollback support would require
        storing down migrations or using a more sophisticated migration system.

        Args:
            version: Target version to rollback to.
        """
        raise NotImplementedError(
            "Rollback not implemented. Manually restore from backup."
        )
