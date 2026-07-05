#!/usr/bin/env python3
# Timestamp: 2026-02-14
# File: scitex_dev/rename/core.py

"""Core orchestration for bulk rename operations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import RenameConfig, RenameResult
from .filters import find_matching_files, should_exclude_path
from .safety import (
    check_directory_safety,
    create_backup,
    has_uncommitted_changes,
)
from .steps import (
    rename_directory_names,
    rename_file_contents,
    rename_file_names,
    rename_symlink_names,
    update_symlink_targets,
)


def _pre_check_safety(
    config: RenameConfig, directory: str
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Lightweight pre-check for collisions and permissions.

    Instead of running a full dry-run (which re-scans all file contents),
    this only checks:
    - Path-based collisions (file/symlink/dir renames)
    - Write permissions on content files and rename parents
    """
    from .steps import _contains, _iter_paths, _replace

    collisions: list[dict[str, Any]] = []
    permission_errors: list[dict[str, str]] = []

    root = Path(directory)

    # Check content files: only need file list + write permission
    content_files = find_matching_files(directory, config, need_content_match=True)
    for f in content_files:
        if f.exists() and not os.access(f, os.W_OK):
            permission_errors.append(
                {
                    "path": str(f),
                    "operation": "content_replace",
                    "reason": "file not writable",
                }
            )

    # Check file name collisions + parent permissions
    all_files = find_matching_files(directory, config)
    for file_path in all_files:
        if _contains(file_path.name, config):
            new_name = _replace(file_path.name, config)
            new_path = file_path.parent / new_name
            if new_path.exists() and new_path != file_path:
                collisions.append({"type": "file", "path": str(new_path)})
            parent = file_path.parent
            if not os.access(parent, os.W_OK):
                permission_errors.append(
                    {
                        "path": str(file_path),
                        "operation": "file_rename",
                        "reason": f"parent not writable: {parent}",
                    }
                )

    # Check symlink collisions + permissions
    for path in _iter_paths(root, config):
        if not path.is_symlink():
            continue
        if should_exclude_path(path, config):
            continue
        if _contains(path.name, config):
            new_name = _replace(path.name, config)
            new_path = path.parent / new_name
            if new_path.exists() and new_path != path:
                collisions.append({"type": "symlink", "path": str(new_path)})
            parent = path.parent
            if not os.access(parent, os.W_OK):
                permission_errors.append(
                    {
                        "path": str(path),
                        "operation": "symlink_rename",
                        "reason": f"parent not writable: {parent}",
                    }
                )

    # Check directory rename collisions + permissions
    glob_iter = root.rglob("*") if config.recursive else root.glob("*")
    for path in glob_iter:
        if not path.is_dir() or path.is_symlink():
            continue
        if should_exclude_path(path, config):
            continue
        if _contains(path.name, config):
            new_name = _replace(path.name, config)
            new_path = path.parent / new_name
            if new_path.exists() and new_path != path:
                collisions.append({"type": "directory", "path": str(new_path)})
            parent = path.parent
            if not os.access(parent, os.W_OK):
                permission_errors.append(
                    {
                        "path": str(path),
                        "operation": "dir_rename",
                        "reason": f"parent not writable: {parent}",
                    }
                )

    return collisions, permission_errors


def _make_error_result(
    pattern: str, replacement: str, directory: str, error: str
) -> RenameResult:
    """Create an error RenameResult."""
    return RenameResult(
        dry_run=False,
        pattern=pattern,
        replacement=replacement,
        directory=directory,
        contents=[],
        symlink_targets=[],
        symlink_names=[],
        file_names=[],
        dir_names=[],
        summary={},
        error=error,
    )


def preview_rename(
    pattern: str,
    replacement: str,
    directory: str = ".",
    django_safe: bool = True,
    extra_excludes: list[str] | None = None,
    skip_ids: list[str] | None = None,
    **kwargs: Any,
) -> RenameResult:
    """Preview rename changes without executing (dry run).

    Parameters
    ----------
    pattern : str
        Pattern to search for.
    replacement : str
        String to replace matches with.
    directory : str
        Target directory.
    django_safe : bool
        Enable Django-safe mode.
    extra_excludes : list of str, optional
        Additional exclude patterns.

    Returns
    -------
    RenameResult
        Preview of all changes that would be made.
    """
    config = RenameConfig(
        pattern=pattern,
        replacement=replacement,
        directory=directory,
        dry_run=True,
        django_safe=django_safe,
        extra_excludes=extra_excludes or [],
        skip_ids=skip_ids or [],
        **kwargs,
    )
    return bulk_rename(config)


