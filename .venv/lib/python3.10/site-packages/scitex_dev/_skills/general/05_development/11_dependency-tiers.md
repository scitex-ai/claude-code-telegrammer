---
description: |
  [TOPIC] Three-tier dependency policy for every scitex-* package and
  the canonical helper for optional imports.
  [DETAILS] Two install modes (default + [all]) plus [dev]. No
  fragmented extras. `scitex_dev.try_import_optional` is the
  ecosystem-wide handler for genuinely optional dependencies — raw
  try/except ImportError is forbidden. Auditors and reviewers check
  this every commit.
tags: [scitex-general-development-dependency-tiers]
---

# Three-tier dependency policy

Every scitex-* package's `pyproject.toml` has exactly three dependency
buckets — no more, no less.

## The three buckets

```toml
[project]
dependencies = [
    # Tier 1 (hard) — required for every public surface to work out of
    # `pip install <pkg>`. Python API + CLI + MCP server + Skills must
    # all start with nothing more than these.
]

[project.optional-dependencies]
all = [
    # Tier 2 — fully-featured. `pip install <pkg>[all]` enables every
    # graceful-degradation feature the package offers. Heavy or
    # platform-specific packages live here.
]

dev = [
    # Tier 3 — what the maintainer needs to develop the package
    # itself. pytest, pytest-cov, pre-commit, nbconvert, ipykernel,
    # etc. NOT included by [all].
]
```

That is the *entire* taxonomy. **No** `[plot]`, `[mcp]`, `[figrecipe]`,
`[logging]`, `[pingouin]`, `[torch]` etc. They all collapse into `[all]`.

## Why two install modes (not five)

Fragmented extras (`[plot]` + `[mcp]` + `[figrecipe]` + …) cost more
than they save:

- Users have to read the README to know which combination they want.
- Adding a new feature means adding a new extra; old releases drift.
- `[all]` ends up depending on `<pkg>[plot]` + `<pkg>[mcp]` + … which
  is hard to keep consistent.
- Most users want either "minimal" or "everything." Forcing them to
  pick the right subset is bureaucracy.

Two modes — default and `[all]` — cover both. `[dev]` is the third
because development tools are conceptually different (they're for
maintainers, not consumers).

## What goes in `[project.dependencies]` (hard)

A package belongs in hard if **any** of these holds:

- The Python API's "obvious" entry points require it. Not the entire
  surface, but the entry points a first-time user will hit.
- The CLI's `--help` or first subcommand needs it for import.
- The MCP server (`<pkg>._mcp.server`) tops at it (server start path).
- A skill file says "this works out of the box" and would lie without it.

If the package is **statistically central** (stats packages: `numpy`,
`scipy`, `pandas`, `statsmodels`, `pingouin`), it goes hard regardless
of whether the API can run without it. Promise of out-of-box function
beats install-size optimization for our scientific-Python use case.

`scitex-dev` and `scitex-logging` are **always** hard. Try-import,
config cascade, linter plugin loading, and logger semantics all break
without them.

`mcp` and `fastmcp` are hard for any package shipping an MCP server —
the server top-level imports `fastmcp`, so without it `mcp start` is
broken on bare install. (Users not using MCP pay ~3MB; cheap.)

## What goes in `[all]`

Everything else that's optional but useful:

- Heavy / platform-specific (`torch`, `tensorflow`, `cuda-*`).
- Niche features (one statistical test out of dozens).
- Integrations with other ecosystems.

Rule of thumb: if a feature has a graceful-degradation path that's
documented, the dep goes in `[all]`.

## What goes in `[dev]`

Things only the **maintainer** of this package needs:

- `pytest`, `pytest-cov`, `pytest-xdist`, `pytest-mock`
- `pre-commit`
- `nbconvert`, `ipykernel` (for notebook tests / docs)
- `openpyxl` (test fixtures touching xlsx)

`[dev]` does **not** include packages that are already in `default`
(hard) — `pip install -e ".[dev]"` walks `default` automatically.

## Optional imports must use `try_import_optional`

`scitex_dev._core.imports.try_import_optional` is the **only**
sanctioned way to import a `[all]`-tier dependency. Raw
`try/except ImportError` is forbidden ecosystem-wide.

```python
from scitex_dev import try_import_optional

# Optional torch dep (lives in [all])
torch = try_import_optional("torch", extra="all", pkg="scitex-stats")
if torch is None:
    # Numpy fallback path
    ...

# Optional module + attr
go_eda = try_import_optional(
    "scitex_genai.protocols.go_eda",
    attr="rank_findings",
    extra="all",
    pkg="scitex-app",
)
```

Why the helper instead of try/except:

- Install hint registered in `scitex_dev._core.imports._HINTS` — error
  paths can call `last_install_hint("torch")` to surface
  "pip install scitex-stats[all]" automatically.
- Single helper means error messages improve across the ecosystem
  when scitex-dev releases — no per-package follow-up.
- Grep target: `try_import_optional(` immediately tells readers
  this is an optional dep, while bare `try: import X` is ambiguous.

## When a package gets *promoted* from `[all]` to hard

The try_import_optional call becomes a plain `import` — delete the
helper at the call site. The helper is for *genuinely* optional;
once a dep is mandatory, keeping the helper there is dead theater.

```python
# Before (when scitex-logging was in [all]):
scitex_logging = try_import_optional("scitex_logging", extra="all", pkg="scitex-stats")
if scitex_logging is None:
    import logging as scitex_logging  # stdlib fallback

# After (scitex-logging is hard):
import scitex_logging
```

## Audit hooks

```bash
# pyproject section count check (default + [all] + [dev] only).
scitex-dev ecosystem audit-project <pkg>

# Raw try/except-on-import grep (catch bypass attempts).
scitex-dev ecosystem audit-skills <pkg>     # SK-future, file an issue if missing
```

If either auditor flags violations, fix the dep taxonomy *before*
opening the PR. Pre-push lint gate (`.githooks/pre-push`) doesn't
catch this yet — manual review still required.

## Migration of an existing package

Step-by-step for a package with fragmented extras:

1. Audit what each public surface needs (run all four: Python API
   import, CLI --help, MCP server import, skills entry-point).
2. Promote any package needed by a public surface to `default`.
3. Collapse every remaining extra (`[plot]`, `[mcp]`, …) into a single
   `[all]`. Delete the old keys.
4. Refactor raw `try/except ImportError` to `try_import_optional`.
5. Delete `try_import_optional` for packages promoted to `default` —
   plain `import` is now correct.
6. Drop any package that has 0 hits in `src/` (genuine dead deps).
7. Run `pytest tests/` and `<pkg> --help` on a fresh venv to verify
   the default install works end-to-end.

## Cross-references

- `05_development/10_package-maintenance-prompt.md` — where this slot
  fits in the standing maintenance loop.
- `01_ecosystem/02_dependency-and-version-pinning.md` — version range
  conventions inside each bucket.
- `01_ecosystem/03_modules-and-standalone-packages.md` — how to decide
  whether to vendor or depend on a sibling scitex-* package.
- `04_docs/01_readme.md` — README must document the two install modes
  (default + [all]).
