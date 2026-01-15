"""Git operations manager for PRDForge."""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .logging import logger


# Default workspace directory for cloned repos
DEFAULT_WORKSPACE_DIR = Path.home() / ".prdforge" / "workspaces"


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

    def pull(
        self, remote: str = "origin", branch: Optional[str] = None, rebase: bool = False
    ) -> GitResult:
        """Pull from remote.

        Args:
            remote: Remote name.
            branch: Branch to pull (default: current branch).
            rebase: If True, use rebase instead of merge.

        Returns:
            GitResult indicating success or failure.
        """
        args = ["pull"]
        if rebase:
            args.append("--rebase")
        args.append(remote)
        if branch:
            args.append(branch)

        result = self._run_git(*args)
        if result.success:
            logger.info(f"Pulled from {remote}")
        else:
            logger.error(f"Pull failed: {result.error}")
        return result

    def get_remote_url(self, remote: str = "origin") -> Optional[str]:
        """Get the URL of a remote.

        Args:
            remote: Remote name.

        Returns:
            Remote URL or None if not found.
        """
        result = self._run_git("remote", "get-url", remote)
        return result.output if result.success else None

    def set_remote_url(self, remote: str, url: str) -> GitResult:
        """Set the URL of a remote.

        Args:
            remote: Remote name.
            url: New URL for the remote.

        Returns:
            GitResult indicating success or failure.
        """
        result = self._run_git("remote", "set-url", remote, url)
        if result.success:
            logger.info(f"Set {remote} URL to {url}")
        return result

    def add_remote(self, name: str, url: str) -> GitResult:
        """Add a new remote.

        Args:
            name: Remote name.
            url: Remote URL.

        Returns:
            GitResult indicating success or failure.
        """
        result = self._run_git("remote", "add", name, url)
        if result.success:
            logger.info(f"Added remote {name}: {url}")
        return result

    def list_remotes(self) -> dict[str, str]:
        """List all remotes and their URLs.

        Returns:
            Dict mapping remote names to URLs.
        """
        result = self._run_git("remote", "-v")
        remotes = {}
        if result.success and result.output:
            for line in result.output.splitlines():
                if "(fetch)" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        remotes[parts[0]] = parts[1]
        return remotes

    def sync_with_remote(
        self, remote: str = "origin", branch: Optional[str] = None
    ) -> GitResult:
        """Sync current branch with remote (fetch + pull).

        Args:
            remote: Remote name.
            branch: Branch to sync (default: current branch).

        Returns:
            GitResult indicating success or failure.
        """
        # First fetch to get latest refs
        fetch_result = self.fetch(remote)
        if not fetch_result.success:
            return fetch_result

        # Then pull
        return self.pull(remote, branch)

    @classmethod
    def clone(
        cls,
        url: str,
        target_path: Optional[Path] = None,
        branch: Optional[str] = None,
        depth: Optional[int] = None,
        workspace_dir: Optional[Path] = None,
    ) -> "GitManager":
        """Clone a remote repository.

        Args:
            url: Repository URL (HTTPS or SSH).
            target_path: Optional explicit path for clone. If None, uses workspace.
            branch: Optional branch to clone.
            depth: Optional shallow clone depth.
            workspace_dir: Optional workspace directory for clones.

        Returns:
            GitManager instance for the cloned repo.

        Raises:
            RuntimeError: If clone fails.
        """
        # Determine target path
        if target_path is None:
            workspace = workspace_dir or DEFAULT_WORKSPACE_DIR
            workspace.mkdir(parents=True, exist_ok=True)

            # Extract repo name from URL
            repo_name = cls._extract_repo_name(url)
            target_path = workspace / repo_name

        # Build clone command
        cmd = ["git", "clone"]
        if branch:
            cmd.extend(["-b", branch])
        if depth:
            cmd.extend(["--depth", str(depth)])
        cmd.extend([url, str(target_path)])

        logger.info(f"Cloning {url} to {target_path}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                error = result.stderr.strip() if result.stderr else "Clone failed"
                raise RuntimeError(f"Failed to clone {url}: {error}")

            logger.info(f"Cloned {url} to {target_path}")
            return cls(target_path)

        except Exception as e:
            logger.error(f"Clone failed: {e}")
            raise

    @staticmethod
    def _extract_repo_name(url: str) -> str:
        """Extract repository name from URL.

        Args:
            url: Git URL (HTTPS or SSH).

        Returns:
            Repository name.
        """
        # Handle SSH URLs (git@github.com:user/repo.git)
        if url.startswith("git@"):
            match = re.search(r":(.+?)(?:\.git)?$", url)
            if match:
                return match.group(1).replace("/", "-")

        # Handle HTTPS URLs
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        if path.endswith(".git"):
            path = path[:-4]

        # Use the last two path components (org/repo)
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}-{parts[-1]}"
        return parts[-1] if parts else "repo"

    @staticmethod
    def is_git_url(path_or_url: str) -> bool:
        """Check if a string is a git URL.

        Args:
            path_or_url: String to check.

        Returns:
            True if it's a git URL (SSH or HTTPS).
        """
        # SSH URL pattern
        if path_or_url.startswith("git@"):
            return True

        # HTTPS URL pattern
        if path_or_url.startswith(("https://", "http://")):
            # Check for common git hosts or .git extension
            if any(host in path_or_url for host in ["github.com", "gitlab.com", "bitbucket.org"]):
                return True
            if path_or_url.endswith(".git"):
                return True

        return False

    def create_worktree(
        self, path: Path, branch: str, create_branch: bool = False
    ) -> GitResult:
        """Create a git worktree.

        Worktrees allow working with multiple branches simultaneously
        without switching branches in the main repository.

        Args:
            path: Path for the new worktree.
            branch: Branch to checkout in the worktree.
            create_branch: If True, create a new branch.

        Returns:
            GitResult indicating success or failure.
        """
        args = ["worktree", "add"]
        if create_branch:
            args.extend(["-b", branch, str(path)])
        else:
            args.extend([str(path), branch])

        result = self._run_git(*args)
        if result.success:
            logger.info(f"Created worktree at {path} for branch {branch}")
        else:
            logger.error(f"Failed to create worktree: {result.error}")
        return result

    def remove_worktree(self, path: Path, force: bool = False) -> GitResult:
        """Remove a git worktree.

        Args:
            path: Path of the worktree to remove.
            force: If True, force removal even with uncommitted changes.

        Returns:
            GitResult indicating success or failure.
        """
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(path))

        result = self._run_git(*args)
        if result.success:
            logger.info(f"Removed worktree at {path}")
        else:
            logger.error(f"Failed to remove worktree: {result.error}")
        return result

    def list_worktrees(self) -> list[dict[str, str]]:
        """List all worktrees for this repository.

        Returns:
            List of dicts with 'path', 'head', and 'branch' keys.
        """
        result = self._run_git("worktree", "list", "--porcelain")
        worktrees = []
        current = {}

        if result.success and result.output:
            for line in result.output.splitlines():
                if line.startswith("worktree "):
                    if current:
                        worktrees.append(current)
                    current = {"path": line[9:]}
                elif line.startswith("HEAD "):
                    current["head"] = line[5:]
                elif line.startswith("branch "):
                    current["branch"] = line[7:].replace("refs/heads/", "")
                elif line == "bare":
                    current["bare"] = True

            if current:
                worktrees.append(current)

        return worktrees

    def prune_worktrees(self) -> GitResult:
        """Prune stale worktree information.

        Returns:
            GitResult indicating success or failure.
        """
        return self._run_git("worktree", "prune")
