"""Policy and safety checks executed ahead of commits and pushes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List

# Default secret patterns - users can add more via config
DEFAULT_SECRET_PATTERNS = [
    r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*[\"'][A-Za-z0-9\-_\/]{12,}[\"']",
    r"AKIA[0-9A-Z]{16}",  # AWS access key id
    r"(?i)password\s*[:=]\s*[\"'][^\"']{8,}[\"']",  # Password assignments
    r"(?i)(bearer|auth)\s+[A-Za-z0-9\-_\.]{20,}",  # Bearer tokens
    r"(?i)(github|gitlab|bitbucket)[_-]?(token|key)\s*[:=]\s*[\"'][A-Za-z0-9\-_]{20,}[\"']",
    r"(?i)private[_-]?key\s*[:=]",  # Private key markers
]


@dataclass
class PolicyMessage:
    severity: str
    message: str


@dataclass
class PolicyResult:
    passed: bool
    messages: List[PolicyMessage] = field(default_factory=list)

    def add(self, severity: str, message: str) -> None:
        self.messages.append(PolicyMessage(severity=severity, message=message))
        if severity == "error":
            self.passed = False


def _compile_patterns(pattern_strings: List[str]) -> List[re.Pattern]:
    """Compile a list of regex pattern strings, skipping invalid ones."""
    patterns: List[re.Pattern] = []
    for pattern_str in pattern_strings:
        try:
            patterns.append(re.compile(pattern_str))
        except re.error:
            # Skip invalid patterns silently
            pass
    return patterns


def _secret_scan(diff_text: str, custom_patterns: List[str] | None = None) -> List[str]:
    """
    Scan diff text for secret patterns.
    
    Args:
        diff_text: Git diff output to scan
        custom_patterns: Optional list of custom regex patterns to check
        
    Returns:
        List of findings (secret pattern matches)
    """
    findings: List[str] = []
    
    # Combine default and custom patterns
    all_pattern_strings = DEFAULT_SECRET_PATTERNS.copy()
    if custom_patterns:
        all_pattern_strings.extend(custom_patterns)
    
    patterns = _compile_patterns(all_pattern_strings)
    
    for pattern in patterns:
        matches = pattern.findall(diff_text)
        if matches:
            # Truncate pattern for display
            pattern_display = pattern.pattern[:50] + "..." if len(pattern.pattern) > 50 else pattern.pattern
            # Flatten nested tuples from regex groups
            flat_matches = []
            for match in matches:
                if isinstance(match, tuple):
                    flat_matches.extend(str(m) for m in match if m)
                else:
                    flat_matches.append(str(match))
            findings.append(f"Secret pattern detected: {pattern_display}")
    
    return findings


def _check_large_files(files: List[str], diff_text: str, threshold: int = 500) -> List[str]:
    """
    Check for individual files with large diffs.
    
    Args:
        files: List of changed files
        diff_text: Full diff text
        threshold: Line threshold for individual file warning
        
    Returns:
        List of warnings for large files
    """
    warnings: List[str] = []
    
    # Parse diff to count lines per file
    file_line_counts: dict[str, int] = {f: 0 for f in files}
    current_file: str | None = None
    
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            # Extract filename from "diff --git a/path b/path"
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3][2:]  # Remove "b/" prefix
        elif current_file and line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            if current_file in file_line_counts:
                file_line_counts[current_file] += 1
    
    for file_path, line_count in file_line_counts.items():
        if line_count > threshold:
            warnings.append(f"Large diff in {file_path}: {line_count} lines (threshold {threshold})")
    
    return warnings


def run_checks(
    *,
    diff_text: str,
    diff_line_limit: int,
    files: List[str] | None = None,
    secret_patterns: List[str] | None = None,
    protected_branches: List[str] | None = None,
    current_branch: str | None = None,
    large_file_threshold: int = 500,
) -> PolicyResult:
    """
    Execute configured safety and policy checks.
    
    Args:
        diff_text: Git diff output to check
        diff_line_limit: Maximum total diff lines allowed
        files: List of changed files (for large file detection)
        secret_patterns: Custom secret regex patterns
        protected_branches: List of branch names that should not be auto-pushed
        current_branch: Current git branch name
        large_file_threshold: Warn if a single file exceeds this many changed lines
        
    Returns:
        PolicyResult with pass/fail status and messages
    """
    result = PolicyResult(passed=True)

    # Check total diff size
    diff_lines = sum(1 for line in diff_text.splitlines() if line.startswith(("+", "-")))
    if diff_lines > diff_line_limit:
        result.add("error", f"Diff adds/removes {diff_lines} lines (limit {diff_line_limit}).")

    # Secret scanning
    for finding in _secret_scan(diff_text, secret_patterns):
        result.add("error", finding)

    # Protected branch check
    if protected_branches and current_branch:
        if current_branch in protected_branches:
            result.add("warning", f"Branch '{current_branch}' is protected. Auto-push will be skipped.")

    # Large file warnings
    if files and diff_text:
        for warning in _check_large_files(files, diff_text, large_file_threshold):
            result.add("warning", warning)

    return result