def execute_rename(
    pattern: str,
    replacement: str,
    directory: str = ".",
    django_safe: bool = True,
    create_backup: bool = False,
    extra_excludes: list[str] | None = None,
    force: bool = False,
    skip_ids: list[str] | None = None,
    *,
    uncommitted_check_fn=None,
    safety_check_fn=None,
    **kwargs: Any,
) -> RenameResult:
    """Execute rename with safety checks.

    Checks for uncommitted git changes before proceeding.

    Parameters
    ----------
    pattern : str
        Pattern to search for.
    replacement : str
        String to replace matches with.
    directory : str
        Target directory.
    django_safe : bool
        Enable Django-safe mode.
    create_backup : bool
        Create backup before changes.
    extra_excludes : list of str, optional
        Additional exclude patterns.
    force : bool
        Skip uncommitted changes check (default False).

    Returns
    -------
    RenameResult
        Results of the rename operation.
    """
    uncommitted_fn = (
        uncommitted_check_fn
        if uncommitted_check_fn is not None
        else has_uncommitted_changes
    )
    if not force and uncommitted_fn(directory):
        return _make_error_result(
            pattern,
            replacement,
            directory,
            "Uncommitted changes detected. "
            "Run 'git stash --include-untracked' or 'git commit' first, "
            "then retry. This ensures 'git checkout' can revert the rename.",
        )

    config = RenameConfig(
        pattern=pattern,
        replacement=replacement,
        directory=directory,
        dry_run=False,
        django_safe=django_safe,
        create_backup=create_backup,
        extra_excludes=extra_excludes or [],
        skip_ids=skip_ids or [],
        **kwargs,
    )
    return bulk_rename(config, safety_check_fn=safety_check_fn)


def bulk_rename(config: RenameConfig, *, safety_check_fn=None) -> RenameResult:
    """Execute bulk rename operation.

    Parameters
    ----------
    config : RenameConfig
        Configuration for the rename operation.

    Returns
    -------
    RenameResult
        Results including all changes made or previewed.
    """
    directory = str(Path(config.directory).resolve())

    # Safety: block dangerous directories and require git for live runs
    safety_fn = (
        safety_check_fn if safety_check_fn is not None else check_directory_safety
    )
    if not config.dry_run:
        safety_error = safety_fn(directory)
        if safety_error:
            return _make_error_result(
                config.pattern,
                config.replacement,
                directory,
                safety_error,
            )

    if config.create_backup and not config.dry_run:
        create_backup(directory, config.pattern, config.replacement)

    # Lightweight pre-check for collisions and permissions
    # (avoids expensive full dry-run that re-scans all file contents)
    if not config.dry_run:
        collisions, perm_errors = _pre_check_safety(config, directory)
        non_dir_collisions = [c for c in collisions if c.get("type") != "directory"]
        if non_dir_collisions:
            return _make_error_result(
                config.pattern,
                config.replacement,
                directory,
                f"Collisions detected: {len(non_dir_collisions)} target(s) already exist. "
                "Run dry-run to inspect.",
            )
        if perm_errors:
            paths = [e["path"] for e in perm_errors[:5]]
            return _make_error_result(
                config.pattern,
                config.replacement,
                directory,
                f"Permission denied: {len(perm_errors)} path(s) not writable. "
                f"First: {', '.join(paths)}. Run dry-run to inspect all.",
            )

    # Execute in order (critical for path integrity)
    contents = rename_file_contents(config, directory)
    symlink_targets = update_symlink_targets(config, directory)
    symlink_names = rename_symlink_names(config, directory)
    file_names = rename_file_names(config, directory)
    dir_names = rename_directory_names(config, directory)

    # Collect collisions from path-renaming steps
    collisions = []
    for item in symlink_names:
        if item.get("target_exists"):
            collisions.append({"type": "symlink", "path": item["new_name"]})
    for item in file_names:
        if item.get("target_exists"):
            collisions.append({"type": "file", "path": item["new_path"]})
    for item in dir_names:
        if item.get("target_exists"):
            collisions.append({"type": "directory", "path": item["new_path"]})

    # Detect Django app directory renames and emit warnings
    warnings: list[str] = []
    for item in dir_names:
        old_p = Path(item["old_path"])
        new_p = Path(item["new_path"])
        if (old_p / "apps.py").exists() or (new_p / "apps.py").exists():
            warnings.append(
                f"DJANGO APP RENAME DETECTED: {old_p.name} -> {new_p.name}. "
                "You MUST manually: (1) add explicit db_table to all models, "
                "(2) update migration file dependencies/references, "
                "(3) run SQL: UPDATE django_migrations SET app='new' WHERE app='old', "
                "(4) create a migration to update django_content_type rows. "
                "Model class renames need separate RenameModel migrations."
            )

    # Check permissions during dry run
    from .safety import check_permissions as _check_perms

    result_for_perms = RenameResult(
        dry_run=config.dry_run,
        pattern=config.pattern,
        replacement=config.replacement,
        directory=directory,
        contents=contents,
        symlink_targets=symlink_targets,
        symlink_names=symlink_names,
        file_names=file_names,
        dir_names=dir_names,
        summary={},
        collisions=collisions,
    )
    permission_errors = _check_perms(result_for_perms)

    summary: dict[str, Any] = {
        "content_files": len(contents),
        "content_matches": sum(c.get("matches", 0) for c in contents),
        "content_protected": sum(c.get("protected", 0) for c in contents),
        "protected_files": sum(1 for c in contents if c.get("protected", 0) > 0),
        "symlink_targets_updated": len(symlink_targets),
        "symlinks_renamed": len(symlink_names),
        "files_renamed": len(file_names),
        "dirs_renamed": len(dir_names),
        "collisions": len(collisions),
        "permission_errors": len(permission_errors),
    }
    if warnings:
        summary["warnings"] = warnings

    return RenameResult(
        dry_run=config.dry_run,
        pattern=config.pattern,
        replacement=config.replacement,
        directory=directory,
        contents=contents,
        symlink_targets=symlink_targets,
        symlink_names=symlink_names,
        file_names=file_names,
        dir_names=dir_names,
        summary=summary,
        collisions=collisions,
        permission_errors=permission_errors,
    )


# EOF
