"""Repository bootstrap helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_GITIGNORE = """__pycache__/
.venv/
draft_audit.jsonl
"""


def git_setup(worktree: Path | None = None) -> None:
    """Initialize git repository defaults for DRaft."""
    root = Path(worktree or Path.cwd())

    if not (root / ".git").exists():
        subprocess.run(["git", "init"], cwd=root, check=True)

    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(DEFAULT_GITIGNORE)
