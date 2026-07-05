---
description: |
  [TOPIC] Interface Http Api Endpoints
  [DETAILS] REST endpoint conventions — noun-based URLs (`/papers`, `/papers/{id}`), HTTP verbs map to actions (GET=read, POST=create, PUT=replace, DELETE=remove), JSON request/response, Pydantic models for validation, OpenAPI auto-docs at `/docs`. Path style matches CLI's noun-verb convention so the two interfaces stay legible side by side.
tags: [scitex-general-interface-http-api-endpoint-conventions]
---

# Endpoint Conventions

## URL shape — nouns, not verbs

URLs name **resources** (nouns). HTTP verbs name **actions**.

```
✅ Good — noun URLs
GET    /papers                  # list
GET    /papers/{doi}            # read one
POST   /papers                  # create
PUT    /papers/{doi}            # replace
DELETE /papers/{doi}            # remove

❌ Bad — verb URLs
GET  /listPapers
POST /createPaper
POST /deletePaper?id=…
```

This is the universal REST convention. Sticking to it gives you:

- Predictable URLs without consulting docs.
- Clean OpenAPI rendering (FastAPI auto-groups by path prefix).
- Compatibility with HTTP semantics (caching, idempotency).

Note the parallel with the CLI noun-verb rule: CLI is `<cli> papers list` / `<cli> papers get <doi>`; HTTP is `GET /papers` / `GET /papers/{doi}`. Same mental model, different surface — readers don't have to context-switch.

## HTTP verb cheat sheet

| Verb | Means | Idempotent? | Has body? | Returns |
|---|---|---|---|---|
| `GET` | Read a resource or collection | Yes | No (use query params) | The resource(s) |
| `POST` | Create or trigger an action | No | Yes | The new resource (with status 201) |
| `PUT` | Replace a resource entirely | Yes | Yes | The replaced resource |
| `PATCH` | Partial update | No (usually) | Yes | The updated resource |
| `DELETE` | Remove a resource | Yes | No | Empty body (status 204) or the deleted resource |

If your operation doesn't fit any of these (e.g. "rebuild the cache"), prefer `POST` to a sub-resource: `POST /cache/rebuild`. Avoid generic `POST /action` with a verb in the body.

## Request shape — Pydantic

```python
from pydantic import BaseModel, Field

class SaveRequest(BaseModel):
    path: str = Field(..., description="Destination path (extension determines format).")
    obj: dict
    overwrite: bool = False
    dry_run: bool = False

@app.post("/save")
def save_endpoint(req: SaveRequest) -> SaveResponse:
    ...
```

Why Pydantic:

- Type validation runs before your handler — bad input gets a 422 with a structured error pointing at the offending field.
- `Field(description=...)` flows into the auto-generated OpenAPI page.
- Mirrors the type-hint vocabulary in the Python API ([06_type-hints.md](../01_python-api/06_type-hints.md)).

For query parameters on GET endpoints, declare them as function parameters with annotations:

```python
@app.get("/search")
def search(query: str, limit: int = 50, offset: int = 0) -> SearchResponse:
    ...
# becomes: GET /search?query=foo&limit=50&offset=0
```

## Response shape — Pydantic too

```python
class SaveResponse(BaseModel):
    path: str
    bytes_written: int
    elapsed_ms: float

@app.post("/save", response_model=SaveResponse)
def save_endpoint(req: SaveRequest):
    ...
```

Reasons to declare `response_model`:

- FastAPI strips fields the model doesn't include (prevents accidental leaks of internal data).
- Auto-docs show the response shape, not just request shape.
- Type checkers can verify your handler returns the right shape.

## JSON only

Default response content type is `application/json`. Don't return HTML, XML, or text/plain from REST endpoints.

Exceptions:

- File downloads — return `FileResponse`/`StreamingResponse` with appropriate `Content-Type`.
- HTML pages — only if the endpoint is intentionally a web page (a dashboard route), not a REST endpoint. Keep these on a separate path prefix (`/ui/...` vs `/api/...`).

## Path prefixing

For packages that mix REST + dashboard pages, separate the trees:

```
/api/...    ← REST endpoints (JSON only)
/ui/...     ← HTML pages (dashboard)
/static/... ← static assets
/health     ← health check (top-level — see 05_health-and-ops.md)
/docs       ← OpenAPI Swagger UI (auto)
/redoc      ← OpenAPI ReDoc (auto)
```

Mounting REST under `/api/` keeps the OpenAPI spec scoped, lets nginx route dashboard separately, and makes log-grepping ("which API endpoint was hit") trivial.

## OpenAPI / `/docs`

FastAPI ships `/docs` (Swagger UI) and `/redoc` (ReDoc) for free. Don't disable them on production unless you have a hard reason — they're a documentation surface for downstream developers.

Configure them with:

```python
app = FastAPI(
    title="scitex-cloud crossref-local",
    description="Local CrossRef metadata + citation graph API.",
    version=__version__,
    docs_url="/docs",       # default
    redoc_url="/redoc",     # default
    openapi_url="/openapi.json",
)
```

If you publish the API publicly, link `/docs` from your README.

## Audit

- Every URL is a noun, not a verb.
- HTTP verb matches the semantic (GET reads, POST creates, ...).
- Every request body and response uses a Pydantic `BaseModel`.
- `response_model=` declared on every non-trivial endpoint.
- `/docs` reachable and accurate.

Linter rule (planned): **PA-1xx-style** — see [09_audit-checklist.md](09_audit-checklist.md) and [TODO.md](TODO.md).
