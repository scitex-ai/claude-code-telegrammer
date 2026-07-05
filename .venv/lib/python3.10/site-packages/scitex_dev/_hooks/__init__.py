"""scitex-dev canonical agent hooks (Pillar-0).

The 2026-06-12 ripple-wm dogfood pinned the fanned-out-copy class:
~10 deployed copies of ``run_lint.sh`` across operator projects each
carried their own drift, and the canonical chain of
``scitex-linter`` (archived) + ``scitex linter`` (dropped #95
umbrella-thinning) silently no-op'd the SciTeX pattern check on
every research script edit. This package ships the AUTHORITATIVE
hook scripts so future fixes land in one place and operator projects
that symlink (or thin-wrap) automatically pick them up.

To install in a project (manual today; future ``scitex-dev hooks
install`` CLI will automate this):

    ln -s "$(python -c 'from scitex_dev._hooks import HOOK_DIR; \
        import pathlib; print(pathlib.Path(HOOK_DIR) / "run_lint.sh")')" \
        docs/to_claude/hooks/post-tool-use/run_lint.sh
"""

from __future__ import annotations

import pathlib

HOOK_DIR: str = str(pathlib.Path(__file__).resolve().parent)
"""Absolute path of the directory holding the canonical hook scripts."""


def run_lint_sh_path() -> str:
    """Return the absolute filesystem path of the canonical ``run_lint.sh``.

    Used by operator-project bootstrap scripts (and the future
    ``scitex-dev hooks install`` CLI) to resolve the file without
    string-concatenating ``HOOK_DIR``. Always returns the path inside
    the installed scitex-dev package, never a copy.
    """
    return str(pathlib.Path(HOOK_DIR) / "run_lint.sh")


def run_testmon_sh_path() -> str:
    """Return the absolute filesystem path of the canonical ``run_testmon.sh``.

    The testmon warm-cache wrapper makes pytest-testmon worktree-
    resilient: every release runs in a FRESH worktree with a COLD
    ``.testmondata``, so testmon re-runs the full suite instead of only
    impacted tests. This wrapper seed-copies a persistent per-(repo,
    pyXY) cache in/out of the worktree. Resolved the same way as
    :func:`run_lint_sh_path` so operator-project bootstrap and the
    ``scitex-dev hooks`` CLI never string-concatenate ``HOOK_DIR``.
    """
    return str(pathlib.Path(HOOK_DIR) / "run_testmon.sh")


__all__ = ["HOOK_DIR", "run_lint_sh_path", "run_testmon_sh_path"]
