---
description: |
  [TOPIC] Interface Http Api Audit Checklist
  [DETAILS] Release-gate checklist for a package's HTTP API. Run before tagging a release. Mirrors the structure of CLI / MCP / Python-API audit checklists. (A) markers indicate items the planned `audit-http` linter will automate.
tags: [scitex-general-interface-http-api-audit-checklist]
---

# HTTP API Audit Checklist

Run before tagging a release of any package that ships an HTTP server. Tick each item or document the deviation in the PR.

`(A)` = planned automation in `scitex-dev ecosystem audit-http` (parallels `audit-cli`, `audit-mcp-tools`, `audit-api`).

## §1 — Need

- [ ] Package has a real reason for HTTP (one of the six in [01_overview.md](01_overview.md) — local relay, dashboard, REST API, real-time push, webhook, agent protocol).
- [ ] If the use case is "expose Python API to AI agents", MCP is preferred over HTTP.

## §2 — Framework

- [ ] (A) Framework is FastAPI (default), aiohttp (only if WebSocket required), or Starlette (only if forced by an SDK).
- [ ] No new code in Flask or stdlib `http.server`.
- [ ] Existing Flask / `http.server` code is tracked in [TODO.md](TODO.md) for migration.

## §3 — Endpoints

- [ ] (A) URLs are nouns (`/papers`, `/papers/{doi}`), not verbs.
- [ ] HTTP verbs match semantics (GET reads, POST creates, ...).
- [ ] (A) Request bodies and responses use Pydantic `BaseModel`.
- [ ] (A) `response_model=` declared on every non-trivial endpoint.
- [ ] REST endpoints under `/api/...`; dashboards under `/ui/...`; static under `/static/...`.
- [ ] `/docs` (Swagger UI) reachable; not disabled in production.

## §4 — Errors

- [ ] All error responses use the canonical `ErrorResponse` shape (error, code, detail, remediation, timestamp).
- [ ] HTTP status codes match semantics (404 for not-found, 409 for conflict, 503 for dep-down, ...).
- [ ] `ScitexError(code=...)` from the Python API maps to the right status via the global handler.
- [ ] Production has `DEBUG=False`; tracebacks not in response bodies.
- [ ] No file paths or library versions in error responses.

## §5 — Health and ops

- [ ] (A) `/health` exists, returns 200, sub-millisecond response time, no DB queries.
- [ ] `/ready` exists for services with dependencies; returns 503 on degradation.
- [ ] CORS configured explicitly (no `"*"` in production).
- [ ] Request logs include method, path, status, duration.
- [ ] `X-Request-ID` header set per response (when structured logging is enabled).
- [ ] Static assets have `Cache-Control` headers; API responses set `no-cache`.
- [ ] `/metrics` exposed for cloud-deployed services.

## §6 — Auth

- [ ] Production deployment documents nginx (or equivalent) reverse proxy.
- [ ] No hand-rolled auth check inside endpoints.
- [ ] Local dev mode uses `scitex_dev.http.require_token` middleware (once shipped).
- [ ] No tokens in URL query strings.
- [ ] Identity (when needed) injected via `X-Forwarded-User` header by the proxy.

## §7 — CLI integration

- [ ] (A) `<cli> http start` subcommand exists.
- [ ] Standard flags: `--host` (default `127.0.0.1`), `--port` (registered default), `--reload`, `--workers`, `--log-level`.
- [ ] (A) Default port is registered in [07_cli-integration.md](07_cli-integration.md) port table; no clash.
- [ ] (A) Importing the package does NOT start a server.
- [ ] `factory=True` pattern used so `--reload` works.
- [ ] Env vars use `SCITEX_<PKG>_HTTP_*` prefix.

## §8 — Documentation

- [ ] Package README documents both the local-dev (`<cli> http start`) and production (nginx + Docker) launch paths.
- [ ] OpenAPI `/docs` linked from README for public APIs.
- [ ] All env vars documented in the package's `NN_env-vars.md` skill leaf.

## §9 — Cross-interface parity

- [ ] Endpoints delegate to the Python API (no original logic in handlers).
- [ ] Shape consistency: HTTP, CLI, MCP all return the same data structure when calling the same underlying function.
- [ ] When the Python API gains a new feature, an HTTP endpoint surfaces it (or the omission is documented).

## §10 — Specialty (A2A)

- [ ] If the package implements A2A, it follows scitex-agent-container's pattern.
- [ ] If the package is *not* an agent host, it does NOT implement A2A.

## Drift fixes (this skill — open at last audit)

- [ ] **scitex-audio**: migrate `_http_server.py` from stdlib `http.server` to FastAPI.
- [ ] **scitex-dev**: migrate dashboard from Flask to FastAPI; new default port `5001`.
- [ ] **scitex-orochi**: migrate query-string `?token=` auth to either nginx-managed (production) or `Authorization: Bearer` via `scitex_dev.http.require_token` (local dev).
- [ ] (Other): see [TODO.md](TODO.md).
