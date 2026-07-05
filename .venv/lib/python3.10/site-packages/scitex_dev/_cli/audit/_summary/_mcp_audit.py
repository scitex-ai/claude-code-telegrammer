"""MCP-tool auditor — companion to `audit-cli`.

Walks each `scitex-*` package's `_mcp_server.mcp` instance (FastMCP) and the
matching umbrella bridge under `scitex._mcp_tools.<pkg>`; checks against the
canonical MCP convention in
`<scitex-python>/src/scitex/_skills/general/03_interface/03_mcp/`.

Rules (matching that skill's section numbers):

- §1   server registration  — one `FastMCP` per package, mount-pattern bridge,
                              no double prefix, no hand-wrap.
- §2   tool naming          — `<pkg>_<verb>_<noun>` snake_case, no banned
                              shapes / synonyms.
- §3   required subcommands — `mcp start | doctor | list-tools | show-installation`
                              on the package CLI (delegated to the existing
                              `audit-cli` walker).
- §4   list-tools ladder    — `-v|-vv|-vvv` + `--json` (behavioral, opt-in).
- §5   skills integration   — `<pkg>_skills_list` and `<pkg>_skills_get` exist.
- §6   Python-API parity    — every tool wraps a public Python API (and v.v.).

The auditor reuses every helper that already exists in `_audit.py`:
registry cascade, severity tiers, filter helpers, watchdog, stream isolation,
human/JSON emitters.
"""

from __future__ import annotations

import click

from . import FLAT_KEEPERS  # noqa: F401  -- reserved for future verb checks
from ._audit import (
    Violation,
    _emit_human,
    _emit_json,
    _filter_violations,
    _isolated_streams,
    _load_registry,
    _max_severity,
    _PackageTimeout,
    _violation_to_dict,
    _watchdog,
)


# --------------------------------------------------------------------- #
# Helpers — locate the standalone MCP server + umbrella bridge          #
# --------------------------------------------------------------------- #


# `_import_name` / `_short_name` are extracted to `_mcp_names` so the §6
# parity split (`_mcp_parity`) can reuse them without a circular import.
from ._mcp_names import _import_name, _short_name  # noqa: E402,F401


# Packages we never audit as MCP standalones (they have no user-facing
# `_mcp_server.mcp` instance of their own). The umbrella `scitex` mounts
# everything; *-mcp / *-server packages ARE the protocol servers.
_MCP_AUDIT_SKIP_PACKAGES = {"scitex"}


def _should_skip(package: str) -> bool:
    if package in _MCP_AUDIT_SKIP_PACKAGES:
        return True
    if package.endswith("-mcp") or package.endswith("-server"):
        return True
    return False


def _list_tools(mcp_instance) -> list:
    """List a FastMCP server's tools; return a list of Tool/FunctionTool.

    Routes through `get_tools_sync` (the FastMCP 2.x/3.x version bridge) so the
    audit works on both: FastMCP 2.x exposes `get_tools()` (dict) while 3.x
    renamed it to `list_tools()` (list). The shim returns `{name: Tool}`; the
    callers here only need a list of objects with a `.name`.
    """
    from scitex_dev._ecosystem._mcp import get_tools_sync

    return list(get_tools_sync(mcp_instance).values())


# --------------------------------------------------------------------- #
# §2 / §5 — tool-name discipline (extracted to `_mcp_tool_naming`)       #
# §1     — bridge / mount-pattern discipline (extracted to `_mcp_bridge`)#
# --------------------------------------------------------------------- #
# Same line-budget rationale as the §6 split (`_mcp_parity`). Re-exported
# here to preserve every existing call site and test import.
from ._mcp_tool_naming import (  # noqa: E402
    _check_skills_pair,
    _check_tool_naming,
    _OBJECT_FROM_PARAM_VERBS,  # noqa: F401  -- re-export for future use
    _TOOL_NAME_SYNONYMS,  # noqa: F401  -- re-export for test importers
    _VALID_NAME,  # noqa: F401  -- re-export for test importers
    _VERBS_NEED_NOUN,  # noqa: F401  -- re-export for test importers
)
from ._mcp_bridge import (  # noqa: E402
    _check_bridge_pattern,
    _default_import_bridge_pkg,  # noqa: F401  -- re-export for test injection
    _HAND_WRAP_DECORATOR,  # noqa: F401  -- re-export for test importers
    _PLAIN_MOUNT_CALL,  # noqa: F401  -- re-export for test importers
    _read_bridge_source,
    _resolve_mcp_server,
    _SAFE_MOUNT_CALL,  # noqa: F401  -- re-export for test importers
)


# --------------------------------------------------------------------- #
# §6 — Python API parity (extracted to `_mcp_parity`)                    #
# --------------------------------------------------------------------- #
# The §6 parity/orphan check and its per-package `mcp_parity_exempt`
# opt-out live in `_mcp_parity` so this orchestrator stays under the
# per-file line budget. Re-exported here to preserve the `_audit_one_mcp`
# call site and any external importers.
from ._mcp_parity import (  # noqa: E402
    _check_api_parity,
    _python_api_names,  # noqa: F401  -- re-export for parity-test importers
    is_mcp_parity_exempt,  # noqa: F401  -- re-export for convenience
)


