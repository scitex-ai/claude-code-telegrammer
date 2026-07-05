#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/_cli/__init__.py
"""CLI package for scitex-container.

Entry point: scitex-container  (maps to main() here)
"""

from __future__ import annotations

import inspect

import click

from ._apptainer import (
    build,
    cleanup,
    deploy,
    freeze,
    list_containers,
    rollback,
    switch,
    verify,
)
from ._docker import docker
from ._env_snapshot import env_snapshot_cmd
from ._host import host
from ._mcp import mcp
from ._sandbox import sandbox
from ._status import status


def _print_help_recursive(ctx, group, prefix="scitex-container"):
    """Recursively print help for a group and all its subcommands/subgroups."""
    click.secho(f"━━━ {prefix} ━━━", fg="cyan", bold=True)
    click.echo(group.get_help(ctx))

    commands = group.list_commands(ctx) or []
    for name in sorted(commands):
        cmd = group.get_command(ctx, name)
        if cmd is None:
            continue
        sub_prefix = f"{prefix} {name}"
        with click.Context(cmd, info_name=name, parent=ctx) as sub_ctx:
            click.echo()
            if isinstance(cmd, click.Group):
                _print_help_recursive(sub_ctx, cmd, prefix=sub_prefix)
            else:
                click.secho(f"━━━ {sub_prefix} ━━━", fg="cyan", bold=True)
                click.echo(cmd.get_help(sub_ctx))


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(
    None,
    "-V",
    "--version",
    package_name="scitex-container",
    prog_name="scitex-container",
    message="%(prog)s %(version)s",
)
@click.option(
    "--help-recursive", is_flag=True, help="Show help for all commands recursively"
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit machine-readable JSON output (where supported).",
)
@click.pass_context
def main(ctx, help_recursive, as_json):
    """scitex-container: Unified container management (Apptainer + Docker + host).

    \b
    Configuration precedence (highest -> lowest):
      1. Explicit CLI flags
      2. ./config.yaml (project-local)
      3. $SCITEX_CONTAINER_CONFIG (path to a YAML file)
      4. ~/.scitex/container/config.yaml (user-wide)
      5. Built-in defaults
    """
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    if help_recursive:
        _print_help_recursive(ctx, main)
        ctx.exit(0)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)


# Apptainer commands — nested under `apptainer` group per §1 tree form
@main.group("apptainer")
def apptainer_group():
    """Apptainer (SIF) container operations."""


apptainer_group.add_command(build)
apptainer_group.add_command(freeze)
apptainer_group.add_command(list_containers)
apptainer_group.add_command(switch)
apptainer_group.add_command(rollback)
apptainer_group.add_command(deploy)
apptainer_group.add_command(cleanup)
apptainer_group.add_command(verify)


def _deprecated_top_level(old: str, verb_path: str):
    """old at top level → `apptainer <verb_path>`."""

    @click.pass_context
    def _impl(ctx, **_):
        click.echo(
            f"error: `scitex-container {old}` was renamed to "
            f"`scitex-container {verb_path}`.\n"
            f"Re-run with: scitex-container {verb_path} <args>",
            err=True,
        )
        ctx.exit(2)

    return click.command(
        old,
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )(_impl)


for _old, _path in [
    ("build", "apptainer build"),
    ("freeze", "apptainer freeze"),
    ("list", "apptainer list"),
    ("switch", "apptainer switch"),
    ("rollback", "apptainer rollback"),
    ("deploy", "apptainer deploy"),
    ("cleanup", "apptainer cleanup"),
    ("verify", "apptainer verify"),
]:
    main.add_command(_deprecated_top_level(_old, _path))


# Sub-groups
main.add_command(sandbox)
main.add_command(docker)
main.add_command(host)
main.add_command(mcp)

# Unified status dashboard (show-status)
main.add_command(status)

# Clew reproducibility snapshot (save-env-snapshot)
main.add_command(env_snapshot_cmd)

