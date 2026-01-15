"""Unit tests for the skills system."""

import tempfile
from pathlib import Path

import pytest

from src.skills import (
    CodeReviewSkill,
    CodeSimplifySkill,
    LintSkill,
    Skill,
    SkillConfig,
    SkillError,
    SkillRegistry,
    RunTestsSkill,
    TypeCheckSkill,
)
from src.skills.base import SkillContext, SkillResult, SkillSource, SkillStatus


class TestSkillConfig:
    """Tests for SkillConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SkillConfig()
        assert config.enabled is True
        assert config.timeout == 300
        assert config.retry_count == 0
        assert config.env == {}
        assert config.options == {}

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "enabled": False,
            "timeout": 60,
            "retry_count": 3,
            "env": {"MY_VAR": "value"},
            "options": {"verbose": True},
        }
        config = SkillConfig.from_dict(data)
        assert config.enabled is False
        assert config.timeout == 60
        assert config.retry_count == 3
        assert config.env == {"MY_VAR": "value"}
        assert config.options == {"verbose": True}

    def test_config_to_dict(self):
        """Test converting config to dictionary."""
        config = SkillConfig(
            enabled=False,
            timeout=120,
            retry_count=2,
            env={"KEY": "val"},
            options={"opt": 1},
        )
        data = config.to_dict()
        assert data["enabled"] is False
        assert data["timeout"] == 120
        assert data["retry_count"] == 2
        assert data["env"] == {"KEY": "val"}
        assert data["options"] == {"opt": 1}


class TestSkillResult:
    """Tests for SkillResult."""

    def test_success_result(self):
        """Test successful result."""
        result = SkillResult(status=SkillStatus.SUCCESS, output="Done")
        assert result.success is True
        assert result.failed is False
        assert result.output == "Done"

    def test_failed_result(self):
        """Test failed result."""
        result = SkillResult(
            status=SkillStatus.FAILED,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.failed is True
        assert result.error == "Something went wrong"

    def test_skipped_result(self):
        """Test skipped result."""
        result = SkillResult(status=SkillStatus.SKIPPED)
        assert result.success is False
        assert result.failed is False


class TestSkillContext:
    """Tests for SkillContext."""

    def test_default_working_dir(self):
        """Test default working directory is project path."""
        project_path = Path("/test/project")
        context = SkillContext(project_path=project_path)
        assert context.working_dir == project_path

    def test_explicit_working_dir(self):
        """Test explicit working directory."""
        project_path = Path("/test/project")
        working_dir = Path("/test/project/src")
        context = SkillContext(project_path=project_path, working_dir=working_dir)
        assert context.working_dir == working_dir

    def test_dry_run_flag(self):
        """Test dry run flag."""
        context = SkillContext(project_path=Path("/test"), dry_run=True)
        assert context.dry_run is True


class TestConcreteSkill:
    """Test a concrete skill implementation."""

    def test_lint_skill_attributes(self):
        """Test LintSkill has correct attributes."""
        skill = LintSkill()
        assert skill.name == "lint"
        assert skill.category == "quality"
        assert len(skill.description) > 0

    def test_run_tests_skill_attributes(self):
        """Test RunTestsSkill has correct attributes."""
        skill = RunTestsSkill()
        assert skill.name == "test"
        assert skill.category == "quality"

    def test_typecheck_skill_attributes(self):
        """Test TypeCheckSkill has correct attributes."""
        skill = TypeCheckSkill()
        assert skill.name == "typecheck"
        assert skill.category == "quality"

    def test_code_review_skill_attributes(self):
        """Test CodeReviewSkill has correct attributes."""
        skill = CodeReviewSkill()
        assert skill.name == "code-review"
        assert skill.category == "ai"

    def test_code_simplify_skill_attributes(self):
        """Test CodeSimplifySkill has correct attributes."""
        skill = CodeSimplifySkill()
        assert skill.name == "code-simplify"
        assert skill.category == "ai"

    def test_skill_validate(self):
        """Test skill validation."""
        skill = LintSkill()
        errors = skill.validate()
        assert errors == []

    def test_skill_validate_negative_timeout(self):
        """Test validation rejects negative timeout."""
        skill = LintSkill(config=SkillConfig(timeout=-1))
        errors = skill.validate()
        assert any("timeout" in e.lower() for e in errors)

    def test_skill_dry_run(self):
        """Test skill in dry run mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            (project_path / "pyproject.toml").touch()

            skill = LintSkill()
            context = SkillContext(project_path=project_path, dry_run=True)
            result = skill.execute(context)

            assert result.status == SkillStatus.SKIPPED
            assert "DRY RUN" in result.output


