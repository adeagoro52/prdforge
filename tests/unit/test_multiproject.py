"""Unit tests for multi-project management features."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.db import Database, Project, ProjectHealth, ProjectRepository, RunRepository
from src.db.models import Run, RunStatus


class TestProjectTags:
    """Tests for project tagging functionality."""

    @pytest.fixture
    def db(self):
        """Create a test database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        db = Database(db_path)
        db.initialize()
        yield db
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def repo(self, db):
        """Create a project repository."""
        return ProjectRepository(db)

    def test_project_tags_property(self):
        """Test Project.tags property getter and setter."""
        project = Project(id=None, name="test", path="/test")
        assert project.tags == []

        project.tags = ["web", "backend"]
        assert project.tags == ["backend", "web"]  # sorted
        assert '["backend", "web"]' == project.tags_json

    def test_project_tags_with_invalid_json(self):
        """Test tags property with invalid JSON."""
        project = Project(id=None, name="test", path="/test", tags_json="invalid")
        assert project.tags == []

    def test_create_project_with_tags(self, repo):
        """Test creating a project with tags."""
        project = Project(id=None, name="test-project", path="/test")
        project.tags = ["production", "api"]
        project_id = repo.create(project)

        retrieved = repo.get_by_id(project_id)
        assert retrieved.tags == ["api", "production"]

    def test_add_tags_to_project(self, repo):
        """Test adding tags to existing project."""
        project = Project(id=None, name="test-project", path="/test")
        project.tags = ["web"]
        project_id = repo.create(project)

        repo.add_tags(project_id, ["api", "backend"])
        retrieved = repo.get_by_id(project_id)
        assert retrieved.tags == ["api", "backend", "web"]

    def test_add_duplicate_tags(self, repo):
        """Test that duplicate tags are not added."""
        project = Project(id=None, name="test-project", path="/test")
        project.tags = ["web", "api"]
        project_id = repo.create(project)

        repo.add_tags(project_id, ["web", "backend"])
        retrieved = repo.get_by_id(project_id)
        assert retrieved.tags == ["api", "backend", "web"]

    def test_remove_tags_from_project(self, repo):
        """Test removing tags from project."""
        project = Project(id=None, name="test-project", path="/test")
        project.tags = ["web", "api", "backend"]
        project_id = repo.create(project)

        repo.remove_tags(project_id, ["api", "backend"])
        retrieved = repo.get_by_id(project_id)
        assert retrieved.tags == ["web"]

    def test_remove_nonexistent_tags(self, repo):
        """Test removing tags that don't exist."""
        project = Project(id=None, name="test-project", path="/test")
        project.tags = ["web"]
        project_id = repo.create(project)

        repo.remove_tags(project_id, ["nonexistent"])
        retrieved = repo.get_by_id(project_id)
        assert retrieved.tags == ["web"]

    def test_set_tags_replaces_existing(self, repo):
        """Test that set_tags replaces existing tags."""
        project = Project(id=None, name="test-project", path="/test")
        project.tags = ["web", "api"]
        project_id = repo.create(project)

        repo.set_tags(project_id, ["production", "critical"])
        retrieved = repo.get_by_id(project_id)
        assert retrieved.tags == ["critical", "production"]

    def test_list_by_tag(self, repo):
        """Test listing projects by tag."""
        # Create projects with different tags
        p1 = Project(id=None, name="project1", path="/p1")
        p1.tags = ["web", "api"]
        repo.create(p1)

        p2 = Project(id=None, name="project2", path="/p2")
        p2.tags = ["web", "backend"]
        repo.create(p2)

        p3 = Project(id=None, name="project3", path="/p3")
        p3.tags = ["mobile"]
        repo.create(p3)

        web_projects = repo.list_by_tag("web")
        assert len(web_projects) == 2
        assert {p.name for p in web_projects} == {"project1", "project2"}

        api_projects = repo.list_by_tag("api")
        assert len(api_projects) == 1
        assert api_projects[0].name == "project1"

    def test_get_all_tags(self, repo):
        """Test getting all unique tags."""
        p1 = Project(id=None, name="project1", path="/p1")
        p1.tags = ["web", "api"]
        repo.create(p1)

        p2 = Project(id=None, name="project2", path="/p2")
        p2.tags = ["web", "backend"]
        repo.create(p2)

        all_tags = repo.get_all_tags()
        assert all_tags == ["api", "backend", "web"]


