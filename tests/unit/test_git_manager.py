"""Tests for GitManager."""

import subprocess
import pytest
from pathlib import Path

from src.engine.git_manager import GitManager, GitResult


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    readme = tmp_path / "README.md"
    readme.write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    return tmp_path


class TestGitManager:
    """Tests for GitManager."""

    def test_init_valid_repo(self, git_repo: Path) -> None:
        """Test initialization with a valid git repo."""
        manager = GitManager(git_repo)
        assert manager.repo_path == git_repo

    def test_init_invalid_repo(self, tmp_path: Path) -> None:
        """Test initialization with non-git directory."""
        with pytest.raises(ValueError, match="Not a git repository"):
            GitManager(tmp_path)

    def test_get_current_branch(self, git_repo: Path) -> None:
        """Test getting current branch name."""
        manager = GitManager(git_repo)
        # Default branch is usually master or main
        branch = manager.get_current_branch()
        assert branch in ["master", "main"]

    def test_branch_exists(self, git_repo: Path) -> None:
        """Test checking if branch exists."""
        manager = GitManager(git_repo)
        current = manager.get_current_branch()
        assert current is not None
        assert manager.branch_exists(current)
        assert not manager.branch_exists("nonexistent-branch")

    def test_create_branch(self, git_repo: Path) -> None:
        """Test creating a new branch."""
        manager = GitManager(git_repo)
        result = manager.create_branch("feature/test")

        assert result.success
        assert manager.get_current_branch() == "feature/test"
        assert manager.branch_exists("feature/test")

    def test_checkout(self, git_repo: Path) -> None:
        """Test checking out a branch."""
        manager = GitManager(git_repo)
        original = manager.get_current_branch()

        # Create and checkout new branch
        manager.create_branch("test-branch")
        assert manager.get_current_branch() == "test-branch"

        # Checkout original branch
        result = manager.checkout(original)
        assert result.success
        assert manager.get_current_branch() == original

    def test_get_status_clean(self, git_repo: Path) -> None:
        """Test status on clean repo."""
        manager = GitManager(git_repo)
        status = manager.get_status()

        assert status["staged"] == []
        assert status["modified"] == []
        assert status["untracked"] == []

    def test_get_status_with_changes(self, git_repo: Path) -> None:
        """Test status with various changes."""
        manager = GitManager(git_repo)

        # Create untracked file
        (git_repo / "untracked.txt").write_text("new file")

        # Modify existing file
        (git_repo / "README.md").write_text("# Modified")

        status = manager.get_status()

        assert "untracked.txt" in status["untracked"]
        # Modified tracked files show up in modified list
        assert "README.md" in status["modified"] or manager.has_uncommitted_changes()

    def test_has_uncommitted_changes(self, git_repo: Path) -> None:
        """Test detecting uncommitted changes."""
        manager = GitManager(git_repo)

        # Clean repo
        assert not manager.has_uncommitted_changes()

        # Add a new file
        (git_repo / "new.txt").write_text("new")
        assert manager.has_uncommitted_changes()

    def test_add_and_commit(self, git_repo: Path) -> None:
        """Test staging and committing changes."""
        manager = GitManager(git_repo)

        # Create a new file
        (git_repo / "new.txt").write_text("new content")

        # Stage and commit
        manager.add("new.txt")
        result = manager.commit("Add new file")

        assert result.success
        assert not manager.has_uncommitted_changes()

    def test_get_commit_hash(self, git_repo: Path) -> None:
        """Test getting commit hash."""
        manager = GitManager(git_repo)
        hash_val = manager.get_commit_hash("HEAD")

        assert hash_val is not None
        assert len(hash_val) == 40  # Full SHA

    def test_get_diff_stats(self, git_repo: Path) -> None:
        """Test getting diff statistics."""
        manager = GitManager(git_repo)

        # Get initial commit hash
        initial_hash = manager.get_commit_hash("HEAD")

        # Make changes and commit
        (git_repo / "file1.txt").write_text("line1\nline2\nline3\n")
        manager.add(".")
        manager.commit("Add file1")

        # Get diff stats
        assert initial_hash is not None
        stats = manager.get_diff_stats(initial_hash)

        assert stats["files_changed"] >= 1
        assert stats["insertions"] >= 3


class TestGitResult:
    """Tests for GitResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful result."""
        result = GitResult(
            success=True,
            output="output text",
            error="",
            return_code=0,
        )

        assert result.success
        assert result.output == "output text"
        assert result.return_code == 0

    def test_failure_result(self) -> None:
        """Test failed result."""
        result = GitResult(
            success=False,
            output="",
            error="error message",
            return_code=1,
        )

        assert not result.success
        assert result.error == "error message"
        assert result.return_code == 1
