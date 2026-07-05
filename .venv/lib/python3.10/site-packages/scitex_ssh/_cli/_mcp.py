#!/usr/bin/env python3
"""MCP CLI subcommands for scitex-ssh."""

import click


@click.group()
def mcp():
    """MCP server management."""


@mcp.command()
@click.option("--dry-run", is_flag=True, help="Print launch plan without starting.")
@click.option(
    "-y", "--yes", is_flag=True, help="Suppress interactive confirmation (assume yes)."
)
def start(dry_run, yes):
    """Start the MCP server.

    \b
    Example:
      $ scitex-ssh mcp start
      $ scitex-ssh mcp start --dry-run
    """
    if dry_run:
        click.echo("DRY RUN — would start scitex-ssh MCP server (stdio transport)")
        return
    try:
        from scitex_ssh._mcp._server import create_server

        server = create_server()
        server.run()
    except ImportError:
        click.secho(
            "ERROR: fastmcp is not installed. Install with: pip install scitex-ssh[mcp]",
            fg="red",
            err=True,
        )
        raise SystemExit(1)


@mcp.command()
def doctor():
    """Check MCP server dependencies and configuration.

    \b
    Example:
      $ scitex-ssh mcp doctor
    """
    issues = []

    try:
        import fastmcp  # noqa: F401

        click.secho("  fastmcp: installed", fg="green")
    except ImportError:
        click.secho("  fastmcp: NOT installed", fg="red")
        issues.append("pip install scitex-ssh[mcp]")

    import shutil

    if shutil.which("autossh"):
        click.secho("  autossh: installed", fg="green")
    else:
        click.secho("  autossh: NOT installed", fg="red")
        issues.append("sudo apt install autossh")

    if issues:
        click.echo()
        click.echo("Fix with:")
        for fix in issues:
            click.echo(f"  {fix}")
        raise SystemExit(1)
    else:
        click.secho("\nAll checks passed.", fg="green")


@mcp.command(
    "installation", hidden=True, context_settings={"ignore_unknown_options": True}
)
@click.pass_context
def installation_deprecated(ctx):
    """(deprecated) Renamed to `show-installation`."""
    click.echo(
        "error: `scitex-ssh mcp installation` was renamed to "
        "`scitex-ssh mcp show-installation`.\n"
        "Re-run with: scitex-ssh mcp show-installation",
        err=True,
    )
    ctx.exit(2)


@mcp.command("show-installation")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def show_installation(as_json):
    """Show MCP server installation instructions.

    \b
    Example:
      $ scitex-ssh mcp show-installation
      $ scitex-ssh mcp show-installation --json
    """
    config = {
        "mcpServers": {
            "scitex-ssh": {
                "command": "scitex-ssh",
                "args": ["mcp", "start"],
            }
        }
    }
    if as_json:
        import json as _json

        click.echo(
            _json.dumps(
                {
                    "install_command": "pip install scitex-ssh[mcp]",
                    "config": config,
                    "verify_commands": ["scitex-ssh mcp doctor"],
                },
                indent=2,
            )
        )
        return

    click.echo("Install scitex-ssh with MCP support:")
    click.echo()
    click.echo("  pip install scitex-ssh[mcp]")
    click.echo()
    click.echo("Add to your Claude Code MCP config:")
    click.echo()
    import json as _json

    for line in _json.dumps(config, indent=2).split("\n"):
        click.echo(f"  {line}")


@mcp.command("list-tools")
@click.option("-v", "--verbose", count=True, help="Verbosity (-v, -vv, -vvv).")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_tools(verbose, as_json):
    """List available MCP tools.

    \b
    Example:
      $ scitex-ssh mcp list-tools
      $ scitex-ssh mcp list-tools -vv
      $ scitex-ssh mcp list-tools --json
    """
    tools = [
        (
            "tunnel_setup",
            "Set up a persistent SSH reverse tunnel",
            "port, bastion_server, secret_key_path",
        ),
        ("tunnel_status", "Check status of SSH reverse tunnels", "port (optional)"),
        ("tunnel_remove", "Remove a persistent SSH reverse tunnel", "port"),
    ]

    if as_json:
        import json as _json

        click.echo(
            _json.dumps(
                {
                    "total": len(tools),
                    "tools": [
                        {"name": n, "description": d, "params": p} for n, d, p in tools
                    ],
                },
                indent=2,
            )
        )
        return

    click.echo("scitex-ssh MCP tools:")
    click.echo()
    for name, desc, params in tools:
        if verbose >= 2:
            click.echo(f"  {name:20s} {desc}")
            click.echo(f"  {' ':20s} params: {params}")
        elif verbose >= 1:
            click.echo(f"  {name:20s} {desc}")
        else:
            click.echo(f"  {name}")


# EOF
