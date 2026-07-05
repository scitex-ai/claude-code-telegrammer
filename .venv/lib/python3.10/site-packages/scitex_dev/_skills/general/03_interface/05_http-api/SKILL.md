---
description: |
  [TOPIC] Interface Http Api
  [DETAILS] Optional HTTP API interface for SciTeX packages — when to expose one, framework choice (FastAPI canonical for REST; aiohttp when WebSocket is genuinely needed; Starlette only when an SDK forces it), REST endpoint conventions, JSON error envelope, `/health` and observability, auth posture (canonical: nginx reverse proxy in front; helper middleware for dev), CLI integration, and the A2A specialty pattern for agent packages. Use when adding HTTP endpoints to a package, choosing a framework, or auditing an existing HTTP server against the ecosystem convention.
tags: [scitex-general-interface-http-api-index]
---

# HTTP API (Optional) — Index

Most SciTeX packages do **not** ship an HTTP API. This skill applies only when a package exposes web-accessible endpoints (REST, WebSocket, or specialty protocols like A2A).

## When this skill applies

You're touching one of these packages, or proposing a new HTTP server:

| Package | Today (drift to fix marked) | Use case |
|---|---|---|
| **scitex-cloud** (deployment containers) | FastAPI ✅ | Public REST APIs (crossref-local, citation-graph) |
| **scitex-orochi** | aiohttp ✅ (WebSocket required) | Real-time agent chat + dashboard |
| **scitex-audio** | stdlib `http.server` ⚠️ drift → migrate to FastAPI | Local TTS relay |
| **scitex-dev** | Flask ⚠️ drift → migrate to FastAPI | Internal version dashboard |
| **scitex-agent-container** | Starlette (forced by A2A SDK) ✅ | A2A agent protocol |

If your package isn't listed, you probably don't need this interface.

## Sections

1. [01_overview.md](01_overview.md) — when to use HTTP, delegation rule, the 3 transport shapes
2. [02_framework-choice.md](02_framework-choice.md) — FastAPI canonical / aiohttp / Starlette / discouraged options
3. [03_endpoint-conventions.md](03_endpoint-conventions.md) — REST routes, HTTP verbs, JSON shape, OpenAPI `/docs`
4. [04_error-envelope.md](04_error-envelope.md) — Pydantic ErrorResponse, HTTP status codes, `ErrorCode` integration
5. [05_health-and-ops.md](05_health-and-ops.md) — `/health`, CORS, caching, observability
6. [06_auth.md](06_auth.md) — nginx reverse proxy canonical; shared middleware for local dev
7. [07_cli-integration.md](07_cli-integration.md) — `<cli> http start` subcommand, port conventions, env vars
8. [08_a2a-pattern.md](08_a2a-pattern.md) — A2A specialty for agent packages (one-off, not generalizable)
9. [09_audit-checklist.md](09_audit-checklist.md) — release-gate checklist
10. [TODO.md](TODO.md) — drift fixes + planned `audit-http` linter
