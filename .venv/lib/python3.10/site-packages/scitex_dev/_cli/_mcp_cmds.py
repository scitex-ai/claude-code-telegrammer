"""MCP (Model Context Protocol) subcommands for `scitex-dev`.

Extracted from `_root.py` to keep the orchestrator under the 512-line
budget. All commands attach to the root `main` group via
`register_mcp_commands(main)`.
"""

from __future__ import annotations

import json

import click


def register_mcp_commands(main: click.Group) -> click.Group:
    """Attach the `mcp` group + its subcommands to *main*."""

    @main.group(invoke_without_command=True)
    @click.option(
        "--help-recursive", is_flag=True, help="Show help for all subcommands."
    )
    @click.pass_context
    def mcp(ctx, help_recursive):
        """MCP (Model Context Protocol) server commands."""
        if help_recursive:
            _print_mcp_help_recursive(ctx, mcp)
            ctx.exit(0)
        elif ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @mcp.command("start")
    @click.option(
        "--dry-run", is_flag=True, help="Print what would be done; do not start."
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def mcp_start(dry_run, yes):
        """Start the scitex-dev MCP server.

        \b
        Example:
            $ scitex-dev mcp start
            $ scitex-dev mcp start --dry-run
        """
        del yes  # accepted for §2; mcp start is non-interactive
        if dry_run:
            click.echo("would start scitex-dev MCP server (fastmcp on stdio)")
            return
        try:
            from .._mcp._server import mcp as mcp_server
        except ImportError as e:
            raise click.ClickException(
                f"Failed to import MCP server. "
                f"Install fastmcp: pip install scitex-dev[mcp]\n{e}"
            ) from e

        click.echo("Starting scitex-dev MCP server...")
        mcp_server.run()

    @mcp.command("doctor")
    def mcp_doctor():
        """Check MCP server dependencies and configuration.

        \b
        Example:
            $ scitex-dev mcp doctor
        """
        click.echo("Checking MCP dependencies...")

        try:
            import fastmcp

            click.echo(f"  [OK] fastmcp {fastmcp.__version__}")
        except ImportError:
            click.echo("  [!!] fastmcp not installed")
            click.echo("    Install with: pip install scitex-dev[mcp]")
            return

        try:
            from .._mcp._server import mcp as mcp_server
            from .._ecosystem._mcp import get_tools_sync

            tool_count = len(get_tools_sync(mcp_server))
            click.echo(f"  [OK] MCP server loaded ({tool_count} tools)")
        except Exception as e:
            click.echo(f"  [!!] MCP server error: {e}")
            return

        click.echo()
        click.echo("MCP server is ready.")
        click.echo("Run with: scitex-dev mcp start")

    @mcp.command(
        "installation",
        hidden=True,
        context_settings={"ignore_unknown_options": True},
    )
    @click.pass_context
    def mcp_installation_deprecated(ctx):
        """(deprecated) Renamed to `install`."""
        click.echo(
            "error: `scitex-dev mcp installation` was renamed to "
            "`scitex-dev mcp install`.\n"
            "Re-run with: scitex-dev mcp install",
            err=True,
        )
        ctx.exit(2)

    @mcp.command(
        "show-installation",
        hidden=True,
        context_settings={"ignore_unknown_options": True},
    )
    @click.pass_context
    def mcp_show_installation_deprecated(ctx):
        """(deprecated) Renamed to `install`."""
        click.echo(
            "error: `scitex-dev mcp show-installation` was renamed to "
            "`scitex-dev mcp install`.\n"
            "Re-run with: scitex-dev mcp install",
            err=True,
        )
        ctx.exit(2)

    @mcp.command("install")
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Emit JSON manifest of MCP install instructions.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Accepted for §2 compliance; this command is informational and never mutates state.",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help="Accepted for §2 compliance; this command is informational and never mutates state.",
    )
    def mcp_install(as_json, dry_run, yes):
        """Show installation instructions for MCP server integration.

        \b
        Example:
            $ scitex-dev mcp install
            $ scitex-dev mcp install --json
        """
        del dry_run, yes  # accepted for §2 mutation flags; this verb is read-only
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "install": "pip install scitex-dev[mcp]",
                        "mcp_servers": {
                            "scitex-dev": {
                                "command": "scitex-dev",
                                "args": ["mcp", "start"],
                            },
                        },
                        "verify": [
                            "scitex-dev mcp doctor",
                            "scitex-dev mcp list-tools",
                        ],
                    },
                    indent=2,
                )
            )
            return
        click.echo("Install scitex-dev with MCP support:")
        click.echo()
        click.echo("  pip install scitex-dev[mcp]")
        click.echo()
        click.echo("Add to your MCP client configuration:")
        click.echo()
        click.echo("  {")
        click.echo('    "mcpServers": {')
        click.echo('      "scitex-dev": {')
        click.echo('        "command": "scitex-dev",')
        click.echo('        "args": ["mcp", "start"]')
        click.echo("      }")
        click.echo("    }")
        click.echo("  }")
        click.echo()
        click.echo("Verify with:")
        click.echo("  scitex-dev mcp doctor")
        click.echo("  scitex-dev mcp list-tools")

    @mcp.command("list-tools")
    @click.option(
        "-v", "--verbose", count=True, help="Verbosity: -v sig, -vv +desc, -vvv full."
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def mcp_list_tools(verbose, as_json):
        """List available MCP tools.

        \b
        Example:
            $ scitex-dev mcp list-tools
            $ scitex-dev mcp list-tools -vv
            $ scitex-dev mcp list-tools --json
        """
        try:
            from .._mcp._server import mcp as mcp_server
        except ImportError as e:
            raise click.ClickException(
                f"fastmcp not installed. Install with: pip install scitex-dev[mcp]\n{e}"
            ) from e

        from .._ecosystem._mcp import get_tools_sync

        tools = list(get_tools_sync(mcp_server).values())
        total = len(tools)

        if as_json:
            from .._core.types import RESULT_SCHEMA

            output = {
                "result_envelope": RESULT_SCHEMA,
                "total": total,
                "tools": [
                    {"name": t.name, "description": t.description or ""} for t in tools
                ],
            }
            click.echo(json.dumps(output, indent=2))
            return

        click.secho(f"scitex-dev MCP: {total} tools", fg="cyan", bold=True)
        click.echo(
            "Returns: Result{success, data, error, error_code, context, hints_on_error}"
        )
        click.echo()

        for tool in sorted(tools, key=lambda t: t.name):
            if verbose == 0:
                click.echo(f"  {tool.name}")
            else:
                click.echo(f"  {tool.name}")
                if tool.description:
                    desc = tool.description.split("\n")[0].strip()
                    click.echo(f"    {desc}")
                click.echo("    -> Result")
                click.echo()

    return mcp


def _print_mcp_help_recursive(ctx: click.Context, mcp_grp: click.Group) -> None:
    fake_parent = click.Context(click.Group(), info_name="scitex-dev")
    parent_ctx = click.Context(mcp_grp, info_name="mcp", parent=fake_parent)

    click.secho("=== scitex-dev mcp ===", fg="cyan", bold=True)
    click.echo(mcp_grp.get_help(parent_ctx))

    for name in sorted(mcp_grp.list_commands(ctx) or []):
        cmd = mcp_grp.get_command(ctx, name)
        if cmd is None:
            continue
        click.echo()
        click.secho(f"=== scitex-dev mcp {name} ===", fg="cyan", bold=True)
        with click.Context(cmd, info_name=name, parent=parent_ctx) as sub_ctx:
            click.echo(cmd.get_help(sub_ctx))


# EOF
