"""Version control helpers built on top of git."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


class GitError(RuntimeError):
    """Raised when a git command exits with a non-zero status."""


@dataclass
class DiffStat:
    insertions: int
    deletions: int

    @property
    def total(self) -> int:
        return self.insertions + self.deletions


class Git:
    """
    Lightweight wrapper around git CLI commands.
    
    Provides a Pythonic interface to common git operations used by DRaft.
    All commands are executed via subprocess and respect the worktree path.
    """

    def __init__(self, worktree: Path | None = None) -> None:
        """
        Initialize the Git wrapper.
        
        Args:
            worktree: Path to git repository (defaults to current directory)
        """
        self.worktree = Path(worktree or Path.cwd())

    def run(self, args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        """
        Run a git command and optionally raise on failure.
        
        Args:
            args: Git command arguments (without 'git' prefix)
            check: If True, raise GitError on non-zero exit
            
        Returns:
            CompletedProcess with stdout/stderr/returncode
            
        Raises:
            GitError: If check=True and command fails
        """
        command = ["git", *args]
        result = subprocess.run(
            command,
            cwd=self.worktree,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode != 0:
            raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
        return result

    # Query helpers -----------------------------------------------------------------

    def status(self, paths: Iterable[str] | None = None) -> str:
        """Return porcelain status for the repository."""
        args = ["status", "--short"]
        if paths:
            args.extend(paths)
        return self.run(args).stdout.strip()

    def changed_files(self) -> list[str]:
        """Return a list of files with working tree or staged changes."""
        output = self.run(["status", "--short"]).stdout.strip()
        files: list[str] = []
        if not output:
            return files
        for line in output.splitlines():
            files.append(line[3:])
        return files

    def diff(self, *, staged: bool = False, paths: Iterable[str] | None = None) -> str:
        """Return the diff for the working tree or staged changes."""
        args = ["diff"]
        if staged:
            args.append("--staged")
        if paths:
            args.extend(paths)
        return self.run(args).stdout

    def diff_stat(self) -> DiffStat:
        """
        Return the diff stat for staged and unstaged changes combined.
        
        Counts insertions (+) and deletions (-) across all changed files.
        
        Returns:
            DiffStat with insertion and deletion counts
        """
        output = self.run(["diff", "--stat"]).stdout
        insertions = deletions = 0
        # Parse lines like "file.py | 10 +++++-----"
        for line in output.splitlines():
            if "|" not in line:
                continue
            _, summary = line.split("|", 1)
            insertions += summary.count("+")
            deletions += summary.count("-")
        return DiffStat(insertions=insertions, deletions=deletions)

    def current_branch(self) -> str:
        """Return the current branch name."""
        return self.run(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()

    def is_clean(self) -> bool:
        """Return True if the working tree has no uncommitted changes."""
        return not self.status()

    # Mutation helpers --------------------------------------------------------------

    def stage(self, paths: Iterable[str] | None = None) -> None:
        """Stage the provided paths or all changes."""
        args = ["add"]
        if paths:
            args.extend(paths)
        else:
            args.append("--all")
        self.run(args)

    def commit(self, message: str, *, allow_empty: bool = False) -> None:
        """Create a commit with the provided message."""
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        self.run(args)

    def push(self, remote: str, refspec: str, *, set_upstream: bool = False) -> None:
        """Push the given refspec to the target remote."""
        args = ["push"]
        if set_upstream:
            args.append("-u")
        args.extend([remote, refspec])
        self.run(args)

    def rebase(self, upstream: str) -> None:
        """Rebase the current branch onto upstream."""
        self.run(["rebase", upstream])

    def reset_index(self) -> None:
        """Clear the staging area without touching the working tree."""
        self.run(["reset"])

    def tag(self, name: str, message: str | None = None, *, force: bool = False) -> None:
        """Create an annotated tag on the current HEAD."""
        args = ["tag"]
        if force:
            args.append("--force")
        if message:
            args.extend(["-a", name, "-m", message])
        else:
            args.append(name)
        self.run(args)
