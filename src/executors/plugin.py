"""Executor plugin system for dynamic backend discovery and management.

This module provides plugin discovery, configuration schemas, and management
functionality for AI executor backends.
"""

import importlib
import importlib.util
import json
import sys
from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from src.engine.logging import logger

from .base import BaseExecutor, ExecutorConfig, ExecutorStatus


class PluginStatus(Enum):
    """Status of an executor plugin."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"


@dataclass
class PluginConfigField:
    """Definition of a configuration field for a plugin.

    Used to generate UI forms and validate configuration.
    """

    name: str
    type: str  # string, integer, number, boolean, array, secret
    description: str
    required: bool = False
    default: Any = None
    enum: list[str] | None = None
    min_value: float | None = None
    max_value: float | None = None
    pattern: str | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format.

        Returns:
            JSON Schema property definition.
        """
        type_map = {
            "string": "string",
            "secret": "string",
            "integer": "integer",
            "number": "number",
            "boolean": "boolean",
            "array": "array",
        }

        schema: dict[str, Any] = {
            "type": type_map.get(self.type, "string"),
            "description": self.description,
        }

        if self.default is not None:
            schema["default"] = self.default

        if self.enum:
            schema["enum"] = self.enum

        if self.min_value is not None:
            schema["minimum"] = self.min_value

        if self.max_value is not None:
            schema["maximum"] = self.max_value

        if self.pattern:
            schema["pattern"] = self.pattern

        if self.type == "secret":
            schema["format"] = "password"

        return schema