class TestSkillRegistry:
    """Tests for SkillRegistry."""

    def test_register_skill(self):
        """Test registering a skill."""
        registry = SkillRegistry()
        skill = LintSkill()
        registry.register(skill)
        assert registry.get("lint") is skill

    def test_register_duplicate_no_override(self):
        """Test registering duplicate without override raises."""
        registry = SkillRegistry()
        skill1 = LintSkill()
        skill2 = LintSkill()
        registry.register(skill1)
        with pytest.raises(SkillError):
            registry.register(skill2, override=False)

    def test_register_duplicate_with_override(self):
        """Test registering duplicate with override succeeds."""
        registry = SkillRegistry()
        skill1 = LintSkill()
        skill2 = LintSkill()
        registry.register(skill1)
        registry.register(skill2, override=True)
        assert registry.get("lint") is skill2

    def test_unregister_skill(self):
        """Test unregistering a skill."""
        registry = SkillRegistry()
        skill = LintSkill()
        registry.register(skill)
        assert registry.unregister("lint") is True
        assert registry.get("lint") is None

    def test_unregister_nonexistent(self):
        """Test unregistering non-existent skill."""
        registry = SkillRegistry()
        assert registry.unregister("nonexistent") is False

    def test_get_nonexistent(self):
        """Test getting non-existent skill."""
        registry = SkillRegistry()
        assert registry.get("nonexistent") is None

    def test_get_or_raise(self):
        """Test get_or_raise raises for non-existent skill."""
        registry = SkillRegistry()
        with pytest.raises(SkillError):
            registry.get_or_raise("nonexistent")

    def test_list_all(self):
        """Test listing all skills."""
        registry = SkillRegistry()
        registry.register(LintSkill())
        registry.register(RunTestsSkill())
        skills = registry.list_all()
        assert len(skills) == 2
        names = [s.name for s in skills]
        assert "lint" in names
        assert "test" in names

    def test_list_names(self):
        """Test listing skill names."""
        registry = SkillRegistry()
        registry.register(LintSkill())
        registry.register(RunTestsSkill())
        names = registry.list_names()
        assert "lint" in names
        assert "test" in names

    def test_discover_builtin(self):
        """Test discovering built-in skills."""
        registry = SkillRegistry()
        count = registry.discover_builtin()
        assert count >= 5  # lint, test, typecheck, code-review, code-simplify
        assert registry.get("lint") is not None
        assert registry.get("test") is not None

    def test_get_source(self):
        """Test getting skill source."""
        registry = SkillRegistry()
        skill = LintSkill(source=SkillSource.PROJECT)
        registry.register(skill)
        assert registry.get_source("lint") == SkillSource.PROJECT

    def test_discover_user_skills_empty(self):
        """Test discovering from empty user directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = SkillRegistry()
            count = registry.discover_user_skills(Path(tmpdir))
            assert count == 0

    def test_discover_project_skills_empty(self):
        """Test discovering from empty project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = SkillRegistry()
            count = registry.discover_project_skills(Path(tmpdir))
            assert count == 0

    def test_discover_project_skills_from_yaml(self):
        """Test discovering skills from YAML config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            skills_dir = project_path / ".prdforge" / "skills"
            skills_dir.mkdir(parents=True)

            # Create a YAML skill config
            skill_config = """
name: my-custom-skill
description: A custom skill
type: command
command: echo "Hello from custom skill"
"""
            (skills_dir / "custom.yaml").write_text(skill_config)

            registry = SkillRegistry()
            count = registry.discover_project_skills(project_path)
            assert count == 1
            skill = registry.get("my-custom-skill")
            assert skill is not None
            assert skill.description == "A custom skill"
            assert skill.source == SkillSource.PROJECT

    def test_skill_override_hierarchy(self):
        """Test skill override: project > user > package."""
        registry = SkillRegistry()

        # Register built-in
        registry.discover_builtin()
        assert registry.get_source("lint") == SkillSource.PACKAGE

        # Create user skill that overrides
        with tempfile.TemporaryDirectory() as user_dir:
            skills_dir = Path(user_dir) / "skills"
            skills_dir.mkdir()
            skill_config = """
name: lint
description: User-level lint
type: command
command: echo "User lint"
"""
            (skills_dir / "lint.yaml").write_text(skill_config)
            registry.discover_user_skills(Path(user_dir))
            assert registry.get_source("lint") == SkillSource.USER

        # Create project skill that overrides user
        with tempfile.TemporaryDirectory() as project_dir:
            skills_dir = Path(project_dir) / ".prdforge" / "skills"
            skills_dir.mkdir(parents=True)
            skill_config = """
name: lint
description: Project-level lint
type: command
command: echo "Project lint"
"""
            (skills_dir / "lint.yaml").write_text(skill_config)
            registry.discover_project_skills(Path(project_dir))
            assert registry.get_source("lint") == SkillSource.PROJECT
            assert registry.get("lint").description == "Project-level lint"


class TestSkillExecution:
    """Tests for skill execution."""

    def test_lint_skill_auto_detect_python(self):
        """Test lint skill auto-detects Python project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            (project_path / "pyproject.toml").write_text("[project]\nname='test'\n")

            skill = LintSkill()
            context = SkillContext(project_path=project_path, dry_run=True)
            result = skill.execute(context)

            # Dry run should succeed
            assert result.status == SkillStatus.SKIPPED
            assert "DRY RUN" in result.output

    def test_test_skill_auto_detect_pytest(self):
        """Test test skill auto-detects pytest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            (project_path / "pytest.ini").write_text("[pytest]\n")

            skill = RunTestsSkill()
            context = SkillContext(project_path=project_path, dry_run=True)
            result = skill.execute(context)

            assert result.status == SkillStatus.SKIPPED

    def test_skill_no_auto_detect(self):
        """Test skill skips when can't auto-detect."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            # Empty directory - no project files

            skill = LintSkill()
            context = SkillContext(project_path=project_path)
            result = skill.execute(context)

            assert result.status == SkillStatus.SKIPPED
            assert "auto-detect" in result.output.lower()
