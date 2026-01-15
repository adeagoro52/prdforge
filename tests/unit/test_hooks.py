"""Unit tests for the hooks system."""

import tempfile
from pathlib import Path

import pytest

from src.skills import (
    Hook,
    HookBehavior,
    HookError,
    HookResult,
    HookRunner,
    HookType,
    SkillRegistry,
    create_hooks_from_config,
)
from src.skills.base import SkillContext, SkillStatus
from src.skills.hooks import BUILTIN_HOOKS


class TestHook:
    """Tests for Hook dataclass."""

    def test_default_hook(self):
        """Test default hook values."""
        hook = Hook(name="test", hook_type=HookType.SKILL, target="lint")
        assert hook.name == "test"
        assert hook.hook_type == HookType.SKILL
        assert hook.target == "lint"
        assert hook.on_failure == HookBehavior.WARN
        assert hook.enabled is True
        assert hook.config == {}

    def test_hook_from_dict(self):
        """Test creating hook from dictionary."""
        data = {
            "name": "my-hook",
            "type": "command",
            "target": "echo hello",
            "on_failure": "halt",
            "enabled": False,
            "config": {"timeout": 60},
        }
        hook = Hook.from_dict(data)
        assert hook.name == "my-hook"
        assert hook.hook_type == HookType.COMMAND
        assert hook.target == "echo hello"
        assert hook.on_failure == HookBehavior.HALT
        assert hook.enabled is False
        assert hook.config == {"timeout": 60}

    def test_hook_to_dict(self):
        """Test converting hook to dictionary."""
        hook = Hook(
            name="test",
            hook_type=HookType.SKILL,
            target="lint",
            on_failure=HookBehavior.CONTINUE,
            enabled=True,
            config={"verbose": True},
        )
        data = hook.to_dict()
        assert data["name"] == "test"
        assert data["type"] == "skill"
        assert data["target"] == "lint"
        assert data["on_failure"] == "continue"
        assert data["enabled"] is True
        assert data["config"] == {"verbose": True}


class TestHookResult:
    """Tests for HookResult."""

    def test_success_result(self):
        """Test successful hook result."""
        hook = Hook(name="test", hook_type=HookType.SKILL, target="lint")
        result = HookResult(hook=hook, status=SkillStatus.SUCCESS)
        assert result.success is True
        assert result.should_halt is False

    def test_failed_result_with_halt(self):
        """Test failed result with HALT behavior."""
        hook = Hook(
            name="test",
            hook_type=HookType.SKILL,
            target="test",
            on_failure=HookBehavior.HALT,
        )
        result = HookResult(hook=hook, status=SkillStatus.FAILED)
        assert result.success is False
        assert result.should_halt is True

    def test_failed_result_with_warn(self):
        """Test failed result with WARN behavior."""
        hook = Hook(
            name="test",
            hook_type=HookType.SKILL,
            target="lint",
            on_failure=HookBehavior.WARN,
        )
        result = HookResult(hook=hook, status=SkillStatus.FAILED)
        assert result.success is False
        assert result.should_halt is False


class TestBuiltinHooks:
    """Tests for built-in hook presets."""

    def test_builtin_hooks_exist(self):
        """Test built-in hooks are defined."""
        assert "test" in BUILTIN_HOOKS
        assert "lint" in BUILTIN_HOOKS
        assert "typecheck" in BUILTIN_HOOKS
        assert "simplify" in BUILTIN_HOOKS
        assert "review" in BUILTIN_HOOKS

    def test_test_hook_halts_on_failure(self):
        """Test that test hook halts on failure."""
        hook = BUILTIN_HOOKS["test"]
        assert hook.on_failure == HookBehavior.HALT

    def test_lint_hook_warns_on_failure(self):
        """Test that lint hook warns on failure."""
        hook = BUILTIN_HOOKS["lint"]
        assert hook.on_failure == HookBehavior.WARN


