---
description: |
  [TOPIC] Python API
  [DETAILS] Public callables — PriorityConfig, get_config, get_paths, load_dotenv, load_yaml, get_scitex_dir.
tags: [scitex-config-python-api]
---

# Python API

## Imports

```python
from scitex_config import (
    PriorityConfig,
    get_config,
    get_paths,
    load_dotenv,
    load_yaml,
    get_scitex_dir,
)
```

## `PriorityConfig`

The cascade primitive. Resolves a value from `direct → yaml[key] → env → default`.

```python
pc = PriorityConfig(yaml_path="config/app.yaml")
value = pc.resolve(
    direct=cli_arg,         # explicit override (e.g., from --flag)
    key="section.subkey",   # YAML lookup (dot-notation)
    env_var="MY_VAR",       # env-var fallback
    default=None,           # final fallback
)
```

## `get_config() → ScitexConfig`

Process-wide cached config. Auto-discovers `./config/*.yaml`. The returned
object exposes `.resolve(key, default)` for the same cascade.

## `get_paths() → ScitexPaths`

`$SCITEX_DIR`-aware path manager. Properties: `.logs`, `.cache`, `.capture`,
`.screenshots`, `.scholar`, `.writer`, and more. Method
`.resolve(category, user_supplied)` returns the default or a user-supplied path.

For per-package state resolution (SciTeX-ecosystem packages), use
`from scitex_config._ecosystem import local_state` — see SKILL.md.

## Utilities

| Callable | Purpose |
|---|---|
| `load_dotenv()` | Read `.env` into `os.environ` |
| `load_yaml(path)` | Parse a YAML file (dict result) |
| `get_scitex_dir()` | Resolve `$SCITEX_DIR` (default `~/.scitex/`) |

## Ecosystem-internal (`_ecosystem`)

`from scitex_config._ecosystem import local_state` — project-scope-aware path
helpers for scitex-* package authors only. **Not stable.** See SKILL.md.
