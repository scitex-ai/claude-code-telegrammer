---
description: |
  [TOPIC] Interface Http Api Cli Integration
  [DETAILS] Every package shipping HTTP exposes `<cli> http start` as the canonical launch command. Standard flags (`--host`, `--port`, `--reload`). Port conventions (avoid stdlib defaults). Env-var prefix `SCITEX_<PKG>_HTTP_*`. Don't auto-start servers as a side-effect of import.
tags: [scitex-general-interface-http-api-cli-integration]
---

# CLI Integration

## The launch command — `<cli> http start`

Following the noun-verb CLI convention, every package with an HTTP API exposes its server under the `http` noun:

```bash
scitex-cloud http start              # starts the FastAPI server
scitex-cloud http start --reload     # dev mode — auto-reload on code change
scitex-cloud http start --port 9000  # override port
scitex-cloud http stop               # graceful shutdown (if package manages a daemon)
scitex-cloud http status             # is it running? where?
```

The `http` noun parallels `mcp` (`<cli> mcp start`, `<cli> mcp doctor`). Operators learn one mental model.

## Standard flags

| Flag | Default | Notes |
|---|---|---|
| `--host` | `127.0.0.1` | Default to localhost only. `0.0.0.0` is opt-in (and prints a warning since it's network-exposed). |
| `--port` | per-package, see table below | Avoid stdlib / well-known defaults |
| `--reload` | off | Dev only. Watches source, restarts on change. |
| `--workers` | 1 | uvicorn workers for production. Set via `--workers 4` or env. |
| `--log-level` | `info` | `debug` / `info` / `warning` / `error` |

## Port conventions

Avoid clashing with anything well-known. Each scitex package picks a stable default port:

| Package | Port | Notes |
|---|---|---|
| scitex-cloud crossref-local | 8001 | |
| scitex-cloud citation-graph | 8002 | |
| scitex-orochi HTTP dashboard | 8559 | (existing) |
| scitex-orochi WebSocket | 9559 | (existing) |
| scitex-audio relay | 31293 | (existing — high port; intentional, avoids conflicts) |
| scitex-dev dashboard | 5001 | (Flask currently on 5000 — drift to fix; new default leaves 5000 alone) |
| scitex-agent-container A2A | 9999 | (per-agent override via YAML) |

When adding a new package, **register its port here first.** Avoid 80, 443, 3000 (Node default), 5000 (Flask default), 8000 (Django default), 8080 (common), 8888 (Jupyter).

## Env-var prefix

Per the ecosystem env-var convention (`01_ecosystem/04_environment-variables.md`), HTTP-related vars use `SCITEX_<PKG>_HTTP_*`:

```bash
SCITEX_CLOUD_HTTP_HOST=0.0.0.0
SCITEX_CLOUD_HTTP_PORT=8001
SCITEX_CLOUD_HTTP_TOKEN=...           # for local dev mode (require_token middleware)
SCITEX_CLOUD_HTTP_DEBUG=0             # 0 (default) — never leaks tracebacks
SCITEX_CLOUD_HTTP_ORIGINS=https://scitex.ai   # CORS allow-list
```

Document them in the package's `NN_env-vars.md` skill leaf alongside the rest of the package's env vars.

## Don't auto-start servers as an import side-effect

```python
# ❌ Anti-pattern
# in scitex_audio/__init__.py
from ._http_server import app
import uvicorn
uvicorn.run(app)   # ← starts a server when anyone does `import scitex_audio`!
```

Importing a package must never start a server. The CLI subcommand is the only entry point.

The Python API surface should expose the FastAPI `app` object as a *factory*, not a started server:

```python
# ✅ Canonical
# in scitex_audio/_http_server.py
def make_app() -> "FastAPI":
    from fastapi import FastAPI
    app = FastAPI(...)
    # routes, middleware, etc.
    return app

# CLI subcommand — only this starts uvicorn:
def cli_http_start(host: str, port: int, reload: bool):
    import uvicorn
    uvicorn.run("scitex_audio._http_server:make_app", host=host, port=port, reload=reload, factory=True)
```

The `factory=True` flag tells uvicorn to call `make_app()` each time it spawns a worker — supports `--reload` correctly and keeps imports cheap.

## Production deployment

For production, the CLI launches uvicorn with the right flags:

```bash
scitex-cloud http start --host 0.0.0.0 --port 8001 --workers 4 --log-level info
```

Or use Docker (scitex-cloud's pattern):

```dockerfile
ENTRYPOINT ["scitex-cloud", "http", "start", "--host", "0.0.0.0", "--port", "8001"]
```

Document the recommended Docker invocation in the package README.

## Multi-server packages (orochi)

When a package serves both HTTP and WebSocket on different ports (orochi: 8559 + 9559), `<cli> http start` brings up *both* by default:

```bash
scitex-orochi http start            # starts HTTP (8559) + WebSocket (9559)
scitex-orochi http start --no-ws    # HTTP only
scitex-orochi http start --no-http  # WebSocket only (rare)
```

Document the multi-process behaviour in the package's CLI help and README.

## `<cli> http status` and `<cli> http stop`

Optional but recommended for daemonized servers:

```bash
scitex-orochi http status
# → running
#   pid: 12345
#   host: 127.0.0.1
#   port: 8559
#   uptime: 3h 12m

scitex-orochi http stop
# → SIGTERM sent; waiting up to 10s
#   stopped (clean)
```

Implementation: write the PID to `~/.scitex/<pkg>/http.pid` on start; `status` reads it; `stop` sends `SIGTERM` then `SIGKILL` after a grace period.

## Audit

- `<cli> http start` exists.
- Standard flags (`--host`, `--port`, `--reload`) implemented.
- Default port is registered in the table above (no clashes).
- Env vars use `SCITEX_<PKG>_HTTP_*` prefix.
- Importing the package does NOT start a server.
- `factory=True` pattern used so `--reload` works.

## See also

- [03_interface/02_cli/](../02_cli/) — the noun-verb CLI convention this builds on.
- [01_ecosystem/04_environment-variables.md](../../01_ecosystem/04_environment-variables.md) — env-var prefix rule.