# Hidden deprecation redirects for legacy top-level names
main.add_command(_deprecated_top_level("status", "show-status"))
main.add_command(_deprecated_top_level("env-snapshot", "save-env-snapshot"))


@main.command("list-python-apis")
@click.option(
    "-v", "--verbose", count=True, help="Verbosity: -v with signatures, -vv +docstring"
)
@click.option(
    "--json", "as_json", is_flag=True, help="Emit machine-readable JSON output."
)
@click.pass_context
def list_python_apis(ctx, verbose: int, as_json: bool):
    """List scitex_container Python APIs (apptainer, docker, host modules).

    \b
    Example:
      $ scitex-container list-python-apis
      $ scitex-container list-python-apis -vv
      $ scitex-container list-python-apis --json
    """
    import scitex_container.apptainer as apptainer_mod
    import scitex_container.docker as docker_mod
    import scitex_container.host as host_mod

    ctx.ensure_object(dict)
    if not as_json:
        as_json = bool(ctx.obj.get("as_json"))

    modules = [
        ("apptainer", apptainer_mod),
        ("docker", docker_mod),
        ("host", host_mod),
    ]

    if as_json:
        import json as _json

        envelope: dict = {"package": "scitex_container", "modules": {}}
        for mod_name, mod in modules:
            public_names = [n for n in dir(mod) if not n.startswith("_")]
            entries = []
            for name in sorted(public_names):
                obj = getattr(mod, name, None)
                if obj is None:
                    continue
                entry: dict = {"name": name}
                if isinstance(obj, type):
                    entry["kind"] = "class"
                elif callable(obj):
                    entry["kind"] = "callable"
                    try:
                        entry["signature"] = str(inspect.signature(obj))
                    except (ValueError, TypeError):
                        entry["signature"] = "()"
                    doc = inspect.getdoc(obj)
                    if doc:
                        entry["doc"] = doc.split("\n")[0].strip()
                else:
                    entry["kind"] = "value"
                    entry["repr"] = repr(obj)
                entries.append(entry)
            envelope["modules"][mod_name] = entries
        click.echo(_json.dumps(envelope, indent=2))
        return

    for mod_name, mod in modules:
        public_names = [n for n in dir(mod) if not n.startswith("_")]
        click.secho(f"{mod_name}: {len(public_names)} APIs", fg="green", bold=True)

        for name in sorted(public_names):
            obj = getattr(mod, name, None)
            if obj is None:
                continue

            if callable(obj) and not isinstance(obj, type):
                if verbose == 0:
                    click.echo(f"  {name}")
                elif verbose >= 1:
                    try:
                        sig_str = str(inspect.signature(obj))
                    except (ValueError, TypeError):
                        sig_str = "()"
                    click.echo(f"  {click.style(name, fg='white', bold=True)}{sig_str}")
                    if verbose >= 2:
                        doc = inspect.getdoc(obj)
                        if doc:
                            first_line = doc.split("\n")[0].strip()
                            click.echo(f"    {first_line}")
            elif isinstance(obj, type):
                click.echo(f"  {name}  [class]")
            else:
                if verbose >= 1:
                    click.echo(f"  {name} = {obj!r}")
                else:
                    click.echo(f"  {name}")

        click.echo()


# §1a: install-shell-completion + print-shell-completion (canonical leaves)
try:
    from scitex_dev._cli._completion import attach_shell_completion

    attach_shell_completion(main, prog_name="scitex-container")
except ImportError:
    pass


__all__ = ["main"]

# EOF


# audit §4 — inject version into root --help
try:
    from importlib.metadata import version as _v
    main.help = (
        f"scitex-container (v{_v('scitex-container')}) — "
        + (main.help or "").lstrip()
    )
except Exception:
    pass

# audit-cli §1a — packages with _skills/ MUST expose
# `<cli> skills {list,get,install}`.
from ._skills import skills_group as _skills_group

main.add_command(_skills_group, name="skills")
