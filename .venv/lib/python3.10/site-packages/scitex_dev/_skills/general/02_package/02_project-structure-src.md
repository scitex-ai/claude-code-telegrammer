---
description: |
  [TOPIC] Package Src
  [DETAILS] `./src/<pkg>/` layout for a SciTeX *package* — the production code that ships in the wheel. Covers the one-package-per-repo rule, absolute-import discipline, the cascade-direction rule (inter-scitex package imports along the cascade are healthy; only the umbrella `scitex` should not be imported from a scitex-* package's own `src/` because it re-exports the package itself, creating a real cycle), and the public/private filename convention (`_foo.py` for private, mirrored by `tests/<pkg>/test__foo.py`).
tags: [scitex-general-package-project-structure-src]
---

# `./src` — pip-installable package

> Sibling leaves: [`./root`](01_project-structure-root.md) · [`./scripts`](03_project-structure-scripts.md) · [`./scripts/makefile`](04_project-structure-makefile.md) · [`./examples`](05_project-structure-examples.md) · [`./tests`](06_project-structure-tests.md)

## Layout

- The production package — everything here ships in the wheel.
- One package per repo: `<repo>/src/<package_name>/...`.

```
<repo>/
├── src/
│   └── <package_name>/
│       ├── __init__.py
│       ├── <public_module>.py
│       ├── _<private_module>.py
│       └── <subpkg>/
│           ├── __init__.py
│           └── ...
```

## Subpackage clusters — keep `src/<pkg>/` navigable

Once `src/<pkg>/` accumulates **3+ flat `.py` files sharing a common
prefix** (`_cli_*.py`, `_skills_*.py`, `_mcp_*.py`, `sync_*.py`, …),
promote them into a subpackage. A common prefix on three files is a
reliable signal that the cluster wants to be a directory.

```
# Before — flat, hard to scan
src/<pkg>/
├── _cli.py
├── _cli_audit.py
├── _cli_audit_api.py
├── _cli_skills.py
├── _cli_stats.py

# After — grouped by responsibility
src/<pkg>/
└── _cli/
    ├── __init__.py
    ├── _root.py
    ├── _audit.py
    ├── _audit_api.py
    ├── _skills.py
    └── _stats.py
```

Group **by responsibility, not blind prefix-promotion** — if the CLI
surface (`<pkg> --help`) already groups commands into Ecosystem /
Development / Documentation / Interface / Shell sections, mirror those
same categories in the source layout. The CLI grouping is your
designed-in taxonomy; the source layout should match it.

`audit-project`'s **PS-108** rule flags packages where prefix-clusters
have grown past the threshold and rolls all clusters into one
violation, so you land the reorganization in a single coherent pass
rather than fixing one prefix at a time across separate PRs.

When PS-108 fires alongside PS-204 (orphan tests), the orphan-test
hint also tells you where each test should be moved — refactor the
src and the tests in the same change.

### Logical categorization, not blind prefix-promotion

The prefix is a *trigger* for noticing a cluster, not a *recipe* for
the new layout. When PS-108 fires, resist the temptation to mechanically
move every `<prefix>_*.py` into `_<prefix>/` and stop. Two files with
the same prefix can belong to two different responsibilities, and two
files with different prefixes can belong together.

Decision rules, in order:

1. **Group by what callers ask of these files, not by their leaf name.**
   If `mcp.py`, `mcp_utils.py`, `_mcp_compat.py`, `_mcp_server.py` all
   serve "the MCP integration", they belong in `_mcp/`. If among those
   one file is actually only there for *agentic-test* harness code,
   that file goes in `_agentic_testing/` regardless of its name.
2. **Use the public-API surface as the taxonomy.** If `<pkg> --help`
   already groups commands (Ecosystem / Development / Documentation /
   Interface / Shell), mirror that taxonomy in the source layout. One
   subpackage per category is a strong default — the CLI grouping was
   already designed by humans for humans, so reusing it is free
   discoverability.
3. **A single file with no peers does not need a directory.** PS-108
   threshold is 3 for a reason: 1–2 files are findable as flat siblings.
   Don't create a `_logging/` package for one `logging.py`.
4. **Cross-cluster shared helpers go up one level, not into either cluster.**
   If `_mcp/` and `_cli/` both import a `_dispatch_table` helper, keep
   that helper as a flat sibling at `src/<pkg>/_dispatch.py` rather than
   picking a "primary" subpackage to host it. PS-108 won't flag a single
   file.
5. **When unsure, prefer fewer larger directories over many small ones.**
   You can split later (cheap) but un-splitting is messy (every external
   caller has the deeper path memorized).

A worked example — the **wrong** way to refactor scitex-dev's `_cli_*`:

```
src/scitex_dev/_cli/
├── _audit.py
├── _audit_api.py
├── _audit_project.py
├── _audit_skills.py
├── _completion.py
├── _doctor.py
├── _ecosystem.py
├── _quality.py
├── _quality_frontmatter.py
├── _skills.py
├── _skills_tags.py
└── _stats.py
```

That's just the prefix moved one level deeper. Twelve siblings in one
flat dir is the same smell at a different depth.

The **right** way — group by what each command actually does:

```
src/scitex_dev/_cli/
├── __init__.py            # root group + register_*  helpers
├── _root.py               # main(), version flag, --help-recursive
├── audit/                 # everything that *audits*
│   ├── __init__.py
│   ├── _project.py        # was _cli_audit_project.py glue
│   ├── _api.py            # was _cli_audit_api.py glue
│   ├── _skills.py         # was _cli_audit_skills.py glue
│   └── _summary.py        # was _cli_audit.py (cross-cutting)
├── ecosystem/             # `<pkg> ecosystem ...` commands
│   ├── __init__.py
│   └── _registry.py       # was _cli_ecosystem.py
├── quality/               # quality / linting commands
│   ├── __init__.py
│   ├── _check.py
│   └── _frontmatter.py
├── skills/                # skill-management commands
│   ├── __init__.py
│   ├── _manage.py
│   └── _tags.py
├── _completion.py         # one file — leave flat
├── _doctor.py             # one file — leave flat
└── _stats.py              # one file — leave flat
```

The new tree mirrors the CLI's own `--help` categories (Ecosystem /
Development / Documentation / Interface / Shell) plus an `audit/`
group that didn't exist as a CLI category but obviously *should* —
the refactor surfaces a missing piece of the public taxonomy too.
**That's the test** for whether your grouping is right: it should
reveal something true about the package's structure, not just shuffle
files into shorter siblings.

