"""Tests for AI executor implementations."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.executors.base import (
    BaseExecutor,
    ExecutionResult,
    ExecutorConfig,
    ExecutorStatus,
    TaskContext,
)
from src.executors.claude_cli import (
    ClaudeCLIConfig,
    ClaudeCLIExecutor,
    OutputParser,
)
from src.executors.factory import (
    DryRunExecutor,
    ExecutorFactory,
    ExecutorRegistry,
)


# Test fixtures
@pytest.fixture
def task_context() -> TaskContext:
    """Create a sample task context."""
    return TaskContext(
        task_id="test-001",
        description="Implement test feature",
        steps=["Step 1: Do this", "Step 2: Do that"],
        project_path="/tmp/test-project",
        prd_path="/tmp/test-project/prd.json",
        phase=1,
        category="backend",
    )


@pytest.fixture
def executor_config() -> ExecutorConfig:
    """Create a sample executor config."""
    return ExecutorConfig(
        max_retries=2,
        base_delay=0.1,
        max_delay=1.0,
        timeout=60,
    )


class TestExecutorConfig:
    """Tests for ExecutorConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ExecutorConfig()

        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.timeout == 600
        assert config.model is None
        assert config.temperature == 0.0

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = ExecutorConfig(
            max_retries=5,
            timeout=300,
            model="test-model",
        )

        assert config.max_retries == 5
        assert config.timeout == 300
        assert config.model == "test-model"


