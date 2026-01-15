"""Tests for PRDExecutor."""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from src.engine.config import ExecutionConfig, TaskResult, TaskStatus
from src.engine.prd_executor import (
    BaseExecutor,
    DryRunExecutor,
    PRDExecutor,
    Task,
)


@pytest.fixture
def mock_config(tmp_path: Path) -> ExecutionConfig:
    """Create a mock execution config."""
    prd_file = tmp_path / "test.json"
    prd_file.write_text('{"tasks": []}')

    return ExecutionConfig(
        project_path=tmp_path,
        prd_path=prd_file,
        dry_run=True,
    )


@pytest.fixture
def sample_tasks() -> list[Task]:
    """Create sample tasks for testing."""
    return [
        Task(
            id="task-001",
            phase=1,
            category="backend",
            description="First task",
            steps=["Step 1", "Step 2"],
            passes=False,
            blocked_by=[],
        ),
        Task(
            id="task-002",
            phase=1,
            category="backend",
            description="Second task",
            steps=["Step A"],
            passes=False,
            blocked_by=["task-001"],
        ),
        Task(
            id="task-003",
            phase=1,
            category="backend",
            description="Third task (already done)",
            steps=[],
            passes=True,
            blocked_by=[],
        ),
    ]


class TestTask:
    """Tests for Task dataclass."""

    def test_task_creation(self) -> None:
        """Test creating a task."""
        task = Task(
            id="test-001",
            phase=1,
            category="backend",
            description="Test task",
        )

        assert task.id == "test-001"
        assert task.phase == 1
        assert task.category == "backend"
        assert task.passes is False
        assert task.blocked_by == []


class TestDryRunExecutor:
    """Tests for DryRunExecutor."""

    def test_name(self) -> None:
        """Test executor name."""
        executor = DryRunExecutor()
        assert executor.name == "dry-run"

    def test_execute(self, mock_config: ExecutionConfig) -> None:
        """Test dry run execution."""
        executor = DryRunExecutor()
        task = Task(
            id="test-001",
            phase=1,
            category="backend",
            description="Test task",
        )

        result = executor.execute(task, mock_config)

        assert result.status == TaskStatus.COMPLETED
        assert result.task_id == "test-001"
        assert "DRY RUN" in result.output


class TestPRDExecutor:
    """Tests for PRDExecutor."""

    def test_can_execute_no_dependencies(
        self, mock_config: ExecutionConfig, sample_tasks: list[Task]
    ) -> None:
        """Test can_execute with no dependencies."""
        executor = PRDExecutor(
            config=mock_config,
            executor=DryRunExecutor(),
            git_manager=MagicMock(),
        )

        # Task with no dependencies should be executable
        assert executor.can_execute(sample_tasks[0])

    def test_can_execute_with_dependencies(
        self, mock_config: ExecutionConfig, sample_tasks: list[Task]
    ) -> None:
        """Test can_execute with unmet dependencies."""
        executor = PRDExecutor(
            config=mock_config,
            executor=DryRunExecutor(),
            git_manager=MagicMock(),
        )

        # Task with unmet dependency should not be executable
        assert not executor.can_execute(sample_tasks[1])

        # After completing dependency, should be executable
        executor._completed_tasks.add("task-001")
        assert executor.can_execute(sample_tasks[1])

    def test_can_execute_skip_completed(
        self, mock_config: ExecutionConfig, sample_tasks: list[Task]
    ) -> None:
        """Test skip_completed behavior."""
        executor = PRDExecutor(
            config=mock_config,
            executor=DryRunExecutor(),
            git_manager=MagicMock(),
        )

        # Task already marked as passes should not execute when skip_completed=True
        assert not executor.can_execute(sample_tasks[2])

        # But should execute when skip_completed=False
        mock_config.skip_completed = False
        assert executor.can_execute(sample_tasks[2])

    def test_execute_task_success(self, mock_config: ExecutionConfig) -> None:
        """Test successful task execution."""
        executor = PRDExecutor(
            config=mock_config,
            executor=DryRunExecutor(),
            git_manager=MagicMock(),
        )
        executor.git_manager.has_uncommitted_changes.return_value = False

        task = Task(
            id="test-001",
            phase=1,
            category="backend",
            description="Test task",
        )

        result = executor.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert "test-001" in executor._completed_tasks

    def test_execute_task_blocked(self, mock_config: ExecutionConfig) -> None:
        """Test executing a blocked task."""
        executor = PRDExecutor(
            config=mock_config,
            executor=DryRunExecutor(),
            git_manager=MagicMock(),
        )

        task = Task(
            id="test-002",
            phase=1,
            category="backend",
            description="Blocked task",
            blocked_by=["test-001"],
        )

        result = executor.execute_task(task)

        assert result.status == TaskStatus.BLOCKED
        assert "test-001" in str(result.error)

    def test_get_executable_tasks(
        self, mock_config: ExecutionConfig, sample_tasks: list[Task]
    ) -> None:
        """Test getting list of executable tasks."""
        executor = PRDExecutor(
            config=mock_config,
            executor=DryRunExecutor(),
            git_manager=MagicMock(),
        )

        executable = executor.get_executable_tasks(sample_tasks)

        # Only task-001 should be executable (task-002 is blocked, task-003 is passed)
        assert len(executable) == 1
        assert executable[0].id == "task-001"

    def test_execute_tasks_in_order(
        self, mock_config: ExecutionConfig, sample_tasks: list[Task]
    ) -> None:
        """Test executing tasks respects dependency order."""
        executor = PRDExecutor(
            config=mock_config,
            executor=DryRunExecutor(),
            git_manager=MagicMock(),
        )
        executor.git_manager.has_uncommitted_changes.return_value = False

        # Execute only tasks that aren't already passed
        tasks_to_run = [t for t in sample_tasks if not t.passes]
        results = executor.execute_tasks(tasks_to_run)

        # task-001 should complete first, then task-002
        assert results["task-001"].status == TaskStatus.COMPLETED
        assert results["task-002"].status == TaskStatus.COMPLETED


class TestBaseExecutor:
    """Tests for BaseExecutor abstract class."""

    def test_build_prompt(self, mock_config: ExecutionConfig) -> None:
        """Test prompt building."""
        executor = DryRunExecutor()
        task = Task(
            id="test-001",
            phase=1,
            category="backend",
            description="Test task",
            steps=["Step 1", "Step 2"],
        )

        prompt = executor.build_prompt(task, mock_config)

        assert "test-001" in prompt
        assert "Test task" in prompt
        assert "Step 1" in prompt
        assert "Step 2" in prompt
