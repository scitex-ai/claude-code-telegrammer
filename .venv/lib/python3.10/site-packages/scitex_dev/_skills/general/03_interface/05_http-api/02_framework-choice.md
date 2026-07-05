---
description: |
  [TOPIC] Interface Http Api Framework Choice
  [DETAILS] Framework selection rules — FastAPI canonical for REST APIs (auto-OpenAPI, Pydantic validation, async). aiohttp allowed only when WebSocket is genuinely needed. Starlette only when an SDK forces it. Flask and stdlib `http.server` are drift to migrate.
tags: [scitex-general-interface-http-api-framework-choice]
---

# Framework Choice

## Decision tree

```
Are you serving anything other than request/response?
├── YES (live updates, streaming, server-pushed messages)
│   └── Need WebSocket alongside HTTP?
│       ├── Heavy WS + light HTTP        → aiohttp
│       └── Heavy HTTP + occasional WS   → FastAPI (it has WebSocket support)
└── NO (everyone is REST)
    └── FastAPI ⭐ canonical
```

External constraint overrides the tree:

- **An SDK forces a specific framework** (e.g., A2A SDK requires Starlette) → use what it requires; document the exception in the package's README.
- **You are migrating an existing Flask or stdlib `http.server` app** → migrate to FastAPI when you next touch the code.

## FastAPI — the default

```python
from fastapi import FastAPI
from pydantic import BaseModel
from scitex_io import save, list_formats

app = FastAPI(title="scitex-io HTTP API", version=__version__)

class SaveRequest(BaseModel):
    path: str
    obj: dict
    dry_run: bool = False

class SaveResponse(BaseModel):
    path: str
    bytes_written: int

@app.get("/formats")
def get_formats() -> list[str]:
    return list_formats()

@app.post("/save")
def save_endpoint(req: SaveRequest) -> SaveResponse:
    p = save(req.obj, req.path, dry_run=req.dry_run)
    return SaveResponse(path=str(p), bytes_written=p.stat().st_size)
```

What you get for free:

- **Auto-generated OpenAPI** at `/docs` (Swagger UI) and `/redoc`. Click endpoints, fill in fields, send test requests in the browser.
- **Pydantic validation** — request bodies that don't match `SaveRequest` are rejected with a structured error before your code runs.
- **Type-hint synergy** — same `from __future__ import annotations`, `Literal`, `Optional` patterns the Python API skill mandates ([06_type-hints.md](../01_python-api/06_type-hints.md)). One vocabulary across both.
- **Modern async** — `async def` works natively. Critical for high-concurrency endpoints; harmless for sync ones.

Run with `uvicorn`:

```python
# in <pkg>/_http_server.py
def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port)
```

## aiohttp — only when WebSocket is needed

```python
from aiohttp import web

async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    async for msg in ws:
        await ws.send_str(f"echo: {msg.data}")
    return ws

app = web.Application()
app.router.add_get("/ws", handle_ws)
app.router.add_get("/api/status", handle_status)
web.run_app(app, host="0.0.0.0", port=8559)
```

When this earns its place:

- Real-time agent chat with sub-second push (orochi)
- Dashboard with live counters that update without polling
- Streaming output from long-running jobs (when MCP streaming isn't enough)

When it doesn't:

- "We might want WebSocket someday" — start with FastAPI; add WebSocket via FastAPI's `@app.websocket(...)` if it ever materializes.
- "We need real-time but only for one feature" — use FastAPI's WebSocket support. Don't switch frameworks for one route.

aiohttp lacks auto-OpenAPI; you write `/docs` by hand or skip it. That's an acceptable cost for genuine WS needs, **not** for plain REST.

## Starlette — only when an SDK forces it

scitex-agent-container uses Starlette because the A2A SDK is built on it. That's the only reason. Don't pick Starlette for a new package.

If you find yourself reaching for Starlette without an SDK constraint, you actually want FastAPI (which is built on Starlette and gives you everything Starlette does plus auto-docs).

## Discouraged: Flask, stdlib `http.server`

| Framework | Why discouraged | Migration path |
|---|---|---|
| **Flask** | Synchronous (slower under concurrency); no auto-OpenAPI; older API style; ecosystem moving to FastAPI | Migrate to FastAPI when next touched. scitex-dev's dashboard is the only current user. |
| **stdlib `http.server`** | Manual JSON serialization, no validation, no auto-docs, not production-grade. Each handler reinvents request parsing. | Migrate to FastAPI. scitex-audio's relay (~3 endpoints) is ~30 lines of FastAPI; not a big rewrite. |

Don't add new code in either. Existing code is drift, tracked in [TODO.md](TODO.md).

## A note on "I just need one endpoint"

The temptation to grab `http.server` for "just one endpoint, no need for the full FastAPI machinery" is how you end up with audio's drift. **A 30-line FastAPI app weighs less than the resulting "I'll add validation later" tech debt.** The FastAPI/uvicorn deps are small; the operational benefit (`/docs`, validation, async) outweighs the install cost on the first day you need to debug a request.

## Why we're picky about this

Five frameworks across five packages was the state we found. Each was chosen sensibly in isolation; together they're a maintenance burden. One canonical (FastAPI) plus one allowed exception (aiohttp for WS) plus one external-constraint (Starlette for A2A) is the sweet spot — broad enough for reality, narrow enough that an operator can read any package's HTTP code without re-learning conventions.
