---
description: |
  [TOPIC] Crash Early, Crash Loud — the ecosystem's default failure posture
  [DETAILS] The principle that precedes the §98 failure playbook and §99 checklist. Every `scitex-*` package validates at the boundary and raises the instant an invariant breaks (early), with a specific, actionable, context-bearing error (loud). No silent fallbacks, no swallowed exceptions, no degraded-result-that-looks-like-success. Distinguishes a *legitimate explicit guard* (return False for a type check when an optional dep is absent) from a *silent failure* (except: pass).
tags: [scitex-general-quality-crash-early-crash-loud]
version: 0.11.22.dev12+gab85d0591.d20260522
exported_via: installed
---

# Crash Early, Crash Loud

The default failure posture for all ecosystem `src/` code. The §98
playbook is the cookbook of what goes wrong; this leaf is the
principle that keeps those failures *visible at their source* instead
of leaking into downstream repos as wrong answers.

## The two halves

**Crash early** — validate at the boundary, raise before doing work.
A function that receives a bad argument fails on entry, not 200 lines
later inside a numpy reduction. Missing required config is a hard
error at load time, not a `None` that detonates in a consumer package.

**Crash loud** — the exception names what failed, where, and the
offending value, and it *propagates*. Never `except: pass`, never
catch-and-`print`, never catch-and-return-a-default. If you catch,
re-raise with context (`raise ConfigError(...) from e`).

> Not working must be *not working*. A green-looking degraded result
> is worse than a red one — it survives CI and surfaces as a bug in a
> downstream package's release.

## The crucial distinction: explicit guard vs silent failure

These look superficially similar; only one is allowed.

**Allowed — explicit, intentional guard** (optional dep absent →
documented behavior, see §98.5a):
```python
def _is_plotly_figure(obj) -> bool:
    if plotly is None:        # explicit: "no plotly → not a plotly figure"
        return False
    return isinstance(obj, plotly.graph_objs.Figure)
```
The return value is a *correct answer*, not a masked error.

**Forbidden — silent failure masquerading as success:**
```python
def load_dataset(path):
    try:
        return _read(path)
    except Exception:
        return pd.DataFrame()   # caller can't tell empty-from-error
```

## Ecosystem hooks that enforce this
- Optional imports go through `scitex_dev.try_import_optional` — install
  hints + error formatting in one place; never a bare `try/except
  ImportError` that swallows the cause.
- The `Install Test (fresh venv)` CI job and `audit_ecosystem.py`
  (§98.8/§98.9) exist precisely because a silent fallback in `src/`
  passes the dev-env Test job and only breaks for real consumers.
- The PostToolUse CI watcher (§98.10) turns a quiet downstream failure
  into a loud `WARN CI FAILURE` the agent must stop on.

When in doubt, **crash**. A loud crash at the source points straight at
the bug; a quiet fallback ships a plausible wrong answer.