@dataclass
class PluginSchema:
    """Configuration schema for an executor plugin.

    Defines all configurable options for a plugin with validation rules.
    """

    fields: list[PluginConfigField] = field(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format.

        Returns:
            Complete JSON Schema for plugin configuration.
        """
        properties = {}
        required = []

        for f in self.fields:
            properties[f.name] = f.to_json_schema()
            if f.required:
                required.append(f.name)

        schema: dict[str, Any] = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": properties,
        }

        if required:
            schema["required"] = required

        return schema

    def validate(self, config: dict[str, Any]) -> list[str]:
        """Validate configuration against schema.

        Args:
            config: Configuration to validate.

        Returns:
            List of validation error messages.
        """
        errors = []

        for f in self.fields:
            value = config.get(f.name)

            # Check required fields
            if f.required and value is None:
                errors.append(f"Missing required field: {f.name}")
                continue

            if value is None:
                continue

            # Type validation
            if f.type in ("string", "secret") and not isinstance(value, str):
                errors.append(f"{f.name}: expected string, got {type(value).__name__}")
            elif f.type == "integer" and not isinstance(value, int):
                errors.append(f"{f.name}: expected integer, got {type(value).__name__}")
            elif f.type == "number" and not isinstance(value, (int, float)):
                errors.append(f"{f.name}: expected number, got {type(value).__name__}")
            elif f.type == "boolean" and not isinstance(value, bool):
                errors.append(f"{f.name}: expected boolean, got {type(value).__name__}")
            elif f.type == "array" and not isinstance(value, list):
                errors.append(f"{f.name}: expected array, got {type(value).__name__}")

            # Enum validation
            if f.enum and value not in f.enum:
                errors.append(f"{f.name}: must be one of {f.enum}, got {value}")

            # Range validation
            if f.min_value is not None and isinstance(value, (int, float)):
                if value < f.min_value:
                    errors.append(f"{f.name}: must be >= {f.min_value}")

            if f.max_value is not None and isinstance(value, (int, float)):
                if value > f.max_value:
                    errors.append(f"{f.name}: must be <= {f.max_value}")

        return errors


class ExecutorPlugin(BaseExecutor):
    """Enhanced base class for executor plugins.

    Adds plugin-specific functionality including:
    - Configuration schema definition
    - Plugin metadata
    - Capability declaration
    - Cost estimation
    """

    @classmethod
    @abstractmethod
    def get_plugin_info(cls) -> dict[str, Any]:
        """Get plugin metadata.

        Returns:
            Dict with plugin info including:
            - name: Plugin identifier
            - display_name: Human-readable name
            - description: Plugin description
            - version: Plugin version
            - author: Plugin author (optional)
            - homepage: Plugin homepage URL (optional)
        """
        ...

    @classmethod
    @abstractmethod
    def get_config_schema(cls) -> PluginSchema:
        """Get the configuration schema for this plugin.

        Returns:
            PluginSchema defining all configuration options.
        """
        ...

    @classmethod
    def get_capabilities(cls) -> list[str]:
        """Get list of capabilities supported by this plugin.

        Override to declare specific capabilities like:
        - streaming: Supports streaming responses
        - tool_use: Supports tool/function calls
        - vision: Supports image analysis
        - code_execution: Can execute code

        Returns:
            List of capability names.
        """
        return ["code_generation"]

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        """Get default configuration values.

        Returns:
            Dict with default configuration.
        """
        defaults = {}
        schema = cls.get_config_schema()
        for f in schema.fields:
            if f.default is not None:
                defaults[f.name] = f.default
        return defaults

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for given token counts.

        Override in subclasses to provide accurate cost estimation.

        Args:
            prompt_tokens: Number of input tokens.
            completion_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        return 0.0

    def get_plugin_status(self) -> PluginStatus:
        """Get detailed plugin status.

        Returns:
            PluginStatus indicating current state.
        """
        if self._status == ExecutorStatus.UNAVAILABLE:
            return PluginStatus.UNAVAILABLE
        if self._status == ExecutorStatus.ERROR:
            return PluginStatus.ERROR
        if not self.health_check():
            return PluginStatus.NOT_CONFIGURED
        return PluginStatus.ACTIVE


T = TypeVar("T", bound=ExecutorPlugin)


@dataclass
class DiscoveredPlugin:
    """Information about a discovered plugin."""

    name: str
    display_name: str
    description: str
    version: str
    plugin_class: type[ExecutorPlugin]
    source_path: Path | None = None
    source_type: str = "builtin"  # builtin, user, project
    capabilities: list[str] = field(default_factory=list)
    schema: PluginSchema | None = None
    error: str | None = None


class PluginDiscovery:
    """Discovers and loads executor plugins from various sources.

    Plugin discovery order (later overrides earlier):
    1. Built-in plugins (src/executors/)
    2. User plugins (~/.prdforge/plugins/)
    3. Project plugins (.prdforge/plugins/)
    """

    # Default paths for plugin discovery
    USER_PLUGIN_DIR = Path.home() / ".prdforge" / "plugins"
    PROJECT_PLUGIN_DIR = Path(".prdforge") / "plugins"

    def __init__(
        self,
        builtin_dir: Path | None = None,
        user_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        """Initialize plugin discovery.

        Args:
            builtin_dir: Directory for built-in plugins.
            user_dir: Directory for user plugins.
            project_dir: Directory for project plugins.
        """
        self.builtin_dir = builtin_dir or Path(__file__).parent
        self.user_dir = user_dir or self.USER_PLUGIN_DIR
        self.project_dir = project_dir or self.PROJECT_PLUGIN_DIR

        self._discovered: dict[str, DiscoveredPlugin] = {}

    def discover_all(self) -> dict[str, DiscoveredPlugin]:
        """Discover plugins from all sources.

        Returns:
            Dict mapping plugin names to DiscoveredPlugin.
        """
        self._discovered.clear()

        # Discover in order (later overrides)
        self._discover_builtin()
        self._discover_from_directory(self.user_dir, "user")
        self._discover_from_directory(self.project_dir, "project")

        return self._discovered

    def _discover_builtin(self) -> None:
        """Discover built-in executor plugins."""
        # Import known built-in plugins
        try:
            from .claude_cli import ClaudeCLIExecutor

            self._register_plugin_class(ClaudeCLIExecutor, "builtin")
        except ImportError as e:
            logger.warning(f"Failed to load ClaudeCLIExecutor: {e}")

        try:
            from .dry_run import DryRunExecutor

            self._register_plugin_class(DryRunExecutor, "builtin")
        except ImportError as e:
            logger.warning(f"Failed to load DryRunExecutor: {e}")

        try:
            from .openai_executor import OpenAIExecutor

            self._register_plugin_class(OpenAIExecutor, "builtin")
        except ImportError as e:
            logger.warning(f"Failed to load OpenAIExecutor: {e}")

        try:
            from .gemini_executor import GeminiExecutor

            self._register_plugin_class(GeminiExecutor, "builtin")
        except ImportError as e:
            logger.warning(f"Failed to load GeminiExecutor: {e}")

        try:
            from .claude_api_executor import ClaudeAPIExecutor

            self._register_plugin_class(ClaudeAPIExecutor, "builtin")
        except ImportError as e:
            logger.warning(f"Failed to load ClaudeAPIExecutor: {e}")

    def _discover_from_directory(self, directory: Path, source_type: str) -> None:
        """Discover plugins from a directory.

        Args:
            directory: Directory to search.
            source_type: Source type label (user, project).
        """
        if not directory.exists():
            return

        for plugin_file in directory.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue

            try:
                self._load_plugin_from_file(plugin_file, source_type)
            except Exception as e:
                logger.error(f"Failed to load plugin from {plugin_file}: {e}")
                # Record failed plugin
                self._discovered[plugin_file.stem] = DiscoveredPlugin(
                    name=plugin_file.stem,
                    display_name=plugin_file.stem,
                    description="Failed to load",
                    version="unknown",
                    plugin_class=ExecutorPlugin,  # type: ignore
                    source_path=plugin_file,
                    source_type=source_type,
                    error=str(e),
                )

    def _load_plugin_from_file(self, file_path: Path, source_type: str) -> None:
        """Load a plugin from a Python file.

        Args:
            file_path: Path to the plugin file.
            source_type: Source type label.
        """
        module_name = f"prdforge_plugin_{file_path.stem}"

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            raise ImportError(f"Cannot create module spec for {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find ExecutorPlugin subclasses in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, ExecutorPlugin)
                and attr is not ExecutorPlugin
                and attr is not BaseExecutor
            ):
                self._register_plugin_class(attr, source_type, file_path)

    def _register_plugin_class(
        self,
        plugin_class: type[ExecutorPlugin],
        source_type: str,
        source_path: Path | None = None,
    ) -> None:
        """Register a discovered plugin class.

        Args:
            plugin_class: The plugin class.
            source_type: Source type label.
            source_path: Path to source file (if applicable).
        """
        try:
            info = plugin_class.get_plugin_info()
            schema = plugin_class.get_config_schema()
            capabilities = plugin_class.get_capabilities()

            plugin = DiscoveredPlugin(
                name=info["name"],
                display_name=info.get("display_name", info["name"]),
                description=info.get("description", ""),
                version=info.get("version", "1.0.0"),
                plugin_class=plugin_class,
                source_path=source_path,
                source_type=source_type,
                capabilities=capabilities,
                schema=schema,
            )

            self._discovered[plugin.name] = plugin
            logger.debug(f"Discovered plugin: {plugin.name} ({source_type})")

        except Exception as e:
            logger.error(f"Failed to register plugin {plugin_class}: {e}")

    def get_plugin(self, name: str) -> DiscoveredPlugin | None:
        """Get a discovered plugin by name.

        Args:
            name: Plugin name.

        Returns:
            DiscoveredPlugin or None if not found.
        """
        return self._discovered.get(name)

    def list_plugins(self) -> list[DiscoveredPlugin]:
        """List all discovered plugins.

        Returns:
            List of DiscoveredPlugin objects.
        """
        return list(self._discovered.values())


@dataclass
class ExecutorSelection:
    """Configuration for executor selection at project level."""

    enabled_executors: list[str] = field(default_factory=list)
    default_executor: str | None = None
    executor_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    fallback_executor: str | None = None

    def is_enabled(self, executor_name: str) -> bool:
        """Check if an executor is enabled.

        Args:
            executor_name: Executor name to check.

        Returns:
            True if enabled or if no explicit list (all enabled).
        """
        if not self.enabled_executors:
            return True
        return executor_name in self.enabled_executors

    def get_config(self, executor_name: str) -> dict[str, Any]:
        """Get configuration for an executor.

        Args:
            executor_name: Executor name.

        Returns:
            Executor configuration dict.
        """
        return self.executor_configs.get(executor_name, {})

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dict representation.
        """
        return {
            "enabled_executors": self.enabled_executors,
            "default_executor": self.default_executor,
            "executor_configs": self.executor_configs,
            "fallback_executor": self.fallback_executor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutorSelection":
        """Create from dictionary.

        Args:
            data: Dict representation.

        Returns:
            ExecutorSelection instance.
        """
        return cls(
            enabled_executors=data.get("enabled_executors", []),
            default_executor=data.get("default_executor"),
            executor_configs=data.get("executor_configs", {}),
            fallback_executor=data.get("fallback_executor"),
        )


class PluginManager:
    """Manages executor plugins lifecycle.

    Provides:
    - Plugin discovery and loading
    - Plugin configuration validation
    - Plugin instance creation
    - Health monitoring
    """

    def __init__(self, discovery: PluginDiscovery | None = None) -> None:
        """Initialize plugin manager.

        Args:
            discovery: Plugin discovery instance.
        """
        self.discovery = discovery or PluginDiscovery()
        self._plugins: dict[str, DiscoveredPlugin] = {}
        self._instances: dict[str, ExecutorPlugin] = {}

    def refresh(self) -> None:
        """Refresh plugin discovery."""
        self._plugins = self.discovery.discover_all()
        self._instances.clear()

    def get_available_plugins(self) -> list[dict[str, Any]]:
        """Get list of available plugins with info.

        Returns:
            List of plugin info dicts.
        """
        if not self._plugins:
            self.refresh()

        result = []
        for plugin in self._plugins.values():
            info = {
                "name": plugin.name,
                "display_name": plugin.display_name,
                "description": plugin.description,
                "version": plugin.version,
                "source": plugin.source_type,
                "capabilities": plugin.capabilities,
                "schema": plugin.schema.to_json_schema() if plugin.schema else None,
                "error": plugin.error,
            }
            result.append(info)

        return result

    def create_executor(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        selection: ExecutorSelection | None = None,
    ) -> ExecutorPlugin:
        """Create an executor instance.

        Args:
            name: Plugin name.
            config: Executor configuration.
            selection: Project-level executor selection.

        Returns:
            ExecutorPlugin instance.

        Raises:
            ValueError: If plugin not found or disabled.
        """
        if not self._plugins:
            self.refresh()

        plugin = self._plugins.get(name)
        if not plugin:
            available = list(self._plugins.keys())
            raise ValueError(f"Unknown plugin: {name}. Available: {available}")

        if plugin.error:
            raise ValueError(f"Plugin {name} failed to load: {plugin.error}")

        # Check if enabled at project level
        if selection and not selection.is_enabled(name):
            raise ValueError(f"Plugin {name} is disabled for this project")

        # Merge configurations
        merged_config = plugin.plugin_class.get_default_config()
        if selection:
            merged_config.update(selection.get_config(name))
        if config:
            merged_config.update(config)

        # Validate configuration
        if plugin.schema:
            errors = plugin.schema.validate(merged_config)
            if errors:
                raise ValueError(f"Invalid configuration: {'; '.join(errors)}")

        # Separate base ExecutorConfig fields from plugin-specific fields
        base_fields = {
            "max_retries", "base_delay", "max_delay", "timeout",
            "model", "temperature", "max_tokens",
        }
        base_config: dict[str, Any] = {}
        extra_config: dict[str, Any] = {}

        for key, value in merged_config.items():
            if key in base_fields:
                base_config[key] = value
            else:
                extra_config[key] = value

        # Create executor config with extra fields
        if extra_config:
            base_config["extra"] = extra_config
        executor_config = ExecutorConfig(**base_config) if base_config else None

        # Create instance
        instance = plugin.plugin_class(executor_config)
        return instance

    def get_instance(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        selection: ExecutorSelection | None = None,
    ) -> ExecutorPlugin:
        """Get or create a cached executor instance.

        Args:
            name: Plugin name.
            config: Executor configuration.
            selection: Project-level executor selection.

        Returns:
            ExecutorPlugin instance.
        """
        cache_key = f"{name}:{json.dumps(config or {}, sort_keys=True)}"

        if cache_key not in self._instances:
            self._instances[cache_key] = self.create_executor(name, config, selection)

        return self._instances[cache_key]

    def check_health(self, name: str) -> dict[str, Any]:
        """Check health of a plugin.

        Args:
            name: Plugin name.

        Returns:
            Health check result.
        """
        try:
            instance = self.get_instance(name)
            healthy = instance.health_check()
            status = instance.get_plugin_status()

            return {
                "name": name,
                "healthy": healthy,
                "status": status.value,
                "info": instance.get_info(),
            }
        except Exception as e:
            return {
                "name": name,
                "healthy": False,
                "status": PluginStatus.ERROR.value,
                "error": str(e),
            }

    def check_all_health(self) -> list[dict[str, Any]]:
        """Check health of all plugins.

        Returns:
            List of health check results.
        """
        if not self._plugins:
            self.refresh()

        results = []
        for name in self._plugins:
            results.append(self.check_health(name))

        return results


# Global plugin manager instance
plugin_manager = PluginManager()
