"""Unit tests for project configuration system."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.config import (
    ConfigLoader,
    ConfigValidationError,
    ConfigValidator,
    ExecutorSettings,
    GitSettings,
    PRDForgeConfig,
    ProjectConfig,
    load_project_config,
)
from src.config.models import ProjectType
from src.config.loader import create_default_config, write_config_file


class TestProjectConfig:
    """Tests for ProjectConfig model."""

    def test_default_values(self):
        config = ProjectConfig(name="test", path="/tmp/test")
        assert config.name == "test"
        assert config.project_type == ProjectType.LOCAL
        assert len(config.prd_patterns) > 0
        assert isinstance(config.git, GitSettings)
        assert isinstance(config.executor, ExecutorSettings)

    def test_string_project_type_conversion(self):
        config = ProjectConfig(name="test", path="/tmp", project_type="git")
        assert config.project_type == ProjectType.GIT

    def test_dict_to_settings_conversion(self):
        config = ProjectConfig(
            name="test",
            path="/tmp",
            git={"default_branch": "main", "auto_commit": False},
            executor={"max_retries": 5},
        )
        assert config.git.default_branch == "main"
        assert config.git.auto_commit is False
        assert config.executor.max_retries == 5

    def test_is_git_url(self):
        local = ProjectConfig(name="test", path="/tmp/project")
        assert not local.is_git_url

        https = ProjectConfig(name="test", path="https://github.com/user/repo.git")
        assert https.is_git_url

        ssh = ProjectConfig(name="test", path="git@github.com:user/repo.git")
        assert ssh.is_git_url

    def test_to_dict(self):
        config = ProjectConfig(name="test", path="/tmp/test")
        d = config.to_dict()
        assert d["name"] == "test"
        assert d["path"] == "/tmp/test"
        assert "git" in d
        assert "executor" in d


class TestGitSettings:
    """Tests for GitSettings model."""

    def test_defaults(self):
        settings = GitSettings()
        assert settings.default_branch == "develop"
        assert settings.auto_commit is True
        assert settings.auto_push is False


class TestExecutorSettings:
    """Tests for ExecutorSettings model."""

    def test_defaults(self):
        settings = ExecutorSettings()
        assert settings.default_executor == "claude-cli"
        assert settings.max_retries == 2
        assert settings.timeout_seconds == 600
        assert "Read" in settings.allowed_tools


class TestPRDForgeConfig:
    """Tests for PRDForgeConfig model."""

    def test_empty_config(self):
        config = PRDForgeConfig()
        assert config.version == "1"
        assert len(config.projects) == 0

    def test_project_from_dict(self):
        config = PRDForgeConfig(
            projects=[
                {"name": "test", "path": "/tmp/test"},
            ]
        )
        assert len(config.projects) == 1
        assert isinstance(config.projects[0], ProjectConfig)

    def test_get_project_by_name(self):
        config = PRDForgeConfig(
            projects=[
                ProjectConfig(name="proj1", path="/tmp/1"),
                ProjectConfig(name="proj2", path="/tmp/2"),
            ]
        )
        proj = config.get_project("proj2")
        assert proj is not None
        assert proj.name == "proj2"

    def test_get_default_project(self):
        config = PRDForgeConfig(
            projects=[
                ProjectConfig(name="proj1", path="/tmp/1"),
                ProjectConfig(name="proj2", path="/tmp/2"),
            ],
            default_project="proj1",
        )
        proj = config.get_project()
        assert proj is not None
        assert proj.name == "proj1"

    def test_get_single_project(self):
        config = PRDForgeConfig(
            projects=[ProjectConfig(name="only", path="/tmp")]
        )
        proj = config.get_project()
        assert proj is not None
        assert proj.name == "only"

    def test_add_project(self):
        config = PRDForgeConfig()
        config.add_project(ProjectConfig(name="new", path="/tmp"))
        assert len(config.projects) == 1

    def test_add_duplicate_raises(self):
        config = PRDForgeConfig(
            projects=[ProjectConfig(name="test", path="/tmp")]
        )
        with pytest.raises(ValueError, match="already exists"):
            config.add_project(ProjectConfig(name="test", path="/other"))

    def test_resolved_paths(self):
        config = PRDForgeConfig(
            workspace_dir="~/.prdforge/workspaces",
            database_path="~/.prdforge/db.sqlite",
        )
        assert config.resolved_workspace_dir.is_absolute()
        assert config.resolved_database_path.is_absolute()


class TestConfigValidator:
    """Tests for ConfigValidator."""

    @pytest.fixture
    def validator(self):
        return ConfigValidator()

    def test_valid_config(self, validator, tmp_path):
        config = PRDForgeConfig(
            projects=[
                ProjectConfig(name="test", path=str(tmp_path)),
            ]
        )
        result = validator.validate(config)
        assert result.valid

    def test_invalid_log_level(self, validator):
        config = PRDForgeConfig(log_level="INVALID")
        result = validator.validate(config)
        assert not result.valid
        assert any("log_level" in e for e in result.errors)

    def test_invalid_executor(self, validator, tmp_path):
        config = PRDForgeConfig(
            projects=[
                ProjectConfig(
                    name="test",
                    path=str(tmp_path),
                    executor=ExecutorSettings(default_executor="invalid"),
                ),
            ]
        )
        result = validator.validate(config)
        assert not result.valid

    def test_duplicate_project_names(self, validator, tmp_path):
        config = PRDForgeConfig(
            projects=[
                ProjectConfig(name="dupe", path=str(tmp_path)),
                ProjectConfig(name="dupe", path=str(tmp_path / "other")),
            ]
        )
        result = validator.validate(config)
        assert not result.valid
        assert any("Duplicate" in e for e in result.errors)

    def test_nonexistent_path_warning(self, validator):
        config = PRDForgeConfig(
            projects=[
                ProjectConfig(name="test", path="/nonexistent/path/12345"),
            ]
        )
        result = validator.validate(config)
        # Should be warning, not error
        assert result.valid
        assert any("does not exist" in w for w in result.warnings)

    def test_invalid_git_url(self, validator):
        config = PRDForgeConfig(
            projects=[
                ProjectConfig(
                    name="test",
                    path="not-a-git-url",
                    project_type=ProjectType.GIT,
                ),
            ]
        )
        result = validator.validate(config)
        assert not result.valid
        assert any("Invalid git URL" in e for e in result.errors)

    def test_validate_and_raise(self, validator):
        config = PRDForgeConfig(log_level="INVALID")
        with pytest.raises(ConfigValidationError) as exc_info:
            validator.validate_and_raise(config)
        assert len(exc_info.value.errors) > 0


class TestConfigLoader:
    """Tests for ConfigLoader."""

    @pytest.fixture
    def loader(self):
        return ConfigLoader(validate=False)

    def test_load_json_file(self, loader, tmp_path):
        config_file = tmp_path / "prdforge.json"
        config_file.write_text(json.dumps({
            "log_level": "DEBUG",
            "projects": [{"name": "test", "path": str(tmp_path)}],
        }))

        config = loader.load(config_file)
        assert config.log_level == "DEBUG"
        assert len(config.projects) == 1

    def test_load_with_env_override(self, loader, tmp_path, monkeypatch):
        config_file = tmp_path / "prdforge.json"
        config_file.write_text(json.dumps({
            "log_level": "INFO",
        }))

        monkeypatch.setenv("PRDFORGE_LOG_LEVEL", "DEBUG")
        config = loader.load(config_file)
        assert config.log_level == "DEBUG"

    def test_load_missing_file_raises(self, loader):
        with pytest.raises(ConfigValidationError, match="not found"):
            loader.load("/nonexistent/config.json")

    def test_find_config_in_cwd(self, loader, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "prdforge.json"
        config_file.write_text(json.dumps({"log_level": "DEBUG"}))

        config = loader.load()
        assert config.log_level == "DEBUG"


class TestLoadProjectConfig:
    """Tests for load_project_config convenience function."""

    def test_load_single_project(self, tmp_path):
        config_file = tmp_path / "prdforge.json"
        config_file.write_text(json.dumps({
            "projects": [{"name": "test", "path": str(tmp_path)}],
        }))

        project = load_project_config(config_file)
        assert project.name == "test"

    def test_load_named_project(self, tmp_path):
        config_file = tmp_path / "prdforge.json"
        config_file.write_text(json.dumps({
            "projects": [
                {"name": "proj1", "path": str(tmp_path)},
                {"name": "proj2", "path": str(tmp_path / "other")},
            ],
        }))

        project = load_project_config(config_file, project_name="proj2")
        assert project.name == "proj2"

    def test_project_not_found_raises(self, tmp_path):
        config_file = tmp_path / "prdforge.json"
        config_file.write_text(json.dumps({
            "projects": [{"name": "test", "path": str(tmp_path)}],
        }))

        with pytest.raises(ConfigValidationError, match="not found"):
            load_project_config(config_file, project_name="nonexistent")


class TestCreateDefaultConfig:
    """Tests for create_default_config helper."""

    def test_create_from_path(self, tmp_path):
        config = create_default_config(tmp_path)
        assert len(config.projects) == 1
        assert config.projects[0].name == tmp_path.name
        assert config.projects[0].path == str(tmp_path)

    def test_create_with_name(self, tmp_path):
        config = create_default_config(tmp_path, project_name="custom")
        assert config.projects[0].name == "custom"


class TestWriteConfigFile:
    """Tests for write_config_file helper."""

    def test_write_json(self, tmp_path):
        config = PRDForgeConfig(
            projects=[ProjectConfig(name="test", path=str(tmp_path))]
        )
        output = tmp_path / "output.json"
        write_config_file(config, output, format="json")

        content = json.loads(output.read_text())
        assert content["projects"][0]["name"] == "test"

    def test_invalid_format_raises(self, tmp_path):
        config = PRDForgeConfig()
        with pytest.raises(ValueError, match="Unknown format"):
            write_config_file(config, tmp_path / "out.txt", format="invalid")
