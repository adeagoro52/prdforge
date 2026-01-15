"""Git operations manager for PRDForge."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .logging import logger


@dataclass
class GitResult:
    """Result of a git operation.

    Attributes:
        success: Whether the operation succeeded.
        output: stdout from the git command.
        error: stderr from the git command.
        return_code: Process return code.
    """

    success: bool
    output: str
    error: str
    return_code: int


class GitManager:
    """Manages git operations for a project.

    This class encapsulates all git operations needed for PRD execution,
    including branch management, commits, and status checking.
    """

    def __init__(self, repo_path: Path) -> None:
        """Initialize GitManager for a repository.

        Args:
            repo_path: Path to the git repository root.

        Raises:
            ValueError: If path is not a git repository.
        """
        self.repo_path = Path(repo_path).resolve()

        if not self._is_git_repo():
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def _is_git_repo(self) -> bool:
        """Check if the path is a git repository."""
        git_dir = self.repo_path / ".git"
        return git_dir.is_dir()

    def _run_git(
        self, *args: str, check: bool = False, capture_output: bool = True
    ) -> GitResult:
        """Run a git command in the repository.

        Args:
            *args: Git command arguments (without 'git' prefix).
            check: If True, raise on non-zero return code.
            capture_output: If True, capture stdout/stderr.

        Returns:
            GitResult with command output and status.
        """
        cmd = ["git", "-C", str(self.repo_path), *args]
        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=check,
            )
            return GitResult(
                success=result.returncode == 0,
                output=result.stdout.strip() if result.stdout else "",
                error=result.stderr.strip() if result.stderr else "",
                return_code=result.returncode,
            )
        except subprocess.CalledProcessError as e:
            return GitResult(
                success=False,
                output=e.stdout.strip() if e.stdout else "",
                error=e.stderr.strip() if e.stderr else "",
                return_code=e.returncode,
            )

    def get_current_branch(self) -> str | None:
        """Get the current branch name.

        Returns:
            Current branch name, or None if detached HEAD.
        """
        result = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if result.success and result.output != "HEAD":
            return result.output
        return None

    def branch_exists(self, branch: str) -> bool:
        """Check if a branch exists locally.

        Args:
            branch: Branch name to check.

        Returns:
            True if branch exists.
        """
        result = self._run_git("rev-parse", "--verify", f"refs/heads/{branch}")
        return result.success

    def create_branch(self, branch: str, start_point: str | None = None) -> GitResult:
        """Create a new branch.

        Args:
            branch: Name for the new branch.
            start_point: Optional commit/branch to start from.

        Returns:
            GitResult indicating success or failure.
        """
        args = ["checkout", "-b", branch]
        if start_point:
            args.append(start_point)

        result = self._run_git(*args)
        if result.success:
            logger.info(f"Created branch: {branch}")
        else:
            logger.error(f"Failed to create branch: {result.error}")
        return result

    def checkout(self, branch: str) -> GitResult:
        """Checkout a branch.

        Args:
            branch: Branch name to checkout.

        Returns:
            GitResult indicating success or failure.
        """
        result = self._run_git("checkout", branch)
        if result.success:
            logger.info(f"Checked out: {branch}")
        else:
            logger.error(f"Failed to checkout {branch}: {result.error}")
        return result

    def get_status(self) -> dict[str, list[str]]:
        """Get repository status.

        Returns:
            Dict with keys: 'staged', 'modified', 'untracked'.
        """
        status: dict[str, list[str]] = {
            "staged": [],
            "modified": [],
            "untracked": [],
        }

        result = self._run_git("status", "--porcelain")
        if not result.success:
            return status

        for line in result.output.splitlines():
            if len(line) < 3:
                continue

            index_status = line[0]
            worktree_status = line[1]
            filepath = line[3:]

            if index_status != " " and index_status != "?":
                status["staged"].append(filepath)
            if worktree_status == "M":
                status["modified"].append(filepath)
            if index_status == "?":
                status["untracked"].append(filepath)

        return status

    def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes.

        Returns:
            True if there are staged, modified, or untracked files.
        """
        status = self.get_status()
        return bool(status["staged"] or status["modified"] or status["untracked"])

    def add(self, *paths: str) -> GitResult:
        """Stage files for commit.

        Args:
            *paths: File paths to stage. Use '.' for all.

        Returns:
            GitResult indicating success or failure.
        """
        if not paths:
            paths = (".",)
        return self._run_git("add", *paths)

    def commit(self, message: str, allow_empty: bool = False) -> GitResult:
        """Create a commit.

        Args:
            message: Commit message.
            allow_empty: If True, allow commits with no changes.

        Returns:
            GitResult indicating success or failure.
        """
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")

        result = self._run_git(*args)
        if result.success:
            logger.info(f"Committed: {message[:50]}...")
        else:
            logger.error(f"Commit failed: {result.error}")
        return result

    def get_commit_hash(self, ref: str = "HEAD") -> str | None:
        """Get the commit hash for a reference.

        Args:
            ref: Git reference (branch, tag, HEAD, etc.).

        Returns:
            Full commit hash, or None if ref doesn't exist.
        """
        result = self._run_git("rev-parse", ref)
        return result.output if result.success else None

    def get_diff_stats(self, base: str, head: str = "HEAD") -> dict[str, int]:
        """Get diff statistics between two refs.

        Args:
            base: Base reference.
            head: Head reference (default: HEAD).

        Returns:
            Dict with 'files_changed', 'insertions', 'deletions'.
        """
        stats = {"files_changed": 0, "insertions": 0, "deletions": 0}

        result = self._run_git("diff", "--stat", f"{base}..{head}")
        if not result.success:
            return stats

        # Parse the summary line (e.g., "3 files changed, 10 insertions(+), 5 deletions(-)")
        lines = result.output.splitlines()
        if lines:
            summary = lines[-1]
            import re

            if match := re.search(r"(\d+) files? changed", summary):
                stats["files_changed"] = int(match.group(1))
            if match := re.search(r"(\d+) insertions?", summary):
                stats["insertions"] = int(match.group(1))
            if match := re.search(r"(\d+) deletions?", summary):
                stats["deletions"] = int(match.group(1))

        return stats

    def stash(self, message: str | None = None) -> GitResult:
        """Stash uncommitted changes.

        Args:
            message: Optional stash message.

        Returns:
            GitResult indicating success or failure.
        """
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        return self._run_git(*args)

    def stash_pop(self) -> GitResult:
        """Pop the most recent stash.

        Returns:
            GitResult indicating success or failure.
        """
        return self._run_git("stash", "pop")

    def fetch(self, remote: str = "origin") -> GitResult:
        """Fetch from remote.

        Args:
            remote: Remote name.

        Returns:
            GitResult indicating success or failure.
        """
        return self._run_git("fetch", remote)

    def push(
        self, remote: str = "origin", branch: str | None = None, set_upstream: bool = False
    ) -> GitResult:
        """Push to remote.

        Args:
            remote: Remote name.
            branch: Branch to push (default: current branch).
            set_upstream: If True, set upstream tracking.

        Returns:
            GitResult indicating success or failure.
        """
        args = ["push"]
        if set_upstream:
            args.append("-u")
        args.append(remote)
        if branch:
            args.append(branch)

        result = self._run_git(*args)
        if result.success:
            logger.info(f"Pushed to {remote}")
        else:
            logger.error(f"Push failed: {result.error}")
        return result
