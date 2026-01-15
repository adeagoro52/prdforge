"""Tests for GitOperations."""

import subprocess
import pytest
from pathlib import Path

from src.engine.git_operations import (
    BranchConfig,
    ConflictStrategy,
    GitOperations,
    MergeInfo,
    MergeResult,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with develop branch."""
    # Initialize repo
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

    # Create initial commit on master/main
    readme = tmp_path / "README.md"
    readme.write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    # Create develop branch
    subprocess.run(
        ["git", "checkout", "-b", "develop"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    return tmp_path


class TestBranchConfig:
    """Tests for BranchConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = BranchConfig()

        assert config.base_branch == "develop"
        assert config.run_branch_prefix == "prdforge/run"
        assert config.auto_push is False
        assert config.conflict_strategy == ConflictStrategy.ABORT
        assert config.delete_run_branch_on_success is False
        assert config.sync_to_develop is True

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = BranchConfig(
            base_branch="main",
            auto_push=True,
            conflict_strategy=ConflictStrategy.THEIRS,
        )

        assert config.base_branch == "main"
        assert config.auto_push is True
        assert config.conflict_strategy == ConflictStrategy.THEIRS


class TestGitOperations:
    """Tests for GitOperations class."""

    def test_init(self, git_repo: Path) -> None:
        """Test initialization."""
        ops = GitOperations(git_repo)

        assert ops.git.repo_path == git_repo
        assert ops.config.base_branch == "develop"

    def test_resolve_base_branch_default(self, git_repo: Path) -> None:
        """Test base branch resolution with default."""
        ops = GitOperations(git_repo)
        base = ops.resolve_base_branch()

        assert base == "develop"

    def test_resolve_base_branch_from_prd(self, git_repo: Path) -> None:
        """Test base branch resolution from PRD config."""
        # Create a feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/test"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        ops = GitOperations(git_repo)
        base = ops.resolve_base_branch({"base_branch": "feature/test"})

        assert base == "feature/test"

    def test_resolve_base_branch_fallback(self, git_repo: Path) -> None:
        """Test base branch resolution fallback to master/main."""
        # Configure to look for nonexistent branch
        config = BranchConfig(base_branch="nonexistent")
        ops = GitOperations(git_repo, config)

        # Should fall back to master or main
        base = ops.resolve_base_branch()
        assert base in ["master", "main"]

    def test_generate_run_branch_name(self, git_repo: Path) -> None:
        """Test run branch name generation."""
        ops = GitOperations(git_repo)
        name = ops.generate_run_branch_name("abc12345-6789-0000")

        assert name.startswith("prdforge/run/")
        assert "abc12345" in name

    def test_setup_run_branch(self, git_repo: Path) -> None:
        """Test setting up a run branch."""
        ops = GitOperations(git_repo)
        run_branch, base_branch = ops.setup_run_branch("test-run-123")

        assert run_branch.startswith("prdforge/run/")
        assert base_branch == "develop"
        assert ops.git.get_current_branch() == run_branch
        assert ops.git.branch_exists(run_branch)

    def test_setup_run_branch_stashes_changes(self, git_repo: Path) -> None:
        """Test that setup stashes uncommitted changes."""
        # Modify a tracked file (git stash only handles tracked files by default)
        (git_repo / "README.md").write_text("modified content")

        ops = GitOperations(git_repo)
        ops.setup_run_branch("test-run-456")

        # Changes should be stashed
        assert not ops.git.has_uncommitted_changes()

    def test_commit_task_changes(self, git_repo: Path) -> None:
        """Test committing task changes."""
        ops = GitOperations(git_repo)
        ops.setup_run_branch("test-run-789")

        # Make a change
        (git_repo / "task_output.txt").write_text("task result")

        result = ops.commit_task_changes("task-001", "Implement feature X")

        assert result.success
        assert not ops.git.has_uncommitted_changes()

    def test_commit_task_changes_no_changes(self, git_repo: Path) -> None:
        """Test committing when there are no changes."""
        ops = GitOperations(git_repo)
        ops.setup_run_branch("test-run-000")

        result = ops.commit_task_changes("task-001", "No-op task")

        assert result.success
        assert "No changes" in result.output

    def test_merge_branch_success(self, git_repo: Path) -> None:
        """Test successful merge."""
        ops = GitOperations(git_repo)

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/merge-test"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Make a change on feature branch
        (git_repo / "feature.txt").write_text("feature content")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Merge feature into develop
        merge_info = ops.merge_branch("feature/merge-test", "develop")

        assert merge_info.result == MergeResult.SUCCESS
        assert merge_info.commit_hash is not None
        assert ops.git.get_current_branch() == "develop"

    def test_merge_branch_already_merged(self, git_repo: Path) -> None:
        """Test merge when already merged."""
        ops = GitOperations(git_repo)

        # develop and master point to same commit initially
        merge_info = ops.merge_branch("develop", "develop")

        assert merge_info.result == MergeResult.ALREADY_MERGED

    def test_merge_branch_conflict_abort(self, git_repo: Path) -> None:
        """Test merge conflict with abort strategy."""
        ops = GitOperations(git_repo, BranchConfig(conflict_strategy=ConflictStrategy.ABORT))

        # Create conflicting changes
        # First, make a change on develop
        (git_repo / "conflict.txt").write_text("develop content")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add on develop"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Create feature branch from before the change
        subprocess.run(
            ["git", "checkout", "-b", "feature/conflict", "HEAD~1"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Make conflicting change
        (git_repo / "conflict.txt").write_text("feature content")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add on feature"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Try to merge feature into develop
        merge_info = ops.merge_branch("feature/conflict", "develop")

        assert merge_info.result == MergeResult.CONFLICT
        assert merge_info.conflicts is not None
        assert "conflict.txt" in merge_info.conflicts

    def test_complete_run_success(self, git_repo: Path) -> None:
        """Test completing a successful run."""
        ops = GitOperations(git_repo)
        run_branch, base_branch = ops.setup_run_branch("test-complete")

        # Make changes on run branch
        (git_repo / "run_output.txt").write_text("run results")
        ops.commit_task_changes("task-001", "Complete task")

        # Complete the run
        merge_info = ops.complete_run(run_branch, base_branch, success=True)

        assert merge_info is not None
        assert merge_info.result == MergeResult.SUCCESS

    def test_complete_run_failure_keeps_branch(self, git_repo: Path) -> None:
        """Test that failed run keeps the branch."""
        ops = GitOperations(git_repo)
        run_branch, base_branch = ops.setup_run_branch("test-fail")

        # Complete with failure
        merge_info = ops.complete_run(run_branch, base_branch, success=False)

        assert merge_info is None
        assert ops.git.branch_exists(run_branch)

    def test_delete_branch(self, git_repo: Path) -> None:
        """Test deleting a branch."""
        ops = GitOperations(git_repo)

        # Create a branch
        subprocess.run(
            ["git", "checkout", "-b", "to-delete"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        result = ops.delete_branch("to-delete")

        assert result.success
        assert not ops.git.branch_exists("to-delete")

    def test_push_branch(self, git_repo: Path) -> None:
        """Test push branch (will fail without remote, but tests the interface)."""
        ops = GitOperations(git_repo)

        # No remote configured, so push will fail
        result = ops.push_branch("develop")

        assert not result.success
        # Error should mention no remote or similar

    def test_restore_original_branch(self, git_repo: Path) -> None:
        """Test restoring original branch after run."""
        ops = GitOperations(git_repo)

        # Start on develop
        original = ops.git.get_current_branch()
        assert original == "develop"

        # Setup run branch
        ops.setup_run_branch("test-restore")
        assert ops.git.get_current_branch() != "develop"

        # Restore
        result = ops.restore_original_branch()

        assert result is not None
        assert result.success
        assert ops.git.get_current_branch() == "develop"

    def test_get_run_branches(self, git_repo: Path) -> None:
        """Test getting list of run branches."""
        ops = GitOperations(git_repo)

        # Create some run branches
        ops.setup_run_branch("run-1")
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        ops.setup_run_branch("run-2")

        branches = ops.get_run_branches()

        assert len(branches) == 2
        assert all(b.startswith("prdforge/run/") for b in branches)

    def test_cleanup_old_run_branches(self, git_repo: Path) -> None:
        """Test cleaning up old run branches."""
        ops = GitOperations(git_repo)

        # Create several run branches
        for i in range(5):
            ops.setup_run_branch(f"run-{i}")
            subprocess.run(
                ["git", "checkout", "develop"],
                cwd=git_repo,
                capture_output=True,
                check=True,
            )

        # Keep only 2
        deleted = ops.cleanup_old_run_branches(keep_count=2)

        assert len(deleted) == 3
        remaining = ops.get_run_branches()
        assert len(remaining) == 2


class TestConflictStrategies:
    """Tests for different conflict resolution strategies."""

    def test_conflict_strategy_enum_values(self) -> None:
        """Test ConflictStrategy enum values."""
        assert ConflictStrategy.ABORT.value == "abort"
        assert ConflictStrategy.OURS.value == "ours"
        assert ConflictStrategy.THEIRS.value == "theirs"
        assert ConflictStrategy.MANUAL.value == "manual"


class TestMergeInfo:
    """Tests for MergeInfo dataclass."""

    def test_merge_info_creation(self) -> None:
        """Test MergeInfo creation."""
        info = MergeInfo(
            result=MergeResult.SUCCESS,
            source_branch="feature/test",
            target_branch="develop",
            commit_hash="abc123",
        )

        assert info.result == MergeResult.SUCCESS
        assert info.source_branch == "feature/test"
        assert info.target_branch == "develop"
        assert info.commit_hash == "abc123"

    def test_merge_info_with_conflicts(self) -> None:
        """Test MergeInfo with conflicts."""
        info = MergeInfo(
            result=MergeResult.CONFLICT,
            source_branch="feature/test",
            target_branch="develop",
            conflicts=["file1.txt", "file2.txt"],
            error="Merge conflicts detected",
        )

        assert info.result == MergeResult.CONFLICT
        assert info.conflicts == ["file1.txt", "file2.txt"]
        assert info.error == "Merge conflicts detected"
