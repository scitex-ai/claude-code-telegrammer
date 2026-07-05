---
description: |
  [TOPIC] Interface Python Api Import Conventions
  [DETAILS] Standalone vs umbrella import conventions. `pip install scitex-io` → `import scitex_io as sio`. `pip install scitex` → `import scitex.io as sio`. Skills and READMEs document both forms. Inside package source, use the standalone form. In umbrella docs, write `import scitex` (never `as stx`).
tags: [scitex-general-interface-python-api-import-conventions]
---

# Import Conventions

Every SciTeX subpackage ships in two ways. **Both must be documented in every package's skill / README** because which one a user has installed is outside the skill's control.

## The two paths

| Install command                  | Required import                | Notes                                                                |
|----------------------------------|--------------------------------|----------------------------------------------------------------------|
| `pip install scitex-io`          | `import scitex_io as sio`      | Standalone top-level module; `scitex.` namespace not available       |
| `pip install scitex` (umbrella)  | `import scitex.io as sio`      | Umbrella re-exports each standalone via `_LazyModule` machinery      |
| `pip install scitex scitex-io`   | either works                   | Both imports resolve to the same module object                       |

Empirically verified 2026-04-23 in a fresh `python:3.11` container:

```text
pip install scitex-io   → import scitex_io as sio   ✓
                       → import scitex.io as sio    ✗  (ModuleNotFoundError: 'scitex')
```

## Rules for documentation

- **Skill / README examples MUST show both forms** side-by-side, with a one-line note on when each applies. Readers land on the skill without knowing which install path they took.
- **Inside the package's own source code**: use the standalone form (`from scitex_io import save`) — the package cannot assume the umbrella is installed alongside it.
- **In ecosystem docs that assume the umbrella**: use `import scitex` (not `import scitex as stx`) in all examples. Aliases belong to the user, not the documentation.

## Hard rule — no umbrella imports inside standalone source

**OK** in `src/scitex_xxx/`:    `from scitex_yyy import foo`
**NG** in `src/scitex_xxx/`:    `from scitex.yyy import foo` / `import scitex.yyy` / `import scitex`

The umbrella is a re-export shim. When standalone source imports
`scitex.yyy`, Python must first import `scitex`'s `__init__.py` —
which sets up the lazy re-export machinery for **every** subpackage in
the umbrella. On NFS-mounted home directories (HPC, shared workstations)
this turns a single `scitex-scholar` CLI invocation into hundreds of
small `stat()` calls across the whole umbrella tree. A standalone
package that imports its peer through `scitex_yyy` only pays for
`scitex_yyy`.

This applies recursively to peer standalones too:
`scitex-scholar` calling `scitex.dict.DotDict` should be
`scitex_dict.DotDict`. The umbrella version goes through one extra
indirection (`scitex.dict` → `scitex_dict`) but the cost is the
umbrella's `__init__.py` setup, not the indirection itself.

Audited by **PA-304** (`audit-python-apis`). Triggers as `error` on any
`from scitex.X` / `import scitex.X` / `import scitex` line inside
`src/<pkg>/**/*.py` of a standalone package (i.e. any package whose
`import_name` in the registry is not `scitex`).

## Side-by-side example (copy into package skills)

```python
# If you installed the standalone:
#     pip install scitex-io
import scitex_io as sio
sio.save(df, "results.csv")

# If you installed the umbrella:
#     pip install scitex
import scitex.io as sio
sio.save(df, "results.csv")
```

Both forms call the same function; the difference is which module namespace Python resolves. Choose the install path that matches the project's dependency story — standalone if the package is a leaf dependency, umbrella if the project uses many SciTeX packages at once.

## Why no `as stx` in shipped docs

User aliases (`stx`, `np`, `pd`) are the user's choice. Documentation that bakes in `as stx`:

- forces every reader to either match your alias or mentally rename in every example;
- breaks copy-paste into a notebook that already has `stx` defined as something else;
- couples the brand to a one-letter prefix that competes with NumPy's `np` for prime mental real estate.

Write `import scitex` in skills and READMEs. If a user wants `stx`, they alias once and read your docs unchanged.

## When to use which path

| Project shape                              | Recommended install     |
|--------------------------------------------|-------------------------|
| Leaf research project using only `scitex.io` | `pip install scitex-io` (standalone) |
| Research project using 5+ scitex modules    | `pip install scitex` (umbrella)      |
| Library packaged for distribution           | depend on standalones only (avoid umbrella as transitive dep) |
| Notebook tutorials / teaching material      | umbrella (one install, full surface) |

## See also

- [01_ecosystem/05_re-export.md](../../01_ecosystem/05_re-export.md) — the umbrella's re-export mechanism (`_LazyModule`)
- [04_lazy-imports-and-optional-deps.md](04_lazy-imports-and-optional-deps.md) — the per-standalone optional-dep pattern
