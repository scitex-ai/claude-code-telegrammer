---
description: |
  [TOPIC] Interface Mcp Server Registration
  [DETAILS] SciTeX MCP server registration — single FastMCP per package, mount pattern from the scitex umbrella, conventions A vs B for tool naming under namespace mount.
tags: [scitex-general-interface-mcp-server-registration]
---

# §1. Server registration — single source of truth + mount

## Rule: one FastMCP instance per package

Every standalone `scitex-*` package that ships MCP tools defines **one** `FastMCP` instance — typically:

```python
# src/scitex_<pkg>/_mcp_server.py
from fastmcp import FastMCP
mcp = FastMCP(name="scitex-<pkg>", instructions="…")

@mcp.tool()
async def some_tool(...) -> str: ...
```

Every tool the package exposes is registered on **that** `mcp` object via `@mcp.tool()`. The `scitex` umbrella does **not** redefine them; it imports the standalone's `mcp` and **mounts** it.

## Rule: scitex umbrella delegates via `safe_mount`

The umbrella's per-package bridge file in `~/proj/scitex-python/src/scitex/_mcp_tools/<pkg>.py` is a ~30-line mount shim:

```python
# src/scitex/_mcp_tools/<pkg>.py
def register_<pkg>_tools(mcp) -> None:
    """Mount scitex-<pkg> MCP server."""
    try:
        from scitex_<pkg>._mcp_server import mcp as sub_mcp
        from ._compat import safe_mount

        safe_mount(mcp, sub_mcp, namespace="<pkg>")
    except ImportError:
        @mcp.tool()
        async def <pkg>_not_available() -> str:
            return "scitex-<pkg> required. Install with: pip install scitex[<pkg>]"
```

**Consequences:**

- New tools added to the standalone appear automatically in the umbrella — no per-tool maintenance.
- New parameters on existing tools propagate automatically — no signature-drift bugs.
- The umbrella's bridge file never has to know how many tools the standalone has.

Reference implementations to copy: `_mcp_tools/cloud.py`, `_mcp_tools/stats.py`, `_mcp_tools/dev.py`, `_mcp_tools/clew.py`.

## Hand-wrapping is an anti-pattern

A bridge file that hand-wraps each tool with `@mcp.tool() async def <pkg>_<name>(...)` and forwards parameters by name is the **legacy** pattern. It was the cause of the 2026-04-30 `auto_stash` / `summary_only` drift incident — see [08_lessons-and-pitfalls.md](09_lessons-and-pitfalls.md). Files still using this pattern at the time of writing are tracked in [TODO.md](TODO.md).

## `safe_mount` is the **only** canonical mount call

Every bridge file uses `safe_mount` from `scitex._mcp_tools._compat`. Direct `mcp.mount(...)` calls are deprecated in bridges — they break on FastMCP version drift (2.x `prefix=` vs 3.x `namespace=`) which `safe_mount` papers over via signature inspection.

Two acceptable shapes — both go through `safe_mount`:

| Shape                   | Standalone tool names        | `safe_mount` call                              | Resulting umbrella names |
|-------------------------|------------------------------|------------------------------------------------|--------------------------|
| **With namespace** (recommended) | bare (`run_test`)     | `safe_mount(mcp, sub, namespace="<pkg>")`      | `<pkg>_run_test`         |
| **Without namespace**   | already-prefixed (`io_save`) | `safe_mount(mcp, sub)`                         | `io_save`                |

**Pick "with namespace" by default.** Bare names inside the standalone source are cleaner; the prefix is added at mount time. The "without namespace" shape exists for legacy packages whose source already prefixes (`scitex-io`); new packages should use the namespace form to avoid double-prefix surprises.

The `scitex-dev ecosystem audit-mcp-tools` linter ([08_audit-mcp-tools.md](08_audit-mcp-tools.md)) flags any bridge that calls `mcp.mount(...)` directly instead of `safe_mount(...)`.

## Failure surface

If the standalone is missing, the umbrella bridge installs a single `<pkg>_not_available` tool that returns a clear "install with `pip install scitex[<pkg>]`" message. **Never** silently no-op or raise an obscure `ImportError` — the LLM agent has no recovery path.

See `_mcp_tools/cloud.py` for the canonical fallback shape.
