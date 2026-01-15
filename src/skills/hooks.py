"""Post-task hooks system for PRDForge.

Hooks allow automation after task completion:
- Run skills (lint, test, typecheck, etc.)
- Execute custom commands
- Configure continue/halt behavior on failure
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .base import SkillContext, SkillResult, SkillStatus
from .registry import SkillRegistry, get_default_registry


class HookType(Enum):
    """Type of hook to execute."""

    SKILL = "skill"  # Execute a skill from the registry
    COMMAND = "command"  # Execute a shell command


class HookBehavior(Enum):
    """Behavior on hook failure."""

    CONTINUE = "continue"  # Continue execution despite failure
    HALT = "halt"  # Stop execution on failure
    WARN = "warn"  # Log warning but continue


@dataclass
class Hook:
    """Configuration for a post-task hook.

    Attributes:
        name: Name of the hook (for logging/identification).
        hook_type: Type of hook (skill or command).
        target: Skill name or command to execute.
        on_failure: Behavior when hook fails.
        enabled: Whether the hook is enabled.
        config: Additional configuration options.
    """

    name: str
    hook_type: HookType
    target: str
    on_failure: HookBehavior = HookBehavior.WARN
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hook":
        """Create hook from dictionary.

        Args:
            data: Hook configuration dictionary.

        Returns:
            Hook instance.
        """
        return cls(
            name=data.get("name", "unnamed-hook"),
            hook_type=HookType(data.get("type", "skill")),
            target=data.get("target", ""),
            on_failure=HookBehavior(data.get("on_failure", "warn")),
            enabled=data.get("enabled", True),
            config=data.get("config", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert hook to dictionary.

        Returns:
            Hook as dictionary.
        """
        return {
            "name": self.name,
            "type": self.hook_type.value,
            "target": self.target,
            "on_failure": self.on_failure.value,
            "enabled": self.enabled,
            "config": self.config,
        }


