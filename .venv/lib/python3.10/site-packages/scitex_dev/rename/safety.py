#!/usr/bin/env python3
# Timestamp: 2026-02-14
# File: scitex_dev/rename/safety.py

"""Safety checks for bulk rename operations."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def has_uncommitted_changes(directory: str) -> bool:
    """Check if git working tree has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def is_git_repo(directory: str) -> bool:
    """Check if directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def check_directory_safety(directory: str) -> str | None:
    """Validate directory is safe for bulk rename.

    Returns None if safe, or an error message string.
    """
    resolved = Path(directory).resolve()

    # Block system-critical paths
    dangerous = {
        "/",
        "/home",
        "/usr",
        "/etc",
        "/var",
        "/bin",
        "/sbin",
        "/opt",
        "/tmp",
    }
    if str(resolved) in dangerous:
        return f"Refusing to rename in system directory: {resolved}"

    # Block shallow paths (less than 3 components like /home/user)
    if len(resolved.parts) < 3:
        return f"Refusing to rename in shallow directory: {resolved}"

    # Must be inside a git repo (so we can revert with git checkout)
    if not is_git_repo(str(resolved)):
        return (
            f"Directory is not inside a git repository: {resolved}. "
            "Rename requires git for safety (allows git checkout to revert)."
        )

    return None


def create_backup(directory: str, pattern: str, replacement: str) -> Path:
    """Create a backup of the directory before renaming."""
    backup_base = Path(directory) / ".rename_backups"
    backup_base.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_base / f"backup_{timestamp}"
    backup_dir.mkdir()

    # Save operation metadata
    meta = backup_dir / "operation.txt"
    meta.write_text(
        f"pattern={pattern}\nreplacement={replacement}\n"
        f"directory={directory}\ntimestamp={timestamp}\n"
    )

    # Copy directory contents
    original_dir = backup_dir / "original"
    original_dir.mkdir()
    for item in Path(directory).iterdir():
        if item.name == ".rename_backups":
            continue
        dest = original_dir / item.name
        if item.is_dir():
            shutil.copytree(str(item), str(dest), symlinks=True)
        else:
            shutil.copy2(str(item), str(dest))

    return backup_dir


def check_permissions(result: Any) -> list[dict[str, str]]:
    """Check write permissions for all paths that would be modified.

    Examines the dry-run RenameResult and checks whether each file/directory
    is writable. Returns a list of permission errors found.

    Parameters
    ----------
    result : RenameResult
        A dry-run result from bulk_rename().

    Returns
    -------
    list of dict
        Each dict has 'path', 'operation', and 'reason' keys.
    """
    import os

    errors: list[dict[str, str]] = []

    # Check files whose contents would be modified
    for item in result.contents:
        path = Path(item["file"])
        if path.exists() and not os.access(path, os.W_OK):
            errors.append(
                {
                    "path": str(path),
                    "operation": "content_replace",
                    "reason": "file not writable",
                }
            )

    # Check files that would be renamed (need write on parent dir)
    for item in result.file_names:
        old_path = Path(item["old_path"])
        if old_path.exists():
            parent = old_path.parent
            if not os.access(parent, os.W_OK):
                errors.append(
                    {
                        "path": str(old_path),
                        "operation": "file_rename",
                        "reason": f"parent directory not writable: {parent}",
                    }
                )
            if not os.access(old_path, os.R_OK):
                errors.append(
                    {
                        "path": str(old_path),
                        "operation": "file_rename",
                        "reason": "file not readable",
                    }
                )

    # Check directories that would be renamed
    for item in result.dir_names:
        old_path = Path(item["old_path"])
        if old_path.exists():
            parent = old_path.parent
            if not os.access(parent, os.W_OK):
                errors.append(
                    {
                        "path": str(old_path),
                        "operation": "dir_rename",
                        "reason": f"parent directory not writable: {parent}",
                    }
                )

    # Check symlinks that would be modified
    for item in result.symlink_targets:
        link_path = Path(item["link"])
        if link_path.exists():
            parent = link_path.parent
            if not os.access(parent, os.W_OK):
                errors.append(
                    {
                        "path": str(link_path),
                        "operation": "symlink_update",
                        "reason": f"parent directory not writable: {parent}",
                    }
                )

    for item in result.symlink_names:
        old_path = Path(item["old_name"])
        if old_path.exists():
            parent = old_path.parent
            if not os.access(parent, os.W_OK):
                errors.append(
                    {
                        "path": str(old_path),
                        "operation": "symlink_rename",
                        "reason": f"parent directory not writable: {parent}",
                    }
                )

    return errors


# EOF
