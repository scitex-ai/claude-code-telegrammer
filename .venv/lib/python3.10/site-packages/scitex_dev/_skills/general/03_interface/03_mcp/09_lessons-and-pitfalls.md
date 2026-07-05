---
description: |
  [TOPIC] Interface Mcp Lessons
  [DETAILS] SciTeX MCP — concrete lessons and pitfalls from the 2026-04-30 dev.py mount refactor. Specific failure modes that took hours to diagnose and how to avoid them.
tags: [scitex-general-interface-mcp-lessons-and-pitfalls]
---

# §8. Lessons and pitfalls

Recorded from the 2026-04-30 refactor of `scitex/_mcp_tools/dev.py` from hand-wrap → mount. These are the specific failure modes that *will* bite anyone touching the MCP plumbing without reading them.

## 1. Hand-wrap drops new params silently

**Symptom.** You add a parameter to a handler in `scitex_<pkg>` (or its `_mcp_server` wrapper). You verify the tests pass. You restart the MCP server. The new parameter is missing from the schema visible to LLMs.

**Cause.** A bridge in `scitex/_mcp_tools/<pkg>.py` hand-wraps the tool with an explicit `async def <pkg>_<name>(...)` signature and forwards by name. The new parameter exists in three places (handler, standalone wrapper, umbrella wrapper) and you only updated two.

**Fix.** Use the mount pattern (`safe_mount` from `_compat`) — see [02_server-registration.md](02_server-registration.md). Mount-style bridges have no per-tool maintenance and inherit every new parameter automatically.

**Detection.** The audit linter (§7 [audit-mcp-tools.md](08_audit-mcp-tools.md)) flags any `@mcp.tool()` decorator inside `scitex/_mcp_tools/<pkg>.py` after this convention is rolled out.

## 2. `/mcp reconnect` does NOT restart the server process

**Symptom.** You change source code, run `pip install -e`, run `/mcp reconnect <name>`. Tools list looks unchanged.

**Cause.** `/mcp reconnect` re-handshakes the **client side** — it re-opens the stdio pipe to an already-running server process. The server's Python interpreter is still alive with the old bytecode loaded.

**Fix.** Restart the **server process** itself: kill `scitex mcp start` (or whatever entry point), let the harness respawn it. Or fully quit + reopen Claude Code.

**Quick test.** After reconnect, `ToolSearch select:mcp__scitex__<tool>` and inspect the schema. If your new param is missing, the server process is stale — not the connection.

## 3. Multiple `scitex mcp start` processes (one per Claude Code window)

**Symptom.** You kill one server process; some sessions still see old code.

**Cause.** Each Claude Code window spawns its own `scitex mcp start` subprocess. They are independent.

**Fix.** Kill **all** `scitex mcp start` processes (or restart Claude Code fully). `ps aux | grep "scitex mcp start"` to see them.

## 4. Orphan `site-packages/<pkg>/` shadows the editable install

**Symptom.** `pip install -e <repo>` succeeds. `pip show <pkg>` says `Editable project location: <repo>`. But `import` resolves to `site-packages/<pkg>/__init__.py`, not the editable source.

**Cause.** A previous wheel install left a real `site-packages/<pkg>/` directory. Editable installs use a `.pth` file pointing to the source — but a real directory with the same name takes precedence.

**Fix.**
```bash
pip uninstall -y <pkg>
ls site-packages/ | grep -i <pkg>             # check residue
rm -rf site-packages/<pkg>/
rm -rf site-packages/<pkg>-*.dist-info/
rm -f  site-packages/__editable__.<pkg>-*.pth # leftover editable markers
pip install -e <repo>
```

**Detection.** Run `python -c "import <pkg>; import inspect; print(inspect.getsourcefile(<pkg>))"` after install — must point inside the editable repo, not into `site-packages`.

## 5. Vendored parallel implementations shadow the standalone

**Symptom.** Edits in `~/proj/scitex-dev/src/scitex_dev/rename/` don't take effect when the umbrella's MCP server runs.

**Cause.** The umbrella has its own copy at `~/proj/scitex-python/src/scitex/_dev/_rename/`. The umbrella's tooling reaches into the vendored copy, not the standalone — even if both are editable installs.

