#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI command: scitex-dev doctor -- diagnose the full SciTeX ecosystem."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Literal

import click

Status = Literal["ok", "fail", "skip"]

OK_TAG = "[OK]"
FAIL_TAG = "[!!]"
SKIP_TAG = "[--]"


def _tag(status: Status) -> str:
    return {
        "ok": OK_TAG,
        "fail": FAIL_TAG,
        "skip": SKIP_TAG,
    }[status]


def _color(status: Status) -> str:
    return {
        "ok": "green",
        "fail": "red",
        "skip": "yellow",
    }[status]


def _result(label: str, status: Status, detail: str = "") -> dict:
    return {"check": label, "status": status, "detail": detail}


def _echo_result(r: dict) -> None:
    status = r["status"]
    tag = click.style(_tag(status), fg=_color(status))
    line = f"  {tag}  {r['check']}"
    if r["detail"]:
        line += f": {r['detail']}"
    click.echo(line)


# ------------------------------------------------------------------
# Individual checks
# ------------------------------------------------------------------


def check_python_version() -> dict:
    vi = sys.version_info
    ver_str = f"{vi.major}.{vi.minor}.{vi.micro}"
    ok = (vi.major, vi.minor) >= (3, 10)
    status = "ok" if ok else "fail"
    detail = ver_str if ok else f"{ver_str} (requires >= 3.10)"
    return _result("Python version", status, detail)


def check_venv() -> dict:
    in_venv = sys.prefix != sys.base_prefix or os.environ.get("VIRTUAL_ENV")
    if in_venv:
        venv_path = os.environ.get("VIRTUAL_ENV", sys.prefix)
        return _result("Virtual environment", "ok", venv_path)
    return _result("Virtual environment", "fail", "not active")


def check_scitex_packages() -> list[dict]:
    from importlib.metadata import PackageNotFoundError, version as pkg_version

    packages = [
        "scitex",
        "scitex-dev",
        "scitex-orochi",
        "scitex-agent-container",
    ]
    results = []
    for pkg in packages:
        try:
            ver = pkg_version(pkg)
            results.append(_result(f"Package {pkg}", "ok", f"v{ver}"))
        except PackageNotFoundError:
            results.append(_result(f"Package {pkg}", "skip", "not installed"))
    return results


def check_pypi_versions() -> list[dict]:
    """Compare installed scitex packages against PyPI latest."""
    from importlib.metadata import PackageNotFoundError, version as pkg_version

    packages = [
        "scitex",
        "scitex-dev",
        "scitex-orochi",
        "scitex-agent-container",
    ]
    results = []
    for pkg in packages:
        try:
            local_ver = pkg_version(pkg)
        except PackageNotFoundError:
            continue

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "index", "versions", pkg],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                # Output: "package (X.Y.Z)"
                line = proc.stdout.strip().split("\n")[0]
                if "(" in line:
                    pypi_ver = line.split("(")[1].split(")")[0].strip()
                    if pypi_ver == local_ver:
                        results.append(
                            _result(f"PyPI {pkg}", "ok", f"v{local_ver} (latest)")
                        )
                    else:
                        results.append(
                            _result(
                                f"PyPI {pkg}",
                                "fail",
                                f"v{local_ver} installed, v{pypi_ver} available",
                            )
                        )
                else:
                    results.append(
                        _result(f"PyPI {pkg}", "skip", "could not parse version")
                    )
            else:
                results.append(
                    _result(f"PyPI {pkg}", "skip", "pip index not available")
                )
        except Exception:
            results.append(_result(f"PyPI {pkg}", "skip", "version check failed"))
    return results


def check_env_vars() -> list[dict]:
    results = []

    # SCITEX_DIR
    scitex_dir = os.environ.get("SCITEX_DIR")
    if scitex_dir:
        results.append(_result("SCITEX_DIR", "ok", scitex_dir))
    else:
        results.append(_result("SCITEX_DIR", "fail", "not set"))

    # Orochi vars (only if scitex-orochi installed)
    try:
        from importlib.metadata import version as pkg_version

        pkg_version("scitex-orochi")
        orochi_installed = True
    except Exception:
        orochi_installed = False

    if orochi_installed:
        for var in [
            "SCITEX_OROCHI_HOST",
            "SCITEX_OROCHI_PORT",
            "SCITEX_OROCHI_TOKEN",
        ]:
            val = os.environ.get(var)
            if val:
                # Mask token values
                display = "***" if "TOKEN" in var else val
                results.append(_result(var, "ok", display))
            else:
                results.append(_result(var, "skip", "not set"))

    # MCP toggles
    mcp_vars = [k for k in os.environ if k.startswith("SCITEX_MCP_USE_")]
    if mcp_vars:
        for var in sorted(mcp_vars):
            results.append(_result(var, "ok", os.environ[var]))

    # DISABLE vars
    disable_vars = [k for k in os.environ if "DISABLE" in k and "SCITEX" in k]
    for var in sorted(disable_vars):
        results.append(
            _result(var, "fail", f"set to {os.environ[var]} (feature disabled)")
        )

    return results


def check_mcp_server() -> list[dict]:
    results = []

    try:
        import fastmcp  # noqa: F401

        results.append(_result("fastmcp", "ok", "installed"))
    except ImportError:
        results.append(_result("fastmcp", "skip", "not installed"))
        return results

    try:
        from scitex_dev._mcp._server import mcp as mcp_server
        from scitex_dev._ecosystem._mcp import get_tools_sync

        tool_count = len(get_tools_sync(mcp_server))
        results.append(_result("MCP server tools", "ok", f"{tool_count} tools loaded"))
    except Exception as exc:
        results.append(_result("MCP server tools", "fail", str(exc)))

    return results


