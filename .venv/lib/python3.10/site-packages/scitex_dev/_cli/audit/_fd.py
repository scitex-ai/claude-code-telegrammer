#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rust-tool-backed file discovery for the audit suite.

Operator directive (2026-05-21): where the audit does recursive file
discovery, prefer the Rust `fd` tool over Python `os.walk` / `pathlib`
walks. `fd` honours `.gitignore` and is markedly faster on large trees.

fd-preferred, LOUD about absence (2026-05-24): `fd` is the preferred
*accelerator* — the operator wants it because it is faster. But its
absence must never silently degrade and never hard-crash by default.
`fd_find_files`:

- **fd present** → uses `fd`/`fdfind` (fast path).
- **fd absent, `require_fd=False` (default)** → emits a LOUD warning
  every time ("fd/fdfind not found on PATH — falling back to slower
  stdlib scan; install fd for speed") AND falls back to a stdlib
  `pathlib.rglob` walk so the audit runs to completion. This matters
  because downstream CI runners (GitHub `ubuntu-latest`) do not ship
  `fd`. The fallback ANNOUNCES — there is no silent fallback.
- **fd absent, `require_fd=True` (strict knob)** → raises
  `FdNotFoundError` (fail loud). Wired from `.scitex/dev/config.yaml`
  `audit.require-fd: true` (or pyproject `[tool.scitex_dev]
  audit.require_fd`) by the caller; see `_check_orphan_hint`.

The low-level `fd_binary()` primitive still raises `FdNotFoundError` for
callers that genuinely require the binary; `fd_find_files()` only raises
on the missing-binary path when `require_fd=True`.
"""

from __future__ import annotations

import shutil
import subprocess
import warnings
from pathlib import Path

#: Install hint surfaced when `fd` is missing. Covers the common package
#: managers; `fd-find` is the Debian/Ubuntu name (binary is `fdfind`).
FD_INSTALL_HINT = (
    "the Rust `fd` tool is required for audit file discovery but was not "
    "found on PATH. Install it: `cargo install fd-find`, "
    "`brew install fd`, or `apt install fd-find` (Debian/Ubuntu installs "
    "the binary as `fdfind`)."
)

#: Loud message emitted when `fd` is absent and the audit falls back to the
#: slower stdlib walk. Announced (not silent) every time, per operator
#: directive: a missing optional accelerator must be visible.
FD_FALLBACK_WARNING = (
    "fd/fdfind not found on PATH — falling back to slower stdlib scan; "
    "install fd for speed (`cargo install fd-find`, `brew install fd`, or "
    "`apt install fd-find`)."
)


class FdNotFoundError(RuntimeError):
    """Raised when the required `fd` binary is not available on PATH."""


def fd_available() -> str | None:
    """Return the resolved `fd`/`fdfind` path if present, else ``None``.

    Non-raising counterpart of :func:`fd_binary`; used by the graceful
    discovery path to decide between the `fd` fast path and the stdlib
    fallback.
    """
    for name in ("fd", "fdfind"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def fd_binary() -> str:
    """Return the resolved path to the `fd` binary, or raise loudly.

    Accepts the Debian/Ubuntu `fdfind` alias as a fallback name.

    Raises
    ------
    FdNotFoundError
        If neither `fd` nor `fdfind` is found on PATH.
    """
    resolved = fd_available()
    if resolved:
        return resolved
    raise FdNotFoundError(FD_INSTALL_HINT)


def _rglob_find_files(root: Path, *, glob: str) -> list[Path]:
    """Stdlib fallback for :func:`fd_find_files` when `fd` is absent.

    Mirrors the `fd --type f --glob <glob>` result: files only, recursive,
    absolute paths, sorted. Not gitignore-aware (acceptable for an audit
    run over a package's own `src/` tree, which has no vendored deps).
    """
    if not root.is_dir():
        return []
    return sorted(p.resolve() for p in root.rglob(glob) if p.is_file())


def fd_find_files(
    root: Path,
    *,
    glob: str = "*.py",
    require_fd: bool = False,
) -> list[Path]:
    """Recursively find files under `root` matching `glob`.

    Uses the Rust `fd` tool as the preferred fast path when present.

    When neither `fd` nor `fdfind` is on PATH the behaviour depends on
    `require_fd`:

    - ``require_fd=False`` (default): emit a LOUD warning
      (:data:`FD_FALLBACK_WARNING`) and fall back to a stdlib
      `pathlib.rglob` walk, so the audit runs to completion. The
      fallback always announces — never silent.
    - ``require_fd=True`` (strict knob): raise :class:`FdNotFoundError`
      (fail loud), for CI that wants to guarantee the fast path ran.

    Either successful path returns absolute `Path` objects, sorted for
    deterministic ordering. Mirrors `Path.rglob(glob)` semantics for
    plain file discovery (files only, recursive).

    Parameters
    ----------
    root
        Directory to search under.
    glob
        Glob pattern matched against file names (e.g. ``"*.py"``,
        ``"test_*.py"``).
    require_fd
        When True and `fd` is absent, raise :class:`FdNotFoundError`
        instead of falling back. Defaults to False (warn + fall back).

    Raises
    ------
    FdNotFoundError
        Only when `require_fd=True` and `fd`/`fdfind` is not on PATH.
    """
    binary = fd_available()
    if binary is None:
        if require_fd:
            raise FdNotFoundError(FD_INSTALL_HINT)
        warnings.warn(FD_FALLBACK_WARNING, RuntimeWarning, stacklevel=2)
        return _rglob_find_files(root, glob=glob)
    if not root.is_dir():
        return []
    proc = subprocess.run(
        [
            binary,
            "--type",
            "f",
            "--absolute-path",
            "--glob",
            glob,
            str(root),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode not in (0, 1):
        # fd: 0 = matches, 1 = no matches (newer fd uses 0 either way);
        # anything else is a real error — surface it loudly.
        raise RuntimeError(
            f"fd failed under {root} (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    return sorted(Path(line) for line in proc.stdout.splitlines() if line.strip())
