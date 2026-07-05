#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/_cli/_mcp.py
"""MCP CLI sub-group for scitex-container.

Commands:
- scitex-container mcp list-tools   List all registered MCP tools
- scitex-container mcp doctor       Check FastMCP availability and tool health
- scitex-container mcp start        Start the MCP server
"""

from __future__ import annotations

import click


@click.group(invoke_without_command=True)
@click.option("--help-recursive", is_flag=True, help="Show help for all subcommands")
@click.pass_context
def mcp(ctx, help_recursive):
    """MCP (Model Context Protocol) server management."""
    if help_recursive:
        _print_help_recursive(ctx)
        ctx.exit(0)
    elif ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _print_help_recursive(ctx):
    """Print help for mcp and all its subcommands."""
    fake_parent = click.Context(click.Group(), info_name="scitex-container")
    parent_ctx = click.Context(mcp, info_name="mcp", parent=fake_parent)

    click.secho("━━━ scitex-container mcp ━━━", fg="cyan", bold=True)
    click.echo(mcp.get_help(parent_ctx))

    for name in sorted(mcp.list_commands(ctx) or []):
        cmd = mcp.get_command(ctx, name)
        if cmd is None:
            continue
        click.echo()
        click.secho(f"━━━ scitex-container mcp {name} ━━━", fg="cyan", bold=True)
        with click.Context(cmd, info_name=name, parent=parent_ctx) as sub_ctx:
            click.echo(cmd.get_help(sub_ctx))


def _format_tool_signature(tool_name: str, tool_obj) -> str:
    """Format an MCP tool as a Python-like function signature."""
    if not hasattr(tool_obj, "parameters") or not tool_obj.parameters:
        return f"  {click.style(tool_name, fg='green', bold=True)}()"

    schema = tool_obj.parameters
    props = schema.get("properties", {})
    required = schema.get("required", [])

    params = []
    for name, info in props.items():
        ptype = info.get("type", "any")
        default = info.get("default")
        if name in required:
            p = f"{click.style(name, fg='white', bold=True)}: {click.style(ptype, fg='cyan')}"
        elif default is not None:
            def_str = repr(default) if len(repr(default)) < 20 else "..."
            p = (
                f"{click.style(name, fg='white', bold=True)}: "
                f"{click.style(ptype, fg='cyan')} = {click.style(def_str, fg='yellow')}"
            )
        else:
            p = (
                f"{click.style(name, fg='white', bold=True)}: "
                f"{click.style(ptype, fg='cyan')} = {click.style('None', fg='yellow')}"
            )
        params.append(p)

    name_s = click.style(tool_name, fg="green", bold=True)
    return f"  {name_s}({', '.join(params)})"


