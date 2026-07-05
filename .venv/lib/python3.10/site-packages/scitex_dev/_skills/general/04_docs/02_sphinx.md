---
description: |
  [TOPIC] Sphinx Organization
  [DETAILS] Canonical Sphinx documentation layout for every SciTeX package — `docs/source/` tree, required `conf.py` patterns (theme = sphinx_rtd_theme, autodoc, myst-parser, autodoc-typehints, copybutton), `.readthedocs.yaml` for RTD builds, version-switcher, RTD build-status checks, and common troubleshooting (empty autodoc, broken myst include, RTD failing on `import scitex`). Use when setting up RTD for a new package or fixing a failing Read the Docs build.
tags: [scitex-general-docs-sphinx]
---

# Sphinx & Read the Docs Organization (SciTeX)

## SciTeX-Specific conf.py Settings

```python
# Version auto-detection — use the package name
try:
    from importlib.metadata import version as _get_version
    release = _get_version("scitex-io")   # replace with actual package name
except Exception:
    release = "0.1.0"

# GitHub "Edit on GitHub" link — always ywatanabe1989
html_context = {
    "display_github": True,
    "github_user": "ywatanabe1989",
    "github_repo": "scitex-io",           # replace with actual repo name
    "github_version": "develop",
    "conf_py_path": "/docs/sphinx/",
}
```

## Five Interfaces Table (index.rst Rule)

SciTeX packages must include a five-interfaces table in `index.rst` (HTTP API is optional and included only when the package exposes web endpoints):

| Interface | Description |
|-----------|-------------|
| Python API | `import scitex_io` |
| CLI | `scitex-io <command>` |
| MCP | AI agent tools via fastmcp |
| Skills | AI agent knowledge pages |
| HTTP API (optional) | FastAPI endpoints for web clients |

## RTD Reference Implementations

- `~/proj/figrecipe` — working RTD setup
- `~/proj/scitex-writer` — working RTD setup

## SciTeX-Specific Rules

- **Five interfaces table** in index.rst: Python API, CLI, MCP, Skills, plus HTTP API when applicable
- **Use `develop` branch** as github_version for "Edit on GitHub" links
- **Exclude `to_claude/`** from Sphinx builds
- `api/scitex_io.rst` — follow scitex-io naming pattern for API doc files

## Bundling pre-built HTML in the wheel (production serving)

`scitex_dev.docs.get_docs(package=..., format="html")` resolves to a pre-built HTML directory; `scitex-cloud/apps/workspace/docs_app/` consumes that to serve per-package docs at <https://scitex.ai/apps/docs/>. For a package's docs to appear there after `pip install <pkg>`, the HTML must ship in the wheel.

Convention:

```
docs/sphinx/_build/html/        # local Sphinx output; gitignored
src/<pkg>/_sphinx_html/         # bundled in the wheel; refreshed at release
```

**Canonical refresh path: GitHub Actions** (`.github/workflows/docs.yml`).
The workflow:
1. Builds Sphinx HTML on every push/PR.
2. Every build uses `sphinx-build -W --keep-going` (warnings-as-errors
   on BOTH PRs and `main`/`develop` pushes → a warning can never land).
3. `main`/`develop` pushes additionally copy the output to
   `src/<pkg>/_sphinx_html/` and auto-commit when it changes (the
   commit-message guard, not a skip-ci token, prevents rebuild loops).

Reference workflow: `scitex-ssh/.github/workflows/docs.yml`.

