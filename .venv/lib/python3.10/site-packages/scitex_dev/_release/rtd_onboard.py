#!/usr/bin/env python3
# Timestamp: 2026-04-28
# File: scitex_dev/_rtd_onboard.py

"""Scaffold a minimal Read the Docs setup for an ecosystem package.

Codified from the 24/24-green pattern used in scitex-events,
scitex-config, scitex-stats, etc. The output is a working `.readthedocs.yaml`
+ `docs/sphinx/{conf.py,index.rst,api.rst}` tree that builds on RTD with
sphinx-rtd-theme + autodoc + autosummary + napoleon + viewcode +
intersphinx + myst-parser + sphinx-copybutton + sphinx-autodoc-typehints.

Idempotent: skips files that already exist (so it won't trash a
hand-edited tree). Prints what would be written when invoked with
``dry_run=True``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# --- Templates -------------------------------------------------------------

READTHEDOCS_YAML = """version: 2

build:
  os: ubuntu-22.04
  tools:
    python: "3.11"

sphinx:
  configuration: docs/sphinx/conf.py
  fail_on_warning: false

python:
  install:
    - method: pip
      path: .
      extra_requirements:
        - docs
"""

CONF_PY = '''"""Sphinx configuration for {pkg}."""

import os
import sys

sys.path.insert(0, os.path.abspath("../../src"))

project = "{pkg}"
copyright = "2026, Yusuke Watanabe"
author = "Yusuke Watanabe"

try:
    from {imp} import __version__ as release
except ImportError:
    release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_rtd_theme",
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_autodoc_typehints",
]

autodoc_default_options = {{
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}}
autosummary_generate = True

intersphinx_mapping = {{
    "python": ("https://docs.python.org/3", None),
}}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = []
'''

INDEX_RST = """{pkg}
{underline}

{description}

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   api

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
"""

API_RST = """API Reference
=============

.. autosummary::
   :toctree: _autosummary
   :recursive:

   {imp}
"""


# --- Operation -------------------------------------------------------------


@dataclass
class OnboardResult:
    repo: Path
    package: str
    written: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"RTD onboard for {self.package} at {self.repo}"]
        for p in self.written:
            lines.append(f"  WROTE   {p.relative_to(self.repo)}")
        for p in self.skipped:
            lines.append(f"  SKIP    {p.relative_to(self.repo)} (exists)")
        for p, why in self.failed:
            lines.append(f"  FAIL    {p.relative_to(self.repo)}: {why}")
        return "\n".join(lines)


def _read_pyproject_name(pyproject: Path) -> str | None:
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


def _read_pyproject_description(pyproject: Path) -> str:
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r'^description\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else ""


def _has_docs_extra(pyproject: Path) -> bool:
    """Check whether ``[project.optional-dependencies] docs = [...]`` exists."""
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(r"^docs\s*=\s*\[", text, re.MULTILINE))


_DOCS_EXTRA_BLOCK = """
docs = [
    "sphinx>=7.0",
    "sphinx-rtd-theme>=2.0",
    "myst-parser>=2.0",
    "sphinx-copybutton>=0.5",
    "sphinx-autodoc-typehints>=1.25",
]"""


def _ensure_docs_extra(pyproject: Path, dry_run: bool = False) -> bool:
    """Add ``docs`` extra if the file has [project.optional-dependencies]."""
    if _has_docs_extra(pyproject):
        return False
    text = pyproject.read_text(encoding="utf-8")
    m = re.search(r"^\[project\.optional-dependencies\]\s*$", text, re.MULTILINE)
    if not m:
        return False
    insert_at = m.end()
    new_text = text[:insert_at] + _DOCS_EXTRA_BLOCK + text[insert_at:]
    if not dry_run:
        pyproject.write_text(new_text)
    return True


def onboard_rtd(repo: Path, dry_run: bool = False) -> OnboardResult:
    """Scaffold a minimal RTD setup. Idempotent.

    Skips files that already exist; only writes missing ones. Adds the
    ``docs`` extra to pyproject if a ``[project.optional-dependencies]``
    section exists and the extra is missing.
    """
    pyproject = repo / "pyproject.toml"
    pkg = _read_pyproject_name(pyproject) or repo.name
    imp = pkg.replace("-", "_")
    description = _read_pyproject_description(pyproject) or pkg

    rep = OnboardResult(repo=repo, package=pkg)

    targets: list[tuple[Path, str]] = [
        (repo / ".readthedocs.yaml", READTHEDOCS_YAML),
        (
            repo / "docs" / "sphinx" / "conf.py",
            CONF_PY.format(pkg=pkg, imp=imp),
        ),
        (
            repo / "docs" / "sphinx" / "index.rst",
            INDEX_RST.format(
                pkg=pkg,
                underline="=" * len(pkg),
                description=description,
            ),
        ),
        (
            repo / "docs" / "sphinx" / "api.rst",
            API_RST.format(imp=imp),
        ),
    ]

    for path, body in targets:
        try:
            if path.is_file():
                rep.skipped.append(path)
                continue
            if not dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body)
            rep.written.append(path)
        except OSError as exc:
            rep.failed.append((path, str(exc)))

    if pyproject.is_file():
        try:
            if _ensure_docs_extra(pyproject, dry_run=dry_run):
                rep.written.append(pyproject)
        except Exception as exc:
            rep.failed.append((pyproject, str(exc)))

    return rep


__all__ = ["OnboardResult", "onboard_rtd"]
