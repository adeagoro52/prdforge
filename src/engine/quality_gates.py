"""Quality gates (acceptance criteria) for PRDForge.

This module provides a system for defining and checking acceptance criteria
after task completion to ensure code quality.
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from src.engine.logging import logger


class GateType(Enum):
    """Type of quality gate."""

    TEST = "test"  # Run tests
    LINT = "lint"  # Run linter
    TYPECHECK = "typecheck"  # Run type checker
    CUSTOM = "custom"  # Custom command


class GateResult(Enum):
    """Result of a quality gate check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class AcceptanceCriteria:
    """Definition of an acceptance criterion (quality gate).

    Attributes:
        name: Unique name for the gate.
        gate_type: Type of gate.
        command: Command to execute (for custom gates).
        enabled: Whether the gate is enabled.
        blocking: Whether failure should block the task.
        retry_on_fail: Whether to retry the task on failure.
        max_retries: Maximum retry attempts.
        timeout: Timeout in seconds.
        working_dir: Working directory for command execution.
        env: Environment variables.
        args: Additional arguments.
    """

    name: str
    gate_type: GateType
    command: str | None = None
    enabled: bool = True
    blocking: bool = True
    retry_on_fail: bool = False
    max_retries: int = 1
    timeout: int = 300
    working_dir: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "gate_type": self.gate_type.value,
            "command": self.command,
            "enabled": self.enabled,
            "blocking": self.blocking,
            "retry_on_fail": self.retry_on_fail,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
            "working_dir": self.working_dir,
            "env": self.env,
            "args": self.args,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AcceptanceCriteria":
        """Create from dictionary."""
        gate_type = data.get("gate_type", "custom")
        if isinstance(gate_type, str):
            gate_type = GateType(gate_type)

        return cls(
            name=data["name"],
            gate_type=gate_type,
            command=data.get("command"),
            enabled=data.get("enabled", True),
            blocking=data.get("blocking", True),
            retry_on_fail=data.get("retry_on_fail", False),
            max_retries=data.get("max_retries", 1),
            timeout=data.get("timeout", 300),
            working_dir=data.get("working_dir"),
            env=data.get("env", {}),
            args=data.get("args", []),
        )


@dataclass
class GateCheckResult:
    """Result of checking a quality gate.

    Attributes:
        gate: The acceptance criteria checked.
        result: Result of the check.
        output: Command output.
        error: Error message if any.
        duration_seconds: Execution duration.
        timestamp: When the check was performed.
        exit_code: Command exit code.
    """

    gate: AcceptanceCriteria
    result: GateResult
    output: str = ""
    error: str | None = None
    duration_seconds: float = 0.0
    timestamp: datetime | None = None
    exit_code: int | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "gate_name": self.gate.name,
            "gate_type": self.gate.gate_type.value,
            "result": self.result.value,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "exit_code": self.exit_code,
        }


# Built-in gate configurations
BUILTIN_GATES: dict[str, dict] = {
    "pytest": {
        "name": "pytest",
        "gate_type": "test",
        "command": "pytest",
        "args": ["-v", "--tb=short"],
        "blocking": True,
    },
    "npm-test": {
        "name": "npm-test",
        "gate_type": "test",
        "command": "npm",
        "args": ["test"],
        "blocking": True,
    },
    "ruff": {
        "name": "ruff",
        "gate_type": "lint",
        "command": "ruff",
        "args": ["check", "."],
        "blocking": True,
    },
    "eslint": {
        "name": "eslint",
        "gate_type": "lint",
        "command": "npx",
        "args": ["eslint", "."],
        "blocking": True,
    },
    "mypy": {
        "name": "mypy",
        "gate_type": "typecheck",
        "command": "mypy",
        "args": ["."],
        "blocking": True,
    },
    "pyright": {
        "name": "pyright",
        "gate_type": "typecheck",
        "command": "pyright",
        "blocking": True,
    },
    "tsc": {
        "name": "tsc",
        "gate_type": "typecheck",
        "command": "npx",
        "args": ["tsc", "--noEmit"],
        "blocking": True,
    },
}


