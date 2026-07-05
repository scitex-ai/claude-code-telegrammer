---
description: |
  [TOPIC] Interface Http Api Auth
  [DETAILS] Authentication posture — canonical pattern is nginx (or another reverse proxy) in front, doing token / mTLS / OAuth check and forwarding to an unauthenticated upstream. scitex-dev ships a `require_token` middleware for local-dev mode where running a proxy is overkill. Don't bake bespoke auth into individual packages — that's how orochi's stopgap query-string token happened. Token storage, secret rotation, and HTTPS termination live at the proxy layer.
tags: [scitex-general-interface-http-api-auth]
---

# Authentication

## The two-layer model

```
                  ┌────────────────────────────┐
Client (browser   │  Reverse proxy (nginx)     │  ← authenticates here
or curl)  ───────►│  - HTTPS termination       │
                  │  - Token / mTLS / OAuth    │
                  │  - Rate limiting           │
                  └─────────────┬──────────────┘
                                │ plain HTTP, trusted network
                                ▼
                  ┌────────────────────────────┐
                  │  scitex-* HTTP server      │  ← no auth code here
                  │  - FastAPI / aiohttp       │
                  │  - Endpoints just work     │
                  └────────────────────────────┘
```

**Canonical: auth lives at the proxy. The HTTP server itself is open on the trusted network behind it.**

This is what scitex-cloud and scitex-orochi already use today. It's the pattern that scales.

## Why this layering

- **Single source of truth for auth** — one nginx config to update, not N package source trees when a token rotates.
- **Off-the-shelf maturity** — nginx / Caddy / Traefik have decades of hardening. Reinventing token validation in Python is how vulnerabilities ship.
- **HTTPS termination at the edge** — the proxy holds the cert, talks plain HTTP to upstreams. Each scitex package doesn't need cert handling.
- **Rate limiting and abuse control** — proxy primitives, not Python middleware.
- **Composability** — the same proxy can route between scitex-cloud's REST APIs and orochi's WebSocket dashboard with one auth layer for both.

## What this means for your package

**You don't write auth code.** Your endpoints assume the caller is already authenticated (because the proxy let them through):

```python
# ✅ Canonical — no auth check in the handler
@app.post("/save")
def save_endpoint(req: SaveRequest) -> SaveResponse:
    p = save(req.obj, req.path)
    return SaveResponse(path=str(p))
```

If you need user identity (which user is calling), the proxy injects it as a header:

```python
@app.post("/save")
def save_endpoint(req: SaveRequest, x_forwarded_user: str = Header(None)) -> SaveResponse:
    # nginx sets X-Forwarded-User after auth_request
    if x_forwarded_user is None:
        raise HTTPException(401, detail={"error": "missing X-Forwarded-User"})
    ...
```

The header pattern is tolerated as long as the package documents that it relies on a proxy doing the actual auth.

## When you're running locally without a proxy

For audio's local relay, scitex-dev's dashboard, or any "run on my laptop" use case, setting up nginx is overkill. scitex-dev ships a middleware:

```python
from scitex_dev.http import require_token   # ⚠ ships in scitex-dev v0.7+ — see TODO.md

app = FastAPI()
app.add_middleware(require_token, env_var="SCITEX_AUDIO_TOKEN")
```

Behavior:

- Reads token from `os.environ[env_var]`.
- If env var is unset, generates one on first run, persists to `~/.scitex/<pkg>/.token`, prints to stderr once. (Mirror of orochi's current pattern.)
- Caller passes the token via `Authorization: Bearer <token>` header.
- Returns 401 without it.

This is **dev-mode auth**, not production auth. The line in the README should say:

> Local mode: set `SCITEX_<PKG>_TOKEN` and pass `Authorization: Bearer ...` headers.
> Production: deploy behind nginx with `auth_request`. See [scitex-cloud deployment guide].

## What NOT to do

```python
# ❌ Don't — bespoke auth per package
@app.post("/save")
def save_endpoint(req, request: Request):
    if request.query_params.get("token") != MY_TOKEN:
        raise HTTPException(401)
    ...
```

This is what orochi has today (`?token=` in the query string). It's tolerated as a stopgap because it pre-dates this convention; tracked as drift in [TODO.md](TODO.md). Reasons it's bad:

- **Tokens in URLs leak via logs** — every `GET /api/foo?token=xyz` shows up in nginx access logs, browser history, intermediary proxies. Headers don't.
- **Each package implements differently** — orochi's query string, hypothetical future package's bearer header, hypothetical third package's HMAC signature. Operators can't reason about the system.
- **Rotation is a code change** — env-var-based tokens are one config update; hardcoded comparisons require a deploy.

## A note on HTTPS

HTTPS terminates at the proxy. The plain-HTTP upstream is fine **as long as the network between proxy and upstream is trusted** (Docker bridge, K8s pod network, VPS loopback). If you run the upstream on a public IP without a proxy, that's broken — fix the deployment, not the code.

## A note on CSRF

CSRF (Cross-Site Request Forgery) only matters if your service has *cookie-based* auth and a browser-based UI. The token-bearer pattern above isn't vulnerable to CSRF (the attacker can't read the bearer token from another origin). orochi's dashboard, which uses cookies on the same origin, gets CSRF protection from same-site cookie attributes — out of scope for individual scitex package code.

## Audit

- **Production**: package documents nginx (or equivalent) reverse proxy in its deployment guide.
- **Dev mode**: if running directly without proxy, uses `scitex_dev.http.require_token` (once shipped) — not a hand-rolled token check.
- **No tokens in URLs** (query strings) — bearer headers only.
- **No HTTPS termination** in scitex package code.
- **Endpoints don't call back to identity providers** — proxy injects identity via header.

## See also

- [scitex-cloud deployment guide] — concrete nginx config the ecosystem currently uses
- [orochi migration TODO](TODO.md) — moving the query-string token to bearer header (or to proxy)
- [04_error-envelope.md](04_error-envelope.md) — 401/403 status code semantics
