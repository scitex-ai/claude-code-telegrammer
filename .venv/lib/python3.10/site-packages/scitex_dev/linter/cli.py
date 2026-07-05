"""CLI entry point for `scitex-dev linter` (Click-based, audit-compliant).

Canonical subcommands:
    scitex-dev linter check-files <PATH> [--json] [--severity] [--category] [--no-color]
    scitex-dev linter format-files <PATH> [--check] [--diff] [--dry-run] [--yes]
    scitex-dev linter run-python <SCRIPT> [--strict] [-- script_args...]
    scitex-dev linter list-rules [--json] [--category] [--severity]      (built-in)
    scitex-dev linter list-rules-all [--json] [--category] [--severity]  (built-in + plugin)
    scitex-dev linter list-python-apis [-v|-vv|-vvv] [--json]
    scitex-dev linter mcp start [--dry-run] [--yes]
    scitex-dev linter mcp list-tools [-v|-vv|-vvv] [--json]
    scitex-dev linter mcp doctor
    scitex-dev linter mcp show-installation
    scitex-dev linter completion install [--shell bash|zsh] [--dry-run] [--yes]
    scitex-dev linter show-completion-status [--json]
    scitex-dev linter show-completion-bash
    scitex-dev linter show-completion-zsh

Deprecated aliases (still work, redirect to new names):
    check         -> check-files
    format        -> format-files
    python        -> run-python
    rule          -> list-rules
    rules         -> list-rules-all
    api           -> list-python-apis
    mcp installation -> mcp show-installation
    completion status -> show-completion-status
    completion bash   -> show-completion-bash
    completion zsh    -> show-completion-zsh
"""

from __future__ import annotations

import json
import sys

import click

from . import __version__
from .rules import ALL_RULES

# =========================================================================
# Helpers
# =========================================================================


def _print_help_recursive(ctx: click.Context, _param, value):
    """Eager callback for --help-recursive."""
    if not value or ctx.resilient_parsing:
        return
    cmd = ctx.command
    click.echo(cmd.get_help(ctx))

    def walk(group, ancestry):
        if not isinstance(group, click.Group):
            return
        for name in sorted(group.commands):
            sub = group.commands[name]
            sub_ctx = click.Context(sub, info_name=name, parent=ctx)
            click.echo("\n---\n")
            click.echo(f"$ {' '.join(ancestry + [name])} --help\n")
            click.echo(sub.get_help(sub_ctx))
            walk(sub, ancestry + [name])

    walk(cmd, ["scitex-dev", "linter"])
    ctx.exit(0)


# =========================================================================
# Root
# =========================================================================


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, "-V", "--version", prog_name="scitex-dev linter")
@click.option(
    "--help-recursive",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_help_recursive,
    help="Show help for the root command and every subcommand.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit machine-readable JSON output where supported.",
)
@click.pass_context
def main_group(ctx, as_json):
    """SciTeX Linter — enforce reproducible research patterns.

    \b
    Configuration precedence (highest -> lowest):
      1. Explicit CLI flags
      2. ./pyproject.toml [tool.scitex_dev.linter]  (legacy [tool.scitex-linter] still read)
      3. ./config.yaml (project-local)
      4. $SCITEX_DEV_LINTER_CONFIG (path to a YAML file)
      5. ~/.scitex/dev/linter/config.yaml (user-wide)
      6. Built-in defaults

    \b
    Example:
        $ scitex-dev linter check-files src/
        $ scitex-dev linter list-rules --json
        $ scitex-dev linter mcp list-tools
    """
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# =========================================================================
# check-files (lives in ._cmd_check; registered here, re-exported for compat)
# =========================================================================

from ._cmd_check import _do_check  # noqa: E402,F401  back-compat re-export
from ._cmd_check import _collect_files  # noqa: E402,F401  back-compat re-export
from ._cmd_check import register as _register_check_files  # noqa: E402

check_files = _register_check_files(main_group)


# =========================================================================
# format-files
# =========================================================================


def _do_format(path, check, diff, dry_run, as_json):
    from ._format_runner import run as _format_run

    return _format_run(path, check=check, diff=diff, dry_run=dry_run, as_json=as_json)


