"""Tests for quality gates system."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.engine.quality_gates import (
    AcceptanceCriteria,
    BUILTIN_GATES,
    GateCheckResult,
    GateResult,
    GateType,
    QualityGateChecker,
    QualityGateConfig,
    QualityGateManager,
)


class TestAcceptanceCriteria:
    """Tests for AcceptanceCriteria dataclass."""

    def test_create_basic_criteria(self) -> None:
        """Test creating basic acceptance criteria."""
        criteria = AcceptanceCriteria(
            name="test-gate",
            gate_type=GateType.TEST,
        )

        assert criteria.name == "test-gate"
        assert criteria.gate_type == GateType.TEST
        assert criteria.enabled is True
        assert criteria.blocking is True
        assert criteria.command is None

    def test_create_custom_criteria(self) -> None:
        """Test creating custom criteria with command."""
        criteria = AcceptanceCriteria(
            name="custom-lint",
            gate_type=GateType.CUSTOM,
            command="ruff",
            args=["check", "src/"],
            timeout=60,
            blocking=False,
        )

        assert criteria.name == "custom-lint"
        assert criteria.gate_type == GateType.CUSTOM
        assert criteria.command == "ruff"
        assert criteria.args == ["check", "src/"]
        assert criteria.timeout == 60
        assert criteria.blocking is False

    def test_to_dict(self) -> None:
        """Test converting criteria to dictionary."""
        criteria = AcceptanceCriteria(
            name="pytest",
            gate_type=GateType.TEST,
            command="pytest",
            args=["-v"],
        )

        result = criteria.to_dict()

        assert result["name"] == "pytest"
        assert result["gate_type"] == "test"
        assert result["command"] == "pytest"
        assert result["args"] == ["-v"]
        assert result["enabled"] is True
        assert result["blocking"] is True

    def test_from_dict(self) -> None:
        """Test creating criteria from dictionary."""
        data = {
            "name": "mypy",
            "gate_type": "typecheck",
            "command": "mypy",
            "args": ["src/"],
            "timeout": 120,
        }

        criteria = AcceptanceCriteria.from_dict(data)

        assert criteria.name == "mypy"
        assert criteria.gate_type == GateType.TYPECHECK
        assert criteria.command == "mypy"
        assert criteria.args == ["src/"]
        assert criteria.timeout == 120

    def test_from_dict_string_gate_type(self) -> None:
        """Test that string gate type is converted to enum."""
        data = {"name": "test", "gate_type": "lint"}
        criteria = AcceptanceCriteria.from_dict(data)
        assert criteria.gate_type == GateType.LINT

    def test_retry_config(self) -> None:
        """Test retry configuration."""
        criteria = AcceptanceCriteria(
            name="flaky-test",
            gate_type=GateType.TEST,
            retry_on_fail=True,
            max_retries=3,
        )

        assert criteria.retry_on_fail is True
        assert criteria.max_retries == 3


class TestGateCheckResult:
    """Tests for GateCheckResult dataclass."""

    def test_create_passed_result(self) -> None:
        """Test creating a passed result."""
        gate = AcceptanceCriteria(name="test", gate_type=GateType.TEST)
        result = GateCheckResult(
            gate=gate,
            result=GateResult.PASSED,
            output="All tests passed",
            duration_seconds=1.5,
            exit_code=0,
        )

        assert result.result == GateResult.PASSED
        assert result.output == "All tests passed"
        assert result.exit_code == 0
        assert result.error is None

    def test_create_failed_result(self) -> None:
        """Test creating a failed result."""
        gate = AcceptanceCriteria(name="lint", gate_type=GateType.LINT)
        result = GateCheckResult(
            gate=gate,
            result=GateResult.FAILED,
            output="",
            error="Found 5 linting errors",
            exit_code=1,
        )

        assert result.result == GateResult.FAILED
        assert result.error == "Found 5 linting errors"
        assert result.exit_code == 1

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        gate = AcceptanceCriteria(name="test", gate_type=GateType.TEST)
        timestamp = datetime(2025, 1, 15, 12, 0, 0)
        result = GateCheckResult(
            gate=gate,
            result=GateResult.PASSED,
            output="OK",
            duration_seconds=2.5,
            timestamp=timestamp,
            exit_code=0,
        )

        d = result.to_dict()

        assert d["gate_name"] == "test"
        assert d["gate_type"] == "test"
        assert d["result"] == "passed"
        assert d["output"] == "OK"
        assert d["duration_seconds"] == 2.5
        assert d["timestamp"] == "2025-01-15T12:00:00"
        assert d["exit_code"] == 0


class TestBuiltinGates:
    """Tests for BUILTIN_GATES dictionary."""

    def test_pytest_gate_exists(self) -> None:
        """Test pytest gate configuration."""
        assert "pytest" in BUILTIN_GATES
        pytest_config = BUILTIN_GATES["pytest"]
        assert pytest_config["name"] == "pytest"
        assert pytest_config["gate_type"] == "test"
        assert pytest_config["command"] == "pytest"

    def test_ruff_gate_exists(self) -> None:
        """Test ruff gate configuration."""
        assert "ruff" in BUILTIN_GATES
        ruff_config = BUILTIN_GATES["ruff"]
        assert ruff_config["name"] == "ruff"
        assert ruff_config["gate_type"] == "lint"
        assert ruff_config["command"] == "ruff"

    def test_mypy_gate_exists(self) -> None:
        """Test mypy gate configuration."""
        assert "mypy" in BUILTIN_GATES
        mypy_config = BUILTIN_GATES["mypy"]
        assert mypy_config["name"] == "mypy"
        assert mypy_config["gate_type"] == "typecheck"

    def test_npm_test_gate_exists(self) -> None:
        """Test npm-test gate configuration."""
        assert "npm-test" in BUILTIN_GATES
        npm_config = BUILTIN_GATES["npm-test"]
        assert npm_config["gate_type"] == "test"
        assert npm_config["command"] == "npm"

    def test_tsc_gate_exists(self) -> None:
        """Test tsc gate configuration."""
        assert "tsc" in BUILTIN_GATES
        tsc_config = BUILTIN_GATES["tsc"]
        assert tsc_config["gate_type"] == "typecheck"

    def test_builtin_gates_create_valid_criteria(self) -> None:
        """Test that all builtin gates can be converted to AcceptanceCriteria."""
        for name, config in BUILTIN_GATES.items():
            criteria = AcceptanceCriteria.from_dict(config)
            assert criteria.name == name


class TestQualityGateChecker:
    """Tests for QualityGateChecker class."""

    @pytest.fixture
    def checker(self, tmp_path: Path) -> QualityGateChecker:
        """Create a checker with temp working directory."""
        return QualityGateChecker(tmp_path)

    def test_check_disabled_gate(self, checker: QualityGateChecker) -> None:
        """Test that disabled gates are skipped."""
        gate = AcceptanceCriteria(
            name="disabled-test",
            gate_type=GateType.TEST,
            enabled=False,
        )

        result = checker.check(gate)

        assert result.result == GateResult.SKIPPED
        assert "disabled" in result.output.lower()

    @patch("subprocess.run")
    def test_check_passing_gate(
        self, mock_run: MagicMock, checker: QualityGateChecker
    ) -> None:
        """Test checking a passing gate."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="All tests passed",
            stderr="",
        )

        gate = AcceptanceCriteria(
            name="test",
            gate_type=GateType.TEST,
            command="pytest",
        )

        result = checker.check(gate)

        assert result.result == GateResult.PASSED
        assert result.exit_code == 0
        assert result.output == "All tests passed"

    @patch("subprocess.run")
    def test_check_failing_gate(
        self, mock_run: MagicMock, checker: QualityGateChecker
    ) -> None:
        """Test checking a failing gate."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="2 tests failed",
        )

        gate = AcceptanceCriteria(
            name="test",
            gate_type=GateType.TEST,
            command="pytest",
        )

        result = checker.check(gate)

        assert result.result == GateResult.FAILED
        assert result.exit_code == 1
        assert result.error == "2 tests failed"

    @patch("subprocess.run")
    def test_check_timeout(
        self, mock_run: MagicMock, checker: QualityGateChecker
    ) -> None:
        """Test gate timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=10)

        gate = AcceptanceCriteria(
            name="slow-test",
            gate_type=GateType.TEST,
            command="pytest",
            timeout=10,
        )

        result = checker.check(gate)

        assert result.result == GateResult.ERROR
        assert "timeout" in result.error.lower()

    @patch("subprocess.run")
    def test_check_command_not_found(
        self, mock_run: MagicMock, checker: QualityGateChecker
    ) -> None:
        """Test handling command not found."""
        mock_run.side_effect = FileNotFoundError("pytest not found")

        gate = AcceptanceCriteria(
            name="test",
            gate_type=GateType.TEST,
            command="pytest",
        )

        result = checker.check(gate)

        assert result.result == GateResult.ERROR
        assert "not found" in result.error.lower()

    @patch("subprocess.run")
    def test_check_all_stops_on_blocking_failure(
        self, mock_run: MagicMock, checker: QualityGateChecker
    ) -> None:
        """Test that check_all stops on blocking failure."""
        # First gate fails, second should not run
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="failed")

        gates = [
            AcceptanceCriteria(name="gate1", gate_type=GateType.TEST, command="test1", blocking=True),
            AcceptanceCriteria(name="gate2", gate_type=GateType.TEST, command="test2", blocking=True),
        ]

        results = checker.check_all(gates, stop_on_failure=True)

        assert len(results) == 1  # Only first gate ran
        assert results[0].result == GateResult.FAILED

    @patch("subprocess.run")
    def test_check_all_continues_on_non_blocking_failure(
        self, mock_run: MagicMock, checker: QualityGateChecker
    ) -> None:
        """Test that check_all continues on non-blocking failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="failed")

        gates = [
            AcceptanceCriteria(name="gate1", gate_type=GateType.LINT, command="lint", blocking=False),
            AcceptanceCriteria(name="gate2", gate_type=GateType.TEST, command="test", blocking=True),
        ]

        results = checker.check_all(gates, stop_on_failure=True)

        assert len(results) == 2  # Both gates ran

    def test_detect_project_gates_python(self, tmp_path: Path) -> None:
        """Test detecting gates in a Python project."""
        # Create Python project indicators
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")
        (tmp_path / "tests").mkdir()
        (tmp_path / "ruff.toml").write_text("")

        checker = QualityGateChecker(tmp_path)
        detected = checker.detect_project_gates()

        gate_names = [g.name for g in detected]
        assert "pytest" in gate_names
        assert "ruff" in gate_names

    def test_detect_project_gates_nodejs(self, tmp_path: Path) -> None:
        """Test detecting gates in a Node.js project."""
        # Create Node.js project indicators
        package = {
            "name": "test-app",
            "scripts": {
                "test": "jest",
                "lint": "eslint .",
            },
        }
        (tmp_path / "package.json").write_text(json.dumps(package))
        (tmp_path / "tsconfig.json").write_text("{}")

        checker = QualityGateChecker(tmp_path)
        detected = checker.detect_project_gates()

        gate_names = [g.name for g in detected]
        assert "npm-test" in gate_names
        assert "npm-lint" in gate_names
        assert "tsc" in gate_names

    def test_detect_project_gates_empty_project(self, tmp_path: Path) -> None:
        """Test detecting gates in empty project returns empty list."""
        checker = QualityGateChecker(tmp_path)
        detected = checker.detect_project_gates()
        assert detected == []


class TestQualityGateConfig:
    """Tests for QualityGateConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = QualityGateConfig()

        assert config.gates == []
        assert config.run_on_task_complete is True
        assert config.run_on_commit is False
        assert config.fail_task_on_failure is True
        assert config.auto_detect is True

    def test_config_with_gates(self) -> None:
        """Test configuration with gates."""
        gate = AcceptanceCriteria(name="test", gate_type=GateType.TEST)
        config = QualityGateConfig(gates=[gate])

        assert len(config.gates) == 1
        assert config.gates[0].name == "test"

    def test_to_dict(self) -> None:
        """Test converting config to dictionary."""
        gate = AcceptanceCriteria(name="test", gate_type=GateType.TEST)
        config = QualityGateConfig(
            gates=[gate],
            run_on_commit=True,
        )

        result = config.to_dict()

        assert len(result["gates"]) == 1
        assert result["run_on_commit"] is True
        assert result["auto_detect"] is True

    def test_from_dict(self) -> None:
        """Test creating config from dictionary."""
        data = {
            "gates": [{"name": "lint", "gate_type": "lint"}],
            "run_on_task_complete": False,
            "auto_detect": False,
        }

        config = QualityGateConfig.from_dict(data)

        assert len(config.gates) == 1
        assert config.gates[0].name == "lint"
        assert config.run_on_task_complete is False
        assert config.auto_detect is False


