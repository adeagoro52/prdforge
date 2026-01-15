"""Tests for engine configuration dataclasses."""

import pytest
from datetime import datetime
from pathlib import Path

from src.engine.config import (
    ExecutionConfig,
    RunState,
    RunStatus,
    TaskResult,
    TaskStatus,
)


class TestExecutionConfig:
    """Tests for ExecutionConfig dataclass."""

    def test_valid_config(self, tmp_path: Path) -> None:
        """Test creating a valid config."""
        # Create a mock PRD file
        prd_file = tmp_path / "test.json"
        prd_file.write_text("{}")

        config = ExecutionConfig(
            project_path=tmp_path,
            prd_path=prd_file,
        )

        assert config.project_path == tmp_path
        assert config.prd_path == prd_file
        assert config.base_branch == "develop"
        assert config.executor == "claude-cli"
        assert config.skip_completed is True
        assert config.dry_run is False

    def test_invalid_project_path(self, tmp_path: Path) -> None:
        """Test that invalid project path raises ValueError."""
        prd_file = tmp_path / "test.json"
        prd_file.write_text("{}")

        with pytest.raises(ValueError, match="Project path does not exist"):
            ExecutionConfig(
                project_path=tmp_path / "nonexistent",
                prd_path=prd_file,
            )

    def test_invalid_prd_path(self, tmp_path: Path) -> None:
        """Test that invalid PRD path raises ValueError."""
        with pytest.raises(ValueError, match="PRD file does not exist"):
            ExecutionConfig(
                project_path=tmp_path,
                prd_path=tmp_path / "nonexistent.json",
            )

    def test_path_resolution(self, tmp_path: Path) -> None:
        """Test that paths are resolved to absolute."""
        prd_file = tmp_path / "test.json"
        prd_file.write_text("{}")

        config = ExecutionConfig(
            project_path=tmp_path,
            prd_path=prd_file,
        )

        assert config.project_path.is_absolute()
        assert config.prd_path.is_absolute()


class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_duration_calculation(self) -> None:
        """Test duration calculation."""
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 12, 5, 30)

        result = TaskResult(
            task_id="test-001",
            status=TaskStatus.COMPLETED,
            started_at=start,
            completed_at=end,
        )

        assert result.duration_seconds == 330.0  # 5 min 30 sec

    def test_duration_without_completion(self) -> None:
        """Test duration is None when not completed."""
        result = TaskResult(
            task_id="test-001",
            status=TaskStatus.RUNNING,
            started_at=datetime.now(),
        )

        assert result.duration_seconds is None


class TestRunState:
    """Tests for RunState dataclass."""

    def test_task_counting(self, tmp_path: Path) -> None:
        """Test completed/failed task counting."""
        prd_file = tmp_path / "test.json"
        prd_file.write_text("{}")

        config = ExecutionConfig(
            project_path=tmp_path,
            prd_path=prd_file,
        )

        state = RunState(
            run_id="test-run",
            config=config,
        )

        # Add some task results
        state.task_results["task-1"] = TaskResult(
            task_id="task-1",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(),
        )
        state.task_results["task-2"] = TaskResult(
            task_id="task-2",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(),
        )
        state.task_results["task-3"] = TaskResult(
            task_id="task-3",
            status=TaskStatus.FAILED,
            started_at=datetime.now(),
        )

        assert state.tasks_completed == 2
        assert state.tasks_failed == 1

    def test_run_duration(self, tmp_path: Path) -> None:
        """Test run duration calculation."""
        prd_file = tmp_path / "test.json"
        prd_file.write_text("{}")

        config = ExecutionConfig(
            project_path=tmp_path,
            prd_path=prd_file,
        )

        state = RunState(
            run_id="test-run",
            config=config,
            started_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=datetime(2024, 1, 1, 12, 10, 0),
        )

        assert state.duration_seconds == 600.0  # 10 minutes


class TestEnums:
    """Tests for status enums."""

    def test_run_status_values(self) -> None:
        """Test RunStatus enum values."""
        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.RUNNING.value == "running"
        assert RunStatus.PAUSED.value == "paused"
        assert RunStatus.COMPLETED.value == "completed"
        assert RunStatus.FAILED.value == "failed"
        assert RunStatus.CANCELLED.value == "cancelled"

    def test_task_status_values(self) -> None:
        """Test TaskStatus enum values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.BLOCKED.value == "blocked"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.SKIPPED.value == "skipped"
