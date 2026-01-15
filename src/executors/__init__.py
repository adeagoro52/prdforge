"""AI executor implementations for PRDForge.

This module provides the executor abstraction layer for different AI backends.
"""

from .base import (
    BaseExecutor,
    ExecutionResult,
    ExecutorConfig,
    ExecutorStatus,
    TaskContext,
)
from .claude_api_executor import ClaudeAPIConfig, ClaudeAPIExecutor
from .claude_cli import ClaudeCLIConfig, ClaudeCLIExecutor, OutputParser
from .dry_run import DryRunExecutor
from .factory import ExecutorFactory, ExecutorRegistry, executor_factory
from .gemini_executor import GeminiConfig, GeminiExecutor
from .openai_executor import OpenAIConfig, OpenAIExecutor
from .selector import ExecutorHealth, ExecutorSelector, SelectionResult, SelectionStrategy
from .plugin import (
    DiscoveredPlugin,
    ExecutorPlugin,
    ExecutorSelection,
    PluginConfigField,
    PluginDiscovery,
    PluginManager,
    PluginSchema,
    PluginStatus,
    plugin_manager,
)

__all__ = [
    # Base classes
    "BaseExecutor",
    "ExecutorConfig",
    "ExecutorStatus",
    "ExecutionResult",
    "TaskContext",
    # Plugin system
    "ExecutorPlugin",
    "PluginSchema",
    "PluginConfigField",
    "PluginStatus",
    "DiscoveredPlugin",
    "PluginDiscovery",
    "PluginManager",
    "ExecutorSelection",
    "plugin_manager",
    # Claude CLI
    "ClaudeCLIExecutor",
    "ClaudeCLIConfig",
    "OutputParser",
    # Claude API
    "ClaudeAPIExecutor",
    "ClaudeAPIConfig",
    # OpenAI
    "OpenAIExecutor",
    "OpenAIConfig",
    # Gemini
    "GeminiExecutor",
    "GeminiConfig",
    # Selector
    "ExecutorSelector",
    "SelectionStrategy",
    "SelectionResult",
    "ExecutorHealth",
    # Factory
    "ExecutorFactory",
    "ExecutorRegistry",
    "DryRunExecutor",
    "executor_factory",
]
