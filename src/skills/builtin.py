"""Built-in skills for PRDForge.

This module provides standard skills that come with PRDForge:
- CodeReviewSkill: Review code for issues and improvements
- CodeSimplifySkill: Simplify and refactor code
- LintSkill: Run linting tools
- TestSkill: Run test suites
- TypeCheckSkill: Run type checking
"""

import subprocess
import time
from pathlib import Path
from typing import Optional

from .base import (
    Skill,
    SkillConfig,
    SkillContext,
    SkillResult,
    SkillSource,
    SkillStatus,
)


class CommandSkill(Skill):
    """Base class for skills that run shell commands."""

    # Command template with {project_path} placeholder
    command_template: str = ""

    def _run_command(
        self,
        command: str,
        context: SkillContext,
        timeout: Optional[int] = None,
    ) -> SkillResult:
        """Run a shell command and capture output.

        Args:
            command: Command to execute.
            context: Execution context.
            timeout: Optional timeout override.

        Returns:
            SkillResult with command output.
        """
        start_time = time.time()
        timeout = timeout or self.config.timeout

        # Build environment
        env = {**context.env, **self.config.env}

        try:
            if context.dry_run:
                return SkillResult(
                    status=SkillStatus.SKIPPED,
                    output=f"[DRY RUN] Would execute: {command}",
                    duration=0.0,
                )

            result = subprocess.run(
                command,
                shell=True,
                cwd=str(context.working_dir or context.project_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**subprocess.os.environ, **env} if env else None,
            )

            duration = time.time() - start_time
            output = result.stdout + result.stderr

            if result.returncode == 0:
                return SkillResult(
                    status=SkillStatus.SUCCESS,
                    output=output,
                    duration=duration,
                    metadata={"return_code": result.returncode},
                )
            else:
                return SkillResult(
                    status=SkillStatus.FAILED,
                    output=output,
                    error=f"Command exited with code {result.returncode}",
                    duration=duration,
                    metadata={"return_code": result.returncode},
                )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return SkillResult(
                status=SkillStatus.FAILED,
                error=f"Command timed out after {timeout} seconds",
                duration=duration,
            )
        except Exception as e:
            duration = time.time() - start_time
            return SkillResult(
                status=SkillStatus.FAILED,
                error=str(e),
                duration=duration,
            )


class LintSkill(CommandSkill):
    """Run linting tools on the codebase."""

    name = "lint"
    description = "Run linting tools (ruff, eslint, etc.)"
    category = "quality"

    # Supported linters with auto-detection
    linters = {
        "python": ["ruff check .", "flake8 .", "pylint ."],
        "javascript": ["eslint .", "npm run lint"],
        "typescript": ["eslint . --ext .ts,.tsx", "npm run lint"],
    }

    def execute(self, context: SkillContext) -> SkillResult:
        """Execute linting.

        Args:
            context: Execution context.

        Returns:
            SkillResult with lint output.
        """
        # Get configured linter or auto-detect
        linter_cmd = self.config.options.get("command")

        if not linter_cmd:
            # Try to auto-detect based on project files
            project_path = context.project_path
            if (project_path / "pyproject.toml").exists() or (
                project_path / "setup.py"
            ).exists():
                linter_cmd = "ruff check . || flake8 . 2>/dev/null || true"
            elif (project_path / "package.json").exists():
                linter_cmd = "npm run lint 2>/dev/null || npx eslint . 2>/dev/null || true"
            else:
                return SkillResult(
                    status=SkillStatus.SKIPPED,
                    output="No linter configured and could not auto-detect",
                )

        return self._run_command(linter_cmd, context)


class RunTestsSkill(CommandSkill):
    """Run test suites."""

    name = "test"
    description = "Run test suites (pytest, jest, etc.)"
    category = "quality"

    def execute(self, context: SkillContext) -> SkillResult:
        """Execute tests.

        Args:
            context: Execution context.

        Returns:
            SkillResult with test output.
        """
        test_cmd = self.config.options.get("command")

        if not test_cmd:
            # Auto-detect test framework
            project_path = context.project_path
            if (project_path / "pyproject.toml").exists() or (
                project_path / "pytest.ini"
            ).exists():
                test_cmd = "pytest -v"
            elif (project_path / "package.json").exists():
                test_cmd = "npm test"
            elif (project_path / "Makefile").exists():
                test_cmd = "make test"
            else:
                return SkillResult(
                    status=SkillStatus.SKIPPED,
                    output="No test framework configured and could not auto-detect",
                )

        return self._run_command(test_cmd, context)