**Fix.** The umbrella `scitex/_mcp_tools/<pkg>.py` MUST `from scitex_<pkg>._mcp_server import mcp as ...` — never define a parallel rename / handler module under `scitex._<pkg>._...`. The vendored copies are migration leftovers and should be deleted once the standalone covers everything.

**Detection.** Grep for `from scitex._<pkg>._` in `_mcp_tools/<pkg>.py` — there should be no such imports under the mount pattern.

## 6. `safe_mount` is the only canonical mount call (revised 2026-04-30)

**Symptom.** Tool names come out as `dev_dev_bulk_rename` (double prefix), `bulk_rename` (no prefix), or break across FastMCP 2.x/3.x machines.

**Cause.** Three drift patterns existed in the wild before the spec was tightened:

1. **Hand-wrap.** Bridge file uses `@mcp.tool()` per tool — the original cause of the 2026-04-30 `auto_stash` / `summary_only` incident.
2. **Direct `mcp.mount(...)`.** Works on one FastMCP version, fails on the other (`prefix=` vs `namespace=` rename).
3. **Mixing.** Standalone bakes the prefix into source AND bridge calls `safe_mount(... namespace="…")` → double prefix `pkg_pkg_*`.

**Fix.** Every umbrella bridge calls `safe_mount(...)` from `scitex._mcp_tools._compat`. Two acceptable shapes — both go through `safe_mount`:

| Standalone source | Bridge call                                | Resulting names |
|-------------------|--------------------------------------------|------------------|
| Bare (`run_test`) — recommended | `safe_mount(mcp, sub, namespace="<pkg>")`   | `<pkg>_run_test` |
| Already-prefixed (`io_save`) — legacy only | `safe_mount(mcp, sub)` (no namespace) | `io_save`        |

**Detection.** `audit-mcp-tools §1` flags both `@mcp.tool()` decorators in bridges (hand-wrap) AND direct `mcp.mount(...)` calls without `safe_mount`. See [08_audit-mcp-tools.md](08_audit-mcp-tools.md).

## 7. The MCP server entry point may not be where you expect

**Symptom.** You edit `scitex_dev/_mcp_server.py`, restart, no change. Investigation shows the umbrella has its own `_mcp_tools/dev.py` overriding what gets registered.

**Cause.** `scitex mcp start` runs `scitex.__main__:main`, which registers tools from `scitex/_mcp_tools/*.py`, NOT from `scitex_dev._mcp._server` directly. The two are linked by the `safe_mount` import in the bridge file.

**Fix.** Always check both:
1. The standalone's `_mcp_server.py` (source of truth for tools).
2. The umbrella's `_mcp_tools/<pkg>.py` (whether it mounts or hand-wraps).

If the bridge hand-wraps, edits in the standalone won't propagate until the bridge is converted to the mount pattern.

## 8. FastMCP 2.x vs 3.x API differences

**Symptom.** `mcp.mount(sub, prefix="…")` works on one machine, `mcp.mount(sub, namespace="…")` on another.

**Cause.** FastMCP 3.x renamed `prefix=` → `namespace=`. The `_compat.safe_mount` shim handles both.

**Fix.** Always use `safe_mount(mcp, sub, namespace="…")` from `scitex._mcp_tools._compat`. Don't call `mcp.mount` directly unless you've checked the installed FastMCP version.

## 9. Lint hooks may require `Any` import that wasn't needed before

**Symptom.** Adding any function to `safety.py` triggers a Pyright error about `Any` being undefined — even though that function existed unchanged.

**Cause.** Pyright runs a fresh diagnosis on every edit. A pre-existing missing import shows up the first time the file is touched in this session.

**Fix.** Add `from typing import Any` when first touching such a file. It's not your bug, but the lint hook will block your edit until you fix it.

## 10. The bulk-rename `dev_bulk_rename` is the right tool for in-file mass renames

**Symptom.** You `sed -i 's/async def dev_/async def /'` and lose the trailing space, breaking 12 function definitions silently.

**Cause.** `sed` literal-string semantics; off-by-one on whitespace.

**Fix.** Use `dev_bulk_rename(pattern="def dev_", replacement="def ", directory=…, confirm=False)` first — the dry-run report shows every match in context. After review, rerun with `confirm=True`. The before/after snippets catch whitespace bugs the human eye misses.

This is the canonical use case for the tool — it exists precisely because sed/grep loops drop trailing space, miss collisions, and don't dry-run.
