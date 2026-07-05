---
description: |
  [TOPIC] Interface Http Api Health And Ops
  [DETAILS] Operational endpoints every HTTP server must expose — `/health` (liveness, fast), `/ready` (readiness, checks deps), CORS configuration, request logging, optional `/metrics` for Prometheus. Cache headers for static assets. Health checks must be cheap so load balancers can poll without overhead.
tags: [scitex-general-interface-http-api-health-and-ops]
---

# Health and Operations

Every HTTP server in the SciTeX ecosystem exposes a small set of operational endpoints. They're how nginx / Docker / Kubernetes / oncall-humans verify the service is alive.

## `/health` — fast liveness check

```python
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "scitex-cloud-crossref-local",
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
```

Rules:

- **Returns 200 if the process is alive.** No DB query, no upstream check.
- **Sub-millisecond latency.** Load balancers poll this every 1–5 seconds; expensive checks here translate to wasted CPU and false alerts.
- **Always exists**, even if the rest of the API is broken (auth, DB down, etc.).
- **Top-level path** (`/health`, not `/api/health`). Routing exemptions in nginx are simpler when health lives at root.

## `/ready` — readiness, allowed to be slow

```python
@app.get("/ready")
async def ready() -> dict:
    checks = {
        "db": await _check_db(),
        "cache": _check_cache(),
        "version": __version__,
    }
    healthy = all(v is True or v == "ok" for v in checks.values() if not isinstance(v, str) or v != "version")
    status_code = 200 if healthy else 503
    return JSONResponse(status_code=status_code, content={"status": "ready" if healthy else "degraded", **checks})
```

Difference from `/health`:

- **Touches dependencies** — DB ping, cache check, optional-extra availability.
- **Allowed to be slow** (~50–200ms). K8s polls less frequently for readiness than liveness.
- **Returns 503** when a dependency is down — load balancer pulls the pod out of rotation but doesn't restart it.

If your service has no external dependencies (pure compute), `/ready` and `/health` can be the same endpoint. Don't manufacture checks just to differ.

## CORS — what it is, when to enable it

**CORS** (Cross-Origin Resource Sharing) is a browser security feature. By default, a web page at `https://app.example.com` cannot call `https://api.example.com` from JavaScript. The API has to opt in by sending specific HTTP headers.

You only need CORS if:

- A browser-based UI on a *different* origin will call your API.
- Examples: scitex-cloud's frontend (`scitex.ai`) calling its REST API on a different host; orochi's dashboard JS hitting the dashboard API.

You don't need CORS if:

- Your API is consumed only by Python clients, curl, or backends.
- Your UI is served from the *same* origin as the API.

Enable explicitly when needed:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://scitex.ai", "https://app.scitex.ai"],   # ← explicit list, NOT "*"
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    allow_credentials=True,
)
```

`allow_origins=["*"]` is anti-pattern in production — it disables the protection. Use an explicit list. For dev, you can read it from an env var:

```python
import os
origins = os.environ.get("SCITEX_HTTP_ORIGINS", "").split(",")
```

## Request logging

Every request should produce a single log line on completion. uvicorn does this by default:

```
INFO:     127.0.0.1:54321 - "GET /papers/10.1234%2Fexample HTTP/1.1" 200 OK
```

If you need structured logs (JSON, with request IDs), use middleware:

```python
import logging
import time
import uuid
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.time()
    response = await call_next(request)
    elapsed_ms = (time.time() - start) * 1000
    logging.info(
        "%s %s %d %.1fms request_id=%s",
        request.method, request.url.path, response.status_code, elapsed_ms, request_id,
    )
    response.headers["X-Request-ID"] = request_id
    return response
```

The `X-Request-ID` header lets clients correlate their failure with your logs.

## Optional: `/metrics` for Prometheus

When the service is in production and observability matters:

```python
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

Exposes counters and latency histograms in Prometheus text format. Don't add this to small local-machine relays (audio); it's for cloud-deployed services.

## Cache headers for static assets

If the server hosts static assets (`/static/...`):

```python
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.middleware("http")
async def add_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"   # 1 year (use hashed filenames!)
    elif request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"                              # never cache JSON
    return response
```

For HTML dashboards (orochi pattern), set `Cache-Control: no-cache` so users see fresh data on refresh. Long max-age is reserved for content-hashed assets (`/static/main.abc123.js`).

## Audit

- `/health` exists, returns 200, takes <10ms.
- `/ready` exists if there are external deps; returns 503 on degradation.
- CORS configured explicitly (no `"*"` in production).
- Request logs include method, path, status, duration.
- Static assets have appropriate `Cache-Control` headers.
- `/metrics` exposed for cloud-deployed services.
