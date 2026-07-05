"""PS-121 / PS-122 / PS-124-PS-127 — Sphinx + Read the Docs setup.

scitex-cloud serves per-package docs from the in-wheel
``src/<pkg>/_sphinx_html/`` bundle. The canonical refresh path is a
GitHub Actions workflow that rebuilds and auto-commits the bundle on
every push to main/develop. RTD also builds the same source tree so
the live site stays in sync.

PS-122 historically required ``.github/workflows/docs.yml`` by name.
After the ecosystem-wide workflow-naming rename (PS-164), the
canonical filename is now descriptive (e.g.
``rtd-sphinx-build-on-ubuntu-latest.yml``). PS-122 therefore detects
the RTD/Sphinx workflow by *content* — any workflow that runs
``sphinx-build``, ``make html``, or references RTD satisfies the rule.

All checks fire only when the package has a Sphinx source tree
(``docs/sphinx/conf.py``). Packages without docs skip these rules.
"""

from __future__ import annotations

import re
from pathlib import Path

# Canonical pinned deps from `_skills/general/04_docs/02_sphinx.md`.
_CANONICAL_DOCS_DEPS = [
    re.compile(r"^\s*sphinx\s*>=\s*7", re.MULTILINE),
    re.compile(r"^\s*sphinx-rtd-theme\s*>=\s*2", re.MULTILINE),
    re.compile(r"^\s*myst-parser\s*>=\s*2", re.MULTILINE),
    re.compile(r"^\s*sphinx-copybutton\s*>=\s*0\.5", re.MULTILINE),
    re.compile(r"^\s*sphinx-autodoc-typehints\s*>=\s*1", re.MULTILINE),
]


def _has_sphinx_source(repo: Path) -> bool:
    return (repo / "docs" / "sphinx" / "conf.py").is_file()


# PS-122 content-based detection: any workflow that builds Sphinx docs
# satisfies the rule, regardless of filename.
_RTD_WORKFLOW_PATTERNS = (
    re.compile(r"\bsphinx-build\b"),
    re.compile(r"\bmake\s+html\b"),
    re.compile(r"readthedocs", re.IGNORECASE),
)


def _has_rtd_workflow(repo: Path) -> bool:
    """Return True iff at least one ``.github/workflows/*.y(a)ml`` file
    contains a sphinx-build / make html / RTD reference."""
    workflows_dir = repo / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return False
    for wf in workflows_dir.iterdir():
        if wf.suffix not in (".yml", ".yaml") or not wf.is_file():
            continue
        try:
            text = wf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(pat.search(text) for pat in _RTD_WORKFLOW_PATTERNS):
            return True
    return False


def _src_pkg_with_html(repo: Path) -> Path | None:
    """Return the first ``src/<pkg>/`` dir whose ``_sphinx_html/index.html``
    exists, else None."""
    src = repo / "src"
    if not src.is_dir():
        return None
    for child in src.iterdir():
        if not child.is_dir():
            continue
        if (child / "_sphinx_html" / "index.html").is_file():
            return child / "_sphinx_html"
    return None


