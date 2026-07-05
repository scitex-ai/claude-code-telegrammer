---
description: |
  [TOPIC] Todo
  [DETAILS] HTTP API skill — open TODOs — see file body for details.
tags: [scitex-general-interface-http-api-TODO]
---

# HTTP API skill — open TODOs

Strike through (`~~item~~`) when done.

## Drift to fix in existing packages

- [ ] **scitex-audio**: migrate `~/proj/scitex-audio/src/scitex_audio/mcp_server.py` (the `run_relay_server` function) from stdlib `http.server` to FastAPI. Three endpoints (`/speak`, `/health`, `/list_backends`) — small rewrite. Add `/docs` for free.
- [ ] **scitex-dev**: migrate `~/proj/scitex-dev/src/scitex_dev/dashboard/app.py` from Flask to FastAPI. New default port `5001` (leave 5000 alone). Internal-only — low priority but fix when next touched.
- [ ] **scitex-orochi**: migrate query-string `?token=<...>` auth to:
  - Production: nginx with `auth_request` (matches scitex-cloud).
  - Local dev: `Authorization: Bearer <token>` via `scitex_dev.http.require_token` (once shipped).
- [ ] **scitex-orochi**: aiohttp → consider whether the dashboard API portion (the REST half, port 8559) could move to FastAPI alongside aiohttp serving the WebSocket half (port 9559). Two processes vs one — design Q.
- [ ] **scitex-cloud**: ensure all error responses use the canonical `ErrorResponse` shape (some endpoints currently return ad-hoc `{"error": ...}` dicts).

## Ship `scitex_dev.http` helpers

- [ ] **`scitex_dev.http.require_token`** — middleware that reads token from env var, generates + persists if missing, validates `Authorization: Bearer` header. Drop-in for FastAPI's `app.add_middleware()`.
- [ ] **`scitex_dev.http.install_error_handlers(app)`** — registers the `ScitexError` → `ErrorResponse` translator per [04_error-envelope.md](04_error-envelope.md). One call per FastAPI app.
- [ ] **`scitex_dev.http.health_endpoint`** — factory returning a `/health` route handler with the canonical shape (status, service name, version, timestamp).
- [ ] **`scitex_dev.http.standard_logging_middleware`** — request ID + structured log line per request.

These four helpers make the canonical pattern a 5-line setup in any new HTTP package.

## `audit-http` linter (companion to `audit-cli`, `audit-mcp-tools`, `audit-api`)

- [ ] **New command: `scitex-dev quality audit-http <distribution>`** — parallels `audit-api`. Static + behavioral checks against §1–§10 in [09_audit-checklist.md](09_audit-checklist.md).

  Static checks:
  - Detect framework (`fastapi`, `aiohttp`, `flask`, `http.server`) → flag non-canonical.
  - Parse FastAPI app for endpoints; check Pydantic `response_model=` declared.
  - Detect URL paths starting with verbs (`/createPaper`) → flag.
  - Look for `app.run()` / `uvicorn.run()` at module level (server starts on import) → flag.

  Behavioral checks (with the server temporarily started):
  - Hit `/health` → expect 200, JSON shape.
  - Hit `/docs` → expect 200, OpenAPI HTML.
  - Hit a deliberately malformed request → expect `ErrorResponse` shape.

  Rule numbering: **`H<§><idx>`** — `H101` (need), `H201` (framework), `H301` (noun URLs), etc. Mirrors `PA<§><idx>`.

## Reference example

- [ ] Auto-generate a reference shape file showing the canonical FastAPI app layout (parallels CLI's `16_example.md`). Source candidate: `scitex_cloud.deployment.docker.crossref_local.server` (current best example with Pydantic + auto-OpenAPI + ErrorResponse).

## Open design questions

- [ ] **Port table maintenance**: is the table in [07_cli-integration.md](07_cli-integration.md) the source of truth, or should it live in a YAML the linter can read? Lean toward YAML once a third package needs HTTP.
- [ ] **Multi-process packages** (orochi: HTTP + WebSocket): do we recommend one uvicorn worker doing both via FastAPI, or two processes (FastAPI + aiohttp)? The latter is what orochi has; the former is simpler. Survey says: depends on traffic shape — defer until a third multi-protocol package appears.
- [ ] **Versioning**: should REST endpoints be path-versioned (`/v1/papers`) from day one, or unversioned with the assumption that breaking changes get a new endpoint? Current packages are inconsistent.
- [ ] **WebSocket auth**: nginx `auth_request` doesn't naturally cover WebSocket upgrades. Pattern for orochi-style WS auth needs a leaf in the future.

## Documentation

- [x] Split monolithic `03_interface/05_http-api.md` into per-section files (this directory).
- [x] Remove the legacy `03_interface/05_http-api.md` flat file. Parent `general/SKILL.md` now points at `03_interface/05_http-api/SKILL.md`.
