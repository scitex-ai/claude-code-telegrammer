#!/usr/bin/env python3
"""Main CLI entry point for scitex-ssh."""

import socket

import click

from ._introspect import list_python_apis
from ._mcp import mcp
from ._primitives import attach_cmd, copy_cmd, exec_cmd, sync_cmd

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

COMMAND_CATEGORIES = [
    ("SSH Primitives", ["exec", "copy", "sync", "attach"]),
    ("Tunnel Management", ["tunnel"]),
    ("Integration", ["mcp", "list-python-apis"]),
]


class CategorizedGroup(click.Group):
    """Custom Click group that displays commands organized by category."""

    def format_commands(self, ctx, formatter):
        """Write categorized commands to the formatter."""
        commands = {}
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is not None and not cmd.hidden:
                commands[subcommand] = cmd

        if not commands:
            return

        displayed = set()

        for category_name, category_commands in COMMAND_CATEGORIES:
            category_items = []
            for name in category_commands:
                if name in commands and name not in displayed:
                    cmd = commands[name]
                    help_text = cmd.get_short_help_str(limit=formatter.width)
                    category_items.append((name, help_text))
                    displayed.add(name)

            if category_items:
                with formatter.section(category_name):
                    formatter.write_dl(category_items)

        uncategorized = [
            (name, commands[name].get_short_help_str(limit=formatter.width))
            for name in sorted(commands.keys())
            if name not in displayed
        ]
        if uncategorized:
            with formatter.section("Other"):
                formatter.write_dl(uncategorized)


def _show_recursive_help(ctx):
    """Recursively show help for all commands."""
    click.echo(ctx.get_help())
    click.echo()
    group = ctx.command
    if isinstance(group, click.Group):
        for name in sorted(group.list_commands(ctx)):
            cmd = group.get_command(ctx, name)
            sub_ctx = click.Context(cmd, parent=ctx, info_name=name)
            click.echo(f"{'=' * 60}")
            click.echo(f"Command: {name}")
            click.echo(f"{'=' * 60}")
            click.echo(sub_ctx.get_help())
            click.echo()
            if isinstance(cmd, click.Group):
                for sub_name in sorted(cmd.list_commands(sub_ctx)):
                    sub_cmd = cmd.get_command(sub_ctx, sub_name)
                    sub_sub_ctx = click.Context(
                        sub_cmd, parent=sub_ctx, info_name=sub_name
                    )
                    click.echo(f"  {'─' * 56}")
                    click.echo(f"  Subcommand: {name} {sub_name}")
                    click.echo(f"  {'─' * 56}")
                    click.echo(sub_sub_ctx.get_help())
                    click.echo()


def _get_version():
    """Read version from package."""
    from scitex_ssh import __version__

    return __version__


def _default_host() -> str:
    return socket.gethostname().split(".")[0]


@click.group(
    cls=CategorizedGroup,
    invoke_without_command=True,
    context_settings=CONTEXT_SETTINGS,
)
@click.option("--version", "-V", is_flag=True, help="Show version and exit.")
@click.option("--help-recursive", is_flag=True, help="Show help for all commands.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit structured JSON output (propagates to subcommands that honour it).",
)
@click.pass_context
def main(ctx, version, help_recursive, as_json):
    """scitex-ssh - SSH primitives (exec/copy/attach) and gated reverse tunnels.

    \b
    Config is loaded with the SciTeX precedence chain:
      config.yaml -> $SCITEX_SSH_CONFIG -> ~/.scitex/ssh/config.yaml -> defaults
    """
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    if version:
        click.echo(f"scitex-ssh {_get_version()}")
        ctx.exit(0)

    if help_recursive:
        _show_recursive_help(ctx)
        ctx.exit(0)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# -----------------------------------------------------------------------
# Tunnel subgroup
# -----------------------------------------------------------------------


@main.group("tunnel")
def tunnel():
    """Manage persistent SSH reverse tunnels (allowlist-gated)."""


def _do_tunnel_setup(port, bastion, secret_key, host, *, setup_fn=None):
    import scitex_ssh
    from scitex_ssh._allowlist import PolicyError

    if setup_fn is None:
        setup_fn = scitex_ssh.setup
    try:
        result = setup_fn(port, bastion, secret_key, host=host)
    except PolicyError as e:
        click.secho(f"ERROR: {e}", fg="red", err=True)
        raise SystemExit(2)
    except ValueError as e:
        click.secho(f"ERROR: {e}", fg="red", err=True)
        raise SystemExit(1)
    if result["success"]:
        click.secho(f"Tunnel on port {port} set up successfully.", fg="green")
        if result["stdout"]:
            click.echo(result["stdout"])
    else:
        click.secho(f"Failed to set up tunnel on port {port}.", fg="red", err=True)
        if result["stderr"]:
            click.echo(result["stderr"], err=True)
        raise SystemExit(1)


def _do_tunnel_remove(port, host, *, remove_fn=None):
    import scitex_ssh
    from scitex_ssh._allowlist import PolicyError

    if remove_fn is None:
        remove_fn = scitex_ssh.remove
    try:
        result = remove_fn(port, host=host)
    except PolicyError as e:
        click.secho(f"ERROR: {e}", fg="red", err=True)
        raise SystemExit(2)
    if result["success"]:
        click.secho(f"Tunnel on port {port} removed.", fg="green")
        if result["stdout"]:
            click.echo(result["stdout"])
    else:
        click.secho(f"Failed to remove tunnel on port {port}.", fg="red", err=True)
        if result["stderr"]:
            click.echo(result["stderr"], err=True)
        raise SystemExit(1)


