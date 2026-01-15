"""Unit tests for database layer."""

import json
from datetime import datetime

import pytest

from src.db import (
    Database,
    LogEntry,
    LogRepository,
    MigrationManager,
    Project,
    ProjectRepository,
    Run,
    RunRepository,
    Task,
    TaskExecution,
    TaskRepository,
)
from src.db.models import LogLevel, RunStatus, TaskStatus


class TestDatabase:
    """Tests for Database class."""

    def test_initialize_creates_tables(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()

        # Check that tables exist
        with db.connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row["name"] for row in cursor.fetchall()}

        assert "projects" in tables
        assert "runs" in tables
        assert "tasks" in tables
        assert "task_executions" in tables
        assert "logs" in tables
        assert "schema_version" in tables

    def test_schema_version(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()

        version = db.get_schema_version()
        assert version == 1

    def test_drop_all_tables(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()
        db.drop_all_tables()

        with db.connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = cursor.fetchall()

        assert len(tables) == 0


class TestMigrationManager:
    """Tests for MigrationManager."""

    def test_get_pending_migrations_on_new_db(self, tmp_path):
        db = Database(tmp_path / "test.db")
        manager = MigrationManager(db)

        pending = manager.get_pending_migrations()
        assert len(pending) >= 1
        assert pending[0][0] == 1  # First migration is version 1

    def test_run_migrations(self, tmp_path):
        db = Database(tmp_path / "test.db")
        manager = MigrationManager(db)

        applied = manager.run_migrations()
        assert 1 in applied

        # Running again should apply nothing
        applied_again = manager.run_migrations()
        assert len(applied_again) == 0


class TestProjectRepository:
    """Tests for ProjectRepository."""

    @pytest.fixture
    def db(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.initialize()
        return db

    @pytest.fixture
    def repo(self, db):
        return ProjectRepository(db)

    def test_create_and_get(self, repo):
        project = Project(
            id=None,
            name="test-project",
            path="/path/to/project",
            project_type="local",
        )
        project_id = repo.create(project)
        assert project_id is not None

        retrieved = repo.get_by_id(project_id)
        assert retrieved is not None
        assert retrieved.name == "test-project"
        assert retrieved.path == "/path/to/project"

    def test_get_by_name(self, repo):
        project = Project(id=None, name="named-project", path="/tmp")
        repo.create(project)

        retrieved = repo.get_by_name("named-project")
        assert retrieved is not None
        assert retrieved.name == "named-project"

    def test_list_all(self, repo):
        repo.create(Project(id=None, name="proj1", path="/tmp/1"))
        repo.create(Project(id=None, name="proj2", path="/tmp/2"))

        projects = repo.list_all()
        assert len(projects) == 2

    def test_update(self, repo):
        project = Project(id=None, name="original", path="/tmp")
        project_id = repo.create(project)

        project.id = project_id
        project.name = "updated"
        repo.update(project)

        retrieved = repo.get_by_id(project_id)
        assert retrieved.name == "updated"

    def test_delete(self, repo):
        project_id = repo.create(Project(id=None, name="to-delete", path="/tmp"))
        repo.delete(project_id)

        retrieved = repo.get_by_id(project_id)
        assert retrieved is None


class TestRunRepository:
    """Tests for RunRepository."""

    @pytest.fixture
    def db(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.initialize()
        return db

    @pytest.fixture
    def project_id(self, db):
        repo = ProjectRepository(db)
        return repo.create(Project(id=None, name="test", path="/tmp"))

    @pytest.fixture
    def repo(self, db):
        return RunRepository(db)

    def test_create_and_get(self, repo, project_id):
        run = Run(
            id=None,
            run_id="test-run-123",
            project_id=project_id,
            prd_path="/path/to/prd.json",
            status=RunStatus.PENDING,
        )
        run_db_id = repo.create(run)
        assert run_db_id is not None

        retrieved = repo.get_by_run_id("test-run-123")
        assert retrieved is not None
        assert retrieved.prd_path == "/path/to/prd.json"
        assert retrieved.status == RunStatus.PENDING

    def test_list_by_project(self, repo, project_id):
        for i in range(3):
            repo.create(Run(
                id=None,
                run_id=f"run-{i}",
                project_id=project_id,
                prd_path="/prd.json",
            ))

        runs = repo.list_by_project(project_id)
        assert len(runs) == 3

    def test_update_status(self, repo, project_id):
        repo.create(Run(
            id=None,
            run_id="status-test",
            project_id=project_id,
            prd_path="/prd.json",
        ))

        repo.update_status("status-test", RunStatus.COMPLETED, datetime.utcnow())

        retrieved = repo.get_by_run_id("status-test")
        assert retrieved.status == RunStatus.COMPLETED
        assert retrieved.completed_at is not None

    def test_update_progress(self, repo, project_id):
        repo.create(Run(
            id=None,
            run_id="progress-test",
            project_id=project_id,
            prd_path="/prd.json",
            total_tasks=10,
        ))

        repo.update_progress("progress-test", completed_tasks=5, failed_tasks=1)

        retrieved = repo.get_by_run_id("progress-test")
        assert retrieved.completed_tasks == 5
        assert retrieved.failed_tasks == 1

    def test_list_active(self, repo, project_id):
        repo.create(Run(
            id=None, run_id="running", project_id=project_id,
            prd_path="/prd.json", status=RunStatus.RUNNING,
        ))
        repo.create(Run(
            id=None, run_id="paused", project_id=project_id,
            prd_path="/prd.json", status=RunStatus.PAUSED,
        ))
        repo.create(Run(
            id=None, run_id="completed", project_id=project_id,
            prd_path="/prd.json", status=RunStatus.COMPLETED,
        ))

        active = repo.list_active()
        assert len(active) == 2
        assert {r.run_id for r in active} == {"running", "paused"}


class TestTaskRepository:
    """Tests for TaskRepository."""

    @pytest.fixture
    def db(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.initialize()
        return db

    @pytest.fixture
    def run_db_id(self, db):
        proj_repo = ProjectRepository(db)
        project_id = proj_repo.create(Project(id=None, name="test", path="/tmp"))

        run_repo = RunRepository(db)
        return run_repo.create(Run(
            id=None, run_id="test-run", project_id=project_id,
            prd_path="/prd.json",
        ))

    @pytest.fixture
    def repo(self, db):
        return TaskRepository(db)

    def test_create_and_get(self, repo, run_db_id):
        task = Task(
            id=None,
            run_id=run_db_id,
            task_id="phase1-001",
            phase=1,
            category="backend",
            description="Test task",
            steps_json='["step1", "step2"]',
        )
        task_db_id = repo.create(task)

        retrieved = repo.get_by_id(task_db_id)
        assert retrieved is not None
        assert retrieved.task_id == "phase1-001"
        assert retrieved.description == "Test task"

    def test_create_many(self, repo, run_db_id):
        tasks = [
            Task(id=None, run_id=run_db_id, task_id=f"task-{i}",
                 phase=1, category="backend", description=f"Task {i}",
                 order_index=i)
            for i in range(5)
        ]
        repo.create_many(tasks)

        retrieved = repo.list_by_run(run_db_id)
        assert len(retrieved) == 5

    def test_list_by_run_ordered(self, repo, run_db_id):
        for i in [2, 0, 1]:  # Insert out of order
            repo.create(Task(
                id=None, run_id=run_db_id, task_id=f"task-{i}",
                phase=1, category="backend", description=f"Task {i}",
                order_index=i,
            ))

        tasks = repo.list_by_run(run_db_id)
        assert [t.order_index for t in tasks] == [0, 1, 2]

    def test_create_and_update_execution(self, repo, run_db_id):
        task_db_id = repo.create(Task(
            id=None, run_id=run_db_id, task_id="exec-test",
            phase=1, category="backend", description="Test",
        ))

        execution = TaskExecution(
            id=None,
            task_id=task_db_id,
            run_id=run_db_id,
            status=TaskStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        exec_id = repo.create_execution(execution)

        execution.id = exec_id
        execution.status = TaskStatus.COMPLETED
        execution.completed_at = datetime.utcnow()
        execution.duration_seconds = 10.5
        execution.output = "Success"
        repo.update_execution(execution)

        latest = repo.get_latest_execution(task_db_id)
        assert latest.status == TaskStatus.COMPLETED
        assert latest.duration_seconds == 10.5


class TestLogRepository:
    """Tests for LogRepository."""

    @pytest.fixture
    def db(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.initialize()
        return db

    @pytest.fixture
    def run_db_id(self, db):
        proj_repo = ProjectRepository(db)
        project_id = proj_repo.create(Project(id=None, name="test", path="/tmp"))

        run_repo = RunRepository(db)
        return run_repo.create(Run(
            id=None, run_id="test-run", project_id=project_id,
            prd_path="/prd.json",
        ))

    @pytest.fixture
    def repo(self, db):
        return LogRepository(db)

    def test_create_and_list(self, repo, run_db_id):
        for i in range(3):
            repo.create(LogEntry(
                id=None,
                run_id=run_db_id,
                level=LogLevel.INFO,
                message=f"Log message {i}",
            ))

        logs = repo.list_by_run(run_db_id)
        assert len(logs) == 3

    def test_filter_by_level(self, repo, run_db_id):
        repo.create(LogEntry(id=None, run_id=run_db_id, level=LogLevel.INFO, message="Info"))
        repo.create(LogEntry(id=None, run_id=run_db_id, level=LogLevel.ERROR, message="Error"))

        errors = repo.list_by_run(run_db_id, level=LogLevel.ERROR)
        assert len(errors) == 1
        assert errors[0].message == "Error"

    def test_delete_by_run(self, repo, run_db_id):
        for i in range(5):
            repo.create(LogEntry(
                id=None, run_id=run_db_id, level=LogLevel.INFO, message=f"Log {i}"
            ))

        deleted = repo.delete_by_run(run_db_id)
        assert deleted == 5

        remaining = repo.list_by_run(run_db_id)
        assert len(remaining) == 0
