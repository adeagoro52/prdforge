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
    (
        2,
        "Add project tags and archiving",
        """
        -- Add tags_json column for project tagging/grouping
        ALTER TABLE projects ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]';

        -- Add archived_at column for soft archiving
        ALTER TABLE projects ADD COLUMN archived_at TIMESTAMP DEFAULT NULL;

        -- Index for archived projects
        CREATE INDEX IF NOT EXISTS idx_projects_archived ON projects(archived_at);
        """,
    ),
    (
        3,
        "Add cost tracking tables",
        """
        -- Cost records table (per task execution)
        CREATE TABLE IF NOT EXISTS cost_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            run_id INTEGER,
            task_execution_id INTEGER,
            executor TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE SET NULL,
            FOREIGN KEY (task_execution_id) REFERENCES task_executions(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cost_records_project ON cost_records(project_id);
        CREATE INDEX IF NOT EXISTS idx_cost_records_run ON cost_records(run_id);
        CREATE INDEX IF NOT EXISTS idx_cost_records_executor ON cost_records(executor);
        CREATE INDEX IF NOT EXISTS idx_cost_records_created ON cost_records(created_at);

        -- Cost budgets table (per project)
        CREATE TABLE IF NOT EXISTS cost_budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL UNIQUE,
            daily_budget_usd REAL,
            monthly_budget_usd REAL,
            total_budget_usd REAL,
            alert_threshold_percent REAL DEFAULT 80.0,
            is_hard_limit BOOLEAN NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_cost_budgets_project ON cost_budgets(project_id);

        -- Cost alerts table (triggered alerts)
        CREATE TABLE IF NOT EXISTS cost_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            budget_amount_usd REAL,
            current_amount_usd REAL,
            threshold_percent REAL,
            acknowledged BOOLEAN NOT NULL DEFAULT 0,
            acknowledged_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_cost_alerts_project ON cost_alerts(project_id);
        CREATE INDEX IF NOT EXISTS idx_cost_alerts_acknowledged ON cost_alerts(acknowledged);
        CREATE INDEX IF NOT EXISTS idx_cost_alerts_created ON cost_alerts(created_at);
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
