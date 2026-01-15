"""Unit tests for the executor plugin system."""

import tempfile
from pathlib import Path

import pytest

from src.executors import (
    ClaudeCLIExecutor,
    DryRunExecutor,
    ExecutorPlugin,
    ExecutorSelection,
    PluginConfigField,
    PluginDiscovery,
    PluginManager,
    PluginSchema,
    PluginStatus,
)


class TestPluginConfigField:
    """Tests for PluginConfigField."""

    def test_basic_field(self):
        """Test creating a basic config field."""
        field = PluginConfigField(
            name="api_key",
            type="secret",
            description="API key for authentication",
            required=True,
        )
        assert field.name == "api_key"
        assert field.type == "secret"
        assert field.required is True

    def test_field_with_defaults(self):
        """Test field with default value."""
        field = PluginConfigField(
            name="timeout",
            type="integer",
            description="Timeout in seconds",
            default=60,
        )
        assert field.default == 60

    def test_field_with_enum(self):
        """Test field with enum options."""
        field = PluginConfigField(
            name="model",
            type="string",
            description="Model to use",
            enum=["gpt-4", "gpt-3.5-turbo"],
        )
        assert field.enum == ["gpt-4", "gpt-3.5-turbo"]

    def test_to_json_schema(self):
        """Test converting field to JSON Schema."""
        field = PluginConfigField(
            name="temperature",
            type="number",
            description="Temperature for generation",
            default=0.7,
            min_value=0.0,
            max_value=2.0,
        )
        schema = field.to_json_schema()

        assert schema["type"] == "number"
        assert schema["description"] == "Temperature for generation"
        assert schema["default"] == 0.7
        assert schema["minimum"] == 0.0
        assert schema["maximum"] == 2.0

    def test_secret_field_format(self):
        """Test that secret fields get password format."""
        field = PluginConfigField(
            name="api_key",
            type="secret",
            description="Secret key",
        )
        schema = field.to_json_schema()
        assert schema["format"] == "password"


class TestPluginSchema:
    """Tests for PluginSchema."""

    def test_empty_schema(self):
        """Test empty schema."""
        schema = PluginSchema()
        json_schema = schema.to_json_schema()

        assert json_schema["type"] == "object"
        assert json_schema["properties"] == {}

    def test_schema_with_fields(self):
        """Test schema with multiple fields."""
        schema = PluginSchema(
            fields=[
                PluginConfigField(
                    name="api_key",
                    type="secret",
                    description="API key",
                    required=True,
                ),
                PluginConfigField(
                    name="timeout",
                    type="integer",
                    description="Timeout",
                    default=60,
                ),
            ]
        )
        json_schema = schema.to_json_schema()

        assert "api_key" in json_schema["properties"]
        assert "timeout" in json_schema["properties"]
        assert "api_key" in json_schema["required"]
        assert "timeout" not in json_schema.get("required", [])

    def test_validate_valid_config(self):
        """Test validating a valid configuration."""
        schema = PluginSchema(
            fields=[
                PluginConfigField(
                    name="api_key",
                    type="string",
                    description="API key",
                    required=True,
                ),
                PluginConfigField(
                    name="timeout",
                    type="integer",
                    description="Timeout",
                    default=60,
                    min_value=1,
                    max_value=300,
                ),
            ]
        )

        errors = schema.validate({"api_key": "test-key", "timeout": 120})
        assert len(errors) == 0

    def test_validate_missing_required(self):
        """Test validation fails for missing required field."""
        schema = PluginSchema(
            fields=[
                PluginConfigField(
                    name="api_key",
                    type="string",
                    description="API key",
                    required=True,
                ),
            ]
        )

        errors = schema.validate({})
        assert len(errors) == 1
        assert "api_key" in errors[0]

    def test_validate_type_mismatch(self):
        """Test validation fails for type mismatch."""
        schema = PluginSchema(
            fields=[
                PluginConfigField(
                    name="timeout",
                    type="integer",
                    description="Timeout",
                ),
            ]
        )

        errors = schema.validate({"timeout": "not-an-int"})
        assert len(errors) == 1
        assert "integer" in errors[0]

    def test_validate_enum_mismatch(self):
        """Test validation fails for invalid enum value."""
        schema = PluginSchema(
            fields=[
                PluginConfigField(
                    name="model",
                    type="string",
                    description="Model",
                    enum=["gpt-4", "gpt-3.5"],
                ),
            ]
        )

        errors = schema.validate({"model": "invalid-model"})
        assert len(errors) == 1
        assert "gpt-4" in errors[0]

    def test_validate_range(self):
        """Test validation for numeric range."""
        schema = PluginSchema(
            fields=[
                PluginConfigField(
                    name="temperature",
                    type="number",
                    description="Temperature",
                    min_value=0.0,
                    max_value=1.0,
                ),
            ]
        )

        errors = schema.validate({"temperature": 1.5})
        assert len(errors) == 1
        assert "<=" in errors[0]


