"""Package-resolution helpers for the Python API auditor.

Split out of `_audit.py` — pure refactor, no behaviour change. Resolves a
distribution name to its on-disk ``__init__.py`` (installed package first,
then the ecosystem-registry source tree). Re-exported from `_audit` so
existing imports (`from ..._audit import _locate_init`) keep resolving.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _import_name(distribution: str) -> str:
    """`scitex-io` → `scitex_io` (canonical SciTeX convention)."""
    return distribution.replace("-", "_")


def _locate_init(distribution: str, import_name: str) -> Path | None:
    """Locate ``<pkg>/__init__.py`` for the given distribution.

    Resolution order (each step proceeds to the next on miss, so a package
    that is *neither* pip-installed *nor* registered still returns None and
    the caller skips the audit cleanly):

    1. **Installed package.** Import via ``importlib.util.find_spec``; use
       ``spec.origin`` when it points at an ``__init__.py``.
    2. **On-disk source tree (registry fallback).** When the package is
       NOT installed in the auditor's venv (the common case on a fresh
       ecosystem clone or in a CI runner that audits before
       ``pip install -e .``), look up ``distribution`` in
       ``scitex_dev._ecosystem._registry.ECOSYSTEM`` and probe
       ``<local_path>/src/<import_name>/__init__.py``.

    Without step 2, every non-installed peer's audit-python-apis silently
    "skips" (`return 0` with an info-level "package not importable"
    message) even when its on-disk `__init__.py` is right there waiting
    to be audited — a fail-silent class that hides real PA-1xx through
    PA-3xx violations behind a clean exit code. Mirrors the same fix
    landed for `_locate_skills_dir` in PR #177.
    """
    # 1. Installed package.
    spec = importlib.util.find_spec(import_name)
    if spec is not None and spec.origin is not None:
        origin = Path(spec.origin)
        if origin.name == "__init__.py":
            return origin

    # 2. On-disk source tree via the ecosystem registry. Defensive — a
    # stale / partial registry import must never break the per-package
    # audit; fall through to None and let the caller skip cleanly.
    try:
        from ....._ecosystem._registry import ECOSYSTEM
    except Exception:  # pragma: no cover — defensive
        return None
    info = ECOSYSTEM.get(distribution) or {}
    local_path = info.get("local_path")
    if not local_path:
        return None
    try:
        root = Path(local_path).expanduser()
    except (RuntimeError, OSError):  # pragma: no cover — defensive
        return None
    if not root.is_dir():
        return None
    candidate = root / "src" / import_name / "__init__.py"
    if candidate.is_file():
        return candidate
    return None


__all__ = ["_import_name", "_locate_init"]
