---
description: |
  [TOPIC] Ecosystem Modules And Standalone Packages
  [DETAILS] How to decide whether a `scitex.<module>` should stay a submodule of scitex-python or split out as a standalone `scitex-<name>` package — decision rule (zero scitex deps + heavy standalone value → standalone; everything else → module), distinct `_skills/` directories and re-export bridges, lessons from splitting scitex-scholar/scitex-browser out of the scitex monolith (path-injection beats path-coupling, never hardcode `~/.scitex/<pkg>/`, always via `PathManager`, record failure outcomes in metadata), and when to merge a standalone back. Use when starting a new scitex-* repo or evaluating a submodule for extraction.
tags: [scitex-general-ecosystem-modules-and-standalone-packages]
---

# SciTeX Standalonization Lessons

Lessons from the April 2026 scitex-scholar + scitex-browser decoupling.

## 1. Audit reverse-direction imports

When splitting a child package out of the monolith, the obvious direction
(monolith → child) is usually clean. The danger is the **reverse**: the
child's standalone repo still has `from scitex.parent.x import Y` or even
`from scitex_child` inside the *parent* repo. Both make the decoupling
a lie — the child doesn't stand alone.

```bash
# From the child repo:
grep -rn "from scitex[._ ]" src --include="*.py" | grep -v "scitex_child"

# From the parent / sibling repos:
grep -rn "scitex_child" src --include="*.py"
```

Both directions must be clean before claiming loose coupling. Add a
regression test in the child's test suite that reads its own source and
asserts the parent's namespace does not appear.

## 2. `try: from .x import Y\nexcept ImportError: Y = None` is almost always wrong

Either `x` is a required dep — make it a direct import and let the
failure propagate; or `x` is a genuine optional extra — declare it in
`[project.optional-dependencies]` and use a clear gate:

```python
try:
    import scitex_clew as _clew
except ImportError:
    _clew = None
if _clew is not None:
    _clew.hash_file(path)   # real use, real failure surface
```

Silent `X = None` downgrades produce confusing `AttributeError` at
call-time and hide dep problems.

## 3. `scitex[session]` is the minimal monolith dep

`@stx.session` lives in `scitex-python` itself (not `scitex-core`). If a
standalone package only needs the session decorator, depend on
`"scitex[session]>=2.0.0"` — not `"scitex>=2.0.0"`. Same pattern for
`scitex[sh]`, `scitex[social]`, etc. See
`~/proj/scitex-python/pyproject.toml` for the canonical extras list.

## 4. `scitex-logging` is its own package — prefer direct

```python
# NO  — pulls the monolith transitively:
from scitex.logging import getLogger
from scitex import logging

# YES — standalone:
from scitex_logging import getLogger
import scitex_logging as logging
```

`scitex-logging` is the **ecosystem-wide errors-and-logging tier** — it owns
both `getLogger` and the canonical typed exceptions every SciTeX package
raises (`SciTeXError`, `IOError`, `SaveError`, `LoadError`, `PathError`,
`ConfigurationError`, `AuthenticationError`, `ScholarError`, `ModelError`,
`PlottingError`, …). The `Scholar*` / `BibTeX*` / `PDF*` names are
scholar-domain *types* hosted in the central errors module; that's
intentional so any package can `raise ScholarError("...")` without
depending on `scitex-scholar`. Zero heavy deps.

## 5. Path injection beats path coupling

Child packages should not import the parent's config to find their own
cache/data dirs. Inject the path as a constructor arg:

```python
# scitex-browser BEFORE (reaches into scitex-scholar):
class ChromeProfileManager:
    def __init__(self, profile_name, config=None):
        self.config = config or ScholarConfig()           # bad
        self.profile_dir = self.config.get_cache_chrome_dir(profile_name)

# AFTER (pure path injection):
class ChromeProfileManager:
    def __init__(self, profile_name, chrome_cache_dir=None):
        self.profile_dir = Path(chrome_cache_dir or _DEFAULT) / profile_name
```

Callers in the upstream package pass the resolved path explicitly. A
back-compat duck-typed `config` kwarg can bridge the transition without
reintroducing the import.

## 6. Local-state root — always via `PathManager`

