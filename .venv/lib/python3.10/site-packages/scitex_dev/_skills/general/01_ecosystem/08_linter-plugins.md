---
description: |
  [TOPIC] Linting Across the Ecosystem
  [DETAILS] How SciTeX lint rules are physically distributed: each package ships the rules that enforce *its own* API, and `scitex-dev linter` (the engine, formerly `scitex-linter`) aggregates them at runtime via Python entry points. Result — one CLI surface across the ecosystem, but rules live next to the API they enforce, so a rename or deprecation can land in a single PR. Covers the entry-point group, the `get_plugin()` contract, the `requires=` runtime gate, doc-block linting (`.md`/`.rst`), and the `scitex-dev linter sweep` ecosystem-wide sweep.
  [WHEN] Adding a new lint rule, shipping a new package, debugging why a rule does or doesn't fire, or wiring lint into CI.
tags: [scitex-general-ecosystem-linter-plugins]
---

# Linting Across the Ecosystem

Lint rules are **owned by the package whose API they enforce**, not by `scitex-dev`. The engine in `scitex-dev` only aggregates them.

## The split

| Concern | Lives in | Reason |
|---|---|---|
| Engine: `Rule` dataclass, AST framework, `lint_source`, plugin loader, CLI, severity machinery | `scitex-dev` (`scitex_dev.linter`) | Most-depended-on dev tool — every leaf can plug in without circular deps. |
| Rules + their AST checkers (e.g. P006 `scatter(..., s=...)`, IO001 `np.save → stx.io.save`) | The package whose API they discuss (`figrecipe._linter_plugin`, `scitex_io._linter_plugin`, …) | Rule and API change in lockstep — a rename breaks both at the same PR. |

When `scitex-dev linter` runs, it discovers every package that registers a plugin and merges the rule set. Users see a single rule list (`scitex-dev linter list-rules-all`); they don't care which package produced which rule.

## How a package ships rules

### 1. Write a `_linter_plugin.py` that exposes `get_plugin()`

```python
# src/<pkg>/_linter_plugin.py

def get_plugin():
    from scitex_dev.linter._rules._base import Rule
    # Legacy fallback while the soft-migration window is open:
    # `from scitex_linter._rules._base import Rule` also works today.

    P006 = Rule(
        id="STX-P006",
        severity="warning",
        category="plot",
        message="`scatter(..., s=...)` — drop `s=`; SciTeX style sizes markers automatically",
        suggestion="Remove the `s=` kwarg.",
        requires="figrecipe",          # gated to runs where figrecipe is installed
    )

    return {
        "rules":      [P006],
        "call_rules": {(None, "savefig"): P006},   # optional: pattern-keyed table
        "axes_hints": {"scatter": P006},           # optional: ax-method hints
        "checkers":   [],                          # optional: NodeVisitor classes
    }
```

The `checkers` list lets you ship richer AST visitors (e.g. multi-kwarg detection). Each class needs `__init__(source_lines, config)`, a `.issues` list, and a `.category` attribute. See `figrecipe/src/figrecipe/_linter_plugin.py` for a working example.

### 2. Declare the entry point in `pyproject.toml`

```toml
[project.entry-points."scitex_dev.linter.plugins"]
figure = "figrecipe._linter_plugin:get_plugin"
```

The name (`figure` here) is arbitrary but should be unique across the ecosystem. The engine **also** reads the legacy group `scitex_linter.plugins` for the duration of the soft-migration window — projects don't need to re-register on day one.

### 3. Reinstall (`pip install -e .`) — entry points only refresh on install

`scitex-dev linter list-rules-all` should now show the new rule.

## Rule conventions