class TestTaskContext:
    """Tests for TaskContext dataclass."""

    def test_task_context_creation(self) -> None:
        """Test creating a task context."""
        context = TaskContext(
            task_id="task-123",
            description="Test task",
            steps=["Step 1", "Step 2"],
            project_path="/test",
            prd_path="/test/prd.json",
        )

        assert context.task_id == "task-123"
        assert context.description == "Test task"
        assert len(context.steps) == 2
        assert context.phase == 1
        assert context.category == "general"

    def test_task_context_with_extra(self) -> None:
        """Test task context with extra context."""
        context = TaskContext(
            task_id="task-123",
            description="Test",
            steps=[],
            project_path="/test",
            prd_path="/test/prd.json",
            extra_context={"key": "value"},
        )

        assert context.extra_context == {"key": "value"}


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful execution result."""
        result = ExecutionResult(
            success=True,
            output="Task completed successfully",
            tokens_used=100,
        )

        assert result.success
        assert result.error is None
        assert result.tokens_used == 100

    def test_failure_result(self) -> None:
        """Test failed execution result."""
        result = ExecutionResult(
            success=False,
            output="",
            error="Something went wrong",
        )

        assert not result.success
        assert result.error == "Something went wrong"


class TestOutputParser:
    """Tests for OutputParser."""

    def test_parse_success_output(self) -> None:
        """Test parsing successful output."""
        output = "Task completed successfully. All changes have been applied."
        result = OutputParser.parse(output)

        assert result["success"] is True
        assert result["error"] is None

    def test_parse_failure_output(self) -> None:
        """Test parsing failure output."""
        output = "Error: Failed to compile the code. Syntax error on line 42."
        result = OutputParser.parse(output)

        assert result["success"] is False
        assert "Error" in result["error"]

    def test_parse_file_changes(self) -> None:
        """Test parsing file changes from output."""
        output = """
        Created file `src/feature.py`
        Updated `tests/test_feature.py`
        Modified 'config.yaml'
        """
        result = OutputParser.parse(output)

        assert len(result["files_changed"]) >= 1
        # Should extract file paths
        files = result["files_changed"]
        assert any("feature" in f for f in files)

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        result = OutputParser.parse("")

        assert result["success"] is False
        assert "Empty output" in result["error"]

    def test_parse_ambiguous_output(self) -> None:
        """Test parsing output without clear success/failure."""
        output = "Processing complete. See results above."
        result = OutputParser.parse(output)

        # Should assume success for ambiguous output with positive words
        assert result["success"] is True


class TestDryRunExecutor:
    """Tests for DryRunExecutor."""

    def test_name_and_version(self) -> None:
        """Test executor name and version."""
        executor = DryRunExecutor()

        assert executor.name == "dry-run"
        assert executor.version == "1.0.0"

    def test_execute(self, task_context: TaskContext) -> None:
        """Test dry run execution."""
        executor = DryRunExecutor()
        result = executor.execute(task_context)

        assert result.status.value == "completed"
        assert "DRY RUN" in result.output
        assert result.task_id == task_context.task_id

    def test_health_check(self) -> None:
        """Test health check always passes."""
        executor = DryRunExecutor()
        assert executor.health_check() is True


class TestClaudeCLIExecutor:
    """Tests for ClaudeCLIExecutor."""

    def test_name(self) -> None:
        """Test executor name."""
        executor = ClaudeCLIExecutor()
        assert executor.name == "claude-cli"

    def test_config_defaults(self) -> None:
        """Test default configuration."""
        config = ClaudeCLIConfig()

        assert config.max_turns == 50
        assert config.print_output is False
        assert "Read" in config.allowed_tools
        assert "Write" in config.allowed_tools

    def test_build_prompt(self, task_context: TaskContext) -> None:
        """Test prompt building."""
        executor = ClaudeCLIExecutor()
        prompt = executor.build_prompt(task_context)

        assert task_context.task_id in prompt
        assert task_context.description in prompt
        assert "Step 1" in prompt

    @patch("shutil.which")
    def test_get_claude_path_not_found(self, mock_which: MagicMock) -> None:
        """Test error when claude CLI not found."""
        mock_which.return_value = None

        executor = ClaudeCLIExecutor()

        with pytest.raises(RuntimeError, match="Claude CLI not found"):
            executor._get_claude_path()

    @patch("shutil.which")
    def test_get_claude_path_from_path(self, mock_which: MagicMock) -> None:
        """Test finding claude in PATH."""
        mock_which.return_value = "/usr/local/bin/claude"

        executor = ClaudeCLIExecutor()
        path = executor._get_claude_path()

        assert path == "/usr/local/bin/claude"

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_execute_success(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
        task_context: TaskContext,
    ) -> None:
        """Test successful execution."""
        mock_which.return_value = "/usr/local/bin/claude"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Task completed successfully. All changes applied.",
            stderr="",
        )

        executor = ClaudeCLIExecutor()
        result = executor.execute(task_context)

        assert result.status.value == "completed"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_execute_timeout(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
        task_context: TaskContext,
    ) -> None:
        """Test execution timeout."""
        import subprocess

        mock_which.return_value = "/usr/local/bin/claude"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=60)

        config = ClaudeCLIConfig(timeout=60)
        executor = ClaudeCLIExecutor(config)
        result = executor.execute(task_context)

        assert result.status.value == "failed"
        assert "timed out" in result.error.lower()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_health_check_success(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """Test health check with available claude."""
        mock_which.return_value = "/usr/local/bin/claude"
        mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0", stderr="")

        executor = ClaudeCLIExecutor()
        assert executor.health_check() is True


class TestExecutorRegistry:
    """Tests for ExecutorRegistry."""

    def test_register_and_get(self) -> None:
        """Test registering and getting executors."""
        # Clear registry first
        ExecutorRegistry.clear()

        ExecutorRegistry.register("test-executor", DryRunExecutor)
        executor_class = ExecutorRegistry.get("test-executor")

        assert executor_class == DryRunExecutor

    def test_get_nonexistent(self) -> None:
        """Test getting non-existent executor."""
        result = ExecutorRegistry.get("nonexistent")
        assert result is None

    def test_list_executors(self) -> None:
        """Test listing registered executors."""
        ExecutorRegistry.clear()
        ExecutorRegistry.register("exec-1", DryRunExecutor)
        ExecutorRegistry.register("exec-2", DryRunExecutor)

        executors = ExecutorRegistry.list_executors()

        assert "exec-1" in executors
        assert "exec-2" in executors


class TestExecutorFactory:
    """Tests for ExecutorFactory."""

    def test_create_dry_run(self) -> None:
        """Test creating dry-run executor."""
        factory = ExecutorFactory()
        executor = factory.create("dry-run")

        assert executor.name == "dry-run"
        assert isinstance(executor, DryRunExecutor)

    def test_create_with_config(self) -> None:
        """Test creating executor with config."""
        factory = ExecutorFactory()
        config = {"max_retries": 5, "timeout": 300}
        executor = factory.create("dry-run", config)

        assert executor.config.max_retries == 5
        assert executor.config.timeout == 300

    def test_create_unknown_executor(self) -> None:
        """Test error for unknown executor."""
        factory = ExecutorFactory()

        with pytest.raises(ValueError, match="Unknown executor"):
            factory.create("nonexistent-executor")

    def test_create_for_task(self) -> None:
        """Test creating executor based on task config."""
        factory = ExecutorFactory()

        # Task-level config
        executor = factory.create_for_task(
            task_config={"executor": "dry-run"},
        )
        assert executor.name == "dry-run"

        # Project-level config
        executor = factory.create_for_task(
            project_config={"default_executor": "dry-run"},
        )
        assert executor.name == "dry-run"

    def test_list_available(self) -> None:
        """Test listing available executors."""
        factory = ExecutorFactory()
        available = factory.list_available()

        assert len(available) >= 2  # At least dry-run and claude-cli
        names = [e["name"] for e in available]
        assert "dry-run" in names


class TestRetryLogic:
    """Tests for retry and backoff logic."""

    def test_calculate_backoff(self) -> None:
        """Test exponential backoff calculation."""
        executor = DryRunExecutor(ExecutorConfig(base_delay=1.0, max_delay=60.0))

        # First retry should be around base_delay
        delay1 = executor._calculate_backoff(1)
        assert 0.9 <= delay1 <= 1.1  # Allow for jitter

        # Second retry should be around 2x
        delay2 = executor._calculate_backoff(2)
        assert 1.8 <= delay2 <= 2.2

        # Third retry should be around 4x
        delay3 = executor._calculate_backoff(3)
        assert 3.6 <= delay3 <= 4.4

    def test_backoff_respects_max_delay(self) -> None:
        """Test that backoff doesn't exceed max_delay."""
        executor = DryRunExecutor(ExecutorConfig(base_delay=1.0, max_delay=5.0))

        # Large attempt number should still respect max_delay
        delay = executor._calculate_backoff(10)
        assert delay <= 5.5  # Allow small jitter over max

    def test_should_retry_rate_limit(self) -> None:
        """Test retry on rate limit error."""
        executor = DryRunExecutor()
        result = ExecutionResult(
            success=False,
            output="",
            error="Rate limit exceeded. Please retry later.",
        )

        assert executor._should_retry(result) is True

    def test_should_retry_timeout(self) -> None:
        """Test retry on timeout error."""
        executor = DryRunExecutor()
        result = ExecutionResult(
            success=False,
            output="",
            error="Request timeout after 60 seconds",
        )

        assert executor._should_retry(result) is True

    def test_should_not_retry_success(self) -> None:
        """Test no retry on success."""
        executor = DryRunExecutor()
        result = ExecutionResult(
            success=True,
            output="Done",
        )

        assert executor._should_retry(result) is False

    def test_should_not_retry_permanent_error(self) -> None:
        """Test no retry on permanent errors."""
        executor = DryRunExecutor()
        result = ExecutionResult(
            success=False,
            output="",
            error="Invalid API key",
        )

        assert executor._should_retry(result) is False
