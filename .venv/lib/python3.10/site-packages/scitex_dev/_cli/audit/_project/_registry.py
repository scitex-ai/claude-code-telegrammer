"""Rule registry for the project-structure auditor.

Split out of `_audit.py` (issue #103) — pure refactor, no behaviour change.
Contains the `Rule` dataclass, the raw `RULES` definitions, the severity-
override + slug tables, and the merge with `_extra_rules.EXTRA_RULES`.

Re-exported from `_audit` for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    code: str
    section: str
    message: str
    # Severity drives the audit's exit code:
    #   E (error)   — at least one E finding fails the audit (exit 1)
    #   W (warning) — printed but does not fail (exit 0 if no E findings)
    #   I (info)    — printed only with --severity info; never fails
    # Default W keeps existing rules backward-compatible until each is
    # explicitly tagged. Promote to E when the rule is well-tested and the
    # ecosystem has already been brought into compliance.
    severity: str = "W"
    # Short kebab-case human-readable name (e.g. "examples-need-finished-success").
    # Surfaces in `audit-all` output as `[CODE §X slug] …` so reviewers can
    # read intent without cross-referencing rule numbers.
    slug: str = ""


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # §1 Top-level layout ---------------------------------------------------
        Rule(
            "PS-101",
            "§1",
            "missing pyproject.toml at repo root",
            slug="pyproject-missing",
        ),
        Rule(
            "PS-102",
            "§1",
            "forbidden top-level dir present (use the canonical location instead)",
            slug="top-level-forbidden-dir",
        ),
        Rule(
            "PS-103",
            "§1",
            "top-level junk file (move to ./.dev/<category>/ or delete)",
            slug="top-level-junk-file",
        ),
        Rule(
            "PS-104",
            "§1",
            "uses `.playground/` — collapsed into `.dev/` for easier typing",
        ),
        Rule(
            "PS-105",
            "§1",
            (
                "package registers console_scripts but has no `__main__.py` — "
                "`python -m <pkg>` will fail with 'No module named <pkg>.__main__'. "
                "Add `src/<pkg>/__main__.py` that imports and calls the CLI entry "
                "(usually `from . import _cli; _cli.main()`) so both `<pkg>` and "
                "`python -m <pkg>` work."
            ),
        ),
        Rule(
            "PS-106",
            "§1",
            (
                "README.md is missing a coverage badge — every scitex-* "
                "package should surface its current test coverage at the "
                "top of the README so reviewers and downstream consumers "
                "can see at a glance whether the package is well-tested. "
                "Add a `[![coverage](https://img.shields.io/...)](url)` "
                "or `![codecov](https://codecov.io/...)` line near the "
                "title. The badge must be in README.md (not a sub-doc)."
            ),
        ),
        Rule(
            "PS-107",
            "§1",
            (
                "README.md is missing required H2 sections "
                "(## Installation / ## Quick Start / ## Part of SciTeX) — "
                "see _skills/general/04_docs/01_readme_template.md for the "
                "canonical layout."
            ),
        ),
        Rule(
            "PS-109",
            "§1",
            (
                "README.md is missing a PyPI version badge "
                "(badge.fury.io/py/<pkg> or img.shields.io/pypi/v/<pkg>) "
                "in the first ~4 KB."
            ),
        ),
        Rule(
            "PS-110",
            "§1",
            (
                "README.md is missing the Four Freedoms for Research "
                "blockquote — the SciTeX community-license footer."
            ),
        ),
        Rule(
            "PS-111",
            "§1",
            (
                "README.md contains a banned personal email "
                "(ywatanabe@scitex.ai) — SciTeX is a community project."
            ),
        ),
        Rule(
            "PS-112",
            "§1",
            (
                "README.md is missing a SciTeX logo image at the top "
                "(docs/scitex-logo-*.png or docs/assets/images/scitex-logo-*.png)."
            ),
        ),
        Rule(
            "PS-113",
            "§1",
            (
                "README.md is missing a SciTeX icon footer — centered "
                "scitex-icon image link in the last ~2 KB of the file."
            ),
        ),
        Rule(
            "PS-114",
            "§1",
            (
                "README.md `## Problem and Solution` section is prose-only — "
                "convention is a markdown table with columns "
                "`| # | Problem | Solution |`."
            ),
        ),
        Rule(
            "PS-115",
            "§1",
            (
                "README.md `## Part of SciTeX` section does not open with "
                "the canonical `<pkg> is part of [SciTeX](https://scitex.ai)` "
                "sentence. Synergy code is optional; the opener is required."
            ),
        ),
        Rule(
            "PS-108",
            "§1",
            (
                "flat package layout: ≥3 sibling `.py` files at `src/<pkg>/` "
                "share a common prefix (e.g. `_cli_*.py`, `_skills_*.py`) — "
                "promote them to a `<prefix>/` subpackage for navigability. "
                "A common prefix on 3+ flat files is a reliable signal that "
                "the cluster wants to be a directory."
            ),
        ),
        Rule(
            "PS-108b",
            "§1",
            (
                "topical clutter: >15 flat `.py` files at `src/<pkg>/` root "
                "(or any subpackage) without shared prefix. PS-108 only "
                "catches prefix clusters; this catches the second mess "
                "pattern — many flat files sharing a topic but no prefix. "
                "Group into `_release/`, `_docs/`, `_core/`, `_quality/` "
                "subpackages by topical responsibility (single-file "
                "orphans stay flat). See "
                "general/02_package/02_project-structure-src.md."
            ),
        ),
        Rule(
            "PS-116",
            "§1",
            (
                "README.md uses the deprecated `> **Interfaces:** ...` "
                "summary callout. Per 2026-05 convention, put star ratings "
                "directly on each interface section header instead "
                "(e.g. `## Python API ⭐⭐⭐`)."
            ),
        ),
        Rule(
            "PS-117",
            "§1",
            (
                'README.md has a duplicate badge block: a `<p align="center">` '
                "row of img.shields.io / badge.fury.io / readthedocs badges "
                "appears in addition to the canonical "
                "`<!-- scitex-badges:start --> ... :end -->` block. Keep "
                "only the canonical block."
            ),
        ),
        Rule(
            "PS-118",
            "§1",
            (
                "README.md interface section header carries a banned "
                "descriptor like `(Application Programming Interface)`, "
                "`-- for AI Agents`, or `— for AI Agent Discovery`. The "
                "section names themselves carry meaning — strip the prose."
            ),
        ),
        Rule(
            "PS-119",
            "§1",
            (
                "README.md contains a `> **SciTeX users**: pip install scitex "
                "already includes ...` install hint. These belong in the "
                "umbrella `scitex` README, not in sub-package READMEs "
                "(extras like `pip install scitex[ssh]` drift)."
            ),
        ),
        # PS-120 retired 2026-05-18 — the umbrella one-liner content
        # check (pip install scitex[…] + scitex.<module> + scitex <subcmd>
        # tokens) was too strict and clashed with the `uv pip install`
        # recommendation. PS-116 already guards `## Part of SciTeX`
        # section presence; that's sufficient for the surface contract.
        Rule(
            "PS-121",
            "§1",
            (
                "package has `docs/sphinx/conf.py` but no "
                "`src/<pkg>/_sphinx_html/index.html` bundled. scitex-cloud "
                "serves docs from the in-wheel `_sphinx_html/` — without it "
                "the package is invisible at https://scitex.ai/apps/docs/. "
                "Refresh via the canonical CI workflow "
                "(`.github/workflows/docs.yml`)."
            ),
        ),
        Rule(
            "PS-122",
            "§1",
            (
                "package has `docs/sphinx/` but no "
                "`.github/workflows/docs.yml` CI workflow. Auto-refreshing "
                "`_sphinx_html/` in CI is the canonical pattern (see "
                "scitex-ssh as reference). Manual refresh drifts; CI keeps "
                "the bundle fresh on every push to main/develop."
            ),
        ),
        Rule(
            "PS-123",
            "§1",
            (
                "README.md interface section has a `Full X reference` link "
                "pointing at the bare RTD root (e.g. "
                "`https://<pkg>.readthedocs.io/`) instead of a deep-link "
                "anchor page. Use the canonical deep-link per interface — "
                "see `_skills/general/04_docs/01_readme.md` 'Canonical Full "
                "X reference deep-link patterns'."
            ),
        ),
        Rule(
            "PS-124",
            "§1",
            (
                "package has `docs/sphinx/` but no `.readthedocs.yaml` (or "
                "`.readthedocs.yml`) at the repo root. Without it, RTD won't "
                "build the docs. Use the canonical config — see "
                "`_skills/general/04_docs/02_sphinx.md`."
            ),
        ),
        Rule(
            "PS-125",
            "§1",
            (
                "`.readthedocs.yaml` deviates from the canonical SciTeX "
                "shape (version: 2, build.os: ubuntu-22.04, "
                "build.tools.python: '3.11', sphinx.configuration: "
                "docs/sphinx/conf.py). Drift breaks the cross-package "
                "uniformity scitex-cloud relies on."
            ),
        ),
        Rule(
            "PS-126",
            "§1",
            (
                "`docs/sphinx/requirements.txt` is missing or doesn't pin "
                "the canonical SciTeX docs deps (sphinx>=7.0, "
                "sphinx-rtd-theme>=2.0, myst-parser>=2.0, "
                "sphinx-copybutton>=0.5, sphinx-autodoc-typehints>=1.25). "
                "Pinned versions keep RTD builds reproducible across the "
                "ecosystem."
            ),
        ),
        Rule(
            "PS-127",
            "§1",
            (
                "`pyproject.toml [project.urls]` has no "
                '`Documentation = "https://<pkg>.readthedocs.io"` entry '
                "(or it points elsewhere). PyPI surfaces this URL on the "
                "project page; missing it makes the docs invisible to new "
                "users."
            ),
        ),
        Rule(
            "PS-128",
            "§1",
            (
                "`.gitignore` excludes `src/<pkg>/_sphinx_html/` but the "
                "convention requires committing the bundle. scitex-cloud "
                "serves from the in-wheel HTML; CI's hatchling "
                "force-include will fail with `FileNotFoundError: Forced "
                "include not found`. Remove the line."
            ),
        ),
        Rule(
            "PS-129",
            "§1",
            (
                "package source references `SCITEX_<MODULE>_*` env vars "
                "but documents them in NEITHER a README "
                "`## Environment Variables` section NOR a `.env.example` "
                "at repo root. Pick one — see "
                "`_skills/general/04_docs/03_env-vars-and-state.md`."
            ),
        ),
        Rule(
            "PS-130",
            "§1",
            (
                "README has `## Environment Variables` AND `.env.example` "
                "exists at repo root — the two will drift. Pick one: keep "
                "the README table (small lists), OR keep `.env.example` "
                "and reference it from the `## Installation` section."
            ),
        ),
        Rule(
            "PS-131",
            "§1",
            (
                "README.md `## <N> Interfaces` section must have at least "
                "one `<details open>` block — the primary interface, or "
                "all top-rated interfaces when several tie at the highest "
                "star count. The primary's minimal example doubles as "
                "the quick-start (no separate `## Quick Start` H2)."
            ),
        ),
        Rule(
            "PS-132",
            "§1",
            (
                "README.md has a standalone `## Modules` H2 (a hand-curated "
                "table of Python modules + functions). This duplicates the "
                "Python API `<details>` block AND the autoapi page on RTD, "
                "and drifts as the package evolves. Drop the section — "
                "the Python API block + Full API reference deep-link "
                "cover this."
            ),
        ),
        Rule(
            "PS-133",
            "§1",
            (
                "missing CLA.md at repo root — every public scitex-* package "
                "needs a Contributor License Agreement so external PRs can be "
                "merged without legal ambiguity. Use the canonical CLA.md "
                "from any current sibling package as the template."
            ),
        ),
        Rule(
            "PS-134",
            "§1",
            (
                "missing CHANGELOG.md at repo root — every shipping package "
                "needs a Keep-a-Changelog-style file so consumers can see "
                "what changed across versions. New packages start with an "
                "[Unreleased] section."
            ),
        ),
        Rule(
            "PS-135",
            "§1",
            (
                "missing CONTRIBUTING.md at repo root — every public package "
                "needs contributor guidance (branch naming, test workflow, "
                "PR conventions). Use the canonical CONTRIBUTING.md from "
                "any current sibling package as the template."
            ),
        ),
        Rule(
            "PS-136",
            "§1",
            (
                "missing or empty examples/ directory at repo root — every "
                "scitex-* package must show working code: at least one "
                "runnable `examples/<NN_>name.py` (or `.ipynb`) demonstrating "
                "the primary use case. Without examples, agents and humans "
                "have to grep tests/ to learn the API. See `_skills/general/"
                "02_package/01_project-structure-root.md`."
            ),
        ),
        Rule(
            "PS-137",
            "§1",
            (
                "missing README.md at repo root — every package's first-touch "
                "documentation surface. Use the canonical template at "
                "`_skills/general/04_docs/01_readme_template.md`."
            ),
        ),
        Rule(
            "PS-138",
            "§1",
            (
                "missing LICENSE at repo root — every public scitex-* "
                "package must declare its license. Accepted: `LICENSE`, "
                "`LICENSE.md`, or `LICENSE.txt`. The umbrella ships AGPL-3.0 "
                "with the Four-Freedoms-for-Research footer."
            ),
        ),
        Rule(
            "PS-138b",
            "§1",
            (
                "LICENSE file exists but content does not match SPDX "
                "declaration `AGPL-3.0-only` — likely a copyright stub "
                "instead of the full AGPL-3.0 text. The on-disk license "
                "must contain the full GNU AGPL v3 license, not just a "
                "title + copyright line. See "
                "`_skills/general/01_ecosystem/07_license-and-cla.md`."
            ),
        ),
        Rule(
            "PS-139",
            "§1",
            (
                "pyproject.toml lists `scitex` (the umbrella) as a dependency "
                "or extras member. This creates a circular drag: the umbrella "
                "depends on standalones, so a standalone depending on the "
                "umbrella means installing one pulls the entire ecosystem and "
                "every `import scitex_<pkg>` traverses the umbrella's lazy "
                "re-export __init__. Replace with the specific peer "
                "standalone(s) (e.g. `scitex-session>=0.1.0`). See "
                "`_skills/general/03_interface/01_python-api/"
                "11_import-conventions.md`."
            ),
        ),
        Rule(
            "PS-141",
            "§1",
            (
                "README.md is missing a mandatory `## Demo` section "
                "containing at least one visual element. Accepted (inside "
                "the section body): Markdown image `![alt](path.png)`, "
                'HTML `<img src="…">` pointing at a non-shields.io URL, '
                "or a fenced ```mermaid block. Demos drive discovery; "
                "every package must show what it does, not just describe "
                "it."
            ),
        ),
        Rule(
            "PS-142",
            "§1",
            (
                "README.md is missing a mandatory `## Architecture` "
                "section. Accepted body forms: a fenced ```mermaid block, "
                "an ASCII text diagram (fenced code block ≥10 lines), a "
                "file-tree listing (lines containing `├──`/`└──`/`│`), or "
                "an `<img>` tag. Even small packages should sketch their "
                "module layout so readers see structure at a glance."
            ),
        ),
        Rule(
            "PS-143",
            "§1",
            (
                "README.md sections do not appear in canonical order. The "
                "expected order (skipping any section the package omits) "
                "is: `Problem and Solution` → `Installation` → "
                "`Architecture` → `<N> Interfaces` → `Demo` → "
                "`Quick Start` (optional) → `Part of SciTeX`. Re-order "
                "the H2 headers; drift accumulates fast across packages "
                "if order is left to taste."
            ),
        ),
        Rule(
            "PS-144",
            "§1",
            (
                "README.md `## Problem and Solution` table cells violate "
                "bold-emphasis rules. A cell must (a) contain at least "
                "one `**bold**` span, (b) bold ≤ 30 % of the cell's text "
                "(bolding entire sentences defeats emphasis), and (c) be "
                "≤ 200 characters per cell (long prose belongs in section "
                "body, not a row). Bold the key noun phrase only."
            ),
        ),
        Rule(
            "PS-152",
            "§1",
            (
                "README.md has separate `## Problem` and/or `## Solution` "
                "H2 sections instead of a single merged "
                "`## Problem and Solution` table (one row per pain "
                "point). See scitex-io README for the canonical form."
            ),
            slug="readme-split-problem-solution",
        ),
        Rule(
            "PS-153",
            "§1",
            (
                "README.md `## Architecture` (or `## How it works`) "
                "section contains a file tree (`├──`/`└──`/`│`) but "
                "no ```mermaid fence. The directory tree is duplicate "
                "information already in `_sphinx_html/` and `autoapi`. "
                "Replace it with a `mermaid flowchart` showing the "
                "logic/workflow — see scitex-io README §1."
            ),
            slug="readme-architecture-filetree-not-mermaid",
        ),
        Rule(
            "PS-154",
            "§1",
            (
                "README.md `## Installation` section must start with one "
                '`uv pip install "<pkg>[all]"` fenced bash line; any '
                "per-module extras matrix table must live inside a "
                "`<details>` block. See scitex-io README §Installation."
            ),
            slug="readme-installation-not-canonical",
        ),
        Rule(
            "PS-155",
            "§1",
            (
                "README.md badge row between `<!-- scitex-badges:start "
                "-->` and `<!-- scitex-badges:end -->` should split "
                'into exactly two `<p align="center">` rows — row 1: '
                "PyPI / Python / Read the Docs; row 2: Tests / Install "
                "Test / Coverage. See scitex-io README header for the "
                "canonical form."
            ),
            slug="readme-badge-row-not-two-rows",
        ),
        Rule(
            "PS-156",
            "§1",
            (
                "examples/ directory contains only `.py` scripts and no "
                "`.ipynb` notebooks — prefer Jupyter notebooks for "
                "examples so users can read prose + code + output side "
                "by side and execute in-place. Reference: "
                "https://github.com/ywatanabe1989/scitex-seizure-metrics/"
                "tree/develop/examples (every example is .ipynb). Some "
                "packages (e.g. scitex-io) document a script-style "
                "examples set in their README and may keep .py files; "
                "mix .py and .ipynb freely — the rule only fires when "
                "examples/ has .py files and ZERO .ipynb files."
            ),
            slug="examples-no-ipynb",
        ),
        Rule(
            "PS-157",
            "§1",
            (
                "README.md codecov badge URL is unbranched "
                "(`codecov.io/<owner>/<pkg>/graph/badge.svg`) — pin a "
                "branch so the badge doesn't render 'unknown' when "
                "uploads only land on develop. Use "
                "`codecov.io/<owner>/<pkg>/branch/develop/graph/"
                "badge.svg`. See scitex-io README header for the "
                "canonical form."
            ),
            slug="readme-codecov-badge-unbranched",
        ),
        Rule(
            "PS-158",
            "§1",
            (
                "README.md Read-the-Docs badge uses readthedocs.org's "
                "own /badge endpoint which bakes the literal label "
                "'docs' into the SVG. Switch to the shields.io proxy "
                "so the visible label matches the project: "
                "`img.shields.io/readthedocs/<pkg>?label=Read%20the%20"
                "Docs`. See scitex-io README header."
            ),
            slug="readme-rtd-badge-baked-label",
        ),
        Rule(
            "PS-159",
            "§1",
            (
                "README.md figure / table caption numbering is broken — "
                "`<b>Figure N.</b>` and `<b>Table N.</b>` captions must "
                "form [1, 2, 3, ...] with no gaps, no duplicates, "
                "starting at 1. See scitex-stats README for the "
                "canonical caption form: "
                '`<p align="center"><sub><b>Figure N.</b> caption '
                "...</sub></p>`."
            ),
            slug="readme-figures-tables-numbering",
        ),
        Rule(
            "PS-160",
            "§1",
            (
                "README.md has a figure or table without a caption — "
                "every `<img>` data figure (excluding badges, the "
                "centered logo, and the icon footer) and every "
                "```mermaid``` fenced block must have a "
                "`<sub><b>Figure N.</b> ...</sub>` caption; every "
                "pipe-table (except the Problem and Solution table and "
                "tables inside `<details>`) must have a "
                "`<sub><b>Table N.</b> ...</sub>` caption. See "
                "scitex-stats README for the canonical caption form."
            ),
            slug="readme-figures-tables-missing-caption",
        ),
        Rule(
            "PS-161",
            "§1",
            (
                "codecov.yml project/patch coverage target is below 90% "
                "(or set to `auto`/`auto-target`) — pin a fixed `target: "
                "90%` so the coverage bar is visible. See scitex-io "
                "codecov.yml for the canonical config."
            ),
            slug="readme-codecov-coverage-target-too-low",
        ),
        Rule(
            "PS-162",
            "§1",
            (
                "README.md badge block (`<!-- scitex-badges:start -->...`) "
                "is missing a Codecov coverage badge — every public "
                "scitex package should expose CI coverage. See scitex-io "
                "README header for the canonical form."
            ),
            slug="readme-missing-codecov-badge",
        ),
        Rule(
            "PS-163",
            "§1",
            (
                "README.md badge block (`<!-- scitex-badges:start -->...`) "
                "is missing a Read-the-Docs badge — every scitex package "
                "shipping RTD docs should expose the build status. See "
                "scitex-io README header for the canonical form."
            ),
            slug="readme-missing-rtd-badge",
        ),
        Rule(
            "PS-140",
            "§2",
            (
                "package source has cross-package imports (`scitex_<X>` "
                "peer or `scitex.<X>` umbrella) but no "
                "`tests/integration/test_cross_package_imports.py` runtime "
                "gate, OR the gate's `CROSS_PACKAGE_IMPORTS` list is "
                "stale (missing some imports / contains removed ones). "
                "Without this gate, renames in peer standalones surface "
                "as silent ModuleNotFoundError at user runtime — the "
                "scitex_io._load_cache rename was undetected for weeks "
                "because of this gap. Regenerate via "
                "`python /tmp/write-integration-tests.py <pkg-dir>` "
                "(or the equivalent scitex-dev subcommand)."
            ),
        ),
        # §2 src ↔ tests mirror -------------------------------------------------
        Rule(
            "PS-201",
            "§2",
            "src/<pkg>/ exists but tests/<pkg>/ is missing — every package needs the tests/<pkg>/ parent",
            slug="tests-pkg-parent-missing",
        ),
        Rule(
            "PS-202",
            "§2",
            "src/<pkg>/<sub>/ has files but tests/<pkg>/<sub>/ is missing",
            slug="src-tests-mirror-dir-missing",
        ),
        Rule(
            "PS-203",
            "§2",
            "loose test_*.py at tests/ root that should live inside tests/<pkg>/...",
            slug="loose-top-level-test",
        ),
        Rule(
            "PS-204",
            "§2",
            "orphan test file: tests/<pkg>/<path>/test_*.py with no matching src/<pkg>/<path>/*.py",
            slug="orphan-test-file",
        ),
        Rule(
            "PS-205",
            "§2",
            "wrong public/private prefix (private `_foo.py` must be tested by `test__foo.py`, not `test_foo.py`)",
            slug="test-name-prefix-mismatch",
        ),
        Rule(
            "PS-145",
            "§1",
            (
                "source reads another scitex package's user-state tree "
                "(`~/.scitex/<other-pkg>/...`) or `SCITEX_<OTHER>_*` env "
                "var directly. Cross-package state coupling breaks "
                "`SCITEX_DIR` relocation and standalone-ability. Use the "
                "plugin-port pattern: expose your own `SCITEX_<THIS>_*_DIRS` "
                "slot and let consumers populate it. See "
                "_skills/general/01_ecosystem/06_local-state-directories.md "
                "§9.5."
            ),
            slug="local-state-cross-package-read",
        ),
        Rule(
            "PS-146",
            "§1",
            (
                "pyproject.toml declares an install-time hook (hatch build "
                "hook or setuptools cmdclass) that creates `~/.scitex/"
                "<pkg-short>/` — `pip install` side-effects break wheel "
                "inertness, fresh-CI runs, and `$SCITEX_DIR` relocation. "
                "Drop the hook and rely on lazy `PathManager` mkdir on "
                "first write (§3.5)."
            ),
            slug="local-state-pip-install-side-effect",
        ),
        Rule(
            "PS-147",
            "§1",
            (
                "source writes an eval-form shell-completion line "
                '(`eval "$(_<NAME>_COMPLETE=bash_source <bin>)"`) into '
                "the user's rc file. The eval form re-invokes the binary "
                "on every shell start (~0.4s/binary). Use the cache-file "
                "pattern instead: generate the completion once into "
                "`~/.scitex/<pkg-short>/runtime/completion/<binary>` and "
                "have rc `source` it. See _skills/general/03_interface/02_"
                "cli/03_required-introspection-commands.md."
            ),
            slug="local-state-eval-completion",
        ),
        Rule(
            "PS-150",
            "§1",
            (
                "pyproject.toml `[project.optional-dependencies.dev]` does not "
                "declare `scitex-dev` (or `scitex-dev[cli-audit]`). "
                '`tests/develop/test_audit.py` calls `shutil.which("scitex-dev")` '
                "and pytest.skip()s when absent — i.e. the audit-conformance gate "
                "silently does NOT run in CI's fresh venv. Add `scitex-dev>=0.11.5` "
                "(or current latest) to `[dev]` so the gate fires."
            ),
        ),
        Rule(
            "PS-164",
            "§1",
            (
                "GitHub Actions workflow naming/structure violates convention "
                "(one file = one check, descriptive kebab-case filename; see "
                "_skills/general/02_package/12_workflows-naming.md). Three "
                "sub-checks: vague filename in denylist, multi-job file with "
                "unrelated job IDs, or `name:` field mismatching the filename."
            ),
            slug="workflow-naming",
        ),
        Rule(
            "PS-151",
            "§1",
            (
                "scitex-dev pin floor in `[dev]` is below the known-good version "
                "(currently 0.11.5). Older scitex-dev releases ship a smaller / "
                "differently-classified rule corpus, so the same package gets "
                "different audit verdicts depending on which scitex-dev wheel "
                "PyPI happens to surface. Bump the floor to the current minimum."
            ),
        ),
        Rule(
            "PS-206",
            "§2",
            "placeholder-only test (no `def test_` or `class Test`)",
        ),
        Rule(
            "PS-206b",
            "§2",
            (
                "import-smoke-only test (`def test_*` exists but the file "
                "has no assertion at all — `assert`, `pytest.raises`, "
                "`mock.assert_*`, `self.assertX`, etc.). Pure "
                "`importlib.import_module(...)` smokes pass PS-206 + PS-202 "
                "without exercising behaviour. Add a real assertion or "
                "delete the file."
            ),
        ),
        Rule(
            "PS-210",
            "§2",
            (
                "`[dev]` extras incomplete — an optional `[X]` extra dep is "
                "imported unguarded by the test suite but missing from `[dev]` "
                "(see _skills/general/01_ecosystem/02_dependency-and-version-"
                "pinning.md `[dev]` extras completeness — fastmcp lesson, "
                "2026-05-02). A bare `pip install -e .[dev]` will fail at "
                "test-collection."
            ),
        ),
        Rule(
            "PS-207",
            "§2",
            (
                "empty test directory (no `test_*.py` files, only `__pycache__/` "
                "or nothing) — created during a partial migration but never filled. "
                "Either move the corresponding `tests/<sub>/test_*.py` files in, "
                "or remove the empty dir."
            ),
        ),
        Rule(
            "PS-211",
            "§2",
            (
                "missing `tests/smoke/` layer (fast <60s subprocess-driven CLI "
                "happy-path tests). Every SciTeX package with a CLI should keep "
                "a small set of subprocess-level smoke tests that run on every "
                "PR. Required: ≥1 `tests/smoke/test_*.py` AND register the "
                "`smoke` pytest marker in `[tool.pytest.ini_options].markers`. "
                "Opt-out: `[tool.scitex_dev]\\nno_cli = true` in pyproject.toml. "
                "Severity W during ecosystem adoption — will promote to E."
            ),
            slug="tests-smoke-layer-missing",
        ),
        Rule(
            "PS-212",
            "§2",
            (
                "missing `tests/e2e/` layer (slow end-to-end workflows against "
                "real subsystems). Required: ≥1 `tests/e2e/test_*.py`, register "
                "the `e2e` pytest marker, and gate execution via the `RUN_E2E=1` "
                "env var so the suite is skipped by default. Opt-out: "
                "`[tool.scitex_dev]\\nno_e2e = true` in pyproject.toml. "
                "Severity W during ecosystem adoption — will promote to E."
            ),
            slug="tests-e2e-layer-missing",
        ),
        # §3 tests/ subdirectory convention -------------------------------------
        Rule(
            "PS-301",
            "§3",
            "top-level ./htmlcov/ exists — coverage reports should live in tests/coverage/ (gitignored)",
        ),
        Rule(
            "PS-302",
            "§3",
            "unrecognized subdir at tests/ root (must be tests/<pkg>/ or one of the known categories: scripts/examples/skills/agentic/integration/e2e/github_actions/coverage/results/logs/reports/custom)",
        ),
        Rule(
            "PS-303",
            "§3",
            "examples/<name>.{py,sh,ipynb} has no matching tests/examples/test_<name>.py",
        ),
        Rule(
            "PS-501",
            "§5",
            (
                "examples/<n>_*.py main() does not use @stx.session — the "
                "canonical pattern (see ~/proj/figrecipe/examples/ and "
                "~/proj/scitex-python/examples/01_session.py) decorates main "
                "with @stx.session for auto-CLI, auto-organized output "
                "(SDIR_RUN/FINISHED_SUCCESS/<id>/), config injection, and "
                "session reproducibility. Replace manual `OUTPUT_DIR = "
                "Path(__file__).parent / '<n>_out'` boilerplate with `OUT = "
                "Path(CONFIG.SDIR_RUN)` inside the decorated main()."
            ),
        ),
        Rule(
            "PS-502",
            "§5",
            (
                "examples/<n>_*_out/ exists but is empty (or contains only "
                "__pycache__) — the example was never run end-to-end. Either "
                "execute it once so SciTeX's session machinery populates the "
                "FINISHED_SUCCESS marker, or remove the empty _out/ if the "
                "example doesn't yet work."
            ),
        ),
        Rule(
            "PS-503",
            "§5",
            (
                "examples/<n>_*_out/ has no FINISHED_SUCCESS/<session_id>/ "
                "subdir — the demo's already-run artefacts must be tracked "
                "in git so users see them on GitHub. Run the example once "
                "with @stx.session and commit the FINISHED_SUCCESS dir."
            ),
            slug="examples-need-finished-success",
        ),
        Rule(
            "PS-504",
            "§5",
            (
                "examples/<n>.ipynb has no committed cell outputs — looks "
                "nbstripped. GitHub renders cell outputs inline, so the "
                "demo is invisible without them. Re-run the notebook and "
                "commit with outputs intact."
            ),
        ),
        Rule(
            "PS-505",
            "§5",
            (
                "examples/<n>.ipynb has a sibling test "
                "tests/examples/test_<n>.py but the test does not invoke "
                "`nbconvert --execute` or `pytest --nbval` — runpy/import "
                "tricks don't execute notebooks. Mirror the .py "
                "smoke-test convention with one of those commands."
            ),
        ),
        Rule(
            "PS-506",
            "§5",
            (
                "examples/<n>.ipynb imports matplotlib but lacks the "
                "`%matplotlib inline` cell magic — figure outputs won't "
                "embed in the notebook, so GitHub-rendered cells will be "
                "blank. Add `%matplotlib inline` near the top."
            ),
        ),
        Rule(
            "PS-507",
            "§5",
            (
                "examples/<n>.ipynb imports matplotlib but does not call "
                "`plt.show()` (or rely on inline auto-display) — figures "
                "may not appear in the rendered cell outputs. Call "
                "`plt.show()` explicitly after each plot."
            ),
        ),
        Rule(
            "PS-508",
            "§5",
            (
                "examples/<n>.ipynb contains warning output in committed "
                "cells (DeprecationWarning, UserWarning, FutureWarning, "
                "RuntimeWarning, or stderr-stream `Warning:` text). "
                "Demos must be clean — silence the warning at the source, "
                "filter it explicitly with `warnings.filterwarnings`, or "
                "fix the underlying cause before re-running and committing."
            ),
        ),
        # §4 docs/ structure ----------------------------------------------------
        Rule(
            "PS-401",
            "§4",
            "./docs/to_claude/ is tracked — must be gitignored (local-machine agent context, not part of the shipped repo)",
        ),
        Rule(
            "PS-402",
            "§4",
            "top-level ./assets/ exists — figures/screenshots belong under ./docs/assets/",
        ),
    ]
}

# Severity escalation table.
#
# Per 2026-05-06 directive: every rule that ships a concrete spec defaults to
# E (error → fails CI). Demote back to W only after a documented false
# positive lands on develop. New rules MAY start at W during their initial
# bake-in, but the bar for staying W is "active false-positive history",
# not "we haven't promoted it yet".
#
# E (error) — fails CI; the rule is well-tested and the fix is mechanical.
# W (warn)  — prints, doesn't fail; for rules with active false-positive
#             history that haven't been demoted yet.
# I (info)  — printed only with --severity info; never fails. Use for
#             purely advisory categorizations (no actionable violation).
_SEVERITY_OVERRIDES: dict[str, str] = {
    # Structural — must hold for any package
    "PS-101": "E",  # missing pyproject.toml
    "PS-102": "E",  # forbidden top-level dir (logs/, mgmt/, ...)
    "PS-103": "E",  # top-level junk file
    "PS-104": "E",  # uses .playground/
    "PS-105": "E",  # console_scripts present but no __main__.py
    # README content — every public package follows the convention
    "PS-106": "E",
    "PS-107": "E",
    "PS-108": "E",
    "PS-108b": "E",
    "PS-109": "E",
    "PS-110": "E",
    "PS-111": "E",
    "PS-112": "E",
    "PS-113": "E",
    "PS-114": "E",
    "PS-115": "E",
    "PS-116": "E",
    "PS-117": "E",
    "PS-118": "E",
    "PS-119": "E",
    # PS-120 retired 2026-05-18 (umbrella one-liner content rule).
    "PS-123": "E",
    "PS-129": "E",
    "PS-130": "E",
    "PS-131": "E",
    "PS-132": "E",
    # Sphinx / RTD bundle
    "PS-121": "E",
    "PS-122": "E",
    "PS-124": "E",
    "PS-125": "E",
    "PS-126": "E",
    "PS-127": "E",
    "PS-128": "E",
    # Community files — every public package needs them
    "PS-133": "E",  # CLA.md
    "PS-134": "E",  # CHANGELOG.md
    "PS-135": "E",  # CONTRIBUTING.md
    "PS-136": "E",  # examples/
    "PS-137": "E",  # README.md
    "PS-138": "E",  # LICENSE present
    "PS-138b": "E",  # LICENSE content matches SPDX (no stub)
    "PS-139": "E",  # pyproject.toml depends on scitex umbrella (anti-pattern)
    "PS-140": "E",  # missing/stale tests/integration/test_cross_package_imports.py
    "PS-141": "E",  # README missing `## Demo` with visual content
    "PS-142": "E",  # README missing `## Architecture` with diagram/tree
    "PS-145": "W",  # cross-package state read (bake-in: warn first)
    "PS-146": "E",  # pip-install side-effect (clear violation)
    "PS-147": "W",  # eval-form shell completion (bake-in: warn first)
    "PS-152": "W",  # README split Problem/Solution headings (warn)
    "PS-153": "W",  # README architecture file-tree, no mermaid (warn)
    "PS-154": "W",  # README installation not canonical (warn)
    "PS-155": "I",  # README badge row not two centered rows (info)
    "PS-156": "I",  # examples/ has .py but zero .ipynb (info)
    "PS-157": "W",  # codecov badge URL unbranched (warn)
    "PS-158": "I",  # RTD badge uses readthedocs.org baked label (info)
    "PS-159": "W",  # README figure/table numbering broken (warn)
    "PS-160": "W",  # README figure/table missing caption (warn)
    "PS-161": "W",  # codecov.yml coverage target below 90 (warn)
    "PS-162": "W",  # README missing Codecov badge (warn)
    "PS-163": "W",  # README missing Read-the-Docs badge (warn)
    "PS-150": "W",  # [dev] missing scitex-dev pin — audit gate silently skips
    "PS-151": "W",  # scitex-dev pin floor < known-good (rule corpus drift)
    "PS-164": "W",  # workflow naming/structure (warn-only during adoption)
    # src ↔ tests mirror — load-bearing for CI confidence
    "PS-201": "E",
    "PS-202": "E",
    "PS-203": "E",
    "PS-204": "E",
    "PS-205": "E",
    "PS-206": "E",  # placeholder-only test (no `def test_*` / `class Test*` at all)
    "PS-206b": "W",  # has `def test_*` but body has no assertion (import-smoke only)
    "PS-207": "E",  # empty test directory
    "PS-210": "E",  # [dev] extras incomplete
    "PS-211": "W",  # tests/smoke/ layer missing — W during ecosystem adoption
    "PS-212": "W",  # tests/e2e/ layer missing  — W during ecosystem adoption
    "PS-301": "E",  # top-level htmlcov/
    "PS-302": "E",  # unrecognized tests/ subdir
    "PS-303": "E",  # examples/<n>.py without tests/examples/test_<n>.py
    "PS-401": "E",  # docs/to_claude/ tracked
    "PS-402": "E",  # top-level assets/
    "PS-501": "E",  # examples missing @stx.session
    "PS-502": "E",  # empty examples/<n>_out/
    "PS-503": "E",  # examples/<n>_out/ missing FINISHED_SUCCESS/<id>/
    "PS-504": "E",  # .ipynb has no committed cell outputs
    "PS-505": "E",  # .ipynb test does not nbconvert / nbval
    "PS-506": "E",  # .ipynb missing %matplotlib inline
    "PS-507": "E",  # .ipynb missing plt.show()
    "PS-508": "E",  # .ipynb has warning output in committed cells
}

# Human-readable kebab-case slugs. Surfaced inline in audit output as
# `[CODE §X slug]` so reviewers can read intent without cross-referencing
# rule numbers. Backfilled in batches; missing entries render in the old
# `[CODE §X]` form (no breakage). New rules SHOULD include a slug from
# definition.
_SLUGS: dict[str, str] = {
    # §1 — top-level layout already slugged at definition (PS-101–PS-103)
    "PS-104": "uses-playground-dir",
    "PS-105": "main-py-missing",
    # README structure
    "PS-106": "readme-missing-coverage-badge",
    "PS-107": "readme-missing-h2-sections",
    # PS-108 / PS-108b detect flat-package-layout patterns in src/, NOT
    # README badges. (The badge-shaped slugs that used to sit here
    # described long-retired README rules and confused every reader.)
    "PS-108": "src-prefix-cluster-mess",
    "PS-108b": "src-flat-py-files-over-threshold",
    "PS-109": "readme-missing-pypi-version-badge",
    "PS-110": "readme-missing-four-freedoms",
    "PS-111": "readme-personal-email",
    "PS-112": "readme-missing-logo",
    "PS-113": "readme-banned-emoji",
    "PS-114": "readme-banned-marketing",
    "PS-115": "readme-missing-architecture",
    "PS-116": "readme-banned-buzzword",
    "PS-117": "readme-missing-quickstart",
    "PS-118": "readme-missing-installation",
    "PS-119": "readme-missing-part-of-scitex",
    # PS-120 retired 2026-05-18.
    "PS-123": "readme-banned-future-claim",
    "PS-129": "readme-banned-trademark-symbol",
    "PS-130": "readme-missing-related-projects",
    "PS-131": "readme-missing-citation",
    "PS-132": "readme-missing-roadmap",
    # Sphinx / RTD
    "PS-121": "rtd-onboarding-missing",
    "PS-122": "rtd-config-missing",
    "PS-124": "sphinx-conf-missing",
    "PS-125": "sphinx-makefile-missing",
    "PS-126": "sphinx-extensions-bad",
    "PS-127": "sphinx-theme-bad",
    "PS-128": "sphinx-build-broken",
    # Community files
    "PS-133": "missing-cla",
    "PS-134": "missing-changelog",
    "PS-135": "missing-contributing",
    "PS-136": "missing-examples-dir",
    "PS-137": "missing-readme",
    "PS-138": "missing-license",
    "PS-138b": "license-stub-mismatched",
    "PS-139": "pyproject-depends-on-umbrella",
    "PS-140": "cross-package-imports-test-missing",
    "PS-141": "readme-missing-demo",
    "PS-142": "readme-missing-architecture-diagram",
    "PS-143": "readme-missing-badge-row",
    "PS-144": "readme-missing-pypi-status",
    "PS-152": "readme-split-problem-solution",
    "PS-153": "readme-architecture-filetree-not-mermaid",
    "PS-154": "readme-installation-not-canonical",
    "PS-155": "readme-badge-row-not-two-rows",
    "PS-156": "examples-no-ipynb",
    "PS-157": "readme-codecov-badge-unbranched",
    "PS-158": "readme-rtd-badge-baked-label",
    "PS-159": "readme-figures-tables-numbering",
    "PS-160": "readme-figures-tables-missing-caption",
    "PS-161": "readme-codecov-coverage-target-too-low",
    "PS-162": "readme-missing-codecov-badge",
    "PS-163": "readme-missing-rtd-badge",
    "PS-150": "dev-extras-missing-scitex-dev",
    "PS-151": "dev-extras-scitex-dev-floor-too-old",
    # §2 src↔tests already slugged at definition (PS-201–PS-205)
    "PS-206": "test-placeholder-only",
    "PS-206b": "test-import-smoke-only",
    "PS-207": "empty-test-dir",
    "PS-210": "dev-extras-incomplete",
    # §3 docs / examples
    "PS-301": "top-level-htmlcov",
    "PS-302": "tests-unknown-subdir",
    "PS-303": "example-without-test",
    # §4 docs/to_claude
    "PS-401": "docs-to-claude-tracked",
    "PS-402": "top-level-assets",
    # §5 examples + notebooks (PS-503 already slugged)
    "PS-501": "example-without-stx-session",
    "PS-502": "examples-out-empty",
    "PS-504": "ipynb-no-cell-outputs",
    "PS-505": "ipynb-test-not-nbconvert",
    "PS-506": "ipynb-missing-matplotlib-inline",
    "PS-507": "ipynb-missing-plt-show",
    "PS-508": "ipynb-warning-in-output",
}


# Apply the overrides — replace each tagged Rule with a promoted copy that
# carries both the (optional) severity override and the (optional) slug.
def _patch(rule: Rule) -> Rule:
    sev = _SEVERITY_OVERRIDES.get(rule.code, rule.severity)
    slug = rule.slug or _SLUGS.get(rule.code, "")
    if sev == rule.severity and slug == rule.slug:
        return rule
    return Rule(rule.code, rule.section, rule.message, sev, slug)


RULES = {code: _patch(rule) for code, rule in RULES.items()}

# hook-bypass: line-limit
# Sidecar rule registration — see ._extra_rules / GITIGNORED/REFACTORING.md.
from ._extra_rules import EXTRA_RULES as _EXTRA_RULES  # noqa: E402

for _c, _sec, _msg, _sev, _slug in _EXTRA_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

