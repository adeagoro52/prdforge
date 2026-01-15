"""Configuration data models for PRDForge."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ProjectType(Enum):
    """Type of project source."""

    LOCAL = "local"  # Local filesystem path
    GIT = "git"  # Git repository URL


@dataclass
class GitSettings:
    """Git-related configuration settings.

    Attributes:
        default_branch: Default branch to use as base (default: develop).
        auto_commit: Whether to auto-commit after each task.
        auto_push: Whether to push after commits.
        commit_template: Template for commit messages.
        run_branch_prefix: Prefix for run branch names.
    """

    default_branch: str = "develop"
    auto_commit: bool = True
    auto_push: bool = False
    commit_template: str = "[PRDForge] {task_id}: {description}"
    run_branch_prefix: str = "prdforge/run"


@dataclass
class ExecutorSettings:
    """AI executor configuration settings.

    Attributes:
        default_executor: Default executor to use (claude-cli, codex, gemini).
        max_retries: Maximum retry attempts for failed tasks.
        timeout_seconds: Timeout per task in seconds.
        claude_cli_path: Path to claude CLI binary (auto-detected if None).
        claude_model: Claude model to use.
        allowed_tools: List of allowed tools for Claude CLI.
    """

    default_executor: str = "claude-cli"
    max_retries: int = 2
    timeout_seconds: int = 600
    claude_cli_path: str | None = None
    claude_model: str = "sonnet"
    allowed_tools: list[str] = field(default_factory=lambda: [
        "Read", "Write", "Edit", "Bash", "Glob", "Grep"
    ])


@dataclass
class ProjectConfig:
    """Configuration for an individual project.

    Attributes:
        name: Human-readable project name.
        path: Local filesystem path or git URL.
        project_type: Type of project (local or git).
        prd_patterns: Glob patterns for finding PRD files.
        skills_dir: Directory containing project-specific skills.
        git: Git-related settings.
        executor: Executor settings.
        hooks: Post-task hooks configuration.
        metadata: Additional project metadata.
    """

    name: str
    path: str
    project_type: ProjectType = ProjectType.LOCAL
    prd_patterns: list[str] = field(default_factory=lambda: [
        "docs/prds/*.json",
        "docs/prds/*.md",
        "*.prd.json",
        "*.prd.md",
    ])
    skills_dir: str = ".prdforge/skills"
    git: GitSettings = field(default_factory=GitSettings)
    executor: ExecutorSettings = field(default_factory=ExecutorSettings)
    hooks: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize and validate basic fields."""
        # Convert string project_type to enum
        if isinstance(self.project_type, str):
            self.project_type = ProjectType(self.project_type.lower())

        # Convert nested dicts to dataclasses
        if isinstance(self.git, dict):
            self.git = GitSettings(**self.git)
        if isinstance(self.executor, dict):
            self.executor = ExecutorSettings(**self.executor)

    @property
    def resolved_path(self) -> Path:
        """Get the resolved local path for this project.

        For local projects, returns the path directly.
        For git projects, returns the workspace directory.
        """
        if self.project_type == ProjectType.LOCAL:
            return Path(self.path).resolve()
        # For git projects, path is stored in workspace after clone
        return Path(self.path)

    @property
    def is_git_url(self) -> bool:
        """Check if path is a git URL."""
        path_lower = self.path.lower()
        return (
            path_lower.startswith("git@")
            or path_lower.startswith("https://")
            or path_lower.startswith("http://")
            or path_lower.endswith(".git")
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "path": self.path,
            "project_type": self.project_type.value,
            "prd_patterns": self.prd_patterns,
            "skills_dir": self.skills_dir,
            "git": {
                "default_branch": self.git.default_branch,
                "auto_commit": self.git.auto_commit,
                "auto_push": self.git.auto_push,
                "commit_template": self.git.commit_template,
                "run_branch_prefix": self.git.run_branch_prefix,
            },
            "executor": {
                "default_executor": self.executor.default_executor,
                "max_retries": self.executor.max_retries,
                "timeout_seconds": self.executor.timeout_seconds,
                "claude_cli_path": self.executor.claude_cli_path,
                "claude_model": self.executor.claude_model,
                "allowed_tools": self.executor.allowed_tools,
            },
            "hooks": self.hooks,
            "metadata": self.metadata,
        }


@dataclass
class PRDForgeConfig:
    """Global PRDForge configuration.

    This is the root configuration that can contain multiple projects
    and global settings.

    Attributes:
        version: Configuration schema version.
        projects: List of project configurations.
        default_project: Name of the default project.
        workspace_dir: Directory for git workspaces.
        database_path: Path to SQLite database.
        log_level: Logging level.
        log_format: Logging format (json or pretty).
    """

    version: str = "1"
    projects: list[ProjectConfig] = field(default_factory=list)
    default_project: str | None = None
    workspace_dir: str = "~/.prdforge/workspaces"
    database_path: str = "~/.prdforge/prdforge.db"
    log_level: str = "INFO"
    log_format: str = "pretty"

    def __post_init__(self) -> None:
        """Convert nested dicts to ProjectConfig objects."""
        converted_projects = []
        for proj in self.projects:
            if isinstance(proj, dict):
                converted_projects.append(ProjectConfig(**proj))
            else:
                converted_projects.append(proj)
        self.projects = converted_projects

    def get_project(self, name: str | None = None) -> ProjectConfig | None:
        """Get a project by name, or the default project."""
        if name is None:
            name = self.default_project

        if name is None and len(self.projects) == 1:
            return self.projects[0]

        for project in self.projects:
            if project.name == name:
                return project
        return None

    def add_project(self, project: ProjectConfig) -> None:
        """Add a project to the configuration."""
        # Check for duplicate names
        existing = self.get_project(project.name)
        if existing:
            raise ValueError(f"Project '{project.name}' already exists")
        self.projects.append(project)

    @property
    def resolved_workspace_dir(self) -> Path:
        """Get resolved workspace directory path."""
        return Path(self.workspace_dir).expanduser().resolve()

    @property
    def resolved_database_path(self) -> Path:
        """Get resolved database path."""
        return Path(self.database_path).expanduser().resolve()

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "projects": [p.to_dict() for p in self.projects],
            "default_project": self.default_project,
            "workspace_dir": self.workspace_dir,
            "database_path": self.database_path,
            "log_level": self.log_level,
            "log_format": self.log_format,
        }
