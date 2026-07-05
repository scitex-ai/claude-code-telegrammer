#!/usr/bin/env python3
# Timestamp: 2026-02-14
# File: scitex_dev/rename/steps.py

"""Five-step execution order for bulk rename operations."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .config import RenameConfig
from .filters import (
    find_matching_files,
    is_django_protected_line,
    is_src_excluded,
    should_exclude_path,
)
from .io import (
    mkdir as _mkdir,
)
from .io import (
    rename_path as _rename_path,
)
from .io import (
    rmdir as _rmdir,
)
from .io import (
    symlink_to as _symlink_to,
)
from .io import (
    unlink_path as _unlink_path,
)
from .io import (
    write_text as _write_text,
)


def _should_skip(item_id: str, skip_ids: list[str]) -> bool:
    """Check whether an item should be skipped based on skip_ids."""
    return item_id in skip_ids


def _contains(text: str, config: RenameConfig) -> bool:
    """Check if text contains the pattern (literal or regex)."""
    if config.regex:
        return re.search(config.pattern, text, re.DOTALL) is not None
    return config.pattern in text


def _replace(text: str, config: RenameConfig) -> str:
    """Replace pattern in text (literal or regex)."""
    if config.regex:
        return re.sub(config.pattern, config.replacement, text, flags=re.DOTALL)
    return text.replace(config.pattern, config.replacement)


def _count(text: str, config: RenameConfig) -> int:
    """Count pattern occurrences in text (literal or regex)."""
    if config.regex:
        return len(re.findall(config.pattern, text, re.DOTALL))
    return text.count(config.pattern)


def rename_file_contents(config: RenameConfig, directory: str) -> list[dict[str, Any]]:
    """Step 0: Replace pattern in file contents.

    When regex=True, operates on the whole file content (supports multiline
    patterns with re.DOTALL). When regex=False, operates line-by-line with
    Django-safe and SRC-level protection.
    """
    files = find_matching_files(directory, config, need_content_match=True)
    results = []

    for i, file_path in enumerate(files):
        file_id = f"c-{i:03d}"

        try:
            content = file_path.read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        skip_entire_file = _should_skip(file_id, config.skip_ids)

        if config.regex:
            # Regex mode: whole-file replacement (supports multiline)
            entry = _regex_replace_content(
                config, file_path, content, file_id, skip_entire_file
            )
        else:
            # Literal mode: line-by-line with protection
            entry = _literal_replace_content(
                config, file_path, content, file_id, skip_entire_file
            )

        if entry is not None:
            results.append(entry)

    return results


def _regex_replace_content(
    config: RenameConfig,
    file_path: Path,
    content: str,
    file_id: str,
    skip_entire_file: bool,
) -> dict[str, Any] | None:
    """Regex-based whole-file content replacement."""
    matches = _count(content, config)
    if matches == 0:
        return None

    new_content = _replace(content, config)

    if not config.dry_run and not skip_entire_file:
        _write_text(file_path, new_content, config.use_sudo)

    entry: dict[str, Any] = {
        "id": file_id,
        "file": str(file_path),
        "matches": matches,
        "protected": 0,
    }
    if config.dry_run:
        # Show before/after snippets for each match
        snippets = []
        for m in re.finditer(config.pattern, content, re.DOTALL):
            if len(snippets) >= 20:
                break
            matched_text = m.group()
            replaced_text = re.sub(
                config.pattern, config.replacement, matched_text, flags=re.DOTALL
            )
            snippets.append(
                {
                    "id": f"{file_id}-M{len(snippets)}",
                    "action": "skip" if skip_entire_file else "replace",
                    "before": matched_text[:200],
                    "after": replaced_text[:200],
                }
            )
        entry["lines"] = snippets

    return entry


def _literal_replace_content(
    config: RenameConfig,
    file_path: Path,
    content: str,
    file_id: str,
    skip_entire_file: bool,
) -> dict[str, Any] | None:
    """Literal string line-by-line content replacement with protection."""
    lines = content.split("\n")
    matches = 0
    protected = 0
    new_lines = []
    line_details: list[dict[str, Any]] = []

    for line_num, line in enumerate(lines, 1):
        if config.pattern in line:
            line_id = f"{file_id}-L{line_num}"
            skip_this_line = skip_entire_file or _should_skip(line_id, config.skip_ids)

            should_protect = False
            if config.django_safe and is_django_protected_line(line, config.pattern):
                should_protect = True
            if is_src_excluded(line, config):
                should_protect = True

            if should_protect:
                protected += 1
                new_lines.append(line)
                if config.dry_run and len(line_details) < 20:
                    line_details.append(
                        {
                            "id": line_id,
                            "line_num": line_num,
                            "action": "protect",
                            "before": line,
                            "after": line,
                        }
                    )
            elif skip_this_line:
                new_lines.append(line)
                if config.dry_run and len(line_details) < 20:
                    line_details.append(
                        {
                            "id": line_id,
                            "line_num": line_num,
                            "action": "skip",
                            "before": line,
                            "after": line,
                        }
                    )
            else:
                matches += line.count(config.pattern)
                replaced = line.replace(config.pattern, config.replacement)
                new_lines.append(replaced)
                if config.dry_run and len(line_details) < 20:
                    line_details.append(
                        {
                            "id": line_id,
                            "line_num": line_num,
                            "action": "replace",
                            "before": line,
                            "after": replaced,
                        }
                    )
        else:
            new_lines.append(line)

    if matches == 0:
        return None

    if not config.dry_run and not skip_entire_file:
        _write_text(file_path, "\n".join(new_lines), config.use_sudo)

    entry: dict[str, Any] = {
        "id": file_id,
        "file": str(file_path),
        "matches": matches,
        "protected": protected,
    }
    if config.dry_run:
        entry["lines"] = line_details

    return entry


def _iter_paths(root: Path, config: RenameConfig):
    """Iterate paths respecting recursive setting."""
    return sorted(root.rglob("*")) if config.recursive else sorted(root.glob("*"))


def update_symlink_targets(
    config: RenameConfig, directory: str
) -> list[dict[str, Any]]:
    """Step 1: Update symlink targets to point to future paths."""
    root = Path(directory)
    results = []
    idx = 0

    for path in _iter_paths(root, config):
        if not path.is_symlink():
            continue
        if should_exclude_path(path, config):
            continue

        target = os.readlink(str(path))
        if _contains(target, config):
            item_id = f"st-{idx:03d}"
            new_target = _replace(target, config)

            if not config.dry_run and not _should_skip(item_id, config.skip_ids):
                _unlink_path(path, config.use_sudo)
                _symlink_to(path, new_target, config.use_sudo)

            results.append(
                {
                    "id": item_id,
                    "link": str(path),
                    "old_target": target,
                    "new_target": new_target,
                }
            )
            idx += 1

    return results


def rename_symlink_names(config: RenameConfig, directory: str) -> list[dict[str, Any]]:
    """Step 2: Rename symlink basenames."""
    root = Path(directory)
    results = []
    idx = 0

    for path in _iter_paths(root, config):
        if not path.is_symlink():
            continue
        if should_exclude_path(path, config):
            continue

        name = path.name
        if _contains(name, config):
            item_id = f"sn-{idx:03d}"
            new_name = _replace(name, config)
            new_path = path.parent / new_name
            target_exists = new_path.exists() and new_path != path

            if not config.dry_run and not _should_skip(item_id, config.skip_ids):
                _rename_path(path, new_path, config.use_sudo)

            results.append(
                {
                    "id": item_id,
                    "old_name": str(path),
                    "new_name": str(new_path),
                    "target_exists": target_exists,
                }
            )
            idx += 1

    return results


def rename_file_names(config: RenameConfig, directory: str) -> list[dict[str, Any]]:
    """Step 3: Rename file basenames."""
    files = find_matching_files(directory, config)
    results = []
    idx = 0

    for file_path in files:
        name = file_path.name
        if _contains(name, config):
            item_id = f"f-{idx:03d}"
            new_name = _replace(name, config)
            new_path = file_path.parent / new_name
            target_exists = new_path.exists() and new_path != file_path

            if not config.dry_run and not _should_skip(item_id, config.skip_ids):
                _rename_path(file_path, new_path, config.use_sudo)

            results.append(
                {
                    "id": item_id,
                    "old_path": str(file_path),
                    "new_path": str(new_path),
                    "target_exists": target_exists,
                }
            )
            idx += 1

    return results


def _merge_directory(src: Path, dst: Path, use_sudo: bool = False) -> int:
    """Move all children from src into dst, then remove empty src.

    Returns number of items moved.
    """
    moved = 0
    for child in list(src.iterdir()):
        target = dst / child.name
        if child.is_dir() and target.is_dir():
            moved += _merge_directory(child, target, use_sudo)
        else:
            if target.exists():
                _unlink_path(target, use_sudo)
            _rename_path(child, target, use_sudo)
            moved += 1
    # Remove src if now empty
    if src.exists() and not any(src.iterdir()):
        _rmdir(src, use_sudo)
    return moved


def rename_directory_names(
    config: RenameConfig, directory: str
) -> list[dict[str, Any]]:
    """Step 4: Rename directories (deepest first).

    Matches pattern against both:
    - Leaf directory name (e.g., 'js')
    - Relative path from root (e.g., 'static/scholar_app/js')
    This enables patterns like 'scholar_app/js' to match path segments.

    When target directory exists, merges contents into it.
    """
    root = Path(directory)
    results = []

    dirs = []
    glob_iter = root.rglob("*") if config.recursive else root.glob("*")
    for path in glob_iter:
        if path.is_dir() and not path.is_symlink():
            if should_exclude_path(path, config):
                continue
            rel_path = str(path.relative_to(root))
            if _contains(path.name, config) or _contains(rel_path, config):
                dirs.append(path)

    dirs.sort(key=lambda p: len(p.parts), reverse=True)

    for idx, dir_path in enumerate(dirs):
        item_id = f"d-{idx:03d}"

        if not dir_path.exists():
            continue  # already moved by parent merge
        if _contains(dir_path.name, config):
            new_name = _replace(dir_path.name, config)
            new_path = dir_path.parent / new_name
        else:
            rel = str(dir_path.relative_to(root))
            new_rel = _replace(rel, config)
            new_path = root / new_rel
        target_exists = new_path.exists() and new_path != dir_path

        if not config.dry_run and not _should_skip(item_id, config.skip_ids):
            _mkdir(new_path.parent, parents=True, use_sudo=config.use_sudo)
            if target_exists:
                _merge_directory(dir_path, new_path, config.use_sudo)
            else:
                _rename_path(dir_path, new_path, config.use_sudo)

        results.append(
            {
                "id": item_id,
                "old_path": str(dir_path),
                "new_path": str(new_path),
                "target_exists": target_exists,
                "merged": target_exists,
            }
        )

    return results


# EOF
