"""High-level git operations for PRD execution workflow.

This module provides the GitOperations class that handles the branching
workflow for PRD runs, including branch creation, merging, and conflict
resolution.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .git_manager import GitManager, GitResult
from .logging import logger


class ConflictStrategy(Enum):
    """Strategy for handling merge conflicts."""

    ABORT = "abort"  # Abort merge on conflict
    OURS = "ours"  # Keep our changes (run branch)
    THEIRS = "theirs"  # Keep their changes (target branch)
    MANUAL = "manual"  # Leave conflict markers for manual resolution


class MergeResult(Enum):
    """Result of a merge operation."""

    SUCCESS = "success"
    CONFLICT = "conflict"
    ALREADY_MERGED = "already_merged"
    FAILED = "failed"


@dataclass
class BranchConfig:
    """Configuration for branch management.

    Attributes:
        base_branch: The branch to base runs on (default: develop).
        run_branch_prefix: Prefix for run branches.
        auto_push: Whether to auto-push after commits.
        conflict_strategy: How to handle merge conflicts.
        delete_run_branch_on_success: Delete run branch after successful merge.
        sync_to_develop: Whether to sync changes to develop after completion.
    """

    base_branch: str = "develop"
    run_branch_prefix: str = "prdforge/run"
    auto_push: bool = False
    conflict_strategy: ConflictStrategy = ConflictStrategy.ABORT
    delete_run_branch_on_success: bool = False
    sync_to_develop: bool = True


@dataclass
class MergeInfo:
    """Information about a merge operation.

    Attributes:
        result: The merge result status.
        source_branch: Branch being merged from.
        target_branch: Branch being merged into.
        commit_hash: Resulting commit hash if successful.
        conflicts: List of conflicting files if any.
        error: Error message if failed.
    """

    result: MergeResult
    source_branch: str
    target_branch: str
    commit_hash: str | None = None
    conflicts: list[str] | None = None
    error: str | None = None


class GitOperations:
    """High-level git operations for PRD execution workflow.

    This class provides workflow-oriented git operations including:
    - Run branch creation and management
    - Per-PRD base branch resolution
    - Merge workflow with conflict handling
    - Branch synchronization
    """

    def __init__(
        self,
        repo_path: Path,
        config: BranchConfig | None = None,
    ) -> None:
        """Initialize GitOperations.

        Args:
            repo_path: Path to the git repository.
            config: Branch configuration. Uses defaults if not provided.
        """
        self.git = GitManager(repo_path)
        self.config = config or BranchConfig()
        self._original_branch: str | None = None

    def resolve_base_branch(self, prd_config: dict[str, Any] | None = None) -> str:
        """Resolve the base branch for a PRD run.

        The base branch is determined by (in order of precedence):
        1. PRD-specific base_branch setting
        2. GitOperations config base_branch
        3. Default 'develop'

        Args:
            prd_config: Optional PRD configuration dict with 'base_branch' key.

        Returns:
            The resolved base branch name.
        """
        # Check PRD-specific setting first
        if prd_config and "base_branch" in prd_config:
            base = prd_config["base_branch"]
            if self.git.branch_exists(base):
                logger.debug(f"Using PRD-specified base branch: {base}")
                return base
            logger.warning(f"PRD base branch '{base}' not found, using default")

        # Fall back to config
        base = self.config.base_branch
        if self.git.branch_exists(base):
            return base

        # Last resort: check for main/master
        for fallback in ["main", "master"]:
            if self.git.branch_exists(fallback):
                logger.warning(f"Base branch '{base}' not found, using '{fallback}'")
                return fallback

        raise ValueError(f"Could not resolve base branch. '{base}' does not exist.")

    def generate_run_branch_name(self, run_id: str) -> str:
        """Generate a unique run branch name.

        Args:
            run_id: The run identifier.

        Returns:
            Branch name in format: <prefix>/<timestamp>-<short_id>
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        short_id = run_id[:8]
        return f"{self.config.run_branch_prefix}/{timestamp}-{short_id}"

    def setup_run_branch(
        self,
        run_id: str,
        prd_config: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Set up a new run branch for PRD execution.

        This method:
        1. Saves the current branch
        2. Stashes any uncommitted changes
        3. Resolves the base branch
        4. Creates and checks out the run branch

        Args:
            run_id: The run identifier.
            prd_config: Optional PRD configuration for base branch resolution.

        Returns:
            Tuple of (run_branch_name, base_branch_name).

        Raises:
            RuntimeError: If branch setup fails.
        """
        # Save current branch for later restoration
        self._original_branch = self.git.get_current_branch()

        # Stash any uncommitted changes
        if self.git.has_uncommitted_changes():
            logger.info("Stashing uncommitted changes")
            result = self.git.stash(f"PRDForge auto-stash before run {run_id}")
            if not result.success:
                raise RuntimeError(f"Failed to stash changes: {result.error}")

        # Resolve base branch
        base_branch = self.resolve_base_branch(prd_config)

        # Checkout base branch
        result = self.git.checkout(base_branch)
        if not result.success:
            raise RuntimeError(f"Failed to checkout base branch: {result.error}")

        # Fetch latest if remote exists
        self.git.fetch()

        # Create run branch
        run_branch = self.generate_run_branch_name(run_id)
        result = self.git.create_branch(run_branch)
        if not result.success:
            raise RuntimeError(f"Failed to create run branch: {result.error}")

        logger.info(f"Set up run branch '{run_branch}' from '{base_branch}'")
        return run_branch, base_branch

    def commit_task_changes(
        self,
        task_id: str,
        task_description: str,
        files: list[str] | None = None,
    ) -> GitResult:
        """Commit changes for a completed task.

        Args:
            task_id: The task identifier.
            task_description: Human-readable task description.
            files: Specific files to commit. If None, commits all changes.

        Returns:
            GitResult indicating success or failure.
        """
        if not self.git.has_uncommitted_changes():
            logger.debug(f"No changes to commit for task {task_id}")
            return GitResult(
                success=True,
                output="No changes to commit",
                error="",
                return_code=0,
            )

        # Stage files
        if files:
            for f in files:
                self.git.add(f)
        else:
            self.git.add(".")

        # Create commit message
        message = f"[PRDForge] {task_id}: {task_description}"

        result = self.git.commit(message)

        if result.success and self.config.auto_push:
            branch = self.git.get_current_branch()
            if branch:
                self.git.push(branch=branch, set_upstream=True)

        return result

    def merge_branch(
        self,
        source: str,
        target: str,
        strategy: ConflictStrategy | None = None,
    ) -> MergeInfo:
        """Merge source branch into target branch.

        Args:
            source: Branch to merge from.
            target: Branch to merge into.
            strategy: Conflict resolution strategy. Uses config default if None.

        Returns:
            MergeInfo with merge result details.
        """
        strategy = strategy or self.config.conflict_strategy

        # Checkout target branch
        result = self.git.checkout(target)
        if not result.success:
            return MergeInfo(
                result=MergeResult.FAILED,
                source_branch=source,
                target_branch=target,
                error=f"Failed to checkout {target}: {result.error}",
            )

        # Check if already merged
        merge_base = self.git._run_git("merge-base", source, target)
        source_hash = self.git.get_commit_hash(source)
        if merge_base.success and merge_base.output == source_hash:
            return MergeInfo(
                result=MergeResult.ALREADY_MERGED,
                source_branch=source,
                target_branch=target,
            )

        # Build merge command
        merge_args = ["merge", source, "--no-edit"]

        if strategy == ConflictStrategy.OURS:
            merge_args.extend(["-X", "ours"])
        elif strategy == ConflictStrategy.THEIRS:
            merge_args.extend(["-X", "theirs"])

        # Attempt merge
        result = self.git._run_git(*merge_args)

        if result.success:
            commit_hash = self.git.get_commit_hash("HEAD")
            logger.info(f"Merged {source} into {target}")
            return MergeInfo(
                result=MergeResult.SUCCESS,
                source_branch=source,
                target_branch=target,
                commit_hash=commit_hash,
            )

        # Check for conflicts
        if "CONFLICT" in result.output or "CONFLICT" in result.error:
            conflicts = self._get_conflicting_files()

            if strategy == ConflictStrategy.ABORT:
                self.git._run_git("merge", "--abort")
                logger.warning(f"Merge aborted due to conflicts: {conflicts}")

            return MergeInfo(
                result=MergeResult.CONFLICT,
                source_branch=source,
                target_branch=target,
                conflicts=conflicts,
                error="Merge conflicts detected",
            )

        return MergeInfo(
            result=MergeResult.FAILED,
            source_branch=source,
            target_branch=target,
            error=result.error,
        )

    def _get_conflicting_files(self) -> list[str]:
        """Get list of files with merge conflicts."""
        result = self.git._run_git("diff", "--name-only", "--diff-filter=U")
        if result.success and result.output:
            return result.output.splitlines()
        return []

    def complete_run(
        self,
        run_branch: str,
        base_branch: str,
        success: bool = True,
    ) -> MergeInfo | None:
        """Complete a run by merging changes back.

        If successful, merges run branch into base branch and optionally
        syncs to develop.

        Args:
            run_branch: The run branch to merge.
            base_branch: The base branch to merge into.
            success: Whether the run completed successfully.

        Returns:
            MergeInfo if merge was attempted, None if skipped.
        """
        if not success:
            logger.info(f"Run failed, keeping run branch '{run_branch}' for inspection")
            return None

        # Merge run branch into base branch
        merge_info = self.merge_branch(run_branch, base_branch)

        if merge_info.result != MergeResult.SUCCESS:
            logger.error(f"Failed to merge run branch: {merge_info.error}")
            return merge_info

        # Push base branch if auto_push enabled
        if self.config.auto_push:
            self.git.push(branch=base_branch)

        # Sync to develop if configured and base != develop
        if self.config.sync_to_develop and base_branch != "develop":
            if self.git.branch_exists("develop"):
                logger.info("Syncing changes to develop")
                develop_merge = self.merge_branch(base_branch, "develop")
                if develop_merge.result == MergeResult.SUCCESS and self.config.auto_push:
                    self.git.push(branch="develop")

        # Delete run branch if configured
        if self.config.delete_run_branch_on_success:
            self.delete_branch(run_branch)

        return merge_info

    def delete_branch(self, branch: str, force: bool = False) -> GitResult:
        """Delete a branch.

        Args:
            branch: Branch name to delete.
            force: If True, force delete even if not fully merged.

        Returns:
            GitResult indicating success or failure.
        """
        flag = "-D" if force else "-d"
        result = self.git._run_git("branch", flag, branch)

        if result.success:
            logger.info(f"Deleted branch: {branch}")
        else:
            logger.warning(f"Failed to delete branch {branch}: {result.error}")

        return result

    def push_branch(
        self,
        branch: str | None = None,
        remote: str = "origin",
        set_upstream: bool = True,
        force: bool = False,
    ) -> GitResult:
        """Push a branch to remote.

        Args:
            branch: Branch to push. Uses current branch if None.
            remote: Remote name.
            set_upstream: Whether to set upstream tracking.
            force: Whether to force push (use with caution).

        Returns:
            GitResult indicating success or failure.
        """
        branch = branch or self.git.get_current_branch()
        if not branch:
            return GitResult(
                success=False,
                output="",
                error="No branch to push",
                return_code=1,
            )

        args = ["push"]
        if set_upstream:
            args.append("-u")
        if force:
            args.append("--force")
        args.extend([remote, branch])

        result = self.git._run_git(*args)

        if result.success:
            logger.info(f"Pushed {branch} to {remote}")
        else:
            logger.error(f"Failed to push {branch}: {result.error}")

        return result

    def restore_original_branch(self) -> GitResult | None:
        """Restore the branch that was active before run setup.

        Returns:
            GitResult if restoration attempted, None if no original branch saved.
        """
        if not self._original_branch:
            return None

        result = self.git.checkout(self._original_branch)
        if result.success:
            logger.info(f"Restored original branch: {self._original_branch}")

            # Pop stash if we stashed changes
            self.git.stash_pop()

        self._original_branch = None
        return result

    def get_run_branches(self) -> list[str]:
        """Get list of existing run branches.

        Returns:
            List of branch names matching the run branch prefix.
        """
        result = self.git._run_git("branch", "--list", f"{self.config.run_branch_prefix}/*")
        if result.success and result.output:
            # Strip leading whitespace and asterisks
            return [b.strip().lstrip("* ") for b in result.output.splitlines()]
        return []

    def cleanup_old_run_branches(self, keep_count: int = 5) -> list[str]:
        """Clean up old run branches, keeping the most recent ones.

        Args:
            keep_count: Number of recent branches to keep.

        Returns:
            List of deleted branch names.
        """
        branches = self.get_run_branches()

        # Sort by name (which includes timestamp) and remove oldest
        branches.sort(reverse=True)
        to_delete = branches[keep_count:]

        deleted = []
        for branch in to_delete:
            result = self.delete_branch(branch, force=True)
            if result.success:
                deleted.append(branch)

        if deleted:
            logger.info(f"Cleaned up {len(deleted)} old run branches")

        return deleted
