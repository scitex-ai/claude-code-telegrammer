#!/usr/bin/env python3
# Timestamp: 2026-04-28
# File: scitex_config/_local_state.py

"""Per-package local-state path resolver.

Implements the canonical SciTeX layout from
``scitex-python/src/scitex/_skills/general/01_arch_06_local-state-directories.md``:

    $SCITEX_DIR (default: ~/.scitex)
    └── <pkg-short>/                  ← user scope, lower precedence
        ├── config.yaml               ← tracked
        ├── _skills/<pkg>/            ← tracked
        └── runtime/                  ← gitignored: logs, caches, PIDs, DBs

    <project-root>/.scitex/<pkg-short>/   ← project scope, HIGHER precedence
        └── (same shape; overrides user scope file-by-file)

Usage::

    from scitex_config import local_state

    cfg = local_state.path("hpc", "config.yaml")
    log = local_state.runtime_path("hpc", "dispatch.log")
    host = local_state.user_path("dev", "host-identity.yaml")  # skip project scope

The helper:

- Reads ``$SCITEX_DIR`` lazily (resolved per call so changes take effect
  during long-running processes).
- For ``path()``: walks up from ``Path.cwd()`` looking for a git
  repository root (``.git/`` directory). If found, checks
  ``<repo-root>/.scitex/<pkg-short>/<sub>``; returns it iff it exists.
  Else falls back to ``$SCITEX_DIR/<pkg-short>/<sub>`` (which may or
  may not exist).
- For ``runtime_path()``: same scope detection but always under
  ``runtime/``; lazily creates the directory + the canonical
  ``.gitkeep`` and ``README.md`` seeds on first access.
- For ``user_path()``: skips project-scope detection entirely.

This is the *path* sibling of ``PriorityConfig.resolve()`` (which
handles per-field precedence). They compose: use ``local_state.path``
to find the YAML, then load it through ``PriorityConfig`` to resolve
each field.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "find_project_scope",
    "path",
    "runtime_path",
    "user_path",
    "user_root",
]


def user_root() -> Path:
    """Return the user-scope root: ``$SCITEX_DIR`` (default ``~/.scitex``).

    Resolved per call so live ``SCITEX_DIR`` changes are honoured.
    """
    return Path(os.environ.get("SCITEX_DIR", str(Path.home() / ".scitex")))


def find_project_scope(pkg_short: str, start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default cwd) looking for a project-scope
    `.scitex/<pkg-short>/` directory inside a git repository.

    The walk stops at the first directory containing ``.git/`` — that's
    the repo root — and returns ``<repo-root>/.scitex/<pkg-short>/`` if
    that directory exists, else ``None``.

    The git boundary is deliberate: it provides an unambiguous "this is
    a project" marker. If a user wants project scope without git, they
    can ``git init``.
    """
    if start is None:
        start = Path.cwd()
    start = start.resolve()
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            scope = candidate / ".scitex" / pkg_short
            return scope if scope.is_dir() else None
    return None


def _ensure_runtime_seeds(runtime_dir: Path) -> None:
    """Create ``.gitkeep`` and ``README.md`` seeds inside ``runtime/``.

    Called lazily by ``runtime_path()`` so the on-disk shape matches
    the layout skill (§1: 'every <pkg-short>/ root MUST contain a
    runtime/ subdirectory'). Ships exactly two files; everything else
    is gitignored by the package's own ``.gitignore``.
    """
    runtime_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = runtime_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("")
    readme = runtime_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# `runtime/`\n"
            "\n"
            "Per-host, per-run state for this SciTeX package: logs, PID files, "
            "caches, ephemeral databases, workspace dirs. Everything here is "
            "regenerable from config + source — never commit anything except "
            "this README and the sibling `.gitkeep`.\n"
            "\n"
            "Layout reference: scitex-python skill "
            "`01_arch_06_local-state-directories.md`.\n"
        )


def path(pkg_short: str, *parts: str) -> Path:
    """Resolve a tracked-state path for ``pkg_short``.

    Project scope wins iff
    ``<git-repo-root>/.scitex/<pkg-short>/<*parts>`` exists; else falls
    back to ``$SCITEX_DIR/<pkg-short>/<*parts>``.

    The fallback path is returned unconditionally (does not have to
    exist) — callers may then choose to read or write it.
    """
    project = find_project_scope(pkg_short)
    if project is not None:
        candidate = project.joinpath(*parts) if parts else project
        if candidate.exists():
            return candidate
    return user_root() / pkg_short / Path(*parts) if parts else user_root() / pkg_short


def runtime_path(pkg_short: str, *parts: str) -> Path:
    """Resolve a runtime path for ``pkg_short``.

    Same scope-precedence as ``path()`` but always under ``runtime/``.
    The runtime dir + its canonical ``.gitkeep``/``README.md`` seeds
    are created on first call (whichever scope is chosen), so callers
    can write logs/PIDs immediately.
    """
    project = find_project_scope(pkg_short)
    if project is not None:
        runtime_dir = project / "runtime"
    else:
        runtime_dir = user_root() / pkg_short / "runtime"
    _ensure_runtime_seeds(runtime_dir)
    return runtime_dir.joinpath(*parts) if parts else runtime_dir


def user_path(pkg_short: str, *parts: str) -> Path:
    """Force user-scope resolution (skip project-scope walk).

    Use for state that must be per-host (machine identity, SSH keys,
    cluster credentials) — these should never live inside a project
    repo even when one is present.
    """
    base = user_root() / pkg_short
    return base.joinpath(*parts) if parts else base


# EOF