## Topical clusters with no shared prefix — the silent mess

PS-108 catches prefix clusters (`_cli_*`, `_skills_*`). It does **not**
catch the second mess pattern: a package root with many flat files that
*share a topic* but no prefix.

Example — scitex-dev's actual `src/scitex_dev/` had ~30 flat top-level
files like `ci.py`, `deploy.py`, `github.py`, `rtd.py`,
`_version_fixer.py`, `_release_publisher.py`, `versions.py` — clearly a
"release/CI" cluster, but no shared prefix means PS-108 stays silent.

**Rule (PS-108b — pending audit)**: when `src/<pkg>/` (or any
subpackage) holds **>15 flat `.py` files** excluding `__init__.py` and
`__main__.py`, group them into topical subpackages. Use the same
decision rules as the prefix case (group by responsibility, mirror the
public taxonomy, leave singletons flat).

Suggested categories every package tends to need (rename to taste):

| Category | Examples of files that belong here |
| -------- | ---------------------------------- |
| `_release/` | CI helpers, deploy, github, rtd, version bumpers |
| `_docs/`    | docs build, search, sphinx hooks |
| `_core/`    | config, errors, types, dist-info, imports, decorators |
| `_quality/` | linters, audit-core (NOT the CLI surface — that lives in `_cli/audit/`) |

Single-file orphans (no peers) **stay flat** — see decision rule #3
above. Don't create `_logging/` for one `logging.py`.

## Imports

- **Absolute imports**: `from <package_name>.x.y import z`.
- **Never** `from src...` and **never** relative-across-package-boundaries (`from ..other_subpkg import …` outside of the same submodule).
- Within one submodule, relative imports (`from . import x`, `from ._helper import y`) are fine and preferred.

## Inter-package dependencies

Inter-scitex package deps follow the **cascade direction** (see [01_ecosystem/01_upstream-and-downstream.md](../01_ecosystem/01_upstream-and-downstream.md)):

