---
description: |
  [TOPIC] Interface Http Api Overview
  [DETAILS] When a SciTeX package warrants an HTTP API, the delegation rule (no original logic — endpoints wrap Python API), and the three transport shapes (REST, WebSocket, specialty protocols). Most packages do not need this interface.
tags: [scitex-general-interface-http-api-overview]
---

# Overview

## When to add an HTTP API

Add one only when you have a real reason. Real reasons (in roughly increasing weight):

1. **Local-machine relay** — you need a process to be reachable from another process on the same machine, and IPC / Unix sockets are inconvenient. (scitex-audio: TTS relay listening on `localhost:31293`.)
2. **Internal dashboard** — a small web UI for ops/debugging that team members open in a browser. (scitex-dev's version dashboard.)
3. **Web-accessible REST API** — external clients (frontends, other services, CI) need to read or write data. (scitex-cloud's crossref-local, citation-graph.)
4. **Real-time push** — clients need updates the moment something changes; request/response isn't enough. (scitex-orochi's agent chat.)
5. **Inbound webhooks** — a third party (Telegram, Slack, Stripe) needs to POST to a URL you own. (scitex-orochi's `/webhook/telegram`.)
6. **Specialty agent protocols** — your package is an agent and other agents must talk to it. (scitex-agent-container's A2A.)

If none of those fit, **don't** add an HTTP server. Python API + CLI + MCP cover most use cases. Adding HTTP increases attack surface, deployment complexity, and skill cost.

## The delegation rule

**HTTP endpoints contain no original logic.** They are thin adapters that:

1. Parse the incoming request (path, query, body) into Python types.
2. Call the package's Python API.
3. Serialize the return value to JSON.

```python
# ✅ Canonical — endpoint wraps Python API
@app.post("/save")
def save_endpoint(req: SaveRequest) -> SaveResponse:
    path = scitex_io.save(req.obj, req.path, dry_run=req.dry_run)
    return SaveResponse(path=str(path))

# ❌ Anti-pattern — endpoint reimplements logic
@app.post("/save")
def save_endpoint(req: SaveRequest) -> SaveResponse:
    if not Path(req.path).parent.exists():
        Path(req.path).parent.mkdir(parents=True)
    if isinstance(req.obj, dict):
        with open(req.path, "w") as f:
            json.dump(req.obj, f)
    # ← reimplementing save() inside the endpoint
```

Reasons:

- **One source of truth** — bug fixes and improvements in the Python API automatically reach HTTP, CLI, and MCP without a sync pass.
- **Testability** — Python API has unit tests; HTTP integration tests then only cover the adapter layer (~10% of code) instead of the full feature.
- **Consistency** — CLI, MCP, and HTTP return the same shape because they all call the same function.

This rule is identical to the one for CLI and MCP. It's **the** structural principle of the five-interface design.

## Three transport shapes

Different problems need different network shapes. Pick the one that matches:

| Shape | What it is | When to use | Framework recommendation |
|---|---|---|---|
| **REST** | Request/response over HTTP. Client asks, server replies. Stateless. | Almost everything — the default. | **FastAPI** ⭐ |
| **WebSocket** | Long-lived two-way connection. Server can push messages to client at any time. | Live chat, live dashboards, agent streams. | **aiohttp** (or FastAPI's WebSocket support if endpoints are mostly REST with a few live channels) |
| **Specialty (A2A, gRPC, …)** | Protocol-specific shape on top of HTTP. Often imposed by an external spec. | Only when an external SDK requires it (A2A → Starlette). | Whatever the SDK forces |

A package can mix shapes — orochi serves both REST endpoints and WebSocket channels from the same aiohttp process. Most packages won't need to.

## See also

- [02_framework-choice.md](02_framework-choice.md) — concrete framework selection
- [03_interface/00_overview.md](../00_overview.md) — the five-interface delegation chain