@main_group.command("format-files")
@click.argument("path", type=click.Path())
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Check if changes needed without writing (exit 1 if changes needed).",
)
@click.option("--diff", is_flag=True, default=False, help="Show diff of changes.")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be fixed without writing.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation (no-op; format is non-destructive on --check/--dry-run).",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def format_files(path, check, diff, dry_run, yes, as_json):
    """Auto-fix SciTeX pattern issues in Python files.

    \b
    Example:
        $ scitex-dev linter format-files src/
        $ scitex-dev linter format-files my_script.py --diff
        $ scitex-dev linter format-files src/ --check
    """
    sys.exit(_do_format(path, check, diff, dry_run, as_json))


# =========================================================================
# run-python
# =========================================================================


@main_group.command("lint-and-run")
@click.argument("script", type=click.Path())
@click.option("--strict", is_flag=True, default=False, help="Abort on lint errors.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.argument("script_args", nargs=-1, type=click.UNPROCESSED)
def run_python(script, strict, as_json, script_args):
    """Lint then execute a Python script.

    Use -- to separate script arguments from linter flags.

    \b
    Example:
        $ scitex-dev linter run-python my_script.py
        $ scitex-dev linter run-python my_script.py --strict
        $ scitex-dev linter run-python my_script.py -- --arg1 value
    """
    from .runner import run_script

    sys.exit(run_script(script, strict=strict, script_args=list(script_args)))


# =========================================================================
# list-rules / list-rules-all
# =========================================================================


def _do_list_rules(rules_list, as_json):
    if as_json:
        data = [
            {
                "id": r.id,
                "severity": r.severity,
                "category": r.category,
                "message": r.message,
                "suggestion": r.suggestion,
            }
            for r in rules_list
        ]
        click.echo(json.dumps(data, indent=2))
        return
    use_color = sys.stdout.isatty()
    sev_color = {"error": "\033[91m", "warning": "\033[93m", "info": "\033[94m"}
    reset = "\033[0m"
    for r in rules_list:
        if use_color:
            c = sev_color.get(r.severity, "")
            click.echo(f"  {c}{r.id}{reset}  [{r.severity}]  {r.message}")
        else:
            click.echo(f"  {r.id}  [{r.severity}]  {r.message}")
    click.echo(f"\n  {len(rules_list)} rules")


@main_group.command("list-rules")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.option(
    "--category",
    default=None,
    help="Filter by category (comma-separated: structure,import,io,plot,stats).",
)
@click.option(
    "--severity",
    type=click.Choice(["error", "warning", "info"]),
    default=None,
    help="Filter by severity.",
)
def list_rules_cmd(as_json, category, severity):
    """List all built-in SciTeX lint rules.

    \b
    Example:
        $ scitex-dev linter list-rules
        $ scitex-dev linter list-rules --json
        $ scitex-dev linter list-rules --category structure --severity error
    """
    categories = set(category.split(",")) if category else None
    rules_list = list(ALL_RULES.values())
    if categories:
        rules_list = [r for r in rules_list if r.category in categories]
    if severity:
        rules_list = [r for r in rules_list if r.severity == severity]
    _do_list_rules(rules_list, as_json)


@main_group.command("list-rules-all")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.option(
    "--category", default=None, help="Filter by category (e.g. io, plot, structure)."
)
@click.option(
    "--severity",
    type=click.Choice(["error", "warning", "info"]),
    default=None,
    help="Filter by severity.",
)
def list_rules_all(as_json, category, severity):
    """List all SciTeX lint rules, including plugin-contributed rules.

    \b
    Example:
        $ scitex-dev linter list-rules-all
        $ scitex-dev linter list-rules-all --category io
    """
    from . import list_rules as _lr

    rules_list = _lr(category=category)
    if severity:
        rules_list = [r for r in rules_list if r.severity == severity]
    _do_list_rules(rules_list, as_json)


# =========================================================================
# list-python-apis
# =========================================================================


@main_group.command("list-python-apis")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.option(
    "-v",
    "--verbose",
    count=True,
    default=0,
    help="Verbosity: -v signatures, -vv +docstrings, -vvv full.",
)
def list_python_apis(as_json, verbose):
    """List the public Python API surface of scitex_linter.

    \b
    Example:
        $ scitex-dev linter list-python-apis
        $ scitex-dev linter list-python-apis -vv
        $ scitex-dev linter list-python-apis --json
    """
    from ._cmd_api import _PUBLIC_API

    if as_json:
        data = [
            {"module": m, "kind": k, "name": n, "signature": s, "doc": d}
            for m, k, n, s, d in _PUBLIC_API
        ]
        click.echo(json.dumps(data, indent=2))
        return

    use_color = sys.stdout.isatty()
    cyan = "\033[96m" if use_color else ""
    green = "\033[92m" if use_color else ""
    yellow = "\033[93m" if use_color else ""
    blue = "\033[94m" if use_color else ""
    dim = "\033[2m" if use_color else ""
    reset = "\033[0m" if use_color else ""
    kind_color = {"F": green, "C": yellow, "V": blue}

    click.echo(f"API tree of scitex_linter ({len(_PUBLIC_API)} items):")
    click.echo("Legend: [M]=Module [C]=Class [F]=Function [V]=Variable")
    current_mod = None
    for mod, kind, name, sig, doc in _PUBLIC_API:
        if mod != current_mod:
            click.echo(f"{cyan}[M] {mod}{reset}")
            current_mod = mod
        kc = kind_color.get(kind, "")
        if verbose == 0:
            click.echo(f"  {kc}[{kind}]{reset} {name}")
        else:
            sep = "" if sig.startswith("(") else " "
            click.echo(f"  {kc}[{kind}]{reset} {name}{sep}{sig}")
            if verbose >= 2 and doc:
                click.echo(f"       {dim}{doc}{reset}")


# =========================================================================
# mcp group + completion commands (extracted; registered here)
# =========================================================================

from ._cmd_mcp import register as _register_mcp  # noqa: E402
from ._cmd_completion_cmds import (  # noqa: E402
    register as _register_completion,
)

mcp_group = _register_mcp(main_group)
completion_group = _register_completion(main_group)


# =========================================================================
# §1a: install-shell-completion + print-shell-completion (canonical leaves)
# Registered alongside the legacy `completion install` / `show-completion-*`
# commands; the canonical leaves are the §1a-required entry points.
# =========================================================================
try:
    from scitex_dev._cli._completion import attach_shell_completion

    attach_shell_completion(main_group, prog_name="scitex-dev linter")
except ImportError:
    pass


# =========================================================================
# Backward-compat shim: translate deprecated argv names to new names
# =========================================================================

_TOP_RENAMES = {
    "check": "check-files",
    "format": "format-files",
    "python": "lint-and-run",
    "run-python": "lint-and-run",
    "run-python-script": "lint-and-run",
    "rule": "list-rules",
    "rules": "list-rules-all",
    "api": "list-python-apis",
}

_MCP_RENAMES = {
    "installation": "show-installation",
}

_COMPLETION_RENAMES_TO_TOP = {
    # `completion <name>` -> top-level `show-completion-<name>`
    "status": "show-completion-status",
    "bash": "show-completion-bash",
    "zsh": "show-completion-zsh",
}


def _rewrite_argv(argv):
    """Translate deprecated subcommand names to canonical Click names.

    Preserves all flags and positional arguments verbatim.
    """
    if not argv:
        return argv

    # Find the first non-flag token (the subcommand)
    i = 0
    while i < len(argv) and argv[i].startswith("-"):
        i += 1
    if i >= len(argv):
        return argv

    sub = argv[i]
    if sub in _TOP_RENAMES:
        argv = argv[:i] + [_TOP_RENAMES[sub]] + argv[i + 1 :]
    elif sub == "mcp" and i + 1 < len(argv):
        nxt = argv[i + 1]
        if nxt in _MCP_RENAMES:
            argv = argv[: i + 1] + [_MCP_RENAMES[nxt]] + argv[i + 2 :]
    elif sub == "completion" and i + 1 < len(argv):
        nxt = argv[i + 1]
        if nxt in _COMPLETION_RENAMES_TO_TOP:
            argv = argv[:i] + [_COMPLETION_RENAMES_TO_TOP[nxt]] + argv[i + 2 :]
    return argv


def main(argv: list = None) -> int:
    """Entry point. Returns exit code (0 on success).

    Wraps Click so existing callers (and tests) that pass argv lists keep working.
    Translates deprecated subcommand names to canonical Click names.
    """
    raw = list(sys.argv[1:]) if argv is None else list(argv)
    raw = _rewrite_argv(raw)

    try:
        main_group.main(args=raw, prog_name="scitex-dev linter", standalone_mode=False)
        return 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        return code
    except click.exceptions.UsageError as e:
        click.echo(f"Error: {e.format_message()}", err=True)
        return 2
    except click.exceptions.Abort:
        click.echo("Aborted.", err=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
