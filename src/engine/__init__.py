"""PRDForge execution engine.

This module provides the core execution engine for PRD-driven code generation.
"""

from .config import (
    ExecutionConfig,
    RunState,
    RunStatus,
    TaskResult,
    TaskStatus,
)
from .git_manager import GitManager, GitResult
from .git_operations import (
    BranchConfig,
    ConflictStrategy,
    GitOperations,
    MergeInfo,
    MergeResult,
)
from .logging import EngineLogger, logger
from .prd_executor import BaseExecutor, DryRunExecutor, PRDExecutor, Task
from .run_manager import RunManager

__all__ = [
    # Configuration
    "ExecutionConfig",
    "RunState",
    "RunStatus",
    "TaskResult",
    "TaskStatus",
    "BranchConfig",
    "ConflictStrategy",
    "MergeInfo",
    "MergeResult",
    # Managers
    "RunManager",
    "PRDExecutor",
    "GitManager",
    "GitResult",
    "GitOperations",
    # Executors
    "BaseExecutor",
    "DryRunExecutor",
    "Task",
    # Logging
    "EngineLogger",
    "logger",
]