- **`id`** — `STX-<CAT><NNN>` where `<CAT>` is the namespace (`P` plot, `IO` i/o, `S` structure, `FM` figure-mm, `I` import, `PA` path, `ST` stats, `EH` error-handling). Allocate ids in the namespace owned by the package whose API the rule enforces; avoid colliding with engine-shipped ids.
- **`severity`** — `error` blocks CI; `warning` is the default for lints that flag a real anti-pattern; `info` is a suggestion ("consider X instead").
- **`requires`** — name of the runtime package that must be importable for the rule to fire. Used to suppress noise on machines where the relevant dep isn't installed (e.g. P006 only fires when `figrecipe` is present).
- **`message`** — one line, present tense, names the offending construct.
- **`suggestion`** — one line, names the replacement. End with a period.

## Tests live with the rule

Rule tests live in the **owning package**, not in `scitex-dev`. The test imports the engine, applies the rule to a snippet, asserts the rule fired:

```python
# tests/test_linter_p006.py  (in figrecipe)
from scitex_dev.linter.checker import lint_source

def test_p006_flags_s_kwarg():
    issues = lint_source("ax.scatter(x, y, s=10)")
    assert any(i.rule.id == "STX-P006" for i in issues)
```

This is the structural argument for the per-package layout: rule + API + test all change in lockstep, so an API rename can't silently outrun the rule.

## Doc-block linting (`.md`, `.rst`)

`scitex-dev linter check-files <file>` works on more than `.py`:

| Extension | Handler | Source-of-truth file |
|---|---|---|
| `.py` | `lint_source` | direct |
| `.ipynb` | `_ipynb.lint_ipynb` — extracts code cells from the JSON | per-cell virtual filepath `nb.ipynb::cell-N` |
| `.md` / `.markdown` | `_md.lint_md` — extracts ` ```python` fenced blocks | per-block virtual filepath `README.md::block-N` |
| `.rst` | `_rst.lint_rst` — extracts `.. code-block:: python` directives | per-block virtual filepath |

Structural rules (`STX-S001`–`S005`) are skipped automatically for snippet contexts (notebooks/READMEs/RST blocks aren't expected to have a `__main__` guard or module docstring). Issue line numbers are remapped back to the source file's actual line.

## Ecosystem-wide sweep

```bash
scitex-dev linter sweep                                   # human-readable
scitex-dev linter sweep --json                            # machine-readable
scitex-dev linter sweep --package figrecipe               # one package
scitex-dev linter sweep --strict                          # CI gate (exits non-zero on any issues)
```

The sweep walks every package registered in `scitex_dev._ecosystem._core.ECOSYSTEM` (skipping `archived` and `template` categories), lints `README.md` / `README.rst` / `docs/sphinx/index.rst` / `docs/sphinx/quickstart.rst` / `docs/index.{md,rst}` for each, and emits a per-package summary.

This is what catches READMEs that *teach* the wrong API — a class of bug nothing else surfaces.

## Migration status (2026-Q2)

- **Engine**: `scitex-dev` ships it. The legacy `scitex-linter` package is a thin alias that still works; the `scitex-linter` console script and `python -m scitex_linter` are kept for the soft-migration window.
- **Plugins**: `figrecipe` ships P001-P009 + FM001-FM009. Other packages with `_linter_plugin.py` declared: `scitex_io`, `scitex_stats`, `scitex_audio`, `scitex_clew`, `scitex_notification`. Engine-shipped (legacy) rules `S*`, `I*`, `IO*`, `PA*`, `ST*`, `EH*` will migrate into their owning packages over subsequent releases.
- **Console scripts**: `scitex-dev linter <subcommand>` is the canonical path. `scitex-linter <subcommand>` aliases it.

## Related

- [`02_package/08_quality.md`](../02_package/08_quality.md) — quality-checklist that calls into `scitex-dev linter` as one of the release gates.
- [`05_development/02_periodic-audits.md`](../05_development/02_periodic-audits.md) — `scitex-dev ecosystem audit-*` is the **structural** auditor (project layout, CLI shape, skill conformance); `scitex-dev linter` is the **code-pattern** auditor (anti-patterns inside `.py`/`.ipynb`/`.md`/`.rst`). Run both periodically.
- [`02_package/07_github-actions.md`](../02_package/07_github-actions.md) — wiring `scitex-dev linter sweep --strict` into CI.
