"""``scitex-dev linter mcp ...`` command group.

Extracted from ``cli.py`` (512-line budget). Registered onto the root
group via :func:`register`.
"""

from __future__ import annotations

import json
import sys

import click

from . import __version__
from .rules import ALL_RULES


def register(main_group):
    """Attach the ``mcp`` command group to ``main_group``."""

    @main_group.group("mcp", invoke_without_command=True)
    @click.pass_context
    def mcp_group(ctx):
        """MCP (Model Context Protocol) server management.

        \b
        Example:
            $ scitex-dev linter mcp start
            $ scitex-dev linter mcp list-tools
            $ scitex-dev linter mcp doctor
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @mcp_group.command("start")
    @click.option(
        "--transport",
        type=click.Choice(["stdio", "sse"]),
        default="stdio",
        help="Transport mode (default: stdio).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Show what would happen without starting the server.",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        default=False,
        help="Skip confirmation prompts.",
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    def mcp_start(transport, dry_run, yes, as_json):
        """Start the MCP server.

        \b
        Example:
            $ scitex-dev linter mcp start
            $ scitex-dev linter mcp start --transport sse
            $ scitex-dev linter mcp start --dry-run
        """
        if dry_run:
            click.echo(f"Would start MCP server (transport={transport}).")
            return
        try:
            from ._server import run_server

            run_server(transport=transport)
        except ImportError:
            click.echo(
                "fastmcp is required for MCP server. "
                "Install with: pip install 'scitex-dev[mcp]'",
                err=True,
            )
            sys.exit(1)

    @mcp_group.command("list-tools")
    @click.option(
        "-v",
        "--verbose",
        count=True,
        default=0,
        help="Verbosity: -v sig, -vv +desc, -vvv full.",
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    def mcp_list_tools(verbose, as_json):
        """List available MCP tools exposed by `scitex-dev linter`.

        \b
        Example:
            $ scitex-dev linter mcp list-tools
            $ scitex-dev linter mcp list-tools -vv
            $ scitex-dev linter mcp list-tools --json
        """
        _KNOWN_TOOLS = ["linter_check", "linter_check_source", "linter_list_rules"]
        tools = []
        try:
            from ._server import mcp as mcp_server
            from .._ecosystem._mcp import get_tools_sync

            tools = list(get_tools_sync(mcp_server).values())
        except Exception:
            pass

        if as_json:
            if not tools:
                click.echo(json.dumps({"tools": _KNOWN_TOOLS}, indent=2))
            else:
                click.echo(
                    json.dumps(
                        {
                            "tools": [
                                t.name for t in sorted(tools, key=lambda t: t.name)
                            ]
                        },
                        indent=2,
                    )
                )
            return

        if not tools:
            click.echo(f"SciTeX Linter MCP\nTools: {len(_KNOWN_TOOLS)}\n")
            for n in _KNOWN_TOOLS:
                click.echo(f"  {n}")
            return
        C = sys.stdout.isatty()
        g, w, cy, y, dm, r = (
            ("\033[92m", "\033[1;37m", "\033[96m", "\033[93m", "\033[2m", "\033[0m")
            if C
            else ("",) * 6
        )
        click.echo(f"{cy}SciTeX Linter MCP{r}\nTools: {len(tools)}\n")
        for t in sorted(tools, key=lambda t: t.name):
            if verbose == 0:
                click.echo(f"  {t.name}")
            else:
                ps = []
                params = t.parameters or {}
                for p, i in params.get("properties", {}).items():
                    pt = i.get("type", "any")
                    if p in params.get("required", []):
                        ps.append(f"{w}{p}{r}: {cy}{pt}{r}")
                    else:
                        d = (
                            repr(i.get("default"))
                            if i.get("default") is not None
                            else "None"
                        )
                        ps.append(f"{w}{p}{r}: {cy}{pt}{r} = {y}{d}{r}")
                click.echo(f"  {g}{t.name}{r}({', '.join(ps)})")
                if verbose >= 2 and t.description:
                    desc = t.description.split("\n")[0]
                    click.echo(f"       {dm}{desc}{r}")
                    if verbose >= 3:
                        for line in t.description.strip().split("\n")[1:]:
                            click.echo(f"       {dm}{line}{r}")
                    click.echo()

    @mcp_group.command("doctor")
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    def mcp_doctor(as_json):
        """Check MCP server health.

        \b
        Example:
            $ scitex-dev linter mcp doctor
        """
        import shutil

        click.echo(f"scitex-dev linter {__version__}\n")
        click.echo("Health Check")
        click.echo("=" * 40)

        checks = []
        try:
            import fastmcp

            checks.append(("fastmcp", True, fastmcp.__version__))
        except ImportError:
            checks.append(("fastmcp", False, "not installed"))
        try:
            from ._mcp.tools import register_all_tools  # noqa: F401

            checks.append(("MCP tools", True, "3 tools"))
        except Exception as e:
            checks.append(("MCP tools", False, str(e)))
        cli_path = shutil.which("scitex-dev")
        checks.append(
            ("CLI", bool(cli_path), cli_path if cli_path else "not in PATH")
        )
        checks.append(("Rules", True, f"{len(ALL_RULES)} rules"))

        all_ok = True
        for name, ok, info in checks:
            status = "✓" if ok else "✗"
            if not ok:
                all_ok = False
            click.echo(f"  {status} {name}: {info}")
        click.echo()
        if all_ok:
            click.echo("All checks passed!")
        else:
            click.echo("Some checks failed. Run 'pip install scitex-dev[mcp]' to fix.")
        sys.exit(0 if all_ok else 1)

    @mcp_group.command(
        "show-installation",
        hidden=True,
        context_settings={"ignore_unknown_options": True},
    )
    @click.pass_context
    def mcp_show_installation_deprecated(ctx):
        """(deprecated) Renamed to `install`."""
        click.echo(
            "error: `scitex-dev linter mcp show-installation` was renamed to "
            "`scitex-dev linter mcp install`.\n"
            "Re-run with: scitex-dev linter mcp install",
            err=True,
        )
        ctx.exit(2)

    @mcp_group.command("install")
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Accepted for §2; this verb is informational, never mutates state.",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help="Accepted for §2; this verb is informational, never mutates state.",
    )
    def mcp_install(as_json, dry_run, yes):
        """Show Claude Desktop MCP configuration snippet.

        \b
        Example:
            $ scitex-dev linter mcp install
        """
        del dry_run, yes  # audit §2 — no-op flags
        import shutil

        click.echo(f"scitex-dev linter {__version__}\n")
        click.echo("Add this to your Claude Desktop config file:\n")
        click.echo(
            "  macOS: ~/Library/Application Support/Claude/claude_desktop_config.json"
        )
        click.echo("  Linux: ~/.config/Claude/claude_desktop_config.json\n")
        cli_path = shutil.which("scitex-dev")
        if cli_path:
            click.echo(f"Your installation path: {cli_path}\n")
        config = (
            "{\n"
            '  "mcpServers": {\n'
            '    "scitex-dev-linter": {\n'
            f'      "command": "{cli_path or "scitex-dev"}",\n'
            '      "args": ["linter", "mcp", "start"]\n'
            "    }\n"
            "  }\n"
            "}"
        )
        click.echo(config)

    return mcp_group


# EOF
