#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main CLI entry point for scitex-dev."""

import json

# click is a HARD core dep (PS-213 console-script-deps-must-be-core).
# scitex-dev's [project.scripts] entry-point IS a click group, so click
# being unavailable is a CI failure, not a runtime fallback.
import click

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

# Names below MUST match the actual registered command names. Anything
# not listed here falls through to the "Other" section in --help.
COMMAND_CATEGORIES = [
    ("CI", ["ci"]),
    ("Development", ["show-config", "rename-symbols"]),
    ("Documentation", ["docs", "search-docs", "skills"]),
    (
        "Ecosystem",
        ["audit-umbrella-pins", "cron", "doctor", "ecosystem", "creds", "service"],
    ),
    ("Interface", ["mcp", "list-python-apis"]),
    ("Shell", ["install-tab-completion"]),
]

from .._ecosystem.click_helpers import make_categorized_group

CategorizedGroup = make_categorized_group(COMMAND_CATEGORIES)

def _command_to_dict(
    cmd: click.Command,
    parent_ctx: click.Context | None,
    info_name: str,
) -> dict:
    """Serialize one click command (and its subcommands recursively) to a dict."""
    sub_ctx = click.Context(cmd, parent=parent_ctx, info_name=info_name)
    options: list[dict] = []
    arguments: list[dict] = []
    for p in cmd.params:
        if isinstance(p, click.Argument):
            arguments.append({"name": p.name, "required": p.required})
        else:
            options.append(
                {
                    "name": p.name,
                    "opts": list(p.opts),
                    "help": getattr(p, "help", "") or "",
                    "is_flag": bool(getattr(p, "is_flag", False)),
                }
            )
    out: dict = {
        "name": info_name,
        "help": (cmd.help or "").strip(),
        "short_help": (cmd.short_help or "").strip(),
        "options": options,
        "arguments": arguments,
    }
    if isinstance(cmd, click.Group):
        commands: dict = {}
        for sub in sorted(cmd.list_commands(sub_ctx)):
            sub_cmd = cmd.get_command(sub_ctx, sub)
            if sub_cmd is None:
                continue
            commands[sub] = _command_to_dict(sub_cmd, sub_ctx, sub)
        out["commands"] = commands
    return out

def _show_recursive_help(ctx: click.Context) -> None:
    """Recursively show help for all commands. Honours ctx.obj['json']."""
    if ctx.obj and ctx.obj.get("json"):
        import json as _json

        tree = _command_to_dict(
            ctx.command, ctx.parent, ctx.info_name or "scitex-dev"
        )
        click.echo(_json.dumps(tree, indent=2))
        return

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

def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("scitex-dev")
    except Exception:
        return "0.0.0-unknown"

# Disable Click's auto --help on THIS group only (parameter, not
# context — does not propagate to subcommands). Then re-add --help /
# -h explicitly via @click.help_option in the desired display slot so
# --help-recursive immediately follows --help.
@click.group(
    cls=CategorizedGroup,
    invoke_without_command=True,
    context_settings=CONTEXT_SETTINGS,
    add_help_option=False,
)
@click.option("--version", "-V", is_flag=True, help="Show version and exit.")
@click.help_option("-h", "--help")
@click.option("--help-recursive", is_flag=True, help="Show help for all commands.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit structured JSON output (propagates to subcommands that honour it).",
)
@click.pass_context
def main(
    ctx: click.Context,
    version: bool,
    help_recursive: bool,
    as_json: bool,
) -> None:
    """scitex-dev — Shared developer utilities for the SciTeX ecosystem.

    \b
    Config path resolution:
        ./config.yaml -> $SCITEX_DEV_CONFIG -> ~/.scitex/dev/config.yaml -> defaults

    \b
    Example:
        $ scitex-dev ecosystem list --json
        $ scitex-dev doctor
        $ scitex-dev mcp start
    """
    # The version is injected into main.help after the decorator binds
    # (below the function definition) so `--help` shows
    # "scitex-dev (v0.10.4) — Shared developer utilities..."
    # Expose the root-level --json flag to subcommands via ctx.obj so
    # commands that already honour `--json` can read the inherited
    # setting and default to structured output without the user
    # repeating the flag at each level.
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json

    if version:
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "name": "scitex-dev",
                        "version": _get_version(),
                    }
                )
            )
        else:
            click.echo(f"scitex-dev {_get_version()}")
        ctx.exit(0)

    if help_recursive:
        _show_recursive_help(ctx)
        ctx.exit(0)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

# Inject the version into the help text so --help shows
# "scitex-dev (v0.10.4) — Shared developer utilities..."
main.help = (
    f"scitex-dev (v{_get_version()}) — "
    "Shared developer utilities for the SciTeX ecosystem.\n"
    "\n"
    "\b\n"
    "Config path resolution:\n"
    "  config.yaml → $SCITEX_DEV_CONFIG → ~/.scitex/dev/config.yaml → defaults"
)

