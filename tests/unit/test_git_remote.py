"""Unit tests for remote git repository functionality."""

import tempfile
from pathlib import Path

import pytest

from src.engine.git_manager import DEFAULT_WORKSPACE_DIR, GitManager


class TestGitManagerUrlDetection:
    """Tests for URL detection methods."""

    def test_is_git_url_ssh(self):
        """Test SSH URL detection."""
        assert GitManager.is_git_url("git@github.com:user/repo.git") is True
        assert GitManager.is_git_url("git@gitlab.com:org/project.git") is True

    def test_is_git_url_https(self):
        """Test HTTPS URL detection."""
        assert GitManager.is_git_url("https://github.com/user/repo.git") is True
        assert GitManager.is_git_url("https://github.com/user/repo") is True
        assert GitManager.is_git_url("https://gitlab.com/org/project") is True

    def test_is_git_url_local_path(self):
        """Test local path is not detected as URL."""
        assert GitManager.is_git_url("/home/user/project") is False
        assert GitManager.is_git_url("./relative/path") is False
        assert GitManager.is_git_url("~/project") is False

    def test_extract_repo_name_ssh(self):
        """Test repo name extraction from SSH URLs."""
        assert GitManager._extract_repo_name("git@github.com:user/repo.git") == "user-repo"
        assert GitManager._extract_repo_name("git@github.com:org/project") == "org-project"

    def test_extract_repo_name_https(self):
        """Test repo name extraction from HTTPS URLs."""
        assert GitManager._extract_repo_name("https://github.com/user/repo.git") == "user-repo"
        assert GitManager._extract_repo_name("https://github.com/user/repo") == "user-repo"
        assert GitManager._extract_repo_name("https://gitlab.com/org/project/") == "org-project"


class TestGitManagerRemoteOperations:
    """Tests for remote operations on existing repos."""

    @pytest.fixture
    def git_repo(self):
        """Create a temporary git repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            # Initialize a git repo
            import subprocess
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            # Create initial commit
            (repo_path / "README.md").write_text("# Test")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
            yield GitManager(repo_path)

    def test_list_remotes_empty(self, git_repo):
        """Test listing remotes when none exist."""
        remotes = git_repo.list_remotes()
        assert remotes == {}

    def test_add_and_list_remote(self, git_repo):
        """Test adding and listing a remote."""
        result = git_repo.add_remote("origin", "https://github.com/test/repo.git")
        assert result.success

        remotes = git_repo.list_remotes()
        assert "origin" in remotes
        assert remotes["origin"] == "https://github.com/test/repo.git"

    def test_get_remote_url(self, git_repo):
        """Test getting remote URL."""
        git_repo.add_remote("origin", "https://github.com/test/repo.git")
        url = git_repo.get_remote_url("origin")
        assert url == "https://github.com/test/repo.git"

    def test_get_remote_url_nonexistent(self, git_repo):
        """Test getting URL for nonexistent remote."""
        url = git_repo.get_remote_url("nonexistent")
        assert url is None

    def test_set_remote_url(self, git_repo):
        """Test setting remote URL."""
        git_repo.add_remote("origin", "https://github.com/test/repo.git")
        result = git_repo.set_remote_url("origin", "https://github.com/other/repo.git")
        assert result.success

        url = git_repo.get_remote_url("origin")
        assert url == "https://github.com/other/repo.git"


class TestGitManagerWorktrees:
    """Tests for git worktree operations."""

    @pytest.fixture
    def git_repo(self):
        """Create a temporary git repository with multiple branches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            import subprocess
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            # Create initial commit
            (repo_path / "README.md").write_text("# Test")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
            # Create a feature branch
            subprocess.run(["git", "branch", "feature"], cwd=repo_path, check=True, capture_output=True)
            yield GitManager(repo_path)

    def test_list_worktrees_main_only(self, git_repo):
        """Test listing worktrees shows only main repo initially."""
        worktrees = git_repo.list_worktrees()
        assert len(worktrees) == 1
        assert worktrees[0]["path"] == str(git_repo.repo_path)

    def test_create_worktree(self, git_repo):
        """Test creating a worktree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir) / "feature-worktree"
            result = git_repo.create_worktree(worktree_path, "feature")
            assert result.success
            assert worktree_path.exists()

            worktrees = git_repo.list_worktrees()
            assert len(worktrees) == 2

    def test_create_worktree_new_branch(self, git_repo):
        """Test creating a worktree with a new branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir) / "new-feature"
            result = git_repo.create_worktree(worktree_path, "new-feature", create_branch=True)
            assert result.success
            assert worktree_path.exists()
            assert git_repo.branch_exists("new-feature")

    def test_remove_worktree(self, git_repo):
        """Test removing a worktree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir) / "feature-worktree"
            git_repo.create_worktree(worktree_path, "feature")

            result = git_repo.remove_worktree(worktree_path)
            assert result.success
            assert not worktree_path.exists()

            worktrees = git_repo.list_worktrees()
            assert len(worktrees) == 1

    def test_prune_worktrees(self, git_repo):
        """Test pruning stale worktree info."""
        result = git_repo.prune_worktrees()
        assert result.success


class TestGitManagerClone:
    """Tests for git clone functionality."""

    def test_clone_local_repo(self):
        """Test cloning a local repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create source repo
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            import subprocess
            subprocess.run(["git", "init"], cwd=source_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=source_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=source_path, check=True, capture_output=True)
            (source_path / "README.md").write_text("# Source")
            subprocess.run(["git", "add", "."], cwd=source_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=source_path, check=True, capture_output=True)

            # Clone it
            target_path = Path(tmpdir) / "clone"
            manager = GitManager.clone(str(source_path), target_path=target_path)

            assert manager.repo_path == target_path
            assert (target_path / "README.md").exists()
            assert (target_path / "README.md").read_text() == "# Source"

    def test_clone_to_workspace(self):
        """Test cloning to default workspace directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create source repo
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            import subprocess
            subprocess.run(["git", "init"], cwd=source_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=source_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=source_path, check=True, capture_output=True)
            (source_path / "README.md").write_text("# Test")
            subprocess.run(["git", "add", "."], cwd=source_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=source_path, check=True, capture_output=True)

            # Clone to custom workspace
            workspace = Path(tmpdir) / "workspaces"
            manager = GitManager.clone(str(source_path), workspace_dir=workspace)

            assert workspace in manager.repo_path.parents or manager.repo_path.parent == workspace
            assert (manager.repo_path / "README.md").exists()