class TestHookRunner:
    """Tests for HookRunner."""

    @pytest.fixture
    def registry(self):
        """Create skill registry with built-in skills."""
        reg = SkillRegistry()
        reg.discover_builtin()
        return reg

    @pytest.fixture
    def context(self):
        """Create execution context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            yield SkillContext(project_path=project_path, dry_run=True)

    def test_add_hook(self, registry):
        """Test adding a hook."""
        runner = HookRunner(registry)
        hook = Hook(name="my-hook", hook_type=HookType.SKILL, target="lint")
        runner.add_hook(hook)
        assert len(runner.list_hooks()) == 1
        assert runner.list_hooks()[0].name == "my-hook"

    def test_add_builtin(self, registry):
        """Test adding a built-in hook."""
        runner = HookRunner(registry)
        assert runner.add_builtin("lint") is True
        assert len(runner.list_hooks()) == 1
        assert runner.list_hooks()[0].name == "lint"

    def test_add_builtin_nonexistent(self, registry):
        """Test adding non-existent built-in hook."""
        runner = HookRunner(registry)
        assert runner.add_builtin("nonexistent") is False
        assert len(runner.list_hooks()) == 0

    def test_remove_hook(self, registry):
        """Test removing a hook."""
        runner = HookRunner(registry)
        runner.add_builtin("lint")
        assert runner.remove_hook("lint") is True
        assert len(runner.list_hooks()) == 0

    def test_remove_nonexistent_hook(self, registry):
        """Test removing non-existent hook."""
        runner = HookRunner(registry)
        assert runner.remove_hook("nonexistent") is False

    def test_clear_hooks(self, registry):
        """Test clearing all hooks."""
        runner = HookRunner(registry)
        runner.add_builtin("lint")
        runner.add_builtin("test")
        runner.clear_hooks()
        assert len(runner.list_hooks()) == 0

    def test_run_skill_hook_dry_run(self, registry, context):
        """Test running skill hook in dry run mode."""
        # Create project with pyproject.toml for lint auto-detection
        (context.project_path / "pyproject.toml").touch()

        runner = HookRunner(registry)
        runner.add_builtin("lint")
        results = runner.run_hooks(context)

        assert len(results) == 1
        assert results[0].status == SkillStatus.SKIPPED
        assert "DRY RUN" in results[0].output

    def test_run_command_hook_dry_run(self, registry, context):
        """Test running command hook in dry run mode."""
        runner = HookRunner(registry)
        hook = Hook(
            name="echo-test",
            hook_type=HookType.COMMAND,
            target="echo 'Hello'",
        )
        runner.add_hook(hook)
        results = runner.run_hooks(context)

        assert len(results) == 1
        assert results[0].status == SkillStatus.SKIPPED
        assert "DRY RUN" in results[0].output

    def test_disabled_hook_skipped(self, registry, context):
        """Test disabled hook is skipped."""
        runner = HookRunner(registry)
        hook = Hook(
            name="disabled",
            hook_type=HookType.SKILL,
            target="lint",
            enabled=False,
        )
        runner.add_hook(hook)
        results = runner.run_hooks(context)

        assert len(results) == 1
        assert results[0].status == SkillStatus.SKIPPED
        assert "disabled" in results[0].output.lower()

    def test_nonexistent_skill_fails(self, registry, context):
        """Test hook with non-existent skill fails."""
        runner = HookRunner(registry)
        hook = Hook(
            name="bad-skill",
            hook_type=HookType.SKILL,
            target="nonexistent-skill",
        )
        runner.add_hook(hook)
        results = runner.run_hooks(context)

        assert len(results) == 1
        assert results[0].status == SkillStatus.FAILED
        assert "not found" in results[0].error.lower()

    def test_halt_behavior_raises(self, registry, context):
        """Test hook with HALT behavior raises on failure."""
        runner = HookRunner(registry)
        hook = Hook(
            name="halt-test",
            hook_type=HookType.SKILL,
            target="nonexistent-skill",
            on_failure=HookBehavior.HALT,
        )
        runner.add_hook(hook)

        with pytest.raises(HookError) as exc_info:
            runner.run_hooks(context)

        assert exc_info.value.hook_name == "halt-test"
        assert len(exc_info.value.results) == 1

    def test_warn_behavior_continues(self, registry, context):
        """Test hook with WARN behavior continues execution."""
        runner = HookRunner(registry)
        hook1 = Hook(
            name="warn-test",
            hook_type=HookType.SKILL,
            target="nonexistent-skill",
            on_failure=HookBehavior.WARN,
        )
        hook2 = Hook(
            name="second-hook",
            hook_type=HookType.COMMAND,
            target="echo success",
        )
        runner.add_hook(hook1)
        runner.add_hook(hook2)

        results = runner.run_hooks(context)

        # Both hooks should have run
        assert len(results) == 2
        assert results[0].status == SkillStatus.FAILED
        assert results[1].status == SkillStatus.SKIPPED  # dry run


class TestCreateHooksFromConfig:
    """Tests for create_hooks_from_config function."""

    def test_create_from_list(self):
        """Test creating hooks from list config."""
        config = {
            "hooks": [
                {
                    "name": "lint",
                    "type": "skill",
                    "target": "lint",
                    "on_failure": "warn",
                },
                {
                    "name": "test",
                    "type": "skill",
                    "target": "test",
                    "on_failure": "halt",
                },
            ]
        }
        hooks = create_hooks_from_config(config)
        assert len(hooks) == 2
        assert hooks[0].name == "lint"
        assert hooks[1].name == "test"

    def test_create_from_shorthand(self):
        """Test creating hooks from shorthand (builtin names)."""
        config = {
            "hooks": ["lint", "test", "typecheck"]
        }
        hooks = create_hooks_from_config(config)
        assert len(hooks) == 3
        assert hooks[0].name == "lint"
        assert hooks[1].name == "test"
        assert hooks[2].name == "typecheck"

    def test_mixed_config(self):
        """Test mixed shorthand and full config."""
        config = {
            "hooks": [
                "lint",
                {
                    "name": "custom",
                    "type": "command",
                    "target": "echo hello",
                },
            ]
        }
        hooks = create_hooks_from_config(config)
        assert len(hooks) == 2
        assert hooks[0].name == "lint"
        assert hooks[1].name == "custom"
        assert hooks[1].hook_type == HookType.COMMAND

    def test_empty_config(self):
        """Test empty config returns empty list."""
        hooks = create_hooks_from_config({})
        assert hooks == []

    def test_invalid_shorthand_ignored(self):
        """Test invalid shorthand names are ignored."""
        config = {
            "hooks": ["nonexistent", "lint"]
        }
        hooks = create_hooks_from_config(config)
        assert len(hooks) == 1
        assert hooks[0].name == "lint"