class QualityGateChecker:
    """Executes quality gate checks.

    Features:
    - Built-in support for test, lint, typecheck gates
    - Custom command support
    - Auto-detection of project tools
    - Result storage and reporting
    """

    def __init__(self, working_dir: Path | str | None = None):
        """Initialize the checker.

        Args:
            working_dir: Default working directory for checks.
        """
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()

    def check(
        self,
        gate: AcceptanceCriteria,
        working_dir: Path | str | None = None,
    ) -> GateCheckResult:
        """Execute a quality gate check.

        Args:
            gate: Acceptance criteria to check.
            working_dir: Override working directory.

        Returns:
            GateCheckResult with check outcome.
        """
        if not gate.enabled:
            return GateCheckResult(
                gate=gate,
                result=GateResult.SKIPPED,
                output="Gate disabled",
                timestamp=datetime.utcnow(),
            )

        work_dir = Path(working_dir or gate.working_dir or self.working_dir)

        logger.info(f"Running quality gate: {gate.name} ({gate.gate_type.value})")

        start_time = datetime.utcnow()
        try:
            cmd = self._build_command(gate)

            result = subprocess.run(
                cmd,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=gate.timeout,
                env={**subprocess.os.environ, **gate.env},
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            gate_result = GateResult.PASSED if result.returncode == 0 else GateResult.FAILED
            output = result.stdout or ""
            error = result.stderr if result.returncode != 0 else None

            logger.info(f"Gate {gate.name}: {gate_result.value} (exit code: {result.returncode})")

            return GateCheckResult(
                gate=gate,
                result=gate_result,
                output=output,
                error=error,
                duration_seconds=duration,
                timestamp=start_time,
                exit_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Gate {gate.name} timed out after {gate.timeout}s")
            return GateCheckResult(
                gate=gate,
                result=GateResult.ERROR,
                error=f"Timeout after {gate.timeout} seconds",
                duration_seconds=duration,
                timestamp=start_time,
            )

        except FileNotFoundError as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Gate {gate.name} failed: command not found - {e}")
            return GateCheckResult(
                gate=gate,
                result=GateResult.ERROR,
                error=f"Command not found: {e}",
                duration_seconds=duration,
                timestamp=start_time,
            )

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Gate {gate.name} error: {e}")
            return GateCheckResult(
                gate=gate,
                result=GateResult.ERROR,
                error=str(e),
                duration_seconds=duration,
                timestamp=start_time,
            )

    def _build_command(self, gate: AcceptanceCriteria) -> list[str]:
        """Build command for a gate.

        Args:
            gate: Acceptance criteria.

        Returns:
            Command list.
        """
        if gate.command:
            cmd = [gate.command] + gate.args
        else:
            # Default commands based on gate type
            if gate.gate_type == GateType.TEST:
                cmd = ["pytest", "-v"]
            elif gate.gate_type == GateType.LINT:
                cmd = ["ruff", "check", "."]
            elif gate.gate_type == GateType.TYPECHECK:
                cmd = ["mypy", "."]
            else:
                raise ValueError(f"No command specified for gate: {gate.name}")

        return cmd

    def check_all(
        self,
        gates: list[AcceptanceCriteria],
        working_dir: Path | str | None = None,
        stop_on_failure: bool = True,
    ) -> list[GateCheckResult]:
        """Execute all quality gates.

        Args:
            gates: List of gates to check.
            working_dir: Working directory.
            stop_on_failure: Stop on first blocking failure.

        Returns:
            List of check results.
        """
        results = []

        for gate in gates:
            result = self.check(gate, working_dir)
            results.append(result)

            if (
                stop_on_failure
                and gate.blocking
                and result.result in [GateResult.FAILED, GateResult.ERROR]
            ):
                logger.warning(f"Stopping gate checks due to blocking failure: {gate.name}")
                break

        return results

    def detect_project_gates(
        self,
        working_dir: Path | str | None = None,
    ) -> list[AcceptanceCriteria]:
        """Auto-detect quality gates based on project structure.

        Args:
            working_dir: Project directory.

        Returns:
            List of detected gates.
        """
        work_dir = Path(working_dir or self.working_dir)
        detected = []

        # Check for Python project
        if (work_dir / "pyproject.toml").exists() or (work_dir / "setup.py").exists():
            # Check for pytest
            if (work_dir / "pytest.ini").exists() or (work_dir / "tests").is_dir():
                detected.append(AcceptanceCriteria.from_dict(BUILTIN_GATES["pytest"]))

            # Check for ruff
            if (work_dir / "ruff.toml").exists() or (work_dir / "pyproject.toml").exists():
                detected.append(AcceptanceCriteria.from_dict(BUILTIN_GATES["ruff"]))

            # Check for mypy
            if (work_dir / "mypy.ini").exists():
                detected.append(AcceptanceCriteria.from_dict(BUILTIN_GATES["mypy"]))

        # Check for Node.js project
        if (work_dir / "package.json").exists():
            package_json = work_dir / "package.json"
            try:
                pkg = json.loads(package_json.read_text())
                scripts = pkg.get("scripts", {})

                if "test" in scripts:
                    detected.append(AcceptanceCriteria.from_dict(BUILTIN_GATES["npm-test"]))

                if "lint" in scripts:
                    detected.append(AcceptanceCriteria(
                        name="npm-lint",
                        gate_type=GateType.LINT,
                        command="npm",
                        args=["run", "lint"],
                    ))

                if "typecheck" in scripts or "type-check" in scripts:
                    detected.append(AcceptanceCriteria(
                        name="npm-typecheck",
                        gate_type=GateType.TYPECHECK,
                        command="npm",
                        args=["run", "typecheck"] if "typecheck" in scripts else ["run", "type-check"],
                    ))
            except (json.JSONDecodeError, IOError):
                pass

            # Check for TypeScript
            if (work_dir / "tsconfig.json").exists():
                detected.append(AcceptanceCriteria.from_dict(BUILTIN_GATES["tsc"]))

        return detected


@dataclass
class QualityGateConfig:
    """Configuration for quality gates on a project/task.

    Attributes:
        gates: List of configured gates.
        run_on_task_complete: Run gates after task completion.
        run_on_commit: Run gates before commits.
        fail_task_on_failure: Fail task if blocking gates fail.
        auto_detect: Auto-detect project gates.
    """

    gates: list[AcceptanceCriteria] = field(default_factory=list)
    run_on_task_complete: bool = True
    run_on_commit: bool = False
    fail_task_on_failure: bool = True
    auto_detect: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "gates": [g.to_dict() for g in self.gates],
            "run_on_task_complete": self.run_on_task_complete,
            "run_on_commit": self.run_on_commit,
            "fail_task_on_failure": self.fail_task_on_failure,
            "auto_detect": self.auto_detect,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QualityGateConfig":
        """Create from dictionary."""
        gates = [AcceptanceCriteria.from_dict(g) for g in data.get("gates", [])]
        return cls(
            gates=gates,
            run_on_task_complete=data.get("run_on_task_complete", True),
            run_on_commit=data.get("run_on_commit", False),
            fail_task_on_failure=data.get("fail_task_on_failure", True),
            auto_detect=data.get("auto_detect", True),
        )


class QualityGateManager:
    """Manages quality gates for a project.

    Features:
    - Gate configuration management
    - Integration with task execution
    - Result storage and reporting
    - Retry handling
    """

    def __init__(
        self,
        config: QualityGateConfig | None = None,
        working_dir: Path | str | None = None,
    ):
        """Initialize the manager.

        Args:
            config: Gate configuration.
            working_dir: Default working directory.
        """
        self.config = config or QualityGateConfig()
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.checker = QualityGateChecker(self.working_dir)
        self.results_history: list[list[GateCheckResult]] = []

    def get_effective_gates(self) -> list[AcceptanceCriteria]:
        """Get the effective list of gates (configured + auto-detected).

        Returns:
            List of gates to check.
        """
        gates = list(self.config.gates)

        if self.config.auto_detect:
            detected = self.checker.detect_project_gates(self.working_dir)
            # Add detected gates that aren't already configured
            existing_names = {g.name for g in gates}
            for gate in detected:
                if gate.name not in existing_names:
                    gates.append(gate)

        return gates

    def run_gates(
        self,
        task_id: str | None = None,
        stop_on_failure: bool = True,
    ) -> tuple[bool, list[GateCheckResult]]:
        """Run all configured quality gates.

        Args:
            task_id: Optional task ID for context.
            stop_on_failure: Stop on first blocking failure.

        Returns:
            Tuple of (all_passed, results).
        """
        gates = self.get_effective_gates()
        enabled_gates = [g for g in gates if g.enabled]

        if not enabled_gates:
            logger.info("No quality gates configured")
            return True, []

        logger.info(f"Running {len(enabled_gates)} quality gates" + (f" for task {task_id}" if task_id else ""))

        results = self.checker.check_all(
            enabled_gates,
            self.working_dir,
            stop_on_failure,
        )

        self.results_history.append(results)

        # Check if any blocking gate failed
        all_passed = all(
            r.result == GateResult.PASSED or r.result == GateResult.SKIPPED or not r.gate.blocking
            for r in results
        )

        return all_passed, results

    def run_gates_with_retry(
        self,
        task_id: str | None = None,
        retry_callback: Callable[[], bool] | None = None,
    ) -> tuple[bool, list[GateCheckResult]]:
        """Run gates with retry support.

        Args:
            task_id: Optional task ID.
            retry_callback: Callback to retry the task (returns True if retry successful).

        Returns:
            Tuple of (final_result, all_results).
        """
        all_results: list[GateCheckResult] = []
        retry_count = 0

        while True:
            passed, results = self.run_gates(task_id, stop_on_failure=True)
            all_results.extend(results)

            if passed:
                return True, all_results

            # Check if any failed gate allows retry
            failed_gates = [r for r in results if r.result == GateResult.FAILED and r.gate.retry_on_fail]

            if not failed_gates:
                return False, all_results

            # Check retry limit
            max_retries = max(g.gate.max_retries for g in failed_gates)
            if retry_count >= max_retries:
                logger.warning(f"Max retries ({max_retries}) reached for quality gates")
                return False, all_results

            # Attempt retry
            if retry_callback:
                logger.info(f"Retrying task due to gate failures (attempt {retry_count + 1})")
                if not retry_callback():
                    logger.error("Retry callback failed")
                    return False, all_results

            retry_count += 1

        return False, all_results

    def get_summary(self, results: list[GateCheckResult] | None = None) -> dict:
        """Get summary of gate results.

        Args:
            results: Results to summarize (defaults to last run).

        Returns:
            Summary dict.
        """
        if results is None:
            results = self.results_history[-1] if self.results_history else []

        passed = sum(1 for r in results if r.result == GateResult.PASSED)
        failed = sum(1 for r in results if r.result == GateResult.FAILED)
        skipped = sum(1 for r in results if r.result == GateResult.SKIPPED)
        errors = sum(1 for r in results if r.result == GateResult.ERROR)
        total_duration = sum(r.duration_seconds for r in results)

        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "total_duration_seconds": total_duration,
            "all_passed": failed == 0 and errors == 0,
            "results": [r.to_dict() for r in results],
        }

    def add_gate(self, gate: AcceptanceCriteria) -> None:
        """Add a gate to the configuration.

        Args:
            gate: Gate to add.
        """
        # Remove existing gate with same name
        self.config.gates = [g for g in self.config.gates if g.name != gate.name]
        self.config.gates.append(gate)

    def remove_gate(self, name: str) -> bool:
        """Remove a gate by name.

        Args:
            name: Gate name to remove.

        Returns:
            True if removed.
        """
        original_len = len(self.config.gates)
        self.config.gates = [g for g in self.config.gates if g.name != name]
        return len(self.config.gates) < original_len

    def enable_gate(self, name: str, enabled: bool = True) -> bool:
        """Enable or disable a gate.

        Args:
            name: Gate name.
            enabled: Whether to enable.

        Returns:
            True if gate found.
        """
        for gate in self.config.gates:
            if gate.name == name:
                gate.enabled = enabled
                return True
        return False
