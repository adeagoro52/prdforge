"""SQLite database connection management."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .migrations import MigrationManager


class Database:
    """SQLite database connection manager.

    Provides connection pooling, WAL mode for concurrency,
    and automatic schema initialization.

    Example:
        db = Database("~/.prdforge/prdforge.db")
        db.initialize()

        with db.connection() as conn:
            cursor = conn.execute("SELECT * FROM projects")
            rows = cursor.fetchall()
    """

    def __init__(self, path: str | Path):
        """Initialize database with path.

        Args:
            path: Path to SQLite database file.
                  Will be created if it doesn't exist.
        """
        self.path = Path(path).expanduser().resolve()
        self._ensure_parent_dir()

    def _ensure_parent_dir(self) -> None:
        """Ensure parent directory exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection.

        Yields:
            SQLite connection with row factory set to sqlite3.Row.
        """
        conn = sqlite3.connect(
            str(self.path),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")

        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys=ON")

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Initialize database schema.

        Creates tables if they don't exist and runs any pending migrations.
        """
        migration_manager = MigrationManager(self)
        migration_manager.run_migrations()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query and return cursor.

        Args:
            query: SQL query string.
            params: Query parameters.

        Returns:
            Cursor with results.
        """
        with self.connection() as conn:
            return conn.execute(query, params)

    def execute_many(self, query: str, params_list: list[tuple]) -> None:
        """Execute a query with multiple parameter sets.

        Args:
            query: SQL query string.
            params_list: List of parameter tuples.
        """
        with self.connection() as conn:
            conn.executemany(query, params_list)

    def get_schema_version(self) -> int:
        """Get current schema version.

        Returns:
            Current schema version number, or 0 if not initialized.
        """
        try:
            with self.connection() as conn:
                cursor = conn.execute(
                    "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
                )
                row = cursor.fetchone()
                return row["version"] if row else 0
        except sqlite3.OperationalError:
            return 0

    def drop_all_tables(self) -> None:
        """Drop all tables. USE WITH CAUTION - for testing only."""
        with self.connection() as conn:
            # Get all table names
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = [row["name"] for row in cursor.fetchall()]

            # Disable foreign keys temporarily
            conn.execute("PRAGMA foreign_keys=OFF")

            # Drop each table
            for table in tables:
                conn.execute(f"DROP TABLE IF EXISTS {table}")

            conn.execute("PRAGMA foreign_keys=ON")
