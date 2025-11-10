"""Heuristic grouping for SoloDev cycles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Set


@dataclass
class GroupPlan:
    title: str
    body: str
    files: List[str]

    def to_dict(self) -> dict[str, object]:
        return {"title": self.title, "body": self.body, "files": list(self.files)}


# Language/file type clusters for better grouping
LANGUAGE_CLUSTERS = {
    "python": {".py", ".pyx", ".pyi"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs"},
    "typescript": {".ts", ".tsx"},
    "web_styles": {".css", ".scss", ".sass", ".less"},
    "web_markup": {".html", ".htm", ".xml"},
    "config": {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"},
    "documentation": {".md", ".rst", ".txt", ".adoc"},
    "shell": {".sh", ".bash", ".zsh", ".fish"},
    "java": {".java", ".kt", ".scala"},
    "cpp": {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"},
    "go": {".go"},
    "rust": {".rs"},
    "ruby": {".rb", ".rake"},
    "php": {".php"},
    "sql": {".sql"},
}


def _get_language_cluster(path: Path) -> str | None:
    """Determine which language cluster a file belongs to."""
    suffix = path.suffix.lower()
    for cluster, extensions in LANGUAGE_CLUSTERS.items():
        if suffix in extensions:
            return cluster
    return None


def _group_key(path: Path) -> str:
    """
    Generate a grouping key for a file path.
    
    Priority order:
    1. Tests (test directories or test_ files)
    2. Documentation (.md, .rst, etc.)
    3. Language/file type cluster
    4. Top-level directory
    5. Root files
    """
    # Check for test files
    if "test" in path.parts or path.name.startswith("test_") or path.name.endswith("_test.py"):
        return "tests"
    
    # Check for documentation
    if path.suffix in {".md", ".rst", ".txt", ".adoc"}:
        return "docs"
    
    # Check for language cluster
    cluster = _get_language_cluster(path)
    if cluster:
        # Further refine by directory if available
        if len(path.parts) > 1:
            return f"{path.parts[0]}_{cluster}"
        return cluster
    
    # Group by top-level directory
    if len(path.parts) > 1:
        return path.parts[0]
    
    return "root"


def _title_for_group(key: str, members: List[str]) -> str:
    """Generate a descriptive title for a group."""
    # Special cases
    if key == "tests":
        return "Test Updates"
    if key == "docs":
        return "Documentation Updates"
    if key == "root":
        return "Root Configuration"
    
    # Check if it's a language cluster
    for lang, _ in LANGUAGE_CLUSTERS.items():
        if key == lang:
            return f"{lang.replace('_', ' ').title()} Changes"
        if key.endswith(f"_{lang}"):
            dir_name = key[: -len(lang) - 1]
            return f"{dir_name.title()}: {lang.replace('_', ' ').title()}"
    
    # Default to directory name
    return f"{key.replace('_', ' ').title()} Changes"


def heuristic_groups(paths: Iterable[str]) -> List[GroupPlan]:
    """
    Group paths by heuristic buckets to prepare for LLM refinement.
    
    Grouping strategy:
    - Test files are grouped together
    - Documentation files are grouped together  
    - Files are clustered by language/file type
    - Within clusters, files from same directory are kept together
    - Root config files are grouped separately
    """
    buckets: Dict[str, List[str]] = {}
    
    for raw in paths:
        path = Path(raw)
        key = _group_key(path)
        buckets.setdefault(key, []).append(raw)

    # Sort buckets: tests and docs first, then by key
    priority = {"tests": 0, "docs": 1}
    sorted_keys = sorted(buckets.keys(), key=lambda k: (priority.get(k, 2), k))
    
    plans: List[GroupPlan] = []
    for key in sorted_keys:
        members = buckets[key]
        title = _title_for_group(key, members)
        plans.append(GroupPlan(title=title, body="", files=sorted(members)))
    
    return plans
