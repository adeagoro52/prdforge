"""Skill registry for discovering and managing skills.

This module provides:
- Skill discovery from package, user, and project directories
- Skill override/inheritance system
- Configuration loading and validation
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

from .base import Skill, SkillConfig, SkillError, SkillSource
from .builtin import BUILTIN_SKILLS


class SkillRegistry:
    """Registry for discovering and managing skills.

    The registry supports a layered skill system:
    1. Package skills (built-in)
    2. User skills (~/.prdforge/skills/)
    3. Project skills (.prdforge/skills/)

    Skills at lower layers override those at higher layers,
    allowing projects to customize behavior.

    Example usage::

        registry = SkillRegistry()
        registry.discover_builtin()
        registry.discover_user_skills()
        registry.discover_project_skills(Path("/path/to/project"))

        skill = registry.get("lint")
        result = skill.execute(context)
    """

    def __init__(self):
        """Initialize the registry."""
        self._skills: dict[str, Skill] = {}
        self._skill_sources: dict[str, SkillSource] = {}

    def register(self, skill: Skill, override: bool = True) -> None:
        """Register a skill.

        Args:
            skill: Skill instance to register.
            override: If True, override existing skill with same name.

        Raises:
            SkillError: If skill with same name exists and override=False.
        """
        if not skill.name:
            raise SkillError("Cannot register skill without a name")

        if skill.name in self._skills and not override:
            raise SkillError(
                f"Skill '{skill.name}' already registered",
                skill_name=skill.name,
            )

        # Validate the skill
        errors = skill.validate()
        if errors:
            raise SkillError(
                f"Skill validation failed: {'; '.join(errors)}",
                skill_name=skill.name,
            )

        self._skills[skill.name] = skill
        self._skill_sources[skill.name] = skill.source

    def unregister(self, name: str) -> bool:
        """Unregister a skill by name.

        Args:
            name: Name of the skill to unregister.

        Returns:
            True if skill was removed, False if not found.
        """
        if name in self._skills:
            del self._skills[name]
            del self._skill_sources[name]
            return True
        return False

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name.

        Args:
            name: Name of the skill.

        Returns:
            Skill instance or None if not found.
        """
        return self._skills.get(name)

    def get_or_raise(self, name: str) -> Skill:
        """Get a skill by name, raising if not found.

        Args:
            name: Name of the skill.

        Returns:
            Skill instance.

        Raises:
            SkillError: If skill not found.
        """
        skill = self.get(name)
        if skill is None:
            raise SkillError(f"Skill '{name}' not found", skill_name=name)
        return skill

    def list_all(self) -> list[Skill]:
        """List all registered skills.

        Returns:
            List of all skill instances.
        """
        return list(self._skills.values())

    def list_names(self) -> list[str]:
        """List names of all registered skills.

        Returns:
            List of skill names.
        """
        return list(self._skills.keys())

    def get_source(self, name: str) -> Optional[SkillSource]:
        """Get the source of a skill.

        Args:
            name: Name of the skill.

        Returns:
            SkillSource or None if not found.
        """
        return self._skill_sources.get(name)

    def discover_builtin(self) -> int:
        """Discover and register built-in skills.

        Returns:
            Number of skills registered.
        """
        count = 0
        for name, skill_class in BUILTIN_SKILLS.items():
            skill = skill_class(source=SkillSource.PACKAGE)
            self.register(skill, override=False)
            count += 1
        return count

    def discover_user_skills(self, user_dir: Optional[Path] = None) -> int:
        """Discover and register user-level skills.

        Args:
            user_dir: User config directory (default: ~/.prdforge).

        Returns:
            Number of skills registered.
        """
        if user_dir is None:
            user_dir = Path.home() / ".prdforge"

        skills_dir = user_dir / "skills"
        if not skills_dir.exists():
            return 0

        return self._discover_skills_from_dir(skills_dir, SkillSource.USER)

    def discover_project_skills(self, project_path: Path) -> int:
        """Discover and register project-level skills.

        Args:
            project_path: Path to the project directory.

        Returns:
            Number of skills registered.
        """
        skills_dir = project_path / ".prdforge" / "skills"
        if not skills_dir.exists():
            return 0

        return self._discover_skills_from_dir(skills_dir, SkillSource.PROJECT)

    def _discover_skills_from_dir(self, skills_dir: Path, source: SkillSource) -> int:
        """Discover skills from a directory.

        Args:
            skills_dir: Directory containing skill definitions.
            source: Source to assign to discovered skills.

        Returns:
            Number of skills registered.
        """
        count = 0

        # Load Python skill modules
        for py_file in skills_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                skill = self._load_skill_from_python(py_file, source)
                if skill:
                    self.register(skill, override=True)
                    count += 1
            except Exception as e:
                # Log but don't fail on individual skill errors
                print(f"Warning: Failed to load skill from {py_file}: {e}")

        # Load YAML/JSON skill configs
        for config_file in list(skills_dir.glob("*.yaml")) + list(skills_dir.glob("*.yml")) + list(skills_dir.glob("*.json")):
            if config_file.name.startswith("_"):
                continue
            try:
                skill = self._load_skill_from_config(config_file, source)
                if skill:
                    self.register(skill, override=True)
                    count += 1
            except Exception as e:
                print(f"Warning: Failed to load skill config from {config_file}: {e}")

        return count

    def _load_skill_from_python(self, py_file: Path, source: SkillSource) -> Optional[Skill]:
        """Load a skill from a Python file.

        Args:
            py_file: Path to Python file.
            source: Source to assign.

        Returns:
            Skill instance or None.
        """
        module_name = f"prdforge_skill_{py_file.stem}"

        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Look for a Skill subclass in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, Skill)
                and attr is not Skill
                and hasattr(attr, "name")
                and attr.name
            ):
                return attr(source=source)

        return None

    def _load_skill_from_config(
        self,
        config_file: Path,
        source: SkillSource,
    ) -> Optional[Skill]:
        """Load a skill from a YAML/JSON config file.

        Config format::

            name: my-skill
            description: My custom skill
            type: command  # or 'script'
            command: echo "Hello"
            # OR
            script: path/to/script.sh

        Args:
            config_file: Path to config file.
            source: Source to assign.

        Returns:
            Skill instance or None.
        """
        with open(config_file) as f:
            if config_file.suffix == ".json":
                data = json.load(f)
            else:
                data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            return None

        name = data.get("name")
        if not name:
            return None

        skill_type = data.get("type", "command")
        config = SkillConfig.from_dict(data.get("config", {}))

        if skill_type == "command":
            return ConfiguredCommandSkill(
                name=name,
                description=data.get("description", ""),
                command=data.get("command", "echo 'No command specified'"),
                config=config,
                source=source,
            )

        return None

    def load_config_for_skill(
        self,
        skill_name: str,
        config_data: dict[str, Any],
    ) -> None:
        """Load configuration for an existing skill.

        Args:
            skill_name: Name of the skill to configure.
            config_data: Configuration data.
        """
        skill = self.get(skill_name)
        if skill:
            skill.config = SkillConfig.from_dict(config_data)