Every package writes into exactly one subdirectory at each scope: `<project>/.scitex/<pkg-short>/` (project, wins) and `~/.scitex/<pkg-short>/` (user, fallback). Prefix-stripping: `scitex-scholar` → `scholar`. Full rules — filename conventions, forbidden locations, `SCITEX_DIR` relocation, migration — live in `01_ecosystem/06_dot_scitex_directory.md`.

Inside the package, never hardcode the absolute path — resolve through `PathManager`:

```python
# NO
screenshot_dir = Path.home() / ".scitex/scholar/workspace/screenshots"

# YES
screenshot_dir = (
    ScholarConfig().path_manager.get_cache_engine_dir() / "workspace" / "screenshots"
)
```

Hardcoded paths break when users set `SCITEX_DIR` or switch between project and user scope.

## 7. Scholar-specific extraction lessons — moved out

Five lessons from the scitex-scholar / scitex-browser extraction (failure-outcome metadata, artifact-count truthfulness, single-worker per publisher, Xvfb timeout handling, OpenAthens redirect semantics) were originally in this skill but are scholar-implementation lore, not general arch rules. They now live in:

- [`scitex-scholar/src/scitex_scholar/_skills/scitex-scholar/30_extraction-lessons.md`](../../../../scitex-scholar/src/scitex_scholar/_skills/scitex-scholar/30_extraction-lessons.md)

Read those if you're touching the scholar download / auth pipeline.

## 8. Every module MUST have an extra listing its standalone package

**Rule.** For every canonical ecosystem package `scitex-<name>` listed in
`scitex dev ecosystem list --json`, the umbrella's `pyproject.toml` MUST
define an extra where the standalone package itself appears:

```toml
[project.optional-dependencies]
<name> = ["scitex-<name>"]            # minimum
# or, if the in-umbrella shim needs base python deps too:
path    = ["scitex-path", "GitPython", "matplotlib"]
```

**Why.** A bare `pip install scitex` gives a thin umbrella with shim
modules. `pip install scitex[<name>]` must actually install
`scitex-<name>` — otherwise `stx.<name>.foo()` silently falls back to the
in-umbrella shim instead of the real standalone package. Observed failure
(2026-04-24 audit): `path = ["GitPython", "matplotlib"]` ships GitPython
but NOT `scitex-path`, so `stx.path.find_git_root()` runs the umbrella
shim — a confusingly different codepath from the standalone.

**TypeScript-only modules (e.g. `ui`).** Two acceptable patterns:

1. The extra still declares the pypi package so the Python re-export path
   resolves: `ui = ["scitex-ui"]`.
2. The extra is intentionally empty AND the umbrella shim raises a clear
   `ImportError` pointing the user at the standalone TS/JS project.
   Silent `None` re-exports are NOT acceptable (see §2).

**`[all]` extra.** Must transitively install every canonical package.
Easiest: `all = [<every scitex-* pinned>]`. A package missing from both
its named extra and `[all]` is invisible to users — treat as a bug.

**Probe.** See `09_quality/02_checklist.md` §14.

## 9. Dead tests at collection break CI

After splitting a package, `pytest` collects ALL test files — including
ones that import modules that were removed. They fail at collection,
not at assertion, so they pollute failure counts. Delete or move them;
don't leave them hoping someone re-adds the module.

## Quick Checklist (modules vs standalone packages)

- [ ] Reverse-direction imports clean: child repo has no `from scitex.<parent>` and parent repo has no `from scitex_<child>` outside the umbrella bridge.
- [ ] No silent `try: import X\nexcept ImportError: X = None` downgrades — either declare the dep or guard at call site with a clear error message.
- [ ] If only `@stx.session` is needed, dep is `scitex[session]` — not the full `scitex`.
- [ ] All ecosystem-wide errors come from `scitex_logging` (not `scitex.logging` from the monolith).
- [ ] Path injection: child packages take cache/data dirs as constructor args; never reach into a parent's `Config` for them.
- [ ] All local-state paths resolve through `PathManager`; no hardcoded `Path.home() / ".scitex/..."`.
- [ ] Every canonical `scitex-<name>` listed by `scitex-dev ecosystem list` has a matching umbrella extra that installs the standalone (`[<name>] = ["scitex-<name>"]`).
- [ ] `[all]` extra transitively installs every canonical package.
- [ ] After a split, dead test files that import removed modules are deleted — `pytest` collects clean.