# -------------------------------------------------------------------
# Ecosystem commands
# -------------------------------------------------------------------

from ._doctor import register_doctor_command

register_doctor_command(main)

from .ecosystem._registry import register_ecosystem_commands

ecosystem_group = register_ecosystem_commands(main)

# Stats now lives under `ecosystem` per noun-verb hierarchy. The legacy
# top-level `show-stats` is kept as a hidden deprecation alias for one
# cycle; remove in 0.11.0.
from ._stats import register_stats_command

register_stats_command(ecosystem_group, main_group=main)

# Quality audits — each one keeps its own command (separation of concern).
# Move them under `ecosystem` so `ecosystem audit-*` is the single
# canonical audit namespace. The top-level `quality` group is dropped;
# individual `quality audit-*` callers must update.
from .quality import _check as _cli_quality

# These sub-rules belong inside their canonical owner per the
# consolidation plan. Hidden until folded in (PR-by-PR) so the public
# surface is just five audit-* commands. Removed in 0.11.0.
#   audit-docs   → splits across audit-python-apis (README API drift)
#                  and audit-skills (SKILL.md code-example drift)
#   audit-scope  → folds into audit-project (test-import boundary)
#   audit-lines  → folds into audit-project (LOC-limits, source metric)
#   audit-frontmatter → DROPPED (frontmatter shape lives in audit-skills)
@ecosystem_group.command("audit-docs", hidden=True)
@click.option("--projects-root", default=None)
def _ecosystem_audit_docs(projects_root):
    """(deprecated) Splits into `audit-python-apis` (README API drift) and `audit-skills` (SKILL.md drift). Removed in 0.11.0."""
    raise SystemExit(_cli_quality.audit_docs(projects_root=projects_root))

@ecosystem_group.command("audit-scope", hidden=True)
@click.option("--projects-root", default=None)
def _ecosystem_audit_scope(projects_root):
    """(deprecated) Folds into `audit-project`. Removed in 0.11.0."""
    raise SystemExit(_cli_quality.audit_scope(projects_root=projects_root))

@ecosystem_group.command("audit-lines", hidden=True)
def _ecosystem_audit_lines():
    """(deprecated) Folds into `audit-project` (LOC-limits). Removed in 0.11.0."""
    raise SystemExit(_cli_quality.audit_lines())

# Umbrella-only pin freshness audit. Designed to fire from the
# umbrella package's CI; on any other package it exits 0, so it's
# safe to wire into a shared CI step.
from .audit._umbrella_pins import cli as _umbrella_pins_cli

ecosystem_group.add_command(_umbrella_pins_cli, name="audit-umbrella-pins")

# ----- Deprecation shim: `scitex-dev quality <cmd>` → ecosystem -----
@main.group("quality", hidden=True)
def _quality_deprecated():
    """(deprecated) Use `scitex-dev ecosystem audit-*` instead."""

