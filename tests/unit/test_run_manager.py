"""Tests for RunManager."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.engine.config import ExecutionConfig, RunStatus, TaskStatus
from src.engine.run_manager import RunManager


@pytest.fixture
def mock_prd(tmp_path: Path) -> Path:
    """Create a mock PRD file."""
    prd_data = {
        "meta": {"feature_name": "Test Feature"},
        "tasks": [
            {
                "id": "task-001",
                "phase": 1,
                "category": "backend",
                "description": "First task",
                "steps": ["Step 1"],
                "passes": False,
                "blocked_by": [],
            },
            {
                "id": "task-002",
                "phase": 1,
                "category": "backend",
                "description": "Second task",
                "steps": ["Step A"],
                "passes": False,
                "blocked_by": ["task-001"],
            },
        ],
    }

    prd_file = tmp_path / "test_prd.json"
    prd_file.write_text(json.dumps(prd_data))
    return prd_file


@pytest.fixture
def mock_config(tmp_path: Path, mock_prd: Path) -> ExecutionConfig:
    """Create a mock execution config."""
    return ExecutionConfig(
        project_path=tmp_path,
        prd_path=mock_prd,
        dry_run=True,
    )


class TestRunManager:
    """Tests for RunManager."""

    @patch("src.engine.run_manager.GitManager")
    def test_create_run(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test creating a new run."""
        manager = RunManager(mock_config)
        state = manager.create_run()

        assert state.run_id is not None
        assert state.status == RunStatus.PENDING
        assert "run_branch" in state.metadata

    @patch("src.engine.run_manager.GitManager")
    def test_generate_run_branch_name(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test run branch name generation."""
        manager = RunManager(mock_config)
        branch = manager._generate_run_branch_name("abc12345-6789")

        assert branch.startswith("prdforge/run/")
        assert "abc12345" in branch

    @patch("src.engine.run_manager.GitManager")
    def test_load_prd_tasks(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test loading tasks from PRD."""
        manager = RunManager(mock_config)
        tasks = manager.load_prd_tasks()

        assert len(tasks) == 2
        assert tasks[0].id == "task-001"
        assert tasks[1].id == "task-002"
        assert tasks[1].blocked_by == ["task-001"]

    @patch("src.engine.run_manager.GitManager")
    def test_on_task_complete_callback(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test task completion callbacks."""
        manager = RunManager(mock_config)

        callback_results: list[tuple[str, TaskStatus]] = []

        def callback(task_id: str, status: TaskStatus) -> None:
            callback_results.append((task_id, status))

        manager.on_task_complete(callback)
        manager._notify_task_complete("task-001", TaskStatus.COMPLETED)

        assert len(callback_results) == 1
        assert callback_results[0] == ("task-001", TaskStatus.COMPLETED)

    @patch("src.engine.run_manager.GitManager")
    def test_on_status_change_callback(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test status change callbacks."""
        manager = RunManager(mock_config)

        status_changes: list[RunStatus] = []

        def callback(status: RunStatus) -> None:
            status_changes.append(status)

        manager.on_status_change(callback)
        manager.create_run()
        manager._set_status(RunStatus.RUNNING)
        manager._set_status(RunStatus.COMPLETED)

        assert RunStatus.RUNNING in status_changes
        assert RunStatus.COMPLETED in status_changes

    @patch("src.engine.run_manager.GitManager")
    def test_start_dry_run(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test starting a dry run."""
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        mock_git.has_uncommitted_changes.return_value = False

        manager = RunManager(mock_config)
        state = manager.start()

        assert state.status == RunStatus.COMPLETED
        assert state.tasks_completed == 2
        assert state.tasks_failed == 0

    @patch("src.engine.run_manager.GitManager")
    def test_get_progress(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test getting run progress."""
        manager = RunManager(mock_config)

        # No run yet
        progress = manager.get_progress()
        assert progress["status"] == "no_run"

        # Create run
        manager.create_run()
        progress = manager.get_progress()

        assert progress["status"] == "pending"
        assert "run_id" in progress

    @patch("src.engine.run_manager.GitManager")
    def test_pause_and_resume(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test pause and resume functionality."""
        manager = RunManager(mock_config)
        manager.create_run()

        # Initially not paused
        assert not manager._paused

        # Set to running and pause
        manager._set_status(RunStatus.RUNNING)
        manager.pause()
        assert manager._paused

        # Resume
        manager._set_status(RunStatus.PAUSED)
        manager.resume()
        assert not manager._paused

    @patch("src.engine.run_manager.GitManager")
    def test_cancel(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test cancel functionality."""
        manager = RunManager(mock_config)
        manager.create_run()

        manager.cancel()

        assert manager._cancelled
        assert not manager._paused  # Should also unblock if paused

    @patch("src.engine.run_manager.GitManager")
    def test_save_state(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig, tmp_path: Path
    ) -> None:
        """Test saving run state to file."""
        manager = RunManager(mock_config)
        manager.create_run()

        save_path = tmp_path / "run_state.json"
        result_path = manager.save_state(save_path)

        assert result_path == save_path
        assert save_path.exists()

        # Verify content
        with open(save_path) as f:
            data = json.load(f)

        assert data["run_id"] == manager.state.run_id
        assert data["status"] == "pending"

    @patch("src.engine.run_manager.GitManager")
    def test_save_state_default_path(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test saving run state to default path."""
        manager = RunManager(mock_config)
        manager.create_run()

        result_path = manager.save_state()

        assert result_path.exists()
        assert ".prdforge/runs" in str(result_path)
        assert manager.state.run_id in str(result_path)


class TestRunManagerIntegration:
    """Integration tests for RunManager with real execution."""

    @patch("src.engine.run_manager.GitManager")
    def test_full_execution_flow(
        self, mock_git_class: MagicMock, mock_config: ExecutionConfig
    ) -> None:
        """Test full execution flow from start to completion."""
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        mock_git.has_uncommitted_changes.return_value = False

        # Track events
        task_events: list[tuple[str, TaskStatus]] = []
        status_events: list[RunStatus] = []

        manager = RunManager(mock_config)
        manager.on_task_complete(lambda tid, status: task_events.append((tid, status)))
        manager.on_status_change(lambda status: status_events.append(status))

        # Run
        state = manager.start()

        # Verify execution order
        assert state.status == RunStatus.COMPLETED
        assert len(task_events) == 2
        assert task_events[0][0] == "task-001"  # First task completed first
        assert task_events[1][0] == "task-002"  # Second task after

        # Verify status transitions
        assert RunStatus.RUNNING in status_events
        assert RunStatus.COMPLETED in status_events