class TypeCheckSkill(CommandSkill):
    """Run type checking tools."""

    name = "typecheck"
    description = "Run type checking (mypy, tsc, etc.)"
    category = "quality"

    def execute(self, context: SkillContext) -> SkillResult:
        """Execute type checking.

        Args:
            context: Execution context.

        Returns:
            SkillResult with typecheck output.
        """
        typecheck_cmd = self.config.options.get("command")

        if not typecheck_cmd:
            # Auto-detect type checker
            project_path = context.project_path
            if (project_path / "pyproject.toml").exists():
                typecheck_cmd = "mypy . 2>/dev/null || pyright . 2>/dev/null || true"
            elif (project_path / "tsconfig.json").exists():
                typecheck_cmd = "tsc --noEmit"
            else:
                return SkillResult(
                    status=SkillStatus.SKIPPED,
                    output="No type checker configured and could not auto-detect",
                )

        return self._run_command(typecheck_cmd, context)


class CodeReviewSkill(Skill):
    """Review code for issues and improvements.

    This skill wraps the Claude CLI's code review capabilities
    to provide automated code review feedback.
    """

    name = "code-review"
    description = "Review code for issues, bugs, and improvements"
    category = "ai"

    def execute(self, context: SkillContext) -> SkillResult:
        """Execute code review.

        Args:
            context: Execution context.

        Returns:
            SkillResult with review feedback.
        """
        start_time = time.time()

        if context.dry_run:
            return SkillResult(
                status=SkillStatus.SKIPPED,
                output="[DRY RUN] Would run code review",
            )

        # Determine files to review
        files = context.files or []
        if not files:
            # Review recently modified files
            files_str = self.config.options.get("files", "")
            if files_str:
                files = [Path(f.strip()) for f in files_str.split(",")]

        if not files:
            return SkillResult(
                status=SkillStatus.SKIPPED,
                output="No files specified for review",
            )

        # Build review command using Claude CLI
        files_arg = " ".join(str(f) for f in files)
        review_cmd = f"claude -p 'Review the following files for bugs, security issues, and code quality: {files_arg}' --no-stream"

        try:
            result = subprocess.run(
                review_cmd,
                shell=True,
                cwd=str(context.working_dir or context.project_path),
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )

            duration = time.time() - start_time
            output = result.stdout + result.stderr

            return SkillResult(
                status=SkillStatus.SUCCESS if result.returncode == 0 else SkillStatus.FAILED,
                output=output,
                error=None if result.returncode == 0 else f"Review failed with code {result.returncode}",
                duration=duration,
            )

        except subprocess.TimeoutExpired:
            return SkillResult(
                status=SkillStatus.FAILED,
                error=f"Code review timed out after {self.config.timeout} seconds",
                duration=time.time() - start_time,
            )
        except FileNotFoundError:
            return SkillResult(
                status=SkillStatus.FAILED,
                error="Claude CLI not found. Install with: pip install claude-cli",
                duration=time.time() - start_time,
            )
        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time,
            )


class CodeSimplifySkill(Skill):
    """Simplify and refactor code.

    This skill wraps the code-simplifier agent to automatically
    improve code readability and maintainability.
    """

    name = "code-simplify"
    description = "Simplify and refactor code for clarity"
    category = "ai"

    def execute(self, context: SkillContext) -> SkillResult:
        """Execute code simplification.

        Args:
            context: Execution context.

        Returns:
            SkillResult with simplification feedback.
        """
        start_time = time.time()

        if context.dry_run:
            return SkillResult(
                status=SkillStatus.SKIPPED,
                output="[DRY RUN] Would run code simplification",
            )

        # Determine files to simplify
        files = context.files or []
        files_arg = ""
        if files:
            files_arg = " ".join(str(f) for f in files)
        else:
            # Default to recently modified files
            files_arg = self.config.options.get("files", "")

        # Build simplify prompt
        prompt = self.config.options.get(
            "prompt",
            "Simplify and refine the code for clarity, consistency, and maintainability while preserving all functionality.",
        )

        if files_arg:
            prompt = f"{prompt} Focus on: {files_arg}"

        simplify_cmd = f"claude -p '{prompt}' --no-stream"

        try:
            result = subprocess.run(
                simplify_cmd,
                shell=True,
                cwd=str(context.working_dir or context.project_path),
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )

            duration = time.time() - start_time
            output = result.stdout + result.stderr

            return SkillResult(
                status=SkillStatus.SUCCESS if result.returncode == 0 else SkillStatus.FAILED,
                output=output,
                error=None if result.returncode == 0 else f"Simplification failed with code {result.returncode}",
                duration=duration,
            )

        except subprocess.TimeoutExpired:
            return SkillResult(
                status=SkillStatus.FAILED,
                error=f"Code simplification timed out after {self.config.timeout} seconds",
                duration=time.time() - start_time,
            )
        except FileNotFoundError:
            return SkillResult(
                status=SkillStatus.FAILED,
                error="Claude CLI not found. Install with: pip install claude-cli",
                duration=time.time() - start_time,
            )
        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time,
            )


# Registry of all built-in skills
BUILTIN_SKILLS: dict[str, type[Skill]] = {
    "lint": LintSkill,
    "test": RunTestsSkill,
    "typecheck": TypeCheckSkill,
    "code-review": CodeReviewSkill,
    "code-simplify": CodeSimplifySkill,
}
