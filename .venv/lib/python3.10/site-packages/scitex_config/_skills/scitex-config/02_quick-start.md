---
description: |
  [TOPIC] Quick start
  [DETAILS] Smallest useful example — the direct → yaml → env → default cascade with PriorityConfig.resolve().
tags: [scitex-config-quick-start]
---

# Quick Start

## The cascade

```python
from scitex_config import PriorityConfig

pc = PriorityConfig(yaml_path="config/app.yaml")

# Resolves in order: cli_arg → yaml["database"]["url"] → $DATABASE_URL → fallback
db_url = pc.resolve(
    direct=cli_arg,                  # highest precedence
    key="database.url",              # yaml lookup (dot-notation)
    env_var="DATABASE_URL",          # env override
    default="sqlite:///dev.db",      # last resort
)
```

## Default config + paths

```python
from scitex_config import get_config, get_paths

config = get_config()                # loads ./config/*.yaml automatically
log_level = config.resolve("logging.level", default="INFO")

paths = get_paths()
print(paths.logs)                    # ~/.scitex/logs
print(paths.cache)                   # ~/.scitex/cache
```

For SciTeX-ecosystem packages, use the per-package state resolver:

```python
from scitex_config._ecosystem import local_state

log_path = local_state.runtime_path("hpc", "dispatch.log")
print(log_path)                      # ~/.scitex/hpc/runtime/dispatch.log
```

## Next

- [03_python-api.md](03_python-api.md) — full surface
- [SKILL.md](SKILL.md) — overview + ecosystem-internal `_ecosystem.local_state`