class TestExecutorSelection:
    """Tests for ExecutorSelection."""

    def test_default_all_enabled(self):
        """Test that all executors are enabled by default."""
        selection = ExecutorSelection()
        assert selection.is_enabled("claude-cli")
        assert selection.is_enabled("any-executor")

    def test_explicit_enabled_list(self):
        """Test explicit enabled executor list."""
        selection = ExecutorSelection(enabled_executors=["claude-cli", "dry-run"])
        assert selection.is_enabled("claude-cli")
        assert selection.is_enabled("dry-run")
        assert not selection.is_enabled("other-executor")

    def test_get_config(self):
        """Test getting executor config."""
        selection = ExecutorSelection(
            executor_configs={
                "claude-cli": {"timeout": 300},
                "dry-run": {"delay": 1.0},
            }
        )

        assert selection.get_config("claude-cli") == {"timeout": 300}
        assert selection.get_config("dry-run") == {"delay": 1.0}
        assert selection.get_config("unknown") == {}

    def test_to_dict(self):
        """Test converting to dict."""
        selection = ExecutorSelection(
            enabled_executors=["claude-cli"],
            default_executor="claude-cli",
            fallback_executor="dry-run",
        )
        data = selection.to_dict()

        assert data["enabled_executors"] == ["claude-cli"]
        assert data["default_executor"] == "claude-cli"
        assert data["fallback_executor"] == "dry-run"

    def test_from_dict(self):
        """Test creating from dict."""
        data = {
            "enabled_executors": ["claude-cli"],
            "default_executor": "claude-cli",
            "executor_configs": {"claude-cli": {"timeout": 300}},
        }
        selection = ExecutorSelection.from_dict(data)

        assert selection.enabled_executors == ["claude-cli"]
        assert selection.default_executor == "claude-cli"
        assert selection.get_config("claude-cli") == {"timeout": 300}


class TestClaudeCLIPlugin:
    """Tests for ClaudeCLIExecutor as a plugin."""

    def test_plugin_info(self):
        """Test getting plugin info."""
        info = ClaudeCLIExecutor.get_plugin_info()

        assert info["name"] == "claude-cli"
        assert info["display_name"] == "Claude CLI"
        assert "description" in info
        assert "version" in info

    def test_config_schema(self):
        """Test getting config schema."""
        schema = ClaudeCLIExecutor.get_config_schema()

        assert isinstance(schema, PluginSchema)
        assert len(schema.fields) > 0

        # Check for expected fields
        field_names = [f.name for f in schema.fields]
        assert "model" in field_names
        assert "max_turns" in field_names
        assert "timeout" in field_names

    def test_capabilities(self):
        """Test getting capabilities."""
        capabilities = ClaudeCLIExecutor.get_capabilities()

        assert "code_generation" in capabilities
        assert "tool_use" in capabilities

    def test_default_config(self):
        """Test getting default config."""
        defaults = ClaudeCLIExecutor.get_default_config()

        assert "model" in defaults
        assert "max_turns" in defaults


class TestDryRunPlugin:
    """Tests for DryRunExecutor as a plugin."""

    def test_plugin_info(self):
        """Test getting plugin info."""
        info = DryRunExecutor.get_plugin_info()

        assert info["name"] == "dry-run"
        assert info["display_name"] == "Dry Run"

    def test_config_schema(self):
        """Test getting config schema."""
        schema = DryRunExecutor.get_config_schema()

        field_names = [f.name for f in schema.fields]
        assert "delay" in field_names
        assert "fail_rate" in field_names

    def test_capabilities(self):
        """Test getting capabilities."""
        capabilities = DryRunExecutor.get_capabilities()
        assert "simulation" in capabilities