# --------------------------------------------------------------------- #
# Single-package audit                                                   #
# --------------------------------------------------------------------- #


def _audit_one_mcp(
    package: str, behavioral: bool = False, timeout: float = 30.0
) -> tuple[str, list[Violation]]:
    """Audit a single package's MCP surface; return (status, violations).

    Status: "ok" | "warn" | "no-mcp-server" | "skip-not-standalone" | "not-auditable: <reason>".
    """
    if _should_skip(package):
        # Umbrella + protocol-server packages aren't user-facing MCP standalones.
        return "skip-not-standalone", []

    with _isolated_streams():
        mcp_instance = _resolve_mcp_server(package)

    out: list[Violation] = []

    # Bridge-pattern check works from the umbrella source alone — run it even
    # when the standalone can't be imported, so `mcp.mount(...)`-style drift
    # is still surfaced for legacy packages whose mcp module path is unusual.
    if mcp_instance is None:
        _check_bridge_pattern(package, out)
        if out:
            return "warn", out
        return "no-mcp-server", []

    # Enumerate tools (may itself be slow / fail) under stream isolation.
    tools = []
    try:
        with _isolated_streams():
            tools = _list_tools(mcp_instance)
    except Exception as e:
        return f"not-auditable: list_tools failed: {type(e).__name__}: {e}", []

    tool_names = [getattr(t, "name", "") for t in tools]
    tool_set = {n for n in tool_names if n}

    _check_tool_naming(package, tool_names, out)
    _check_skills_pair(package, tool_set, out)
    _check_bridge_pattern(package, out)
    _check_api_parity(package, tool_set, out)

    # Behavioral checks (§4 ladder + §3 subcommand presence) reuse the CLI
    # auditor's subprocess machinery to avoid duplicating it.
    if behavioral:
        _check_behavioral_mcp(package, tool_set, out, timeout=timeout)

    return ("ok" if not out else "warn"), out


def _check_behavioral_mcp(
    package: str, tool_names: set[str], out: list[Violation], timeout: float = 30.0
) -> None:
    """§3 / §4 — invoke `<cli> mcp …` subcommands and verify behavior."""
    from ._audit import _run_subprocess  # reuse

    # §3 — required mcp subcommands. Probe each via `--help`; expect exit 0.
    for sub in ("start", "doctor", "list-tools", "show-installation"):
        rc, _so, _se = _run_subprocess(
            [package, "mcp", sub, "--help"], timeout=max(2.0, min(timeout, 10.0))
        )
        if rc != 0 and rc != -1:
            out.append(
                Violation(
                    f"{package} mcp {sub}",
                    "§3",
                    f"missing required subcommand `mcp {sub}` (--help exited {rc})",
                )
            )

    # §4 — verbosity ladder. Each level should produce ⊇ output.
    levels = [[], ["-v"], ["-vv"], ["-vvv"]]
    counts: list[int] = []
    for extra in levels:
        rc, so, _se = _run_subprocess(
            [package, "mcp", "list-tools", *extra], timeout=max(2.0, min(timeout, 10.0))
        )
        counts.append(
            len([ln for ln in so.splitlines() if ln.strip()]) if rc == 0 else -1
        )
    if all(c >= 0 for c in counts):
        for i in range(1, len(counts)):
            if counts[i] < counts[i - 1]:
                out.append(
                    Violation(
                        f"{package} mcp list-tools",
                        "§4",
                        f"verbosity ladder not monotonic: -{'v' * i} produced fewer "
                        f"non-empty lines ({counts[i]}) than -{'v' * (i - 1)} "
                        f"({counts[i - 1]})",
                    )
                )
                break

    # §4 — --json must produce parseable JSON on stdout.
    rc, so, _se = _run_subprocess(
        [package, "mcp", "list-tools", "--json"], timeout=max(2.0, min(timeout, 10.0))
    )
    if rc == 0 and so.strip():
        import json as _json

        try:
            _json.loads(so)
        except _json.JSONDecodeError:
            out.append(
                Violation(
                    f"{package} mcp list-tools",
                    "§4",
                    "--json stdout is not parseable JSON (log contamination?)",
                )
            )


# --------------------------------------------------------------------- #
# Public entry points                                                    #
# --------------------------------------------------------------------- #