@dataclass
class HookResult:
    """Result of hook execution.

    Attributes:
        hook: The hook that was executed.
        status: Execution status.
        skill_result: Result from skill execution (if applicable).
        output: Output/logs from execution.
        error: Error message if failed.
    """

    hook: Hook
    status: SkillStatus
    skill_result: Optional[SkillResult] = None
    output: str = ""
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if hook execution succeeded."""
        return self.status == SkillStatus.SUCCESS

    @property
    def should_halt(self) -> bool:
        """Check if execution should halt based on failure behavior."""
        return (
            self.status == SkillStatus.FAILED
            and self.hook.on_failure == HookBehavior.HALT
        )


class HookError(Exception):
    """Error during hook execution."""

    def __init__(self, message: str, hook_name: str = "", results: list[HookResult] = None):
        """Initialize hook error.

        Args:
            message: Error message.
            hook_name: Name of the hook that failed.
            results: Results from hook executions.
        """
        super().__init__(message)
        self.hook_name = hook_name
        self.results = results or []


# Built-in hook presets
BUILTIN_HOOKS = {
    "test": Hook(
        name="test",
        hook_type=HookType.SKILL,
        target="test",
        on_failure=HookBehavior.HALT,
    ),
    "lint": Hook(
        name="lint",
        hook_type=HookType.SKILL,
        target="lint",
        on_failure=HookBehavior.WARN,
    ),
    "typecheck": Hook(
        name="typecheck",
        hook_type=HookType.SKILL,
        target="typecheck",
        on_failure=HookBehavior.WARN,
    ),
    "simplify": Hook(
        name="simplify",
        hook_type=HookType.SKILL,
        target="code-simplify",
        on_failure=HookBehavior.CONTINUE,
    ),
    "review": Hook(
        name="review",
        hook_type=HookType.SKILL,
        target="code-review",
        on_failure=HookBehavior.CONTINUE,
    ),
}


class HookRunner:
    """Executes hooks after task completion.

    Example usage::

        runner = HookRunner()
        runner.add_hook(Hook(name="lint", hook_type=HookType.SKILL, target="lint"))

        # After task completion
        results = runner.run_hooks(context)
        for result in results:
            print(f"{result.hook.name}: {result.status.value}")
    """

    def __init__(self, registry: Optional[SkillRegistry] = None):
        """Initialize hook runner.

        Args:
            registry: Skill registry for skill-type hooks.
        """
        self._hooks: list[Hook] = []
        self._registry = registry or get_default_registry()

    def add_hook(self, hook: Hook) -> None:
        """Add a hook to the runner.

        Args:
            hook: Hook to add.
        """
        self._hooks.append(hook)

    def add_builtin(self, name: str) -> bool:
        """Add a built-in hook by name.

        Args:
            name: Name of built-in hook (test, lint, typecheck, etc.).

        Returns:
            True if hook was added, False if not found.
        """
        if name in BUILTIN_HOOKS:
            self._hooks.append(BUILTIN_HOOKS[name])
            return True
        return False

    def remove_hook(self, name: str) -> bool:
        """Remove a hook by name.

        Args:
            name: Name of hook to remove.

        Returns:
            True if hook was removed, False if not found.
        """
        for i, hook in enumerate(self._hooks):
            if hook.name == name:
                del self._hooks[i]
                return True
        return False

    def clear_hooks(self) -> None:
        """Remove all hooks."""
        self._hooks.clear()

    def list_hooks(self) -> list[Hook]:
        """List all configured hooks.

        Returns:
            List of hooks.
        """
        return list(self._hooks)

    def run_hooks(
        self,
        context: SkillContext,
        stop_on_halt: bool = True,
    ) -> list[HookResult]:
        """Run all configured hooks.

        Args:
            context: Execution context.
            stop_on_halt: If True, stop running hooks when one fails with HALT behavior.

        Returns:
            List of hook results.

        Raises:
            HookError: If a hook fails with HALT behavior and stop_on_halt is True.
        """
        results = []

        for hook in self._hooks:
            if not hook.enabled:
                results.append(
                    HookResult(
                        hook=hook,
                        status=SkillStatus.SKIPPED,
                        output="Hook is disabled",
                    )
                )
                continue

            result = self._run_hook(hook, context)
            results.append(result)

            if result.should_halt and stop_on_halt:
                raise HookError(
                    f"Hook '{hook.name}' failed with HALT behavior",
                    hook_name=hook.name,
                    results=results,
                )

        return results

    def _run_hook(self, hook: Hook, context: SkillContext) -> HookResult:
        """Run a single hook.

        Args:
            hook: Hook to execute.
            context: Execution context.

        Returns:
            Hook result.
        """
        if hook.hook_type == HookType.SKILL:
            return self._run_skill_hook(hook, context)
        else:
            return self._run_command_hook(hook, context)

    def _run_skill_hook(self, hook: Hook, context: SkillContext) -> HookResult:
        """Run a skill-type hook.

        Args:
            hook: Hook configuration.
            context: Execution context.

        Returns:
            Hook result.
        """
        skill = self._registry.get(hook.target)
        if skill is None:
            return HookResult(
                hook=hook,
                status=SkillStatus.FAILED,
                error=f"Skill '{hook.target}' not found",
            )

        try:
            # Apply hook-specific config to skill
            if hook.config:
                for key, value in hook.config.items():
                    if hasattr(skill.config, key):
                        setattr(skill.config, key, value)
                    else:
                        skill.config.options[key] = value

            skill_result = skill.execute(context)
            return HookResult(
                hook=hook,
                status=skill_result.status,
                skill_result=skill_result,
                output=skill_result.output,
                error=skill_result.error,
            )
        except Exception as e:
            return HookResult(
                hook=hook,
                status=SkillStatus.FAILED,
                error=str(e),
            )

    def _run_command_hook(self, hook: Hook, context: SkillContext) -> HookResult:
        """Run a command-type hook.

        Args:
            hook: Hook configuration.
            context: Execution context.

        Returns:
            Hook result.
        """
        import subprocess
        import time

        if context.dry_run:
            return HookResult(
                hook=hook,
                status=SkillStatus.SKIPPED,
                output=f"[DRY RUN] Would execute: {hook.target}",
            )

        timeout = hook.config.get("timeout", 300)
        start_time = time.time()

        try:
            # Substitute placeholders
            command = hook.target.replace("{project_path}", str(context.project_path))
            command = command.replace("{working_dir}", str(context.working_dir or context.project_path))

            result = subprocess.run(
                command,
                shell=True,
                cwd=str(context.working_dir or context.project_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = result.stdout + result.stderr

            if result.returncode == 0:
                return HookResult(
                    hook=hook,
                    status=SkillStatus.SUCCESS,
                    output=output,
                )
            else:
                return HookResult(
                    hook=hook,
                    status=SkillStatus.FAILED,
                    output=output,
                    error=f"Command exited with code {result.returncode}",
                )

        except subprocess.TimeoutExpired:
            return HookResult(
                hook=hook,
                status=SkillStatus.FAILED,
                error=f"Command timed out after {timeout} seconds",
            )
        except Exception as e:
            return HookResult(
                hook=hook,
                status=SkillStatus.FAILED,
                error=str(e),
            )


def create_hooks_from_config(config: dict[str, Any]) -> list[Hook]:
    """Create hooks from configuration dictionary.

    Config format::

        hooks:
          - name: test
            type: skill
            target: test
            on_failure: halt
          - name: custom-lint
            type: command
            target: "npm run lint"
            on_failure: warn

    Args:
        config: Configuration dictionary with 'hooks' key.

    Returns:
        List of Hook instances.
    """
    hooks = []
    hooks_config = config.get("hooks", [])

    for hook_data in hooks_config:
        if isinstance(hook_data, str):
            # Shorthand: just the builtin hook name
            if hook_data in BUILTIN_HOOKS:
                hooks.append(BUILTIN_HOOKS[hook_data])
        elif isinstance(hook_data, dict):
            hooks.append(Hook.from_dict(hook_data))

    return hooks
