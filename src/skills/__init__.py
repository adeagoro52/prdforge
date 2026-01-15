"""PRDForge Skills System.

This module provides:
- Base Skill class for defining reusable automation tasks
- Built-in skills for common operations (code review, simplify, etc.)
- SkillRegistry for discovering and managing skills
- Support for skill inheritance and project-level overrides
- Hook system for post-task automation
"""

from .base import Skill, SkillConfig, SkillResult, SkillError
from .registry import SkillRegistry
from .builtin import (
    CodeReviewSkill,
    CodeSimplifySkill,
    LintSkill,
    RunTestsSkill,
    TypeCheckSkill,
)
from .hooks import (
    Hook,
    HookBehavior,
    HookError,
    HookResult,
    HookRunner,
    HookType,
    create_hooks_from_config,
)

__all__ = [
    # Base classes
    "Skill",
    "SkillConfig",
    "SkillResult",
    "SkillError",
    # Registry
    "SkillRegistry",
    # Built-in skills
    "CodeReviewSkill",
    "CodeSimplifySkill",
    "LintSkill",
    "RunTestsSkill",
    "TypeCheckSkill",
    # Hooks
    "Hook",
    "HookBehavior",
    "HookError",
    "HookResult",
    "HookRunner",
    "HookType",
    "create_hooks_from_config",
]
