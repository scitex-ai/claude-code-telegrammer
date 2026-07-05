"""§1 — MCP umbrella-bridge / mount-pattern discipline.

Extracted from `_mcp_audit.py` to keep the orchestrator under the
per-file line budget. Mirrors the existing §6 (`_mcp_parity.py`) and §2/§5
(`_mcp_tool_naming.py`) splits.

What lives here:
- ``_resolve_mcp_server(package)`` — locate the standalone `FastMCP`
  instance for a package.
- ``_default_import_bridge_pkg()`` / ``_read_bridge_source(package, *,
  import_bridge_pkg=None)`` — read the umbrella's
  `scitex/_mcp_tools/<short>.py` bridge source.
- ``_check_bridge_pattern(package, out, *, read_bridge_source=None,
  resolve_mcp_server=None)`` — §1 audit rule.

Re-exported from `_mcp_audit` so existing call sites and test imports
keep working.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from ._audit import Violation
from ._mcp_names import _import_name, _short_name


def _resolve_mcp_server(package: str):
    """Locate a `FastMCP` instance for `package`.

    Tries module candidates `scitex_<pkg>._mcp_server`, `scitex_<pkg>.mcp_server`
    and looks for a top-level `mcp` attribute that is a `FastMCP`. Returns the
    instance or None.
    """
    try:
        from fastmcp import FastMCP  # local import to keep the module light
    except ImportError:
        return None

    import_name = _import_name(package)
    candidates = [
        f"{import_name}._mcp_server",
        f"{import_name}.mcp_server",
        f"{import_name}._mcp.server",  # scitex-io shape
        f"{import_name}.mcp.server",
    ]
    for mod_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
        except BaseException:
            # `BaseException` (not just `Exception`) — some packages call
            # `sys.exit(1)` at module-import time when their preconditions
            # fail (e.g. scitex-orochi when telegram-bot env vars are unset).
            # SystemExit derives from BaseException, so a plain `except Exception`
            # would let it propagate and kill the audit run.
            continue
        for attr in ("mcp", "server", "app"):
            obj = getattr(mod, attr, None)
            if isinstance(obj, FastMCP):
                return obj
    return None


def _default_import_bridge_pkg():
    """Default bridge-pkg importer used by `_read_bridge_source`.

    Function-local import (lazy) so PA-304's module-level scan exempts it —
    auditing the umbrella's private bridge package by design is the one
    place where importing `scitex._mcp_tools` is intentional, not a
    violation.
    """
    import scitex._mcp_tools as bridge_pkg  # noqa: PA-304

    return bridge_pkg


def _read_bridge_source(
    package: str,
    *,
    import_bridge_pkg=None,
) -> str | None:
    """Read `scitex/_mcp_tools/<short>.py`; None if absent.

    The optional ``import_bridge_pkg`` callable lets tests inject a fake
    bridge module without monkey-patching — same convention as
    ``read_bridge_source`` / ``resolve_mcp_server`` on
    ``_check_bridge_pattern``.
    """
    if import_bridge_pkg is None:
        import_bridge_pkg = _default_import_bridge_pkg
    short = _short_name(package)
    try:
        bridge_pkg = import_bridge_pkg()
    except Exception:
        return None
    # `__file__` is None for namespace packages (no concrete __init__.py).
    # `getattr(obj, "__file__", "")` with a default of "" does NOT help here:
    # the attribute *exists* and *is None*, so the default never fires.
    # `Path(None)` then raises TypeError — which used to crash
    # `test_audit_all_clean` ecosystem-wide whenever the umbrella's
    # `_mcp_tools` resolved as a namespace pkg, forcing admin-merge on every
    # scitex-* PR. Treat a None `__file__` as "no concrete bridge file" —
    # semantically equivalent to a missing bridge, which the §1 rule
    # already handles silently (presence is checked by §6 parity).
    pkg_file = getattr(bridge_pkg, "__file__", None)
    if pkg_file is None:
        return None
    pkg_dir = Path(pkg_file).parent
    bridge = pkg_dir / f"{short}.py"
    if not bridge.is_file():
        return None
    try:
        return bridge.read_text(encoding="utf-8")
    except OSError:
        return None


_HAND_WRAP_DECORATOR = re.compile(r"@\s*mcp\s*\.\s*tool\s*\(")
_SAFE_MOUNT_CALL = re.compile(r"\bsafe_mount\s*\(")
_PLAIN_MOUNT_CALL = re.compile(r"\.\s*mount\s*\(")


def _check_bridge_pattern(
    package: str,
    out: list[Violation],
    *,
    read_bridge_source=None,
    resolve_mcp_server=None,
) -> None:
    """§1 — umbrella bridge must use `safe_mount` (or equivalent), not hand-wrap.

    Exempt when the standalone has no `<pkg>._mcp_server.mcp`: the bridge
    cannot `safe_mount` a non-existent server, so hand-wrapping is the
    only available option. The §1 rule only applies when the bridge
    *could* mount but chose not to.

    The optional ``read_bridge_source`` / ``resolve_mcp_server`` callables
    let tests inject fakes without monkey-patching the module.
    """
    if read_bridge_source is None:
        read_bridge_source = _read_bridge_source
    if resolve_mcp_server is None:
        resolve_mcp_server = _resolve_mcp_server
    src = read_bridge_source(package)
    if src is None:
        # No bridge → not flagged here; presence is checked under §6 parity.
        return
    short = _short_name(package)
    has_safe_mount = bool(_SAFE_MOUNT_CALL.search(src))
    has_plain_mount = bool(_PLAIN_MOUNT_CALL.search(src))
    has_hand_wrap = bool(_HAND_WRAP_DECORATOR.search(src))

    if has_hand_wrap and not (has_safe_mount or has_plain_mount):
        # Standalone-side check: if `<pkg>._mcp_server.mcp` doesn't
        # resolve, hand-wrap is the only option. Don't penalise the
        # standalone for the umbrella's choice when no alternative exists.
        if resolve_mcp_server(package) is None:
            return
        out.append(
            Violation(
                package,
                "§1",
                f"umbrella bridge `scitex/_mcp_tools/{short}.py` "
                "hand-wraps tools — convert to `safe_mount(mcp, sub_mcp, namespace=…)` "
                "(see scitex/_mcp_tools/cloud.py)",
            )
        )
        return  # don't double-report

    if has_plain_mount and not has_safe_mount:
        out.append(
            Violation(
                package,
                "§1",
                f"umbrella bridge `scitex/_mcp_tools/{short}.py` "
                "uses direct `mcp.mount(...)` — replace with `safe_mount(mcp, sub_mcp)` "
                "from `scitex._mcp_tools._compat` for FastMCP 2.x/3.x portability",
            )
        )
