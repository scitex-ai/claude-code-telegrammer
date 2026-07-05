---
name: scitex-config
description: |
  [WHAT] Configuration primitives — `PriorityConfig` (direct → yaml → env → default cascade), `ScitexConfig`/`get_config` (YAML config), `ScitexPaths`/`get_paths` ($SCITEX_DIR path manager), and ecosystem-internal `_ecosystem.local_state` (project-scope-aware path resolver).
  [WHEN] Reading any tunable, resolving runtime/cache/log directories, or honoring project-level config overrides in a SciTeX package.
  [HOW] `from scitex_config import PriorityConfig, get_config, get_paths` — call `.resolve(direct=..., key=..., env_var=..., default=...)` for the cascade.
tags: [scitex-config]
primary_interface: python
interfaces:
  python: 3
  cli: 0
  mcp: 0
  skills: 2
  http: 0
---

# scitex-config

Layered configuration + path management for the SciTeX ecosystem.

- **Public** (`scitex_config.*`) — convention-free primitives usable by any project.
- **Ecosystem-internal** (`scitex_config._ecosystem.*`) — embeds SciTeX conventions; for scitex-* package authors only.

## Sub-skills

- [01_installation.md](01_installation.md) — pip install + verify
- [02_quick-start.md](02_quick-start.md) — direct → yaml → env → default cascade
- [03_python-api.md](03_python-api.md) — full public surface

## Public API

```python
from scitex_config import PriorityConfig, get_config, get_paths

# direct → yaml → env → default cascade
pc = PriorityConfig(yaml_path="config/app.yaml")
db = pc.resolve(direct=cli_arg, key="database.url",
                env_var="DATABASE_URL", default="sqlite:///dev.db")

# Same cascade for nested keys via the config object.
config = get_config()
log_level = config.resolve("logging.level", default="INFO")

# `$SCITEX_DIR` path manager.
p = get_paths()
print(p.logs, p.cache)                     # ~/.scitex/logs, ~/.scitex/cache
cache_dir = p.resolve("cache", user_supplied)
```

Utilities: `load_dotenv()`, `load_yaml(path)`, `get_scitex_dir()`.

## Ecosystem-internal API (`_ecosystem`)

```python
from scitex_config._ecosystem import local_state

# Project-scope-aware: walks up to .git/, falls back to $SCITEX_DIR/<pkg-short>/.
state_path = local_state.path("dataset", "datasets.db")
runtime = local_state.runtime_path("orochi", "shim-yamls")
user_dir = local_state.user_path("core", "logs")
```

`pkg-short` strips the `scitex-` prefix (`scitex-dataset` → `dataset`).
**Not stable** — may change without a major bump; for scitex-* authors only.

## When to use

- ✅ Reading any tunable (CLI flag, yaml, env, default) — use the cascade
- ✅ Writing runtime state (cache / logs / sessions)
- ✅ Resolving the user's `$SCITEX_DIR`
- ❌ Per-call ephemeral options — overkill

## Pitfalls

- **Importing `_ecosystem` from non-scitex code** — internal surface.
- **Hardcoding `~/.cache/scitex-<pkg>/`** — bypasses `$SCITEX_DIR` and
  project-scope override. Use `local_state.path()` or `get_paths()`.
- **`os.environ.get(...) or default`** — loses yaml + project-config layers.

## See also

- General `01_ecosystem/06_local-state-directories.md` — runtime path policy
- General `01_ecosystem/04_environment-variables.md` — `SCITEX_*` taxonomy
- Failure playbook `09_quality/01_failure-playbook.md` §8–§9