@mcp.command("list-tools")
@click.option(
    "-v", "--verbose", count=True, help="Verbosity: -v signatures, -vv +description"
)
@click.option(
    "--json", "as_json", is_flag=True, help="Emit machine-readable JSON output."
)
@click.pass_context
def list_tools(ctx, verbose: int, as_json: bool):
    """List all registered MCP tools with signatures.

    \b
    Example:
      $ scitex-container mcp list-tools
      $ scitex-container mcp list-tools -vv
      $ scitex-container mcp list-tools --json
    """
    import json as _json

    ctx.ensure_object(dict)
    if not as_json:
        as_json = bool(ctx.obj.get("as_json"))

    try:
        from scitex_container.mcp_server import FASTMCP_AVAILABLE
        from scitex_container.mcp_server import mcp as mcp_server
    except ImportError:
        if as_json:
            click.echo(
                _json.dumps({"error": "Could not import MCP server", "tools": []})
            )
            raise SystemExit(1) from None
        click.secho("ERROR: Could not import MCP server", fg="red", err=True)
        raise SystemExit(1) from None

    if not FASTMCP_AVAILABLE:
        if as_json:
            click.echo(_json.dumps({"error": "FastMCP not installed", "tools": []}))
            raise SystemExit(1)
        click.secho(
            "ERROR: FastMCP not installed. Run: pip install 'scitex-container[mcp]'",
            fg="red",
            err=True,
        )
        raise SystemExit(1)

    if mcp_server is None:
        if as_json:
            click.echo(
                _json.dumps({"error": "MCP server not initialized", "tools": []})
            )
            raise SystemExit(1)
        click.secho("ERROR: MCP server not initialized", fg="red", err=True)
        raise SystemExit(1)

    # Collect tools via FastMCP internal registry
    from scitex_dev import get_tools_sync

    tools_map = get_tools_sync(mcp_server)

    if as_json:
        import inspect as _inspect

        tools_payload = []
        for tool_name in sorted(tools_map.keys()):
            tool_obj = tools_map[tool_name]
            entry: dict = {"name": tool_name}
            params_schema = getattr(tool_obj, "parameters", None)
            if params_schema:
                entry["parameters"] = params_schema
            desc = getattr(tool_obj, "description", None)
            if desc and isinstance(desc, str):
                entry["description"] = desc
            elif hasattr(tool_obj, "fn") and tool_obj.fn:
                doc = _inspect.getdoc(tool_obj.fn)
                if doc:
                    entry["description"] = doc
            tools_payload.append(entry)
        click.echo(
            _json.dumps(
                {"package": "scitex-container", "tools": tools_payload}, indent=2
            )
        )
        return

    if not tools_map:
        click.secho("No tools registered (or unable to inspect).", fg="yellow")
        return

    click.secho(f"scitex-container MCP: {len(tools_map)} tools", fg="cyan", bold=True)
    click.echo()

    for tool_name in sorted(tools_map.keys()):
        tool_obj = tools_map[tool_name]
        if verbose == 0:
            click.echo(f"  {tool_name}")
        elif verbose == 1:
            click.echo(_format_tool_signature(tool_name, tool_obj))
        else:
            click.echo(_format_tool_signature(tool_name, tool_obj))
            desc = getattr(tool_obj, "description", None)
            if desc and isinstance(desc, str):
                click.echo(f"    {desc.split(chr(10))[0].strip()}")
            elif hasattr(tool_obj, "fn") and tool_obj.fn:
                import inspect

                docstring = inspect.getdoc(tool_obj.fn)
                if docstring:
                    click.echo(f"    {docstring.split(chr(10))[0].strip()}")
            click.echo()


@mcp.command("doctor")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed diagnostics")
def doctor(verbose: bool):
    """Check FastMCP availability and MCP tool health.

    \b
    Example:
      $ scitex-container mcp doctor
      $ scitex-container mcp doctor -v
    """
    issues = []

    click.secho("scitex-container MCP Doctor", fg="cyan", bold=True)
    click.echo()

    # Check 1: FastMCP installation
    click.echo("Checking FastMCP installation... ", nl=False)
    try:
        from fastmcp import FastMCP  # noqa: F401

        click.secho("OK", fg="green")
        if verbose:
            import fastmcp

            click.echo(f"  Version: {getattr(fastmcp, '__version__', 'unknown')}")
    except ImportError:
        click.secho("FAIL", fg="red")
        issues.append("FastMCP not installed. Run: pip install 'scitex-container[mcp]'")

    # Check 2: MCP server import
    click.echo("Checking MCP server module... ", nl=False)
    try:
        from scitex_container.mcp_server import FASTMCP_AVAILABLE
        from scitex_container.mcp_server import mcp as mcp_server

        if FASTMCP_AVAILABLE and mcp_server is not None:
            click.secho("OK", fg="green")
        else:
            click.secho("WARN", fg="yellow")
    except ImportError as e:
        click.secho("FAIL", fg="red")
        issues.append(f"Could not import MCP server: {e}")

    # Check 3: Handler imports
    click.echo("Checking MCP handlers... ", nl=False)
    try:
        from scitex_container._mcp.handlers import (  # noqa: F401
            build_handler,
            host_check_handler,
            status_handler,
        )

        click.secho("OK", fg="green")
    except ImportError as e:
        click.secho("FAIL", fg="red")
        issues.append(f"Could not import handlers: {e}")

    # Check 4: Tool count
    click.echo("Checking tool registration... ", nl=False)
    try:
        from scitex_container.mcp_server import mcp as mcp_server

        if mcp_server is not None:
            from scitex_dev import get_tools_sync

            tools_map = get_tools_sync(mcp_server)
            n = len(tools_map)
            if n >= 10:
                click.secho(f"OK ({n} tools)", fg="green")
            else:
                click.secho(f"WARN ({n} tools, expected 10+)", fg="yellow")
        else:
            click.secho("SKIP (FastMCP unavailable)", fg="yellow")
    except Exception as e:
        click.secho("FAIL", fg="red")
        issues.append(f"Tool registration check failed: {e}")

    # Summary
    click.echo()
    if issues:
        click.secho(f"Issues Found: {len(issues)}", fg="red", bold=True)
        for issue in issues:
            click.echo(f"  x {issue}")
    else:
        click.secho("All checks passed!", fg="green", bold=True)

    raise SystemExit(1 if issues else 0)