**Keeping `-W` strict without whack-a-moling docstrings:** `sphinx-build
-W` is correct but bites on benign failure modes (autodoc docstring reST
noise, `_sphinx_html` commit-back GH006, missing-peer autodoc imports,
math renderer). The canonical `conf.py` + workflow defenses for each —
`suppress_warnings = ["docutils"]`, `continue-on-error` commit-back,
`autodoc_mock_imports`, `sphinx.ext.mathjax` — live in
[`04_docs/04_robust-ci.md`](04_robust-ci.md). Reference
implementation: `scitex-seizure-metrics` (PR #6).

Manual fallback (if CI is unavailable):

```bash
sphinx-build -b html docs/sphinx docs/sphinx/_build/html
rm -rf src/<pkg>/_sphinx_html
cp -rf docs/sphinx/_build/html src/<pkg>/_sphinx_html
```

`pyproject.toml` must include the directory in the wheel. Hatchling
needs `force-include` (a plain include glob is dropped because
`_sphinx_html/` lives under `src/<pkg>/` which is already a package
dir):

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/<pkg>"]

[tool.hatch.build.targets.wheel.force-include]
"src/<pkg>/_sphinx_html" = "<pkg>/_sphinx_html"
```

If a package has no Sphinx tree, omit `_sphinx_html/`; `get_docs(format="html")` returns `None` and the docs site skips that package gracefully. See [`02_package/01_project-structure.md`](../02_package/01_project-structure-root.md) for the broader project-structure context.

## CLI reference must be auto-generated via `sphinx-click`

Packages that ship a click-based CLI MUST render the CLI reference from
the live click group via [sphinx-click](https://sphinx-click.readthedocs.io/).
Hand-written `cli_reference.rst` files that re-list commands / flags /
examples in prose are **forbidden** — they cannot be kept in sync with
the click tree programmatically and reliably drift on every CLI
restructure (the 2026-05-06 scitex-dataset case: `cli_reference.rst`,
`quickstart.rst`, and `sources.rst` documented the pre-3-level grammar
months after migration; sphinx-build happily rendered the lie).

Required `docs/sphinx/cli_reference.rst` shape:

```rst
CLI Reference
=============

.. click:: scitex_<pkg>._cli:main
   :prog: scitex-<pkg>
   :nested: full
```

Top-level prose (grammar overview, config precedence, env vars) MAY
live above the directive but MUST NOT re-document subcommand trees
that the directive will render.

Wiring:

1. Add `sphinx-click` to `docs/sphinx/requirements.txt` (or
   `[project.optional-dependencies.docs]`).
2. Add `"sphinx_click"` to `extensions` in `docs/sphinx/conf.py`.
3. Replace any hand-written subcommand tree in `cli_reference.rst`
   with the `.. click::` directive above.
4. Verify `make -C docs/sphinx html` produces a tree consistent with
   `<cli> --help-recursive`.

## Sphinx is required for packages that ship a CLI or MCP server

Sphinx remains optional for pure-utility packages (no CLI, no MCP, no
public Python API surface worth documenting). But the moment a package
ships a click CLI or an MCP server, `docs/sphinx/conf.py` MUST exist —
otherwise users have no rendered CLI reference and nothing to link to
from <https://scitex.ai>. The `audit-project` PS-128 row below enforces
this.

## Audit rules (project-structure auditor)

When `docs/sphinx/conf.py` exists, `scitex-dev ecosystem audit-project`
enforces the canonical setup:

| Code  | Enforces                                                                          |
|-------|-----------------------------------------------------------------------------------|
| PS-121 | `src/<pkg>/_sphinx_html/index.html` is bundled (scitex-cloud serves from it)      |
| PS-122 | `.github/workflows/docs.yml` exists (auto-refreshes the bundle on push)           |
| PS-124 | `.readthedocs.yaml` (or `.yml`) exists at repo root                               |
| PS-125 | `.readthedocs.yaml` matches the canonical shape (version 2, ubuntu-22.04, py3.11) |
| PS-126 | `docs/sphinx/requirements.txt` pins the canonical doc deps                        |
| PS-127 | `pyproject.toml [project.urls]` has `Documentation = "https://<pkg>.readthedocs.io"` |
| PS-128 | If the package ships a click CLI (`scitex_<pkg>._cli:main` resolves), `docs/sphinx/conf.py` MUST exist, list `sphinx_click` in `extensions`, and contain a `.. click::` directive in `cli_reference.rst` (or any RST under `docs/sphinx/`). Hand-written prose subcommand trees under a `Commands` heading without a sibling `.. click::` directive are flagged. |

## GitHub language stats — mark `_sphinx_html/` as generated

Once `_sphinx_html/` is committed, GitHub's Linguist will misclassify
the repo as "HTML" because the bundle outweighs the Python source.
Add a `.gitattributes` line to exclude it:

```
# Sphinx-generated docs bundle — exclude from GitHub language stats.
src/*/_sphinx_html/** linguist-generated
```

`linguist-generated` is the honest tag (the directory is generated from
`docs/sphinx/*.rst` by sphinx-build); `linguist-vendored` would also
work but signals "third-party code", which it isn't.

## CRITICAL: do NOT gitignore `src/<pkg>/_sphinx_html/`

The legacy `.gitignore` template often included `src/*/_sphinx_html/`
to keep build artefacts out of source control. **That is wrong for the
current convention.** scitex-cloud serves docs from the in-wheel bundle,
which means the bundle MUST be committed. Symptom: CI fails with
`FileNotFoundError: Forced include not found:
.../src/<pkg>/_sphinx_html` because hatchling's `force-include` references
a path the checkout doesn't have. Fix: remove that line from `.gitignore`.

## Read the Docs project provisioning

Use the v3 API (token at `~/.dotfiles/src/.bash.d/secrets/access_tokens/read_the_docs.txt`,
also exported as `$RTD_TOKEN`) to register a new project:

```bash
curl -X POST -H "Authorization: Token $RTD_TOKEN" \
  -H "Content-Type: application/json" \
  https://readthedocs.org/api/v3/projects/ \
  -d '{
    "name": "<pkg>",
    "repository": {"url": "https://github.com/ywatanabe1989/<pkg>", "type": "git"},
    "homepage": "https://github.com/ywatanabe1989/<pkg>",
    "programming_language": "py",
    "language": "en",
    "default_branch": "main"
  }'
```

Then trigger the first build:

```bash
curl -X POST -H "Authorization: Token $RTD_TOKEN" \
  https://readthedocs.org/api/v3/projects/<pkg>/versions/latest/builds/
```

Packages without `docs/sphinx/conf.py` skip all six rules — utility
packages without docs are fine (just invisible in the docs site).
