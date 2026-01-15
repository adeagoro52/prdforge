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
from .claude_cli import ClaudeCLIConfig, ClaudeCLIExecutor, OutputParser
from .factory import DryRunExecutor, ExecutorFactory, ExecutorRegistry, executor_factory

__all__ = [
    # Base classes
    "BaseExecutor",
    "ExecutorConfig",
    "ExecutorStatus",
    "ExecutionResult",
    "TaskContext",
    # Claude CLI
    "ClaudeCLIExecutor",
    "ClaudeCLIConfig",
    "OutputParser",
    # Factory
    "ExecutorFactory",
    "ExecutorRegistry",
    "DryRunExecutor",
    "executor_factory",
]