- A downstream package importing from an upstream one is fine and common — e.g. `scitex-stats` depends on `scitex-io` for save/load helpers; `scitex-cloud` depends on `scitex-config` for path resolution.
- Pyproject must declare every such dep. `REL-5_implicit_deps` flags missing declarations.

What `src/` should **not** import is the **umbrella `scitex` package itself** — that umbrella re-exports the package, which creates a real cycle on install. Tests, scripts, and examples are free to import from the umbrella.

```python
# src/scitex_io/__init__.py — GOOD
from .config import load_config       # local
import scitex_config                  # ecosystem peer — declared in pyproject

# src/scitex_io/__init__.py — BAD
import scitex                         # umbrella; would form a cycle
```

## Public / private filename convention

A leading underscore in a filename marks the module as **private** (not part of the public API). Test files mirror this with a **double underscore** between `test` and the basename:

| Source | Test |
| :--- | :--- |
| `src/<pkg>/foo.py` (public) | `tests/<pkg>/test_foo.py` |
| `src/<pkg>/_foo.py` (private) | `tests/<pkg>/test__foo.py` |

The double-underscore visually echoes the source's leading underscore, and PS-205 of `audit-project` enforces it.

`__init__.py` is exempt — it doesn't get its own test file (use `tests/<pkg>/test___init__.py` only when you have a real reason to test package-level behavior, e.g. lazy-import wiring).

## What does NOT live in `src/`

- One-off analysis pipelines or maintenance scripts → [`./scripts/`](03_project-structure-scripts.md).
- Demo files → [`./examples/`](05_project-structure-examples.md).
- Tests → [`./tests/<pkg>/`](06_project-structure-tests.md).
- External material kept verbatim → not used in scitex (no `./references/`).

## `_skills/` — packaged skill assets

If your package ships agent-facing skills, vendor them at `src/<pkg>/_skills/<pkg>/`. The bundling is enforced by `REL-9_skill_bundling` in `scitex_dev._pyproject_lint`. See `_skills/general/03_interface/04_skills/` for the skill-authoring rules.

## `_sphinx_html/` — pre-built docs (production)

If your package wants its docs served at <https://scitex.ai/apps/docs/>, the pre-built HTML must ship under `src/<pkg>/_sphinx_html/`. See [02_package/01_project-structure-root.md](01_project-structure-root.md#production-served-sphinx-html--bundled-in-srcpkg_sphinx_html) for the bundle pattern, and [04_docs/02_sphinx.md](../04_docs/02_sphinx.md) for the release recipe.

## `containers/`, `templates/`, and other non-Python assets — bundle in the wheel

If your package ships container recipes (Dockerfiles, Apptainer
`.def` files), Jinja2 templates, schema YAML, or any other non-Python
asset that the package's own code reads at runtime, vendor it under
`src/<pkg>/<asset-dir>/` — never at the **repo root** (`./containers/`,
`./templates/`).

Repo-root layout:

```
❌ <repo>/containers/apptainer-base.def
❌ <repo>/templates/<thing>.j2
```

is invisible to `pip install`. Users without the repo (the typical
pip-only consumer) get the CLI but no recipes; commands like
`<pkg> image build` fail at runtime with "recipe not found".

In-package layout:

```
✓ src/<pkg>/containers/apptainer-base.def
✓ src/<pkg>/templates/<thing>.j2
```

is automatically packaged by `hatch.build.targets.wheel` (and the
equivalent for setuptools / poetry) when `packages = ["src/<pkg>"]`.
Verify with:

```bash
python -m build --wheel
unzip -l dist/<pkg>-*.whl | grep <asset-dir>
```

The package's runtime code resolves these via `__file__`-relative
paths:

```python
_RECIPES_DIR = Path(__file__).resolve().parent / "containers"
```

This survives `pip install` (the wheel ships into site-packages),
editable installs (`pip install -e .`), and `$SCITEX_DIR` relocation
(it's package-relative, not user-state-relative).

**Built artifacts** (SIFs, sandboxes, generated outputs) are user
state — they belong under `~/.scitex/<pkg-short>/runtime/<asset-dir>/`,
not in the wheel. See `01_ecosystem/06_dot_scitex_directory.md` §4b.

Audit (proposed PS code): grep for `<repo>/containers/` /
`<repo>/templates/` and flag if the package's own code reads them
(except for setup-time manifests like `pyproject.toml`).