class TestPluginDiscovery:
    """Tests for PluginDiscovery."""

    def test_discover_builtin(self):
        """Test discovering built-in plugins."""
        discovery = PluginDiscovery()
        plugins = discovery.discover_all()

        assert "claude-cli" in plugins
        assert "dry-run" in plugins

    def test_discovered_plugin_info(self):
        """Test discovered plugin has correct info."""
        discovery = PluginDiscovery()
        plugins = discovery.discover_all()

        claude = plugins["claude-cli"]
        assert claude.display_name == "Claude CLI"
        assert claude.source_type == "builtin"
        assert len(claude.capabilities) > 0

    def test_get_plugin(self):
        """Test getting a specific plugin."""
        discovery = PluginDiscovery()
        discovery.discover_all()

        plugin = discovery.get_plugin("claude-cli")
        assert plugin is not None
        assert plugin.name == "claude-cli"

        unknown = discovery.get_plugin("unknown")
        assert unknown is None

    def test_list_plugins(self):
        """Test listing all plugins."""
        discovery = PluginDiscovery()
        discovery.discover_all()

        plugins = discovery.list_plugins()
        assert len(plugins) >= 2

        names = [p.name for p in plugins]
        assert "claude-cli" in names
        assert "dry-run" in names


class TestPluginManager:
    """Tests for PluginManager."""

    def test_get_available_plugins(self):
        """Test getting available plugins."""
        manager = PluginManager()
        plugins = manager.get_available_plugins()

        assert len(plugins) >= 2

        # Find claude-cli
        claude = next((p for p in plugins if p["name"] == "claude-cli"), None)
        assert claude is not None
        assert "schema" in claude
        assert "capabilities" in claude

    def test_create_executor(self):
        """Test creating an executor instance."""
        manager = PluginManager()
        executor = manager.create_executor("dry-run")

        assert executor.name == "dry-run"
        assert isinstance(executor, DryRunExecutor)

    def test_create_executor_with_config(self):
        """Test creating executor with custom config."""
        manager = PluginManager()
        executor = manager.create_executor("dry-run", config={"max_retries": 5})

        assert executor.config.max_retries == 5

    def test_create_unknown_executor(self):
        """Test error when creating unknown executor."""
        manager = PluginManager()

        with pytest.raises(ValueError, match="Unknown plugin"):
            manager.create_executor("nonexistent")

    def test_create_disabled_executor(self):
        """Test error when creating disabled executor."""
        manager = PluginManager()
        selection = ExecutorSelection(enabled_executors=["dry-run"])

        with pytest.raises(ValueError, match="disabled"):
            manager.create_executor("claude-cli", selection=selection)

    def test_check_health(self):
        """Test health check for a plugin."""
        manager = PluginManager()
        health = manager.check_health("dry-run")

        assert health["name"] == "dry-run"
        assert "healthy" in health
        assert "status" in health

    def test_check_all_health(self):
        """Test health check for all plugins."""
        manager = PluginManager()
        results = manager.check_all_health()

        assert len(results) >= 2

        # dry-run should be healthy (no external dependencies)
        dry_run = next((r for r in results if r["name"] == "dry-run"), None)
        assert dry_run is not None
        assert dry_run["healthy"] is True


class TestPluginFromFile:
    """Tests for loading plugins from files."""

    def test_load_custom_plugin(self):
        """Test loading a custom plugin from file."""
        plugin_code = '''
"""Custom test plugin."""
from typing import Any
from src.executors.plugin import ExecutorPlugin, PluginSchema, PluginConfigField
from src.executors.base import ExecutionResult, TaskContext


class CustomTestExecutor(ExecutorPlugin):
    """A custom test executor."""

    @classmethod
    def get_plugin_info(cls) -> dict[str, Any]:
        return {
            "name": "custom-test",
            "display_name": "Custom Test",
            "description": "A test plugin",
            "version": "1.0.0",
        }

    @classmethod
    def get_config_schema(cls) -> PluginSchema:
        return PluginSchema(fields=[
            PluginConfigField(
                name="custom_option",
                type="string",
                description="A custom option",
            ),
        ])

    @property
    def name(self) -> str:
        return "custom-test"

    @property
    def version(self) -> str:
        return "1.0.0"

    def _execute_impl(self, context: TaskContext) -> ExecutionResult:
        return ExecutionResult(success=True, output="Custom test executed")
'''

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            plugin_file = plugin_dir / "custom_test.py"
            plugin_file.write_text(plugin_code)

            discovery = PluginDiscovery(
                user_dir=plugin_dir,
                project_dir=Path("/nonexistent"),
            )
            plugins = discovery.discover_all()

            assert "custom-test" in plugins
            custom = plugins["custom-test"]
            assert custom.display_name == "Custom Test"
            assert custom.source_type == "user"
