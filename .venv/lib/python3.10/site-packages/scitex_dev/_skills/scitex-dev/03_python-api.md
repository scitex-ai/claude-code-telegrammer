---
description: |
  [TOPIC] Python API
  [DETAILS] Public surface of `scitex_dev` — versions, ecosystem, rename, docs/search, Result types — with pointers to per-topic deep-dive leaves.
tags: [scitex-dev-python-api]
---

# Python API

`scitex-dev` is primarily a CLI, but every operation is also callable from
Python. Import as:

```python
import scitex_dev as dev
```

## Versions and ecosystem

| Callable | Purpose | Deep dive |
|---|---|---|
| `dev.list_versions()` | All ecosystem packages with installed/PyPI versions | [13_versions.md](13_versions.md) |
| `dev.check_versions()` | Drift report (mismatches between dev / installed / PyPI) | [13_versions.md](13_versions.md) |
| `dev.fix_mismatches(confirm=False)` | Repair version drift | [13_versions.md](13_versions.md) |
| `dev.ECOSYSTEM` | Frozen package registry (`PackageConfig` records) | [14_ecosystem.md](14_ecosystem.md) |
| `dev.sync_local()` / `dev.sync_host(...)` | Editable / SSH sync | [14_ecosystem.md](14_ecosystem.md) |

## Bulk rename

| Callable | Purpose |
|---|---|
| `dev.preview_rename(pattern, replacement, directory)` | Dry-run preview |
| `dev.execute_rename(...)` | Apply (with git-safety guards) |

See [15_rename.md](15_rename.md).

## Documentation

| Callable | Purpose |
|---|---|
| `dev.get_docs(package)` | Aggregated docs for a package |
| `dev.search_docs(query)` | Cross-package full-text search |
| `dev.build_docs()` | (Re)build the local docs cache |

See [16_docs-search.md](16_docs-search.md).

## Result envelope

All return-as-rich functions emit a `Result` with `ErrorCode`, payload,
and optional `SideEffect` records. See [10_result-types.md](10_result-types.md).

## Configuration

`DevConfig`, `HostConfig`, `PackageConfig`, `PyPIAccount` plus loader
helpers — see [12_config.md](12_config.md). Environment overrides:
[20_env-vars.md](20_env-vars.md).

## Discoverability

```bash
scitex-dev list-python-apis              # tree of public callables
python -c "import scitex_dev; help(scitex_dev)"
```
