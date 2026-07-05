---
description: |
  [TOPIC] Interface Python Api Version
  [DETAILS] The canonical `__version__` block — `importlib.metadata.version()` with `PackageNotFoundError` fallback to `0.0.0+local`. Works for both wheel installs and editable installs. Why custom pyproject.toml parsing breaks.
tags: [scitex-general-interface-python-api-version-strategy]
---

# Version Strategy

## The canonical block

Every package's `__init__.py` carries this exact block (adjust the dist name):

```python
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("scitex-io")     # PyPI dist name, with hyphens
except PackageNotFoundError:
    __version__ = "0.0.0+local"
```

And `"__version__"` appears in `__all__`.

## Why `importlib.metadata.version()`

- **Works for wheel installs.** `pip install scitex-io` writes `scitex_io-X.Y.Z.dist-info/METADATA`; `importlib.metadata` reads it.
- **Works for editable installs.** `pip install -e .` writes a `.dist-info/` directory beside the source; same lookup succeeds.
- **PEP 566 / PEP 621 standard.** Stable across CPython 3.8+ (3.9 standard library).
- **No file I/O at import time** beyond what `pip` already cached.

## Why NOT custom `pyproject.toml` parsing

```python
# ❌ Anti-pattern — breaks for wheel installs
def _get_version() -> str:
    here = Path(__file__).parent
    pyproject = here.parent.parent / "pyproject.toml"   # may not exist
    if pyproject.exists():
        return tomllib.loads(pyproject.read_text())["project"]["version"]
    return "unknown"
```

Failure mode: wheels do not ship `pyproject.toml`. The file only exists in source checkouts and editable installs. End users with `pip install scitex-cloud` get `"unknown"` forever.

This pattern currently exists in **scitex-cloud** — drift to fix (tracked in [TODO.md](TODO.md)).

## Fallback string convention

`"0.0.0+local"` — the `+local` segment is a PEP 440 "local version identifier". Tools that compare versions treat it as "newer than 0.0.0 but not a real release". It signals "running from source, no metadata installed" without breaking version comparisons.

Avoid `"unknown"` (not PEP 440 compliant; breaks `pkg_resources.parse_version`) and `"0.0.0"` (looks like a real release).

## Distribution name vs import name

`version()` takes the **PyPI distribution name** (with hyphens), not the Python import name (with underscores):

| Distribution name (`version("...")`) | Import name              |
|--------------------------------------|--------------------------|
| `scitex-io`                          | `scitex_io`              |
| `scitex-stats`                       | `scitex_stats`           |
| `scitex` (umbrella)                  | `scitex`                 |
| `figrecipe`                          | `figrecipe`              |

If you pass the import name, `version("scitex_io")` may still work (case-insensitive normalization), but PEP 503 mandates the distribution name — use it.

## Audit

```bash
python -c "import scitex_io; print(scitex_io.__version__)"
# Expected: real semver from PyPI, OR "0.0.0+local" from editable/source.
# Failure: "unknown", AttributeError, or anything else.
```

Linter rule (planned): **PA-006** — flag any `_get_version()` function or non-`importlib.metadata` version source.