class TestQualityGateManager:
    """Tests for QualityGateManager class."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> QualityGateManager:
        """Create a manager with temp working directory."""
        config = QualityGateConfig(auto_detect=False)
        return QualityGateManager(config, tmp_path)

    def test_get_effective_gates_no_auto_detect(self, manager: QualityGateManager) -> None:
        """Test getting effective gates without auto-detect."""
        gate = AcceptanceCriteria(name="test", gate_type=GateType.TEST)
        manager.add_gate(gate)

        effective = manager.get_effective_gates()

        assert len(effective) == 1
        assert effective[0].name == "test"

    def test_add_gate(self, manager: QualityGateManager) -> None:
        """Test adding a gate."""
        gate = AcceptanceCriteria(name="new-gate", gate_type=GateType.LINT)
        manager.add_gate(gate)

        assert len(manager.config.gates) == 1
        assert manager.config.gates[0].name == "new-gate"

    def test_add_gate_replaces_existing(self, manager: QualityGateManager) -> None:
        """Test that adding a gate with same name replaces existing."""
        gate1 = AcceptanceCriteria(name="test", gate_type=GateType.TEST, timeout=100)
        gate2 = AcceptanceCriteria(name="test", gate_type=GateType.TEST, timeout=200)

        manager.add_gate(gate1)
        manager.add_gate(gate2)

        assert len(manager.config.gates) == 1
        assert manager.config.gates[0].timeout == 200

    def test_remove_gate(self, manager: QualityGateManager) -> None:
        """Test removing a gate."""
        gate = AcceptanceCriteria(name="to-remove", gate_type=GateType.TEST)
        manager.add_gate(gate)

        result = manager.remove_gate("to-remove")

        assert result is True
        assert len(manager.config.gates) == 0

    def test_remove_nonexistent_gate(self, manager: QualityGateManager) -> None:
        """Test removing a gate that doesn't exist."""
        result = manager.remove_gate("nonexistent")
        assert result is False

    def test_enable_gate(self, manager: QualityGateManager) -> None:
        """Test enabling/disabling a gate."""
        gate = AcceptanceCriteria(name="toggle", gate_type=GateType.TEST, enabled=True)
        manager.add_gate(gate)

        result = manager.enable_gate("toggle", enabled=False)

        assert result is True
        assert manager.config.gates[0].enabled is False

    def test_enable_nonexistent_gate(self, manager: QualityGateManager) -> None:
        """Test enabling a gate that doesn't exist."""
        result = manager.enable_gate("nonexistent", enabled=True)
        assert result is False

    @patch.object(QualityGateChecker, "check_all")
    def test_run_gates(
        self, mock_check_all: MagicMock, manager: QualityGateManager
    ) -> None:
        """Test running all gates."""
        gate = AcceptanceCriteria(name="test", gate_type=GateType.TEST)
        manager.add_gate(gate)

        mock_result = GateCheckResult(
            gate=gate,
            result=GateResult.PASSED,
            duration_seconds=1.0,
        )
        mock_check_all.return_value = [mock_result]

        passed, results = manager.run_gates()

        assert passed is True
        assert len(results) == 1
        assert results[0].result == GateResult.PASSED

    @patch.object(QualityGateChecker, "check_all")
    def test_run_gates_with_failure(
        self, mock_check_all: MagicMock, manager: QualityGateManager
    ) -> None:
        """Test running gates with a blocking failure."""
        gate = AcceptanceCriteria(name="test", gate_type=GateType.TEST, blocking=True)
        manager.add_gate(gate)

        mock_result = GateCheckResult(
            gate=gate,
            result=GateResult.FAILED,
            duration_seconds=1.0,
        )
        mock_check_all.return_value = [mock_result]

        passed, results = manager.run_gates()

        assert passed is False
        assert len(results) == 1

    def test_get_summary_empty(self, manager: QualityGateManager) -> None:
        """Test getting summary with no results."""
        summary = manager.get_summary([])

        assert summary["total"] == 0
        assert summary["passed"] == 0
        assert summary["failed"] == 0
        assert summary["all_passed"] is True

    def test_get_summary_with_results(self, manager: QualityGateManager) -> None:
        """Test getting summary with results."""
        gate1 = AcceptanceCriteria(name="test1", gate_type=GateType.TEST)
        gate2 = AcceptanceCriteria(name="test2", gate_type=GateType.LINT)
        gate3 = AcceptanceCriteria(name="test3", gate_type=GateType.TYPECHECK)

        results = [
            GateCheckResult(gate=gate1, result=GateResult.PASSED, duration_seconds=1.0),
            GateCheckResult(gate=gate2, result=GateResult.FAILED, duration_seconds=0.5),
            GateCheckResult(gate=gate3, result=GateResult.SKIPPED, duration_seconds=0.0),
        ]

        summary = manager.get_summary(results)

        assert summary["total"] == 3
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["skipped"] == 1
        assert summary["errors"] == 0
        assert summary["total_duration_seconds"] == 1.5
        assert summary["all_passed"] is False

    def test_results_history(self, manager: QualityGateManager) -> None:
        """Test that results are stored in history."""
        with patch.object(QualityGateChecker, "check_all") as mock_check:
            gate = AcceptanceCriteria(name="test", gate_type=GateType.TEST)
            manager.add_gate(gate)
            mock_check.return_value = [
                GateCheckResult(gate=gate, result=GateResult.PASSED, duration_seconds=1.0)
            ]

            manager.run_gates()
            manager.run_gates()

            assert len(manager.results_history) == 2