def check_sphinx_html(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS-121 / PS-122 violations.

    PS-121 — sphinx source exists but ``_sphinx_html/index.html`` is missing.
    PS-122 — sphinx source exists but no ``.github/workflows/*.yml``
             runs sphinx-build / make html (detected by content, not
             filename — see PS-164 for the rename context).
    """
    if not _has_sphinx_source(repo):
        return

    if _src_pkg_with_html(repo) is None:
        out.append(
            violation_cls(
                "PS-121",
                str(repo / "src"),
                (
                    "package has docs/sphinx/conf.py but no "
                    "src/<pkg>/_sphinx_html/index.html bundled. scitex-cloud "
                    "serves docs from the in-wheel _sphinx_html/ — without "
                    "it the package is invisible at "
                    "https://scitex.ai/apps/docs/. Refresh via the canonical "
                    "RTD/Sphinx CI workflow or manually."
                ),
            )
        )

    if not _has_rtd_workflow(repo):
        out.append(
            violation_cls(
                "PS-122",
                str(repo / ".github" / "workflows"),
                (
                    "package has docs/sphinx/ but no .github/workflows/*.yml "
                    "runs sphinx-build / make html. Auto-refreshing "
                    "_sphinx_html/ in CI is the canonical pattern (see "
                    "scitex-ssh as reference). Manual refresh drifts; CI "
                    "keeps the bundle fresh on every push to main/develop. "
                    "PS-122 detects the workflow by content, not filename — "
                    "any workflow running sphinx-build satisfies the rule."
                ),
            )
        )

    # PS-124 — `.readthedocs.yaml` (or .yml) must exist.
    rtd_yaml = repo / ".readthedocs.yaml"
    rtd_yml = repo / ".readthedocs.yml"
    rtd_path = (
        rtd_yaml if rtd_yaml.is_file() else (rtd_yml if rtd_yml.is_file() else None)
    )
    if rtd_path is None:
        out.append(
            violation_cls(
                "PS-124",
                str(rtd_yaml),
                (
                    "package has docs/sphinx/ but no .readthedocs.yaml at "
                    "the repo root. RTD won't build without it. See "
                    "_skills/general/04_docs/02_sphinx.md for the canonical "
                    "config."
                ),
            )
        )
    else:
        # PS-125 — `.readthedocs.yaml` shape check.
        try:
            rtd_text = rtd_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            rtd_text = ""
        canonical_bits = [
            (re.compile(r"^version:\s*2\b", re.MULTILINE), "version: 2"),
            (
                re.compile(r"os:\s*ubuntu-22\.04", re.MULTILINE),
                "build.os: ubuntu-22.04",
            ),
            (
                re.compile(r"python:\s*[\"']?3\.11[\"']?", re.MULTILINE),
                "build.tools.python: '3.11'",
            ),
            (
                re.compile(r"configuration:\s*docs/sphinx/conf\.py", re.MULTILINE),
                "sphinx.configuration: docs/sphinx/conf.py",
            ),
        ]
        missing = [label for pat, label in canonical_bits if not pat.search(rtd_text)]
        if missing:
            out.append(
                violation_cls(
                    "PS-125",
                    str(rtd_path),
                    (
                        ".readthedocs config deviates from the canonical "
                        "SciTeX shape — missing: "
                        + ", ".join(missing)
                        + ". See _skills/general/04_docs/02_sphinx.md."
                    ),
                )
            )

    # PS-126 — `docs/sphinx/requirements.txt` with canonical pinned deps.
    docs_req = repo / "docs" / "sphinx" / "requirements.txt"
    if not docs_req.is_file():
        out.append(
            violation_cls(
                "PS-126",
                str(docs_req),
                (
                    "package has docs/sphinx/ but no requirements.txt. "
                    "Pinning the canonical doc deps (sphinx>=7.0, "
                    "sphinx-rtd-theme>=2.0, myst-parser>=2.0, "
                    "sphinx-copybutton>=0.5, sphinx-autodoc-typehints>=1.25) "
                    "keeps RTD builds reproducible across the ecosystem."
                ),
            )
        )
    else:
        try:
            req_text = docs_req.read_text(encoding="utf-8", errors="replace")
        except OSError:
            req_text = ""
        if not all(pat.search(req_text) for pat in _CANONICAL_DOCS_DEPS):
            out.append(
                violation_cls(
                    "PS-126",
                    str(docs_req),
                    (
                        "docs/sphinx/requirements.txt is missing one or more "
                        "canonical pinned deps. Required floor: sphinx>=7.0, "
                        "sphinx-rtd-theme>=2.0, myst-parser>=2.0, "
                        "sphinx-copybutton>=0.5, sphinx-autodoc-typehints>=1.25."
                    ),
                )
            )

    # PS-128 — `.gitignore` must NOT exclude `src/<pkg>/_sphinx_html/` —
    # scitex-cloud serves from the bundled in-wheel HTML, which must be
    # tracked. Symptom: CI fails with hatchling 'Forced include not found'.
    gitignore = repo / ".gitignore"
    if gitignore.is_file():
        try:
            gi_text = gitignore.read_text(encoding="utf-8", errors="replace")
        except OSError:
            gi_text = ""
        if re.search(
            r"^\s*src/(?:\*|[\w-]+)/_sphinx_html/?\s*$",
            gi_text,
            re.MULTILINE,
        ):
            out.append(
                violation_cls(
                    "PS-128",
                    str(gitignore),
                    (
                        ".gitignore excludes src/<pkg>/_sphinx_html/ — but "
                        "scitex-cloud serves docs from the in-wheel bundle, "
                        "so it MUST be tracked. Remove the line; CI's "
                        "hatchling force-include will fail otherwise."
                    ),
                )
            )

    # PS-127 — pyproject.toml [project.urls] Documentation entry.
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        try:
            pp_text = pyproject.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pp_text = ""
        # Cheap regex: look for Documentation = "https://...readthedocs.io..."
        if not re.search(
            r"^\s*Documentation\s*=\s*[\"\']https?://[^\"\']*readthedocs\.io",
            pp_text,
            re.MULTILINE | re.IGNORECASE,
        ):
            out.append(
                violation_cls(
                    "PS-127",
                    str(pyproject),
                    (
                        "pyproject.toml [project.urls] has no Documentation "
                        "entry pointing at RTD (e.g. "
                        'Documentation = "https://<pkg>.readthedocs.io"). '
                        "PyPI surfaces this URL — missing it hides the docs "
                        "from new users."
                    ),
                )
            )