def _do_tunnel_status(port, *, status_fn=None):
    import scitex_ssh

    if status_fn is None:
        status_fn = scitex_ssh.status
    result = status_fn(port)
    click.echo(result["stdout"])
    if result["stderr"]:
        click.echo(result["stderr"], err=True)


@tunnel.command("setup")
@click.option("-p", "--port", required=True, type=int, help="Remote port to forward.")
@click.option(
    "-b",
    "--bastion",
    default=None,
    help="Bastion server hostname or IP. [env: SCITEX_SSH_BASTION_SERVER]",
)
@click.option(
    "-s",
    "--secret-key",
    default=None,
    help="Path to SSH private key. [env: SCITEX_SSH_SECRET_KEY_PATH]",
)
@click.option(
    "--host",
    default=None,
    help="Local host label for allowlist gating (default: local hostname).",
)
@click.option("--dry-run", is_flag=True, help="Print plan without setting up tunnel.")
@click.option(
    "-y", "--yes", is_flag=True, help="Suppress interactive confirmation (assume yes)."
)
def tunnel_setup(port, bastion, secret_key, host, dry_run, yes):
    """Set up a persistent SSH reverse tunnel.

    \b
    Example:
      $ scitex-ssh tunnel setup -p 8080 -b bastion.example.com
      $ scitex-ssh tunnel setup -p 8080 --dry-run
    """
    if dry_run:
        click.echo(
            f"DRY RUN — would set up SSH reverse tunnel "
            f"(port={port}, bastion={bastion}, host={host or _default_host()})"
        )
        return
    _do_tunnel_setup(port, bastion, secret_key, host or _default_host())


@tunnel.command("remove")
@click.option("-p", "--port", required=True, type=int, help="Port of tunnel to remove.")
@click.option(
    "--host",
    default=None,
    help="Local host label for allowlist gating (default: local hostname).",
)
@click.option("--dry-run", is_flag=True, help="Print plan without removing tunnel.")
@click.option(
    "-y", "--yes", is_flag=True, help="Suppress interactive confirmation (assume yes)."
)
def tunnel_remove(port, host, dry_run, yes):
    """Remove a persistent SSH reverse tunnel.

    \b
    Example:
      $ scitex-ssh tunnel remove -p 8080
      $ scitex-ssh tunnel remove -p 8080 --dry-run
    """
    if dry_run:
        click.echo(
            f"DRY RUN — would remove tunnel (port={port}, host={host or _default_host()})"
        )
        return
    _do_tunnel_remove(port, host or _default_host())


@tunnel.command("check-status")
@click.option(
    "-p",
    "--port",
    type=int,
    default=None,
    help="Specific port to check (default: all).",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def tunnel_status(port, as_json):
    """Check status of SSH reverse tunnels (informational; not gated).

    \b
    Example:
      $ scitex-ssh tunnel check-status
      $ scitex-ssh tunnel check-status -p 8080
      $ scitex-ssh tunnel check-status --json
    """
    if as_json:
        import json as _json

        import scitex_ssh

        result = scitex_ssh.status(port)
        click.echo(
            _json.dumps(
                {
                    "port": port,
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                },
                indent=2,
            )
        )
        return
    _do_tunnel_status(port)


@tunnel.command("status", hidden=True)
@click.option("-p", "--port", type=int, default=None)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def tunnel_status_deprecated(ctx, port, as_json):
    """(deprecated) Use `tunnel check-status`."""
    _deprecation_warn("tunnel status", "tunnel check-status")
    ctx.invoke(tunnel_status, port=port, as_json=as_json)


# -----------------------------------------------------------------------
# Deprecated top-level aliases (hidden)
# -----------------------------------------------------------------------


def _deprecation_warn(old: str, new: str) -> None:
    click.secho(
        f"warning: `scitex-ssh {old}` is deprecated; use `scitex-ssh {new}`.",
        fg="yellow",
        err=True,
    )


@main.command("setup-tunnel", hidden=True)
@click.option("-p", "--port", required=True, type=int)
@click.option("-b", "--bastion", default=None)
@click.option("-s", "--secret-key", default=None)
@click.option("--host", default=None)
def setup_tunnel_deprecated(port, bastion, secret_key, host):
    """(deprecated) Use `tunnel setup`."""
    _deprecation_warn("setup-tunnel", "tunnel setup")
    _do_tunnel_setup(port, bastion, secret_key, host or _default_host())


@main.command("remove-tunnel", hidden=True)
@click.option("-p", "--port", required=True, type=int)
@click.option("--host", default=None)
def remove_tunnel_deprecated(port, host):
    """(deprecated) Use `tunnel remove`."""
    _deprecation_warn("remove-tunnel", "tunnel remove")
    _do_tunnel_remove(port, host or _default_host())


@main.command("show-status", hidden=True)
@click.option("-p", "--port", type=int, default=None)
def show_status_deprecated(port):
    """(deprecated) Use `tunnel check-status`."""
    _deprecation_warn("show-status", "tunnel check-status")
    _do_tunnel_status(port)


# -----------------------------------------------------------------------
# Register top-level primitive + integration commands
# -----------------------------------------------------------------------

main.add_command(exec_cmd)
main.add_command(copy_cmd)
main.add_command(sync_cmd)
main.add_command(attach_cmd)
main.add_command(list_python_apis)
main.add_command(mcp)

try:
    from scitex_dev._cli._completion import attach_shell_completion

    attach_shell_completion(main, prog_name="scitex-ssh")
except Exception:
    pass


# EOF