class TestProjectArchiving:
    """Tests for project archiving functionality."""

    @pytest.fixture
    def db(self):
        """Create a test database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        db = Database(db_path)
        db.initialize()
        yield db
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def repo(self, db):
        """Create a project repository."""
        return ProjectRepository(db)

    def test_is_archived_property(self):
        """Test Project.is_archived property."""
        project = Project(id=None, name="test", path="/test")
        assert project.is_archived is False

        project.archived_at = datetime.utcnow()
        assert project.is_archived is True

    def test_archive_project(self, repo):
        """Test archiving a project."""
        project = Project(id=None, name="test-project", path="/test")
        project_id = repo.create(project)

        repo.archive(project_id)
        retrieved = repo.get_by_id(project_id)

        assert retrieved.is_archived is True
        assert retrieved.archived_at is not None

    def test_unarchive_project(self, repo):
        """Test unarchiving a project."""
        project = Project(id=None, name="test-project", path="/test")
        project_id = repo.create(project)

        repo.archive(project_id)
        repo.unarchive(project_id)
        retrieved = repo.get_by_id(project_id)

        assert retrieved.is_archived is False
        assert retrieved.archived_at is None

    def test_list_excludes_archived_by_default(self, repo):
        """Test that list_all excludes archived projects by default."""
        p1 = Project(id=None, name="active1", path="/p1")
        repo.create(p1)

        p2 = Project(id=None, name="archived1", path="/p2")
        p2_id = repo.create(p2)
        repo.archive(p2_id)

        projects = repo.list_all()
        assert len(projects) == 1
        assert projects[0].name == "active1"

    def test_list_includes_archived_when_requested(self, repo):
        """Test that list_all includes archived projects when requested."""
        p1 = Project(id=None, name="active1", path="/p1")
        repo.create(p1)

        p2 = Project(id=None, name="archived1", path="/p2")
        p2_id = repo.create(p2)
        repo.archive(p2_id)

        projects = repo.list_all(include_archived=True)
        assert len(projects) == 2

    def test_list_archived_only(self, repo):
        """Test listing only archived projects."""
        p1 = Project(id=None, name="active1", path="/p1")
        repo.create(p1)

        p2 = Project(id=None, name="archived1", path="/p2")
        p2_id = repo.create(p2)
        repo.archive(p2_id)

        p3 = Project(id=None, name="archived2", path="/p3")
        p3_id = repo.create(p3)
        repo.archive(p3_id)

        archived = repo.list_archived()
        assert len(archived) == 2
        assert {p.name for p in archived} == {"archived1", "archived2"}

    def test_list_by_tag_excludes_archived(self, repo):
        """Test that list_by_tag excludes archived projects."""
        p1 = Project(id=None, name="active1", path="/p1")
        p1.tags = ["web"]
        repo.create(p1)

        p2 = Project(id=None, name="archived1", path="/p2")
        p2.tags = ["web"]
        p2_id = repo.create(p2)
        repo.archive(p2_id)

        projects = repo.list_by_tag("web")
        assert len(projects) == 1
        assert projects[0].name == "active1"


class TestProjectHealth:
    """Tests for project health status functionality."""

    @pytest.fixture
    def db(self):
        """Create a test database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        db = Database(db_path)
        db.initialize()
        yield db
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def project_repo(self, db):
        """Create a project repository."""
        return ProjectRepository(db)

    @pytest.fixture
    def run_repo(self, db):
        """Create a run repository."""
        return RunRepository(db)

    def test_unknown_health_no_runs(self, project_repo):
        """Test health is UNKNOWN when project has no runs."""
        project = Project(id=None, name="test-project", path="/test")
        project_id = project_repo.create(project)

        health = project_repo.get_health(project_id)
        assert health == ProjectHealth.UNKNOWN

    def test_healthy_status_completed_no_failures(self, project_repo, run_repo):
        """Test HEALTHY status when last run completed without failures."""
        project = Project(id=None, name="test-project", path="/test")
        project_id = project_repo.create(project)

        run = Run(
            id=None,
            run_id="run-1",
            project_id=project_id,
            prd_path="/prd.json",
            status=RunStatus.COMPLETED,
            total_tasks=10,
            completed_tasks=10,
            failed_tasks=0,
            started_at=datetime.utcnow(),
        )
        run_repo.create(run)

        health = project_repo.get_health(project_id)
        assert health == ProjectHealth.HEALTHY

    def test_warning_status_completed_with_failures(self, project_repo, run_repo):
        """Test WARNING status when last run completed with some failures."""
        project = Project(id=None, name="test-project", path="/test")
        project_id = project_repo.create(project)

        run = Run(
            id=None,
            run_id="run-1",
            project_id=project_id,
            prd_path="/prd.json",
            status=RunStatus.COMPLETED,
            total_tasks=10,
            completed_tasks=8,
            failed_tasks=2,
            started_at=datetime.utcnow(),
        )
        run_repo.create(run)

        health = project_repo.get_health(project_id)
        assert health == ProjectHealth.WARNING

    def test_failing_status_last_run_failed(self, project_repo, run_repo):
        """Test FAILING status when last run failed."""
        project = Project(id=None, name="test-project", path="/test")
        project_id = project_repo.create(project)

        run = Run(
            id=None,
            run_id="run-1",
            project_id=project_id,
            prd_path="/prd.json",
            status=RunStatus.FAILED,
            total_tasks=10,
            completed_tasks=3,
            failed_tasks=7,
            started_at=datetime.utcnow(),
        )
        run_repo.create(run)

        health = project_repo.get_health(project_id)
        assert health == ProjectHealth.FAILING

    def test_healthy_status_when_running(self, project_repo, run_repo):
        """Test HEALTHY status when run is in progress."""
        project = Project(id=None, name="test-project", path="/test")
        project_id = project_repo.create(project)

        run = Run(
            id=None,
            run_id="run-1",
            project_id=project_id,
            prd_path="/prd.json",
            status=RunStatus.RUNNING,
            total_tasks=10,
            completed_tasks=5,
            failed_tasks=0,
            started_at=datetime.utcnow(),
        )
        run_repo.create(run)

        health = project_repo.get_health(project_id)
        assert health == ProjectHealth.HEALTHY

    def test_health_uses_most_recent_run(self, project_repo, run_repo):
        """Test that health is based on most recent run."""
        project = Project(id=None, name="test-project", path="/test")
        project_id = project_repo.create(project)

        # Old failed run
        old_run = Run(
            id=None,
            run_id="run-1",
            project_id=project_id,
            prd_path="/prd.json",
            status=RunStatus.FAILED,
            total_tasks=10,
            completed_tasks=0,
            failed_tasks=10,
            started_at=datetime.utcnow() - timedelta(hours=1),
        )
        run_repo.create(old_run)

        # New successful run
        new_run = Run(
            id=None,
            run_id="run-2",
            project_id=project_id,
            prd_path="/prd.json",
            status=RunStatus.COMPLETED,
            total_tasks=10,
            completed_tasks=10,
            failed_tasks=0,
            started_at=datetime.utcnow(),
        )
        run_repo.create(new_run)

        health = project_repo.get_health(project_id)
        assert health == ProjectHealth.HEALTHY

    def test_health_summary(self, project_repo, run_repo):
        """Test health summary across all projects."""
        # Create projects with different health states
        p1 = Project(id=None, name="healthy-project", path="/p1")
        p1_id = project_repo.create(p1)
        run_repo.create(Run(
            id=None, run_id="r1", project_id=p1_id, prd_path="/prd.json",
            status=RunStatus.COMPLETED, total_tasks=10, completed_tasks=10, failed_tasks=0,
            started_at=datetime.utcnow(),
        ))

        p2 = Project(id=None, name="warning-project", path="/p2")
        p2_id = project_repo.create(p2)
        run_repo.create(Run(
            id=None, run_id="r2", project_id=p2_id, prd_path="/prd.json",
            status=RunStatus.COMPLETED, total_tasks=10, completed_tasks=8, failed_tasks=2,
            started_at=datetime.utcnow(),
        ))

        p3 = Project(id=None, name="unknown-project", path="/p3")
        project_repo.create(p3)

        summary = project_repo.get_health_summary()
        assert summary["healthy"] == 1
        assert summary["warning"] == 1
        assert summary["unknown"] == 1
        assert summary["failing"] == 0
        assert summary["inactive"] == 0