class ConfiguredCommandSkill(Skill):
    """A skill configured from YAML/JSON that runs a command."""

    def __init__(
        self,
        name: str,
        description: str,
        command: str,
        config: Optional[SkillConfig] = None,
        source: SkillSource = SkillSource.USER,
    ):
        """Initialize configured command skill.

        Args:
            name: Skill name.
            description: Skill description.
            command: Command to execute.
            config: Skill configuration.
            source: Skill source.
        """
        super().__init__(config=config, source=source)
        self.name = name
        self.description = description
        self.command = command
        self.category = "custom"

    def execute(self, context: "SkillContext") -> "SkillResult":
        """Execute the configured command.

        Args:
            context: Execution context.

        Returns:
            SkillResult with command output.
        """
        import subprocess
        import time

        from .base import SkillContext, SkillResult, SkillStatus

        start_time = time.time()

        if context.dry_run:
            return SkillResult(
                status=SkillStatus.SKIPPED,
                output=f"[DRY RUN] Would execute: {self.command}",
            )

        try:
            # Substitute placeholders in command
            command = self.command.replace("{project_path}", str(context.project_path))
            command = command.replace("{working_dir}", str(context.working_dir or context.project_path))

            result = subprocess.run(
                command,
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
                error=None if result.returncode == 0 else f"Command exited with code {result.returncode}",
                duration=duration,
            )

        except subprocess.TimeoutExpired:
            return SkillResult(
                status=SkillStatus.FAILED,
                error=f"Command timed out after {self.config.timeout} seconds",
                duration=time.time() - start_time,
            )
        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time,
            )


# Global default registry
_default_registry: Optional[SkillRegistry] = None


def get_default_registry() -> SkillRegistry:
    """Get the default skill registry.

    Returns:
        Default SkillRegistry instance with built-in skills.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = SkillRegistry()
        _default_registry.discover_builtin()
        _default_registry.discover_user_skills()
    return _default_registry
