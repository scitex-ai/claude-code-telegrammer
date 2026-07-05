---
description: |
  [TOPIC] Interface Http Api Error Envelope
  [DETAILS] Canonical error response shape — `ErrorResponse` Pydantic model with `error`, `code` (links to `scitex_dev._errors.ErrorCode`), `detail`, `remediation`, `timestamp`. HTTP status code matches the error semantics. Avoid leaking stack traces in production. FastAPI's `HTTPException` integrates cleanly.
tags: [scitex-general-interface-http-api-error-envelope]
---

# Error Envelope

## Canonical shape

```python
from datetime import datetime
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    error: str                          # Short human-readable summary
    code: str | None = None             # ErrorCode (E001, E101, ...) — see scitex_dev._errors
    detail: dict | str | None = None    # Optional structured detail
    remediation: str | None = None      # What the caller can do
    timestamp: str                      # ISO 8601, server-side
```

Example response (JSON):

```json
{
  "error": "h5py is not installed",
  "code": "E004",
  "detail": null,
  "remediation": "pip install scitex-io[h5]",
  "timestamp": "2026-04-30T12:34:56.789Z"
}
```

## HTTP status code mapping

| Code | Meaning | Use when |
|---|---|---|
| `400 Bad Request` | Client sent something malformed | Invalid JSON; required field missing (caught by Pydantic — automatic 422) |
| `401 Unauthorized` | No / invalid auth | Missing token (when auth is enforced — see [06_auth.md](06_auth.md)) |
| `403 Forbidden` | Authenticated but not allowed | User lacks permission for this resource |
| `404 Not Found` | Resource doesn't exist | DOI not in DB, file not found |
| `409 Conflict` | State doesn't permit the action | `overwrite=False` and target file exists |
| `422 Unprocessable Entity` | Pydantic validation failure | Automatic — FastAPI handles this |
| `429 Too Many Requests` | Rate limit hit | Future, when rate-limiting lands |
| `500 Internal Server Error` | Bug in your code | Unhandled exception. Log the traceback server-side; don't leak it. |
| `503 Service Unavailable` | Dependency down | Database unreachable, optional dep missing |

Match the status code to the semantic. A 200 response with `{"error": "..."}` in the body is anti-pattern — clients have to parse the body to know if the call succeeded. Use HTTP status as the primary signal.

## Integration with `scitex_dev._errors`

When the underlying Python API raises a structured `ScitexError(code=ErrorCode.Exxx, ...)`, translate it directly:

```python
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from scitex_dev._errors import ScitexError

app = FastAPI()

@app.exception_handler(ScitexError)
async def scitex_error_handler(request: Request, exc: ScitexError):
    status = _STATUS_MAP.get(exc.code, 500)
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            error=exc.message,
            code=exc.code.value,
            detail=exc.detail,
            remediation=exc.remediation,
            timestamp=datetime.utcnow().isoformat() + "Z",
        ).model_dump(),
    )

_STATUS_MAP = {
    ErrorCode.E001_INVALID_INPUT:        400,
    ErrorCode.E002_FILE_NOT_FOUND:       404,
    ErrorCode.E003_PERMISSION_DENIED:    403,
    ErrorCode.E004_DEPENDENCY_MISSING:   503,
    ErrorCode.E005_TIMEOUT:              504,
}
```

scitex-dev should ship a helper `scitex_dev.http.install_error_handlers(app)` that registers this once for every FastAPI app — tracked in [TODO.md](TODO.md).

## FastAPI's built-in `HTTPException`

For one-off cases where the underlying call doesn't raise `ScitexError`, raise `HTTPException` directly:

```python
from fastapi import HTTPException

@app.get("/papers/{doi}")
def get_paper(doi: str):
    paper = db.get_by_doi(doi)
    if paper is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"DOI not found: {doi}",
                "code": "E002",
                "remediation": "Check spelling or expand the local index.",
            },
        )
    return paper
```

FastAPI automatically wraps `HTTPException.detail` in the response body. To always emit the canonical shape, register a global handler:

```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    if isinstance(exc.detail, dict):
        body = ErrorResponse(**exc.detail, timestamp=datetime.utcnow().isoformat() + "Z").model_dump()
    else:
        body = ErrorResponse(error=str(exc.detail), timestamp=datetime.utcnow().isoformat() + "Z").model_dump()
    return JSONResponse(status_code=exc.status_code, content=body)
```

## Don't leak tracebacks

In production, **never** include Python tracebacks in the response body. They reveal:

- Internal file paths (`/home/ywatanabe/...`)
- Library versions (helpful for an attacker)
- Code structure (helpful for an attacker)

The default FastAPI behaviour on unhandled exception is a 500 with `{"detail": "Internal Server Error"}` — keep it that way. Log the traceback to stderr (or to a logging backend) instead.

For development, you can opt in to verbose errors:

```python
import os
DEBUG = os.environ.get("SCITEX_HTTP_DEBUG", "0") == "1"

if DEBUG:
    app = FastAPI(debug=True)   # tracebacks in response
```

Default to `DEBUG=False`. Never ship containers with `DEBUG=True`.

## Audit

- Every error response uses `ErrorResponse` shape.
- Every error response has the appropriate HTTP status code (not blanket 200 / 500).
- `ScitexError` from the Python API maps to the right status via `_STATUS_MAP`.
- Production deployments have `DEBUG=False`.
- No file paths or library versions in error response bodies in production.