class TestQualityGateManagerWithRetry:
    """Tests for QualityGateManager retry functionality."""

    @pytest.fixture
    def manager_with_retry(self, tmp_path: Path) -> QualityGateManager:
        """Create manager with retry-enabled gate."""
        config = QualityGateConfig(auto_detect=False)
        manager = QualityGateManager(config, tmp_path)
        gate = AcceptanceCriteria(
            name="flaky-test",
            gate_type=GateType.TEST,
            command="pytest",
            retry_on_fail=True,
            max_retries=2,
        )
        manager.add_gate(gate)
        return manager

    @patch.object(QualityGateChecker, "check_all")
    def test_run_gates_with_retry_succeeds(
        self, mock_check_all: MagicMock, manager_with_retry: QualityGateManager
    ) -> None:
        """Test that retry eventually succeeds."""
        gate = manager_with_retry.config.gates[0]
        fail_result = GateCheckResult(gate=gate, result=GateResult.FAILED, duration_seconds=1.0)
        pass_result = GateCheckResult(gate=gate, result=GateResult.PASSED, duration_seconds=1.0)

        mock_check_all.side_effect = [[fail_result], [pass_result]]

        retry_called = []

        def retry_callback() -> bool:
            retry_called.append(True)
            return True

        passed, results = manager_with_retry.run_gates_with_retry(
            retry_callback=retry_callback
        )

        assert passed is True
        assert len(retry_called) == 1

    @patch.object(QualityGateChecker, "check_all")
    def test_run_gates_with_retry_max_reached(
        self, mock_check_all: MagicMock, manager_with_retry: QualityGateManager
    ) -> None:
        """Test that retry stops after max retries."""
        gate = manager_with_retry.config.gates[0]
        fail_result = GateCheckResult(gate=gate, result=GateResult.FAILED, duration_seconds=1.0)

        # Always fail
        mock_check_all.return_value = [fail_result]

        retry_count = []

        def retry_callback() -> bool:
            retry_count.append(True)
            return True

        passed, results = manager_with_retry.run_gates_with_retry(
            retry_callback=retry_callback
        )

        assert passed is False
        assert len(retry_count) == 2  # max_retries is 2
