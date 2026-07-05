"""PS-165 — `.github/workflows/` presence rules (per package category).

Every SciTeX package must ship a baseline set of GitHub Actions
workflows so the ecosystem-wide audit dashboard, badges, and branch
protection have consistent rows to gate on. The required set is keyed
on the package's *category*, declared in `pyproject.toml`:

    [tool.scitex_dev]
    category = "library"      # default if omitted

Recognised categories:

  - ``library``        — standard scitex-* leaf with a public API.
                          No CLI smoke/e2e required.
  - ``cli-tool``       — package whose primary surface is a CLI.
                          Adds tests/smoke/ + tests/e2e/ expectations
                          (already covered by PS-211 / PS-212).
  - ``infrastructure`` — meta/tooling/glue package (scitex-dev itself,
                          scitex-agent-container's ops side). Same
                          baseline as ``library`` for now.

Spec: ``_skills/general/01_ecosystem/09_package-categories.md`` and
``_skills/general/02_package/07b_workflow-presence.md``.

Severity W during adoption — packages can self-register their category
and rename existing workflows gradually. Promote to E once the ecosystem
has converged.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# pyproject.toml: read [tool.scitex_dev] category
# ---------------------------------------------------------------------------

_TOOL_BLOCK_RE = re.compile(
    r"^\[tool\.scitex[_-]dev\](.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
_CATEGORY_RE = re.compile(
    r"""^\s*category\s*=\s*["']([A-Za-z0-9_\-]+)["']\s*$""",
    re.MULTILINE,
)

_VALID_CATEGORIES = frozenset({"library", "cli-tool", "infrastructure"})
_DEFAULT_CATEGORY = "library"


def read_package_category(repo: Path) -> str:
    """Return the package category declared in pyproject.toml.

    Falls back to ``"library"`` (the default) when the file or key is
    missing. Unknown categories also fall back to ``"library"`` so a
    typo doesn't silently disable presence checks.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return _DEFAULT_CATEGORY
    try:
        txt = pyproject.read_text(errors="ignore")
    except OSError:
        return _DEFAULT_CATEGORY
    m = _TOOL_BLOCK_RE.search(txt)
    if m is None:
        return _DEFAULT_CATEGORY
    cm = _CATEGORY_RE.search(m.group(1))
    if cm is None:
        return _DEFAULT_CATEGORY
    cat = cm.group(1)
    return cat if cat in _VALID_CATEGORIES else _DEFAULT_CATEGORY


# ---------------------------------------------------------------------------
# Required workflow patterns (filename stem regex → human description)
# ---------------------------------------------------------------------------

# Each requirement is a regex matched against the basename (lower-case).
# A workflow is considered "present" if at least one file matches.
#
# Patterns are deliberately permissive of the matrix/runtime suffix
# documented in PS-164 (e.g. `pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml`
# OR `pytest-on-ubuntu-latest.yml`).
_BASELINE_REQUIREMENTS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "cla",
        re.compile(r"^cla\.ya?ml$"),
        "CLA Assistant (`cla.yml`)",
    ),
    (
        "pytest",
        re.compile(r"^pytest-.*\.ya?ml$"),
        "pytest matrix (`pytest-*-on-*.yml`)",
    ),
    (
        "import-smoke",
        re.compile(r"^import-smoke-.*\.ya?ml$"),
        "import smoke (`import-smoke-*-on-*.yml`)",
    ),
    (
        "pypi-publish",
        re.compile(r"^pypi-publish-.*\.ya?ml$"),
        "PyPI publish on tag (`pypi-publish-*-on-tag.yml`)",
    ),
    (
        "quality-audit",
        re.compile(r"^scitex-dev-(quality-audit|audit-all)-.*\.ya?ml$"),
        "scitex-dev quality audit (`scitex-dev-quality-audit-on-*.yml`)",
    ),
    (
        "sync-main",
        re.compile(r"^sync-main-.*\.ya?ml$"),
        "sync main → release tag (`sync-main-to-release-tag-on-push.yml`)",
    ),
]

# Only required if the repo ships docs/ (i.e. has Sphinx)
_RTD_REQUIREMENT: tuple[str, re.Pattern[str], str] = (
    "rtd-sphinx",
    re.compile(r"^rtd-(sphinx-)?build-.*\.ya?ml$"),
    "RTD Sphinx build (`rtd-sphinx-build-on-*.yml`)",
)

# cli-tool-specific additions (smoke + e2e have their own pytest test
# layers under PS-211/PS-212; here we additionally require a runtime
# smoke workflow that exercises the installed CLI end-to-end).
_CLI_TOOL_EXTRAS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "sdk-runtime-smoke",
        re.compile(r"^(sdk-runtime|cli)-smoke-.*\.ya?ml$"),
        "runtime CLI smoke (`sdk-runtime-smoke-on-*.yml` or `cli-smoke-on-*.yml`)",
    ),
]


def _workflow_filenames(repo: Path) -> list[str]:
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    return [
        p.name.lower()
        for p in wf_dir.iterdir()
        if p.is_file() and p.suffix in {".yml", ".yaml"}
    ]


def _has_docs_dir(repo: Path) -> bool:
    """True if the repo ships a Sphinx-style docs/ tree."""
    docs = repo / "docs"
    if not docs.is_dir():
        return False
    # Heuristic: docs/ with conf.py OR docs/source/conf.py
    return (docs / "conf.py").is_file() or (docs / "source" / "conf.py").is_file()


def check_ps165_workflow_presence(
    repo: Path, violation_cls: type, out: list[Any]
) -> None:
    """PS-165 — required workflows are present (per package category).

    Reads ``[tool.scitex_dev] category`` from pyproject.toml; defaults to
    ``library``. Emits one Violation per missing required workflow.
    """
    category = read_package_category(repo)
    filenames = _workflow_filenames(repo)

    if not filenames:
        # No .github/workflows/ at all — surface a single violation rather
        # than spamming one-per-pattern; PS-101/PS-104-class checks should
        # already complain about a repo without CI.
        out.append(
            violation_cls(
                "PS-165",
                str(repo / ".github" / "workflows"),
                (
                    f"no GitHub Actions workflows found — every SciTeX package "
                    f"(category={category!r}) must ship the baseline workflow "
                    f"set. See _skills/general/02_package/07b_workflow-presence.md."
                ),
            )
        )
        return

    requirements = list(_BASELINE_REQUIREMENTS)
    if _has_docs_dir(repo):
        requirements.append(_RTD_REQUIREMENT)
    if category == "cli-tool":
        requirements.extend(_CLI_TOOL_EXTRAS)

    for _key, pattern, label in requirements:
        if not any(pattern.match(name) for name in filenames):
            out.append(
                violation_cls(
                    "PS-165",
                    str(repo / ".github" / "workflows"),
                    (
                        f"missing required workflow for category={category!r}: "
                        f"{label}. See "
                        f"_skills/general/02_package/07b_workflow-presence.md."
                    ),
                )
            )
