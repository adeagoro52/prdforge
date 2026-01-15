# Skills Development Guide

Skills are reusable automation tasks that extend PRDForge's capabilities. This guide covers creating, configuring, and deploying custom skills.

## Overview

Skills are Python classes that implement the `Skill` interface. They can:
- Run shell commands
- Process files
- Integrate with external services
- Perform code analysis
- And more

## Skill System Architecture

PRDForge supports a layered skill system:

```
Priority (highest to lowest):
1. Project skills   (.prdforge/skills/)  - Override for specific project
2. User skills      (~/.prdforge/skills/) - User-wide customizations
3. Package skills   (built-in)            - Default implementations
```

When multiple skills have the same name, the higher-priority version is used.

## Creating a Simple Skill

### Basic Structure

```python
# my_skill.py
from src.skills.base import (
    Skill,
    SkillContext,
    SkillResult,
    SkillStatus,
)


class MySkill(Skill):
    """Description of what this skill does."""

    # Required class attributes
    name = "my-skill"
    description = "Does something useful"
    category = "general"  # Options: general, quality, git, build, test

    def execute(self, context: SkillContext) -> SkillResult:
        """Execute the skill.

        Args:
            context: Execution context with project path, etc.

        Returns:
            Result indicating success or failure.
        """
        try:
            # Your implementation here
            result = self._do_work(context)

            return SkillResult(
                status=SkillStatus.SUCCESS,
                output=result,
                duration=0.0,  # Set actual duration
                metadata={"key": "value"},  # Optional metadata
            )
        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                error=str(e),
            )

    def _do_work(self, context: SkillContext) -> str:
        """Actual implementation logic."""
        # Access project path
        project = context.project_path

        # Check if dry run
        if context.dry_run:
            return "Would do work (dry run)"

        return "Work completed"
```

### Command-Based Skills

For skills that run shell commands, extend `CommandSkill`:

```python
from src.skills.builtin import CommandSkill


class MyLinterSkill(CommandSkill):
    """Custom linting skill."""

    name = "my-linter"
    description = "Run custom linting rules"
    category = "quality"

    def execute(self, context: SkillContext) -> SkillResult:
        # CommandSkill provides _run_command helper
        command = f"my-linter --config {context.project_path}/.lintrc"
        return self._run_command(command, context)
```

## Skill Context

The `SkillContext` provides execution context:

```python
@dataclass
class SkillContext:
    project_path: Path       # Project root directory
    working_dir: Path        # Working directory (defaults to project_path)
    task_id: Optional[str]   # Task ID if running in a PRD task
    run_id: Optional[str]    # Run ID if running in a PRD run
    dry_run: bool           # If True, don't make actual changes
    files: list[Path]       # Specific files to operate on
    env: dict[str, str]     # Additional environment variables
```

## Skill Configuration

Skills can be configured via `SkillConfig`:

```python
@dataclass
class SkillConfig:
    enabled: bool = True          # Enable/disable skill
    timeout: int = 300           # Timeout in seconds
    retry_count: int = 0         # Retries on failure
    env: dict[str, str] = {}     # Environment variables
    options: dict[str, Any] = {} # Skill-specific options
```

### Configuring in prdforge.yaml

```yaml
# prdforge.yaml
skills:
  lint:
    enabled: true
    timeout: 60
    options:
      fix: true
      strict: true

  my-skill:
    enabled: true
    env:
      MY_API_KEY: "xxx"
    options:
      custom_option: "value"
```

### Accessing Configuration

```python
class MyConfigurableSkill(Skill):
    name = "configurable-skill"
    description = "Skill with custom options"

    def execute(self, context: SkillContext) -> SkillResult:
        # Access skill-specific options
        custom_value = self.config.options.get("custom_option", "default")

        # Access environment variables
        api_key = self.config.env.get("MY_API_KEY")

        # Check timeout
        timeout = self.config.timeout

        # Implementation using config...
        return SkillResult(status=SkillStatus.SUCCESS)
```

## Skill Results

Return `SkillResult` from `execute()`:

```python
@dataclass
class SkillResult:
    status: SkillStatus      # PENDING, RUNNING, SUCCESS, FAILED, SKIPPED
    output: str = ""         # stdout/logs
    error: Optional[str]     # Error message if failed
    duration: float = 0.0    # Execution time in seconds
    metadata: dict = {}      # Additional data
```

### Status Values

- `SkillStatus.SUCCESS` - Skill completed successfully
- `SkillStatus.FAILED` - Skill failed (check `error` field)
- `SkillStatus.SKIPPED` - Skill was skipped (e.g., dry run)
- `SkillStatus.PENDING` - Skill is queued
- `SkillStatus.RUNNING` - Skill is executing

## Installing Skills

### Project-Level Skills

Place skills in `.prdforge/skills/`:

```
my-project/
├── .prdforge/
│   └── skills/
│       ├── __init__.py
│       └── custom_lint.py
└── src/
```

```python
# .prdforge/skills/custom_lint.py
from src.skills.base import Skill, SkillContext, SkillResult, SkillStatus


class CustomLintSkill(Skill):
    name = "lint"  # Overrides built-in lint skill
    description = "Project-specific linting"

    def execute(self, context: SkillContext) -> SkillResult:
        # Custom implementation
        pass


# Export skills for auto-discovery
SKILLS = [CustomLintSkill]
```

### User-Level Skills

Place skills in `~/.prdforge/skills/`:

```
~/.prdforge/
└── skills/
    ├── __init__.py
    └── my_global_skill.py
```

### Skill Discovery

Skills are automatically discovered when:
1. They're in the correct directory
2. The module exports a `SKILLS` list
3. Or classes extend `Skill` and are in the module namespace