def _make_quality_redirect(cmd_name: str):
    @_quality_deprecated.command(
        cmd_name,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def _redirect(ctx):
        f"""(deprecated) See `scitex-dev ecosystem {cmd_name}`."""
        click.echo(
            f"warning: `scitex-dev quality {cmd_name}` was moved to "
            f"`scitex-dev ecosystem {cmd_name}`. Will be removed in 0.11.0.",
            err=True,
        )
        target = ecosystem_group.get_command(ctx, cmd_name)
        if target is None:
            ctx.exit(2)
        ctx.invoke(target, *ctx.args)

    return _redirect

for _quality_cmd in (
    "audit-docs",
    "audit-scope",
    "audit-lines",
    "audit-frontmatter",
):
    _make_quality_redirect(_quality_cmd)

# -------------------------------------------------------------------
# Development commands
# -------------------------------------------------------------------

@main.command(
    "config", hidden=True, context_settings={"ignore_unknown_options": True}
)
@click.pass_context
def config_deprecated(ctx):
    """(deprecated) Renamed to `show-config`."""
    click.echo(
        "error: `scitex-dev config` was renamed to `scitex-dev show-config`.\n"
        "Re-run with: scitex-dev show-config",
        err=True,
    )
    ctx.exit(2)

@main.command("show-config")
@click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
def config_cmd(as_json):
    """Show dev configuration.

    \b
    Example:
        $ scitex-dev show-config --json
    """
    from .. import config_to_dict, load_config

    cfg = config_to_dict(load_config())

    if as_json:
        click.echo(json.dumps(cfg, indent=2, default=str))
        return

    # Human-readable text output: section headers + tabular rows
    sections = [
        ("Packages", "packages", ["name", "github_repo", "local_path"]),
        ("Hosts", "hosts", None),
        ("GitHub Remotes", "github_remotes", None),
        ("Branches", "branches", None),
    ]
    for title, key, cols in sections:
        items = cfg.get(key, [])
        if not items:
            continue
        click.echo(f"\n{title} ({len(items)})")
        click.echo("=" * (len(title) + 4 + len(str(len(items)))))
        for item in items:
            if isinstance(item, dict) and cols:
                parts = [str(item.get(c, "")) for c in cols]
                click.echo(
                    "  "
                    + "  ".join(
                        f"{p:25s}" if i == 0 else p for i, p in enumerate(parts)
                    )
                )
            elif isinstance(item, dict):
                click.echo("  " + " | ".join(f"{k}={v}" for k, v in item.items()))
            else:
                click.echo(f"  {item}")

# rename-symbols + the hidden `rename` deprecation alias live in
# _cli/_rename.py. Extracted to keep _root.py under the line budget
# and to give the bulk-rename surface a focused module to grow into.
from ._rename import register as _register_rename

_register_rename(main)

# -------------------------------------------------------------------
# Documentation commands
# -------------------------------------------------------------------

from .._core.dispatch import docs_click_group

docs_grp = docs_click_group(package="scitex-dev")
main.add_command(docs_grp)

# `docs search` — canonical home for ecosystem-wide search across APIs,
# CLI, MCP tools, and documentation. The legacy top-level `search-docs`
# is kept as a hidden deprecation alias (see below). Removed in 0.11.0.
@docs_grp.command("search")
@click.argument("query")
@click.option(
    "--scope", default="all", help="Search scope: all, api, cli, mcp, docs."
)
@click.option("--max-results", default=10, help="Maximum results.")
@click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
def _docs_search(query, scope, max_results, as_json):
    """Search across APIs, CLI, MCP tools, and documentation.

    \b
    Example:
        $ scitex-dev docs search "save figure"
        $ scitex-dev docs search version --scope api
        $ scitex-dev docs search hpc --max-results 20 --json
    """
    from .. import search as do_search
    from ._utils import wrap_as_cli

    wrap_as_cli(
        do_search,
        as_json=as_json,
        query=query,
        scope=scope,
        max_results=max_results,
    )

from .skills._manage import register_skills_commands

register_skills_commands(main)

from ._completion import register_completion_command

register_completion_command(main)

@main.command(
    "search",
    hidden=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.pass_context
def search_deprecated(ctx):
    """(deprecated) Renamed to `search-docs`."""
    click.echo(
        "error: `scitex-dev search` was renamed to `scitex-dev search-docs`.\n"
        "Re-run with: scitex-dev search-docs <query> [...]",
        err=True,
    )
    ctx.exit(2)

@main.command("search-docs", hidden=True)
@click.argument("query")
@click.option(
    "--scope", default="all", help="Search scope: all, api, cli, mcp, docs."
)
@click.option("--max-results", default=10, help="Maximum results.")
@click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
def search_docs_deprecated(query, scope, max_results, as_json):
    """(deprecated) Use `scitex-dev docs search`. Removed in 0.11.0."""
    click.echo(
        "warning: `scitex-dev search-docs` was moved to "
        "`scitex-dev docs search`. Will be removed in 0.11.0.",
        err=True,
    )
    from .. import search as do_search
    from ._utils import wrap_as_cli

    wrap_as_cli(
        do_search,
        as_json=as_json,
        query=query,
        scope=scope,
        max_results=max_results,
    )

# -------------------------------------------------------------------
# Integration commands
# -------------------------------------------------------------------

from ._integrations import register_integration_commands

register_integration_commands(main)

# -------------------------------------------------------------------
# ci runner — self-hosted GitHub Actions runner lifecycle
# -------------------------------------------------------------------

from ..ci.runner import register_ci_runner_commands

register_ci_runner_commands(main)

# -------------------------------------------------------------------
# linter — engine moved here from scitex-linter (soft migration)
# `linter` is a noun per the noun-verb CLI convention (audit-cli §1).
# -------------------------------------------------------------------

try:
    from ..linter.cli import main_group as _linter_group

    _linter_group.name = "linter"
    _linter_group.short_help = (
        "AST-based linter (was scitex-linter). Plugins register rules "
        "via entry-point group `scitex_dev.linter.plugins` "
        "(legacy `scitex_linter.plugins` still honoured)."
    )
    main.add_command(_linter_group)
except Exception:
    pass

# -------------------------------------------------------------------
# list-python-apis
# -------------------------------------------------------------------

from ._list_apis import register_list_python_apis_command

register_list_python_apis_command(main)

# -------------------------------------------------------------------
# gate — submission-gate plugin federation (scitex_dev.gate.checks).
# Leaves register per-package pre/post-submission checks; the hook calls
# ONLY `scitex-dev gate`, staying package-agnostic (SOC).
# -------------------------------------------------------------------

from .gate import register_gate_command

register_gate_command(main)
