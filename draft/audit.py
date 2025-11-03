"""Audit trail utilities for DRaft operations."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_AUDIT_FILE = Path("draft_audit.jsonl")
DEFAULT_SNAPSHOT_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


def record_cycle(entry: dict[str, Any], audit_file: Path | None = None) -> None:
    """Append a cycle record to the audit log."""
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
    target = audit_file or DEFAULT_AUDIT_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def latest_entry(audit_file: Path | None = None) -> dict[str, Any] | None:
    """Return the most recent audit entry if available."""
    target = audit_file or DEFAULT_AUDIT_FILE
    if not target.exists():
        return None
    with target.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        if size == 0:
            return None
        # Read backwards until newline
        chunk_size = 1024
        buffer = b""
        offset = size
        while offset > 0:
            read_size = min(chunk_size, offset)
            offset -= read_size
            handle.seek(offset)
            buffer = handle.read(read_size) + buffer
            if b"\n" in buffer:
                break
        line = buffer.splitlines()[-1]
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


class SnapshotError(Exception):
    """Raised when snapshot operations fail."""


def snapshot_files(
    files: List[str], max_size: int = DEFAULT_SNAPSHOT_MAX_SIZE, root: Path | None = None
) -> Dict[str, str]:
    """
    Capture snapshots of files as base64-encoded content.
    
    Args:
        files: List of file paths relative to root
        max_size: Maximum size per file in bytes (files larger are skipped)
        root: Root directory (defaults to current directory)
        
    Returns:
        Dictionary mapping file paths to base64-encoded content
        
    Raises:
        SnapshotError: If snapshot operation fails critically
    """
    snapshots: Dict[str, str] = {}
    base_path = root or Path.cwd()
    
    for file_path in files:
        full_path = base_path / file_path
        
        # Skip if file doesn't exist (might be deleted)
        if not full_path.exists():
            snapshots[file_path] = ""  # Empty string indicates deleted/missing
            continue
            
        # Skip if file is too large
        try:
            file_size = full_path.stat().st_size
            if file_size > max_size:
                snapshots[file_path] = f"__SKIPPED_TOO_LARGE_{file_size}__"
                continue
        except OSError:
            snapshots[file_path] = "__SKIPPED_ERROR__"
            continue
            
        # Read and encode file content
        try:
            content = full_path.read_bytes()
            encoded = base64.b64encode(content).decode("ascii")
            snapshots[file_path] = encoded
        except (OSError, IOError) as exc:
            # Log but don't fail the entire snapshot operation
            snapshots[file_path] = f"__ERROR_{str(exc)[:50]}__"
            
    return snapshots


def restore_from_snapshot(
    snapshot: Dict[str, str],
    files: List[str] | None = None,
    root: Path | None = None,
    dry_run: bool = False,
) -> List[str]:
    """
    Restore files from a snapshot.
    
    Args:
        snapshot: Dictionary mapping file paths to base64-encoded content
        files: Optional list of specific files to restore (None = all in snapshot)
        root: Root directory (defaults to current directory)
        dry_run: If True, don't actually restore files, just return what would be restored
        
    Returns:
        List of files that were (or would be) restored
        
    Raises:
        SnapshotError: If restoration fails critically
    """
    base_path = root or Path.cwd()
    restored: List[str] = []
    
    # Determine which files to restore
    target_files = files if files is not None else list(snapshot.keys())
    
    for file_path in target_files:
        if file_path not in snapshot:
            continue
            
        encoded_content = snapshot[file_path]
        
        # Handle special markers
        if encoded_content == "":
            # File was deleted/missing in snapshot - delete it now if it exists
            full_path = base_path / file_path
            if full_path.exists() and not dry_run:
                try:
                    full_path.unlink()
                    restored.append(file_path)
                except OSError:
                    pass
            elif full_path.exists() and dry_run:
                restored.append(file_path)
            continue
            
        if encoded_content.startswith("__SKIPPED_") or encoded_content.startswith("__ERROR_"):
            # File was skipped or errored during snapshot - can't restore
            continue
            
        # Decode and write content
        try:
            content = base64.b64decode(encoded_content)
            full_path = base_path / file_path
            
            if not dry_run:
                # Ensure parent directory exists
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_bytes(content)
                
            restored.append(file_path)
        except (OSError, IOError, ValueError) as exc:
            # Silently skip files that can't be restored
            pass
            
    return restored


def find_cycle_entry(
    cycle_id: str, audit_file: Path | None = None
) -> dict[str, Any] | None:
    """
    Find a cycle entry by tag or timestamp.
    
    Args:
        cycle_id: Cycle tag (e.g., 'draft-20251101-142345') or timestamp
        audit_file: Path to audit file (defaults to DEFAULT_AUDIT_FILE)
        
    Returns:
        Cycle entry dict if found, None otherwise
    """
    target = audit_file or DEFAULT_AUDIT_FILE
    if not target.exists():
        return None
        
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("tag") == cycle_id or entry.get("timestamp") == cycle_id:
                    return entry
            except json.JSONDecodeError:
                continue
                
    return None