```python
# skills/__init__.py or individual skill file

# Option 1: Export SKILLS list
SKILLS = [MySkill, AnotherSkill]

# Option 2: Skills auto-discovered by class inheritance
class AutoDiscoveredSkill(Skill):
    name = "auto-discovered"
    # ...
```

## Built-in Skills

PRDForge includes these built-in skills:

| Skill | Description |
|-------|-------------|
| `lint` | Run linting (ruff, eslint, etc.) |
| `test` | Run test suites (pytest, jest, etc.) |
| `type-check` | Run type checking (mypy, tsc) |
| `code-review` | AI-powered code review |
| `code-simplify` | Simplify/refactor code |
| `format` | Format code (black, prettier) |
| `security-scan` | Security vulnerability scanning |

### Overriding Built-in Skills

Create a skill with the same name in your project:

```python
# .prdforge/skills/lint_override.py
from src.skills.base import Skill, SkillContext, SkillResult, SkillStatus
import subprocess


class LintSkill(Skill):
    """Override built-in lint with custom rules."""

    name = "lint"  # Same name overrides built-in
    description = "Custom linting for this project"

    def execute(self, context: SkillContext) -> SkillResult:
        # Your custom linting logic
        result = subprocess.run(
            ["custom-linter", "--strict", str(context.project_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return SkillResult(
                status=SkillStatus.SUCCESS,
                output=result.stdout,
            )
        else:
            return SkillResult(
                status=SkillStatus.FAILED,
                output=result.stdout + result.stderr,
                error=f"Linting failed with code {result.returncode}",
            )


SKILLS = [LintSkill]
```

## Advanced Examples

### File Processing Skill

```python
from pathlib import Path
from src.skills.base import Skill, SkillContext, SkillResult, SkillStatus


class HeaderCheckSkill(Skill):
    """Check that all files have required headers."""

    name = "header-check"
    description = "Verify source files have license headers"
    category = "quality"

    HEADER = "# Copyright (c) 2024 My Company"

    def execute(self, context: SkillContext) -> SkillResult:
        missing = []
        checked = 0

        # Use provided files or scan project
        files = context.files or list(
            context.project_path.rglob("*.py")
        )

        for file_path in files:
            if file_path.name.startswith("__"):
                continue

            content = file_path.read_text()
            if not content.startswith(self.HEADER):
                missing.append(str(file_path))
            checked += 1

        if missing:
            return SkillResult(
                status=SkillStatus.FAILED,
                output=f"Checked {checked} files",
                error=f"Missing headers in: {', '.join(missing[:10])}",
                metadata={"missing_count": len(missing)},
            )

        return SkillResult(
            status=SkillStatus.SUCCESS,
            output=f"All {checked} files have headers",
        )
```

### External API Skill

```python
import httpx
from src.skills.base import Skill, SkillContext, SkillResult, SkillStatus


class SlackNotifySkill(Skill):
    """Send notifications to Slack."""

    name = "slack-notify"
    description = "Send run notifications to Slack"
    category = "notification"

    def execute(self, context: SkillContext) -> SkillResult:
        webhook_url = self.config.env.get("SLACK_WEBHOOK_URL")
        if not webhook_url:
            return SkillResult(
                status=SkillStatus.FAILED,
                error="SLACK_WEBHOOK_URL not configured",
            )

        message = self.config.options.get(
            "message",
            f"PRDForge task completed in {context.project_path.name}"
        )

        if context.dry_run:
            return SkillResult(
                status=SkillStatus.SKIPPED,
                output=f"[DRY RUN] Would send: {message}",
            )

        try:
            response = httpx.post(
                webhook_url,
                json={"text": message},
                timeout=10,
            )
            response.raise_for_status()

            return SkillResult(
                status=SkillStatus.SUCCESS,
                output="Notification sent",
            )
        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                error=str(e),
            )
```

## Validation

Implement `validate()` for custom validation:

```python
class ValidatedSkill(Skill):
    name = "validated-skill"
    description = "Skill with custom validation"

    def validate(self) -> list[str]:
        """Validate skill configuration."""
        errors = super().validate()  # Call parent validation

        # Add custom validation
        if "required_option" not in self.config.options:
            errors.append("required_option must be set")

        if self.config.timeout < 30:
            errors.append("timeout must be at least 30 seconds")

        return errors

    def execute(self, context: SkillContext) -> SkillResult:
        # Implementation
        pass
```

## Testing Skills

```python
# tests/test_my_skill.py
import pytest
from pathlib import Path
from src.skills.base import SkillContext, SkillStatus


class TestMySkill:
    @pytest.fixture
    def context(self, tmp_path):
        return SkillContext(project_path=tmp_path)

    def test_execute_success(self, context):
        from my_skills import MySkill

        skill = MySkill()
        result = skill.execute(context)

        assert result.status == SkillStatus.SUCCESS
        assert "expected output" in result.output

    def test_dry_run(self, context):
        from my_skills import MySkill

        context.dry_run = True
        skill = MySkill()
        result = skill.execute(context)

        assert result.status == SkillStatus.SKIPPED
```

## Best Practices

1. **Handle errors gracefully** - Return `SkillStatus.FAILED` with descriptive error messages
2. **Support dry run** - Check `context.dry_run` and don't make changes if True
3. **Set appropriate timeouts** - Use reasonable default timeouts
4. **Log progress** - Include helpful output for debugging
5. **Validate configuration** - Implement `validate()` for required options
6. **Test thoroughly** - Unit test your skills with various scenarios
7. **Document clearly** - Use docstrings and good naming