def check_orochi_connectivity() -> dict:
    try:
        from importlib.metadata import version as pkg_version

        pkg_version("scitex-orochi")
    except Exception:
        return _result("Orochi connectivity", "skip", "scitex-orochi not installed")

    host = os.environ.get("SCITEX_OROCHI_HOST", "localhost")
    port = os.environ.get("SCITEX_OROCHI_PORT", "8765")

    try:
        import asyncio
        import websockets  # noqa: F401

        async def _probe():
            uri = f"ws://{host}:{port}"
            async with websockets.connect(uri, open_timeout=3):
                return True

        asyncio.run(_probe())
        return _result("Orochi connectivity", "ok", f"ws://{host}:{port}")
    except ImportError:
        return _result("Orochi connectivity", "skip", "websockets not installed")
    except Exception as exc:
        return _result(
            "Orochi connectivity",
            "fail",
            f"ws://{host}:{port} -- {exc}",
        )


def check_agent_container() -> list[dict]:
    try:
        from importlib.metadata import version as pkg_version

        pkg_version("scitex-agent-container")
    except Exception:
        return [
            _result("Agent container", "skip", "scitex-agent-container not installed")
        ]

    results = []

    # Check screen sessions
    try:
        proc = subprocess.run(
            ["screen", "-ls"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = proc.stdout.strip()
        # Screen returns exit code 1 even when listing sessions
        sessions = [
            line.strip()
            for line in output.split("\n")
            if "." in line and ("Attached" in line or "Detached" in line)
        ]
        agent_sessions = [
            s for s in sessions if "agent" in s.lower() or "scitex" in s.lower()
        ]
        if agent_sessions:
            results.append(
                _result(
                    "Agent screen sessions",
                    "ok",
                    f"{len(agent_sessions)} session(s)",
                )
            )
        else:
            results.append(
                _result("Agent screen sessions", "skip", "no agent sessions found")
            )
    except FileNotFoundError:
        results.append(_result("Agent screen sessions", "skip", "screen not available"))
    except Exception as exc:
        results.append(_result("Agent screen sessions", "fail", str(exc)))

    return results


# ------------------------------------------------------------------
# Main command
# ------------------------------------------------------------------


def register_doctor_command(main_group):
    """Register the doctor command on the main CLI group."""

    @main_group.command("doctor")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def doctor_cmd(as_json: bool) -> None:
        """Diagnose the health of the full SciTeX ecosystem.

        \b
        Example:
            $ scitex-dev doctor --json
        """
        from importlib.metadata import version as pkg_version

        try:
            ver = pkg_version("scitex-dev")
        except Exception:
            ver = "dev"

        results: list[dict] = []

        if not as_json:
            click.echo()
            click.secho(f"scitex-dev doctor v{ver}", fg="cyan", bold=True)
            click.echo()

        # -- Python Environment --
        if not as_json:
            click.secho("Python Environment", bold=True)

        r = check_python_version()
        results.append(r)
        if not as_json:
            _echo_result(r)

        r = check_venv()
        results.append(r)
        if not as_json:
            _echo_result(r)
            click.echo()

        # -- SciTeX Packages --
        if not as_json:
            click.secho("SciTeX Packages", bold=True)

        for r in check_scitex_packages():
            results.append(r)
            if not as_json:
                _echo_result(r)

        for r in check_pypi_versions():
            results.append(r)
            if not as_json:
                _echo_result(r)

        if not as_json:
            click.echo()

        # -- Environment Variables --
        if not as_json:
            click.secho("Environment Variables", bold=True)

        for r in check_env_vars():
            results.append(r)
            if not as_json:
                _echo_result(r)

        if not as_json:
            click.echo()

        # -- MCP Server --
        if not as_json:
            click.secho("MCP Server", bold=True)

        for r in check_mcp_server():
            results.append(r)
            if not as_json:
                _echo_result(r)

        if not as_json:
            click.echo()

        # -- Orochi Connectivity --
        if not as_json:
            click.secho("Orochi Connectivity", bold=True)

        r = check_orochi_connectivity()
        results.append(r)
        if not as_json:
            _echo_result(r)
            click.echo()

        # -- Agent Container --
        if not as_json:
            click.secho("Agent Container", bold=True)

        for r in check_agent_container():
            results.append(r)
            if not as_json:
                _echo_result(r)

        if not as_json:
            click.echo()

        # -- Summary --
        ok_count = sum(1 for r in results if r["status"] == "ok")
        fail_count = sum(1 for r in results if r["status"] == "fail")
        skip_count = sum(1 for r in results if r["status"] == "skip")

        if as_json:
            click.echo(
                json.dumps(
                    {
                        "version": ver,
                        "checks": results,
                        "summary": {
                            "ok": ok_count,
                            "fail": fail_count,
                            "skip": skip_count,
                        },
                    },
                    indent=2,
                )
            )
        else:
            summary_parts = [
                click.style(f"{ok_count} ok", fg="green"),
                click.style(
                    f"{fail_count} issues", fg="red" if fail_count else "green"
                ),
                click.style(f"{skip_count} skipped", fg="yellow"),
            ]
            click.echo(", ".join(summary_parts))
            click.echo()

        if fail_count > 0:
            sys.exit(1)