def run_audit_mcp(
    package: str,
    behavioral: bool = False,
    output_json: bool = False,
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Audit a single package's MCP surface (single-target mode)."""
    try:
        from ...._ecosystem import should_skip_audit
    except ImportError:
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(package, "audit-mcp-tools")
    from .._emit import emit as _emit

    if skip:
        if output_json:
            rec = {"package": package, "status": f"skip-{reason}", "violations": []}
            _emit_json([rec], "single-package mode (mcp)")
        else:
            _emit("skip", f"{package}: {reason}")
        return 0
    status, violations = _audit_one_mcp(package, behavioral=behavioral, timeout=timeout)
    violations = _filter_violations(violations, rules, exclude, min_severity)
    if not violations and status == "warn":
        status = "ok"
    if output_json:
        rec = {
            "package": package,
            "status": status,
            "violations": [_violation_to_dict(v) for v in violations],
        }
        _emit_json([rec], "single-package mode (mcp)")
    else:
        if status == "no-mcp-server":
            _emit("info", f"{package}: no `_mcp_server.mcp` found — skipped")
        elif status == "skip-not-standalone":
            _emit(
                "info",
                f"{package}: not an MCP standalone (umbrella or protocol-server) — skipped",
            )
        else:
            _emit_human(package, status, violations)
    if status.startswith("not-auditable"):
        return 2
    return 1 if _max_severity(violations) == "error" else 0


def run_audit_mcp_all(
    behavioral: bool = False,
    output_json: bool = False,
    dry_run: bool = False,
    registry_path: str | Path | None = None,
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Audit every MCP-bearing package in the registry."""
    # Duplicate fd 1 and fd 2 *before* importing any audit target. Some
    # packages close fd 1 during import (MCP servers, asyncio bots).
    # Writing the final summary through these duplicates is the only way
    # to guarantee output reaches the user.
    import os as _os

    try:
        _safe_stdout_fd = _os.dup(1)
        _safe_stderr_fd = _os.dup(2)
    except OSError:
        _safe_stdout_fd = 1
        _safe_stderr_fd = 2

    registry, provenance = _load_registry(registry_path)
    targets: list[str] = []
    for name in registry:
        # Quick filter: a package is auditable if a standalone _mcp_server module
        # exists. We don't import here (deferred to per-target run).
        targets.append(name)

    if dry_run:
        if output_json:
            payload = {
                "registry_source": provenance,
                "dry_run": True,
                "targets": [{"package": n, "action": "audit-mcp"} for n in targets],
            }
            import json as _json

            click.echo(_json.dumps(payload, indent=2))
        else:
            click.echo(f"# registry: {provenance}")
            click.echo(f"# {len(targets)} package(s) — dry-run, no audit performed")
            for n in targets:
                click.echo(f"  audit-mcp    {n}")
        return 0

    records: list[dict] = []
    counts = {
        "ok": 0,
        "warn": 0,
        "no-mcp-server": 0,
        "skip-not-standalone": 0,
        "not-auditable": 0,
    }
    any_error = False
    for name in targets:
        wall_budget = max(timeout + 5.0, 10.0)
        try:
            with _watchdog(wall_budget):
                status, violations = _audit_one_mcp(
                    name, behavioral=behavioral, timeout=timeout
                )
        except _PackageTimeout:
            status, violations = (
                f"not-auditable: timed out after {wall_budget:.0f}s",
                [],
            )

        violations = _filter_violations(violations, rules, exclude, min_severity)
        if not violations and status == "warn":
            status = "ok"

        if not output_json:
            # Don't spam the human report with one line per non-MCP package.
            if status not in ("no-mcp-server", "skip-not-standalone"):
                _emit_human(name, status, violations)

        if _max_severity(violations) == "error" or status.startswith("not-auditable"):
            any_error = True

        records.append(
            {
                "package": name,
                "status": status,
                "violations": [_violation_to_dict(v) for v in violations],
            }
        )
        bucket = "not-auditable" if status.startswith("not-auditable") else status
        counts[bucket] = counts.get(bucket, 0) + 1

    # Accumulated side effects from importing 60+ packages (especially MCP
    # servers that close stdio on init) can leave sys.stdout / click.echo
    # unwritable. For the post-loop summary we bypass Python's stream
    # wrapping and write directly to fd 1 via os.write — guaranteed to
    # land in the user's terminal/pipe regardless of what packages did.
    import os as _os

    def _write1(text: str) -> None:
        try:
            _os.write(_safe_stdout_fd, text.encode("utf-8", errors="replace"))
        except OSError:
            # The duplicate is closed too — try the original fd 1 as last resort.
            try:
                _os.write(1, text.encode("utf-8", errors="replace"))
            except OSError:
                pass

    if output_json:
        import json as _json

        payload = {"registry_source": provenance, "results": records}
        _write1(_json.dumps(payload, indent=2) + "\n")
    else:
        _write1("\n")
        _write1(f"# registry: {provenance}\n")
        _write1(
            f"# summary: {counts['ok']} ok, {counts['warn']} warn, "
            f"{counts['no-mcp-server']} no-mcp-server, "
            f"{counts['skip-not-standalone']} skip-not-standalone, "
            f"{counts['not-auditable']} not-auditable\n"
        )
    return 1 if any_error else 0
