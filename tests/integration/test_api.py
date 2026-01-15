"""Integration tests for the PRDForge REST API."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.api.routes import get_db
from src.db import Database


@pytest.fixture
def test_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        db.initialize()
        yield db


@pytest.fixture
def client(test_db: Database):
    """Create a test client with dependency override."""
    app = create_app()

    # Override the database dependency
    def override_get_db():
        return test_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client


class TestProjectAPI:
    """Tests for project-related API endpoints."""

    def test_list_projects_empty(self, client: TestClient):
        """List projects returns empty list initially."""
        response = client.get("/api/projects")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_project(self, client: TestClient):
        """Create a new project."""
        project_data = {
            "name": "test-project",
            "path": "/path/to/project",
            "project_type": "local",
        }
        response = client.post("/api/projects", json=project_data)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "test-project"
        assert data["path"] == "/path/to/project"
        assert data["project_type"] == "local"
        assert data["id"] is not None

    def test_create_project_duplicate_name(self, client: TestClient):
        """Creating project with duplicate name fails."""
        project_data = {
            "name": "test-project",
            "path": "/path/to/project",
        }
        # Create first project
        response = client.post("/api/projects", json=project_data)
        assert response.status_code == 201

        # Try to create duplicate
        response = client.post("/api/projects", json=project_data)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_get_project(self, client: TestClient):
        """Get a project by ID."""
        # Create a project first
        create_response = client.post(
            "/api/projects",
            json={"name": "test", "path": "/test"},
        )
        project_id = create_response.json()["id"]

        # Get the project
        response = client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "test"

    def test_get_project_not_found(self, client: TestClient):
        """Get non-existent project returns 404."""
        response = client.get("/api/projects/9999")
        assert response.status_code == 404

    def test_delete_project(self, client: TestClient):
        """Delete a project."""
        # Create a project
        create_response = client.post(
            "/api/projects",
            json={"name": "to-delete", "path": "/delete"},
        )
        project_id = create_response.json()["id"]

        # Delete it
        response = client.delete(f"/api/projects/{project_id}")
        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f"/api/projects/{project_id}")
        assert response.status_code == 404

    def test_list_projects(self, client: TestClient):
        """List projects returns created projects."""
        # Create projects
        client.post("/api/projects", json={"name": "proj1", "path": "/p1"})
        client.post("/api/projects", json={"name": "proj2", "path": "/p2"})

        response = client.get("/api/projects")
        assert response.status_code == 200
        projects = response.json()
        assert len(projects) == 2
        names = [p["name"] for p in projects]
        assert "proj1" in names
        assert "proj2" in names


class TestRunAPI:
    """Tests for run-related API endpoints."""

    @pytest.fixture
    def project_id(self, client: TestClient) -> int:
        """Create a project and return its ID."""
        response = client.post(
            "/api/projects",
            json={"name": "run-test", "path": "/test"},
        )
        return response.json()["id"]

    def test_list_runs_empty(self, client: TestClient, project_id: int):
        """List runs returns empty list initially."""
        response = client.get(f"/api/projects/{project_id}/runs")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_run(self, client: TestClient, project_id: int):
        """Create a new run."""
        run_data = {
            "prd_path": "docs/prd.json",
            "base_branch": "main",
            "executor": "claude-cli",
        }
        response = client.post(f"/api/projects/{project_id}/runs", json=run_data)
        assert response.status_code == 201

        data = response.json()
        assert data["prd_path"] == "docs/prd.json"
        assert data["base_branch"] == "main"
        assert data["status"] == "pending"
        assert data["run_id"] is not None

    def test_create_run_project_not_found(self, client: TestClient):
        """Creating run for non-existent project fails."""
        response = client.post(
            "/api/projects/9999/runs",
            json={"prd_path": "test.json"},
        )
        assert response.status_code == 404

    def test_get_run(self, client: TestClient, project_id: int):
        """Get a run by ID."""
        # Create a run
        create_response = client.post(
            f"/api/projects/{project_id}/runs",
            json={"prd_path": "test.json"},
        )
        run_id = create_response.json()["run_id"]

        # Get the run
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        assert response.json()["prd_path"] == "test.json"

    def test_get_run_not_found(self, client: TestClient):
        """Get non-existent run returns 404."""
        response = client.get("/api/runs/nonexistent-uuid")
        assert response.status_code == 404

    def test_list_project_runs(self, client: TestClient, project_id: int):
        """List runs for a project."""
        # Create runs
        client.post(
            f"/api/projects/{project_id}/runs",
            json={"prd_path": "prd1.json"},
        )
        client.post(
            f"/api/projects/{project_id}/runs",
            json={"prd_path": "prd2.json"},
        )

        response = client.get(f"/api/projects/{project_id}/runs")
        assert response.status_code == 200
        runs = response.json()
        assert len(runs) == 2


class TestRunControlAPI:
    """Tests for run control endpoints (pause, resume, cancel)."""

    @pytest.fixture
    def running_run(self, client: TestClient, test_db: Database) -> str:
        """Create a running run and return its run_id."""
        from src.db import ProjectRepository, Run, RunRepository
        from src.db.models import RunStatus
        from datetime import datetime
        from uuid import uuid4

        # Create project
        response = client.post(
            "/api/projects",
            json={"name": "control-test", "path": "/test"},
        )
        project_id = response.json()["id"]

        # Create run directly in running state
        run_repo = RunRepository(test_db)
        run_id = str(uuid4())
        run = Run(
            id=None,
            run_id=run_id,
            project_id=project_id,
            prd_path="test.json",
            status=RunStatus.RUNNING,
            base_branch="main",
            executor="claude-cli",
            started_at=datetime.utcnow(),
        )
        run_repo.create(run)
        return run_id

    def test_pause_running_run(self, client: TestClient, running_run: str):
        """Pause a running run."""
        response = client.post(f"/api/runs/{running_run}/pause")
        assert response.status_code == 200
        assert response.json()["status"] == "paused"

        # Verify state changed
        get_response = client.get(f"/api/runs/{running_run}")
        assert get_response.json()["status"] == "paused"

    def test_resume_paused_run(self, client: TestClient, running_run: str):
        """Resume a paused run."""
        # First pause it
        client.post(f"/api/runs/{running_run}/pause")

        # Then resume
        response = client.post(f"/api/runs/{running_run}/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

    def test_cancel_run(self, client: TestClient, running_run: str):
        """Cancel a running run."""
        response = client.post(f"/api/runs/{running_run}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_pause_non_running_fails(self, client: TestClient):
        """Pause fails for non-running run."""
        # Create a pending run
        client.post("/api/projects", json={"name": "test", "path": "/t"})
        create_response = client.post(
            "/api/projects/1/runs",
            json={"prd_path": "test.json"},
        )
        run_id = create_response.json()["run_id"]

        # Try to pause (should fail - it's pending, not running)
        response = client.post(f"/api/runs/{run_id}/pause")
        assert response.status_code == 400

    def test_resume_non_paused_fails(self, client: TestClient, running_run: str):
        """Resume fails for non-paused run."""
        response = client.post(f"/api/runs/{running_run}/resume")
        assert response.status_code == 400


class TestHTMLPages:
    """Tests for HTML page endpoints."""

    def test_dashboard_page(self, client: TestClient):
        """Dashboard page loads."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "PRDForge" in response.text

    def test_projects_page(self, client: TestClient):
        """Projects page loads."""
        response = client.get("/projects")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Projects" in response.text

    def test_project_detail_page(self, client: TestClient):
        """Project detail page loads."""
        # Create a project first
        create_response = client.post(
            "/api/projects",
            json={"name": "detail-test", "path": "/test"},
        )
        project_id = create_response.json()["id"]

        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "detail-test" in response.text

    def test_project_detail_not_found(self, client: TestClient):
        """Project detail page returns 404 for non-existent project."""
        response = client.get("/projects/9999")
        assert response.status_code == 404

    def test_run_detail_page(self, client: TestClient):
        """Run detail page loads."""
        # Create project and run
        client.post("/api/projects", json={"name": "run-page", "path": "/r"})
        run_response = client.post(
            "/api/projects/1/runs",
            json={"prd_path": "test.json"},
        )
        run_id = run_response.json()["run_id"]

        response = client.get(f"/runs/{run_id}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_run_detail_not_found(self, client: TestClient):
        """Run detail page returns 404 for non-existent run."""
        response = client.get("/runs/nonexistent-uuid")
        assert response.status_code == 404
