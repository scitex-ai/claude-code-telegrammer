"""PS-180 — per-package `runtime/` separation discipline.

Card: ``ecosystem-runtime-separation`` (filed 2026-05-17). Note in the
project tracker: "Per-package runtime/ separation discipline. Default-
track everything except <pkg>/runtime/; exceptions belong in package-
level .gitignore (memory feedback_scitex_state_tracking_policy)."

Invariant
---------
A package's ``src/<pkg>/runtime/`` directory is where the package
caches transient state — logs, shell-completion caches, generated
artefacts. It MUST NOT be tracked by git. Each package's own
``.gitignore`` (either the repo-root ``.gitignore`` or
``src/<pkg>/.gitignore``) is the place to declare the exclusion — the
discipline is *package-level*, not enforced by a single global rule.

The auditor fires PS-180 when:

  * ``src/<pkg>/runtime/`` exists on disk, AND
  * no ``.gitignore`` line in the package tree covers the path.

Accepted ``.gitignore`` shapes (all evaluated against the
``src/<pkg>/runtime/`` path):

  * Bare ``runtime/`` or ``runtime`` (most common — placed in
    ``src/<pkg>/.gitignore`` so it scopes naturally).
  * ``src/<pkg>/runtime/`` or ``src/<pkg>/runtime`` (anchored from the
    repo root — common in the repo-root ``.gitignore``).
  * ``**/runtime/`` or ``**/runtime`` (catch-all pattern).
  * ``/runtime/`` — only when found in ``src/<pkg>/.gitignore`` (the
    leading slash anchors at that file's directory).

Rule shape mirrors sibling ``_check_*.py`` modules — single public
``check_runtime_separation(repo, violation_cls, out)`` that appends a
``violation_cls("PS-180", where, detail)`` per offending package.
"""

from __future__ import annotations

import re
from pathlib import Path


# Match a `.gitignore` line that excludes the package's runtime/ dir.
# We compile per (pkg_name, gitignore_location) because the legal shapes
# depend on where the file lives.
_RUNTIME_PATTERNS_PKG_LOCAL = (
    # bare `runtime/` or `runtime` (line on its own)
    re.compile(r"^\s*/?runtime/?\s*(?:#.*)?$", re.MULTILINE),
    # `**/runtime/` or `**/runtime`
    re.compile(r"^\s*\*\*/runtime/?\s*(?:#.*)?$", re.MULTILINE),
)


def _runtime_patterns_for_root(pkg_name: str) -> tuple[re.Pattern[str], ...]:
    """Patterns valid in the repo-root `.gitignore` for a given pkg."""
    return (
        # bare `runtime/` (root-level bare matches every `runtime/` in tree)
        re.compile(r"^\s*runtime/?\s*(?:#.*)?$", re.MULTILINE),
        # `**/runtime/`
        re.compile(r"^\s*\*\*/runtime/?\s*(?:#.*)?$", re.MULTILINE),
        # explicit `src/<pkg>/runtime/`
        re.compile(
            r"^\s*/?src/" + re.escape(pkg_name) + r"/runtime/?\s*(?:#.*)?$",
            re.MULTILINE,
        ),
    )


def _read_gitignore(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _src_pkg_dirs(repo: Path) -> list[Path]:
    """Return every ``src/<pkg>/`` directory under ``repo``.

    A package is any direct subdirectory of ``src/`` that is itself a
    directory (skips ``__pycache__``). Returns ``[]`` if ``src/`` is
    missing.
    """
    src = repo / "src"
    if not src.is_dir():
        return []
    out: list[Path] = []
    for child in src.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("__"):
            continue
        out.append(child)
    return out


def _is_runtime_ignored(repo: Path, pkg_dir: Path) -> bool:
    """Return True iff a `.gitignore` in the package tree covers
    ``src/<pkg>/runtime/``."""
    pkg_name = pkg_dir.name

    # 1. Repo-root .gitignore.
    root_gi_text = _read_gitignore(repo / ".gitignore")
    if root_gi_text:
        for pat in _runtime_patterns_for_root(pkg_name):
            if pat.search(root_gi_text):
                return True

    # 2. Package-level .gitignore (src/<pkg>/.gitignore).
    pkg_gi_text = _read_gitignore(pkg_dir / ".gitignore")
    if pkg_gi_text:
        for pat in _RUNTIME_PATTERNS_PKG_LOCAL:
            if pat.search(pkg_gi_text):
                return True

    return False


def check_runtime_separation(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-180 violations.

    PS-180 — ``src/<pkg>/runtime/`` exists on disk but no `.gitignore`
    entry covers it. Runtime artefacts (logs, caches, generated state)
    are user-state, not source — they belong outside version control.
    Exceptions live in the package's own ``.gitignore``, not a global
    rule.
    """
    for pkg_dir in _src_pkg_dirs(repo):
        runtime_dir = pkg_dir / "runtime"
        if not runtime_dir.is_dir():
            continue
        if _is_runtime_ignored(repo, pkg_dir):
            continue
        pkg_name = pkg_dir.name
        out.append(
            violation_cls(
                "PS-180",
                str(runtime_dir),
                (
                    f"`src/{pkg_name}/runtime/` exists on disk but no "
                    f".gitignore entry covers it. Runtime artefacts "
                    f"(logs, caches, generated state) are user-state, "
                    f"not source — they must not be tracked by git. "
                    f"Add `runtime/` to `src/{pkg_name}/.gitignore` "
                    f"(package-local, preferred) or "
                    f"`src/{pkg_name}/runtime/` to the repo-root "
                    f".gitignore. The discipline is per-package — "
                    f"exceptions belong in the package's own .gitignore, "
                    f"not a global rule. See "
                    f"_skills/general/02_package/"
                    f"02_project-structure-src.md for context."
                ),
            )
        )