@mcp.command("start")
@click.option(
    "--transport",
    "-t",
    type=click.Choice(["stdio", "sse", "http"]),
    default="stdio",
    help="Transport type (default: stdio)",
)
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
@click.option(
    "--port", "-p", default=8086, type=int, help="Port to bind (default: 8086)"
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
def start(transport: str, host: str, port: int, dry_run: bool, yes: bool):
    """Start the MCP server.

    \b
    Example:
      $ scitex-container mcp start
      $ scitex-container mcp start --transport http --port 8086
      $ scitex-container mcp start --dry-run
    """
    if dry_run:
        click.echo(
            f"[dry-run] would start MCP server transport={transport} "
            f"host={host} port={port}"
        )
        return
    _ = yes
    try:
        from scitex_container.mcp_server import FASTMCP_AVAILABLE
        from scitex_container.mcp_server import mcp as mcp_server
    except ImportError:
        click.secho("ERROR: Could not import MCP server", fg="red", err=True)
        click.echo("Run: pip install 'scitex-container[mcp]'")
        raise SystemExit(1) from None

    if not FASTMCP_AVAILABLE or mcp_server is None:
        click.secho(
            "ERROR: MCP server not available (FastMCP missing)", fg="red", err=True
        )
        raise SystemExit(1)

    click.secho(f"Starting MCP server (transport={transport})...", fg="cyan")
    if transport == "stdio":
        mcp_server.run(transport="stdio")
    else:
        mcp_server.run(transport=transport, host=host, port=port)


@mcp.command("install")
@click.option("--claude-code", is_flag=True, help="Show Claude Code config snippet.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--dry-run", is_flag=True, help="Accepted for §2; this verb is informational, never mutates state.")
@click.option("--yes", "-y", is_flag=True, help="Accepted for §2; this verb is informational, never mutates state.")
def install(claude_code: bool, as_json: bool, dry_run, yes):
    """Show MCP installation instructions.

    \b
    Example:
      $ scitex-container mcp install
      $ scitex-container mcp install --claude-code
    """
    del dry_run, yes  # audit §2 — no-op flags
    config = {
        "mcpServers": {
            "scitex-container": {
                "command": "scitex-container",
                "args": ["mcp", "start"],
            }
        }
    }
    if as_json:
        import json as _json

        click.echo(
            _json.dumps(
                {
                    "install_command": "pip install scitex-container[mcp]",
                    "config": config,
                    "verify_commands": ["scitex-container mcp doctor"],
                },
                indent=2,
            )
        )
        return

    if claude_code:
        click.secho("Add to Claude Code MCP config:", fg="cyan")
        click.echo()
        click.echo('  "scitex-container": {')
        click.echo('    "command": "scitex-container",')
        click.echo('    "args": ["mcp", "start"]')
        click.echo("  }")
        return

    click.secho("scitex-container MCP Server Installation", fg="cyan", bold=True)
    click.echo("=" * 40)
    click.echo()
    click.echo("1. Install: pip install scitex-container[mcp]")
    click.echo("2. Config:  scitex-container mcp install --claude-code")
    click.echo("3. Test:    scitex-container mcp doctor")


# EOF
