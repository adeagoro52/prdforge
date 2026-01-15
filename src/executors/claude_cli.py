"""Claude CLI executor implementation.

This module provides an executor that uses the Claude CLI tool
to execute PRD tasks.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.engine.logging import logger

from .base import (
    BaseExecutor,
    ExecutionResult,
    ExecutorConfig,
    ExecutorStatus,
    TaskContext,
)


@dataclass
class ClaudeCLIConfig(ExecutorConfig):
    """Configuration specific to Claude CLI executor.

    Attributes:
        claude_path: Path to claude CLI executable (auto-detected if None).
        allowed_tools: List of allowed tools for Claude to use.
        model: Claude model to use (e.g., 'claude-sonnet-4-20250514').
        max_turns: Maximum conversation turns.
        print_output: Whether to print output in real-time.
        working_directory: Working directory for execution.
    """

    claude_path: str | None = None
    allowed_tools: list[str] = field(default_factory=lambda: [
        "Read", "Write", "Edit", "Bash", "Glob", "Grep"
    ])
    max_turns: int = 50
    print_output: bool = False
    working_directory: str | None = None


class OutputParser:
    """Parser for Claude CLI output.

    Extracts structured information from Claude's output including
    success/failure status, files changed, and error messages.
    """

    # Patterns for detecting various outcomes
    SUCCESS_PATTERNS = [
        r"(?i)task\s+completed",
        r"(?i)successfully\s+(implemented|completed|created|updated)",
        r"(?i)changes?\s+(?:have\s+been\s+)?(?:made|applied|committed)",
        r"(?i)done\s+with\s+(?:the\s+)?task",
        r"(?i)implementation\s+(?:is\s+)?complete",
    ]

    FAILURE_PATTERNS = [
        r"(?i)error:\s*(.+)",
        r"(?i)failed\s+to\s+(.+)",
        r"(?i)could\s+not\s+(.+)",
        r"(?i)unable\s+to\s+(.+)",
        r"(?i)permission\s+denied",
        r"(?i)syntax\s+error",
        r"(?i)compilation\s+error",
    ]

    FILE_CHANGE_PATTERNS = [
        r"(?:created|wrote|updated|modified|edited)\s+(?:file\s+)?[`'\"]?([^\s`'\"]+)[`'\"]?",
        r"[`'\"]([^\s`'\"]+)[`'\"]\s+(?:has\s+been\s+)?(?:created|updated|modified)",
    ]

    @classmethod
    def parse(cls, output: str) -> dict[str, Any]:
        """Parse Claude CLI output.

        Args:
            output: Raw output from Claude CLI.

        Returns:
            Dict with parsed information:
            - success: bool
            - error: str | None
            - files_changed: list[str]
            - summary: str
        """
        result: dict[str, Any] = {
            "success": False,
            "error": None,
            "files_changed": [],
            "summary": "",
        }

        if not output:
            result["error"] = "Empty output from executor"
            return result

        # Check for success patterns
        for pattern in cls.SUCCESS_PATTERNS:
            if re.search(pattern, output):
                result["success"] = True
                break

        # Check for failure patterns
        for pattern in cls.FAILURE_PATTERNS:
            match = re.search(pattern, output)
            if match:
                result["success"] = False
                result["error"] = match.group(0)
                break

        # Extract changed files
        files_changed = set()
        for pattern in cls.FILE_CHANGE_PATTERNS:
            for match in re.finditer(pattern, output, re.IGNORECASE):
                filepath = match.group(1)
                # Filter out obvious non-files
                if not filepath.startswith(("http", "//", "#")):
                    files_changed.add(filepath)
        result["files_changed"] = list(files_changed)

        # Generate summary (last meaningful paragraph or truncated output)
        lines = output.strip().split("\n")
        summary_lines = [l for l in lines[-5:] if l.strip()]
        result["summary"] = "\n".join(summary_lines)

        # If no explicit success/failure detected, check for common indicators
        if not result["success"] and not result["error"]:
            # Check if output suggests completion
            output_lower = output.lower()
            if any(word in output_lower for word in ["complete", "done", "finished", "success"]):
                result["success"] = True
            elif any(word in output_lower for word in ["error", "fail", "cannot", "unable"]):
                result["success"] = False
                result["error"] = "Task execution appears to have failed"
            else:
                # Assume success if we got output without errors
                result["success"] = True

        return result


class ClaudeCLIExecutor(BaseExecutor):
    """Executor that uses the Claude CLI tool.

    This executor shells out to the `claude` command-line tool to
    execute PRD tasks. It handles:
    - CLI invocation with appropriate flags
    - Output capture and parsing
    - Error detection and retry logic
    """

    def __init__(self, config: ClaudeCLIConfig | None = None) -> None:
        """Initialize the Claude CLI executor.

        Args:
            config: Claude CLI specific configuration.
        """
        super().__init__(config or ClaudeCLIConfig())
        self._claude_path: str | None = None
        self._version_cache: str | None = None

    @property
    def config(self) -> ClaudeCLIConfig:
        """Return typed config."""
        return self._config  # type: ignore

    @config.setter
    def config(self, value: ExecutorConfig) -> None:
        """Set config."""
        self._config = value

    @property
    def name(self) -> str:
        return "claude-cli"

    @property
    def version(self) -> str:
        if self._version_cache:
            return self._version_cache

        try:
            claude_path = self._get_claude_path()
            result = subprocess.run(
                [claude_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                self._version_cache = result.stdout.strip()
                return self._version_cache
        except Exception:
            pass

        return "unknown"

    def _get_claude_path(self) -> str:
        """Get path to claude CLI executable.

        Returns:
            Path to claude executable.

        Raises:
            RuntimeError: If claude is not found.
        """
        if self._claude_path:
            return self._claude_path

        # Check config first
        if self.config.claude_path:
            if Path(self.config.claude_path).exists():
                self._claude_path = self.config.claude_path
                return self._claude_path

        # Try to find in PATH
        claude_path = shutil.which("claude")
        if claude_path:
            self._claude_path = claude_path
            return self._claude_path

        # Common installation locations
        common_paths = [
            Path.home() / ".claude" / "bin" / "claude",
            Path("/usr/local/bin/claude"),
            Path("/opt/homebrew/bin/claude"),
        ]

        for path in common_paths:
            if path.exists():
                self._claude_path = str(path)
                return self._claude_path

        raise RuntimeError(
            "Claude CLI not found. Please install it or set claude_path in config."
        )

    def _execute_impl(self, context: TaskContext) -> ExecutionResult:
        """Execute task using Claude CLI.

        Args:
            context: Task execution context.

        Returns:
            ExecutionResult with execution outcome.
        """
        import time
        start = time.time()

        try:
            claude_path = self._get_claude_path()
        except RuntimeError as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
            )

        # Build the prompt
        prompt = self.build_prompt(context)

        # Build command
        cmd = [claude_path]

        # Add print flag for real-time output
        if self.config.print_output:
            cmd.append("--print")

        # Add allowed tools
        if self.config.allowed_tools:
            for tool in self.config.allowed_tools:
                cmd.extend(["--allowedTools", tool])

        # Add max turns
        cmd.extend(["--max-turns", str(self.config.max_turns)])

        # Add prompt
        cmd.extend(["--prompt", prompt])

        # Set working directory
        cwd = self.config.working_directory or context.project_path

        logger.debug(f"Executing Claude CLI: {' '.join(cmd[:5])}...")

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "prdforge"},
            )

            duration = time.time() - start
            output = result.stdout + result.stderr

            # Parse the output
            parsed = OutputParser.parse(output)

            return ExecutionResult(
                success=parsed["success"],
                output=output,
                error=parsed.get("error"),
                duration_seconds=duration,
                metadata={
                    "files_changed": parsed.get("files_changed", []),
                    "summary": parsed.get("summary", ""),
                    "return_code": result.returncode,
                },
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution timed out after {self.config.timeout}s",
                duration_seconds=time.time() - start,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution failed: {e}",
                duration_seconds=time.time() - start,
            )

    def build_prompt(self, context: TaskContext) -> str:
        """Build Claude-optimized prompt for task execution.

        Args:
            context: Task execution context.

        Returns:
            Formatted prompt string.
        """
        steps_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(context.steps))

        # Include extra context if provided
        extra_context = ""
        if context.extra_context:
            extra_parts = []
            for key, value in context.extra_context.items():
                extra_parts.append(f"{key}: {value}")
            extra_context = "\n\nAdditional Context:\n" + "\n".join(extra_parts)

        return f"""You are executing a task from a PRD (Product Requirements Document).

Task ID: {context.task_id}
Phase: {context.phase}
Category: {context.category}

Description:
{context.description}

Steps to complete:
{steps_text}
{extra_context}

Instructions:
1. Read and understand the existing codebase structure
2. Implement all the steps listed above
3. Follow the project's existing code style and conventions
4. Write clean, maintainable code
5. Add appropriate error handling
6. When done, confirm that all steps are complete

Begin implementing the task now.
"""

    def health_check(self) -> bool:
        """Check if Claude CLI is available and working.

        Returns:
            True if Claude CLI is available.
        """
        try:
            claude_path = self._get_claude_path()
            result = subprocess.run(
                [claude_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            self._status = ExecutorStatus.UNAVAILABLE
            return False
