#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable CLI mixins for ``docs`` and ``skills`` subcommands.

Each package adds subcommands with minimal boilerplate::

    # In scitex_writer/_cli/__init__.py (argparse)
    from scitex_dev.cli import register_docs_subcommand, register_skills_subcommand
    register_docs_subcommand(subparsers, package="scitex-writer")
    register_skills_subcommand(subparsers, package="scitex-writer")

    # Or with Click
    from scitex_dev.cli import docs_click_group
    cli.add_command(docs_click_group(package="scitex-writer"))
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def register_docs_subcommand(
    subparsers: argparse._SubParsersAction,
    package: str,
) -> argparse.ArgumentParser:
    """Register ``docs`` with ``list`` and ``get`` verb subcommands.

    Usage::
        scitex-stats docs list            # List doc pages
        scitex-stats docs get             # Show available pages
        scitex-stats docs get api         # Show specific page
    """
    prog = package.replace("_", "-")
    parser = subparsers.add_parser(
        "docs",
        help=f"View documentation for {package}",
        description=f"Browse and query {package} documentation.",
        epilog=(
            f"Examples:\n"
            f"  {prog} docs list            # List doc pages\n"
            f"  {prog} docs list --json     # JSON output\n"
            f"  {prog} docs get             # Show available pages\n"
            f"  {prog} docs get api         # Show specific page\n"
            f"  {prog} docs get api --json  # Page as JSON\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--help-recursive",
        action="store_true",
        help="Show help for all subcommands",
    )
    docs_sub = parser.add_subparsers(dest="docs_command", title="Commands")

    # docs list
    list_p = docs_sub.add_parser(
        "list",
        help="List available documentation pages",
        epilog=(f"Examples:\n  {prog} docs list\n  {prog} docs list --json\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_p.add_argument("--json", action="store_true", dest="as_json")
    list_p.set_defaults(
        func=lambda args: _run_docs_command(
            argparse.Namespace(
                list_pages=True,
                page=None,
                as_json=args.as_json,
                tldr=False,
                format=None,
            ),
            package=package,
        )
    )

    # docs get [page]
    get_p = docs_sub.add_parser(
        "get",
        help="Show a documentation page",
        epilog=(
            f"Examples:\n"
            f"  {prog} docs get               # show overview\n"
            f"  {prog} docs get api           # specific page\n"
            f"  {prog} docs get api --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_p.add_argument(
        "name", nargs="?", default=None, help="Page name (see 'docs list')"
    )
    get_p.add_argument("--json", action="store_true", dest="as_json")
    get_p.add_argument("--format", type=str, default=None, choices=["html", "json"])
    get_p.set_defaults(func=lambda args: _run_docs_get(args, package=package))

    # bare `docs` → show help
    def _default_handler(args):
        if getattr(args, "help_recursive", False):
            parser.print_help()
            print()
            for sub_name, sub_p in [("list", list_p), ("get", get_p)]:
                print(f"--- {sub_name} ---")
                sub_p.print_help()
                print()
            return
        if args.docs_command is None:
            parser.print_help()

    parser.set_defaults(func=_default_handler)
    return parser


def _run_docs_get(args: argparse.Namespace, package: str) -> None:
    """Handle 'docs get [name]' — show page or list available pages."""
    if args.name is None:
        ns = argparse.Namespace(
            list_pages=True,
            page=None,
            as_json=getattr(args, "as_json", False),
            tldr=False,
            format=None,
        )
    else:
        ns = argparse.Namespace(
            list_pages=False,
            page=args.name,
            as_json=getattr(args, "as_json", False),
            tldr=False,
            format=getattr(args, "format", None),
        )
    _run_docs_command(ns, package=package)


def _run_docs_command(args: argparse.Namespace, package: str) -> None:
    """Execute the docs subcommand."""
    import logging

    logging.getLogger("scitex_dev._core.discovery").setLevel(logging.ERROR)
    from .._docs.docs import get_docs

    # --tldr: concise quick-start
    if args.tldr:
        tldr = _get_tldr(package)
        if args.as_json:
            print(json.dumps({"package": package, "tldr": tldr}))
        else:
            print(tldr)
        return

    # Determine format. Note: page listings always use the rich manifest
    # (format=None) so the text and --json paths show the same data —
    # downgrading to format="json" here would drop page titles.
    fmt = args.format
    if args.list_pages:
        fetch_fmt = None
    elif args.as_json and fmt is None:
        fetch_fmt = "json"
    else:
        fetch_fmt = fmt

    try:
        result = get_docs(package=package, format=fetch_fmt, page=args.page)
    except LookupError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    # --list: show page index
    if args.list_pages:
        _print_page_list(result, as_json=args.as_json)
        return

    # Default output
    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
    elif isinstance(result, dict):
        print(json.dumps(result, indent=2, default=str))
    elif isinstance(result, Path) and result.is_file():
        # --page returns a file path — print its content
        print(result.read_text(encoding="utf-8"))
    else:
        print(result)


def _print_page_list(result, as_json: bool = False) -> None:
    """Print a page listing from a manifest or page dict."""
    if isinstance(result, dict):
        pages = result.get("pages", [])
        if as_json:
            print(json.dumps({"pages": pages}))
        else:
            if isinstance(pages, list) and pages and isinstance(pages[0], dict):
                for p in pages:
                    print(f"  {p.get('name', '?'):20s} {p.get('title', '')}")
            elif isinstance(pages, list):
                for name in pages:
                    print(f"  {name}")
            else:
                print("  (no pages found)")
    else:
        print(result)


def _get_tldr(package: str) -> str:
    """Get a concise quick-start summary for a package.

    Tries to extract from built docs, falls back to a generic template.
    """
    from .._docs.docs import get_docs

    try:
        result = get_docs(package=package)
    except LookupError:
        return f"{package}: package not found in scitex ecosystem."

    # Try to find a quick-start section in the docs
    if isinstance(result, dict):
        description = result.get("description", "")
        version = result.get("version", "?")
        pages = result.get("pages", [])
        page_names = [p["name"] if isinstance(p, dict) else p for p in pages[:5]]

        lines = [
            f"{package} v{version}",
            description[:100] if description else "(no description)",
            "",
            f"  pip install {package}",
            f'  python -c "import {package.replace("-", "_")}"',
        ]
        if page_names:
            lines.append("")
            lines.append(f"Docs pages: {', '.join(page_names)}")

        return "\n".join(lines)

    return f"{package}: documentation available via get_docs(package='{package}')"


def docs_click_group(package: str, name: str = "docs"):  # noqa: D401
    """Create a Click command group for docs (requires Click installed).

    Usage::
        from scitex_dev.cli import docs_click_group
        cli.add_command(docs_click_group(package="scitex-writer"))
    """
    try:
        import click
    except ImportError:
        raise ImportError("Click is required for docs_click_group. pip install click")

    prog = package.replace("_", "-")

    @click.group(name=name, invoke_without_command=True)
    @click.pass_context
    def docs_grp(ctx):
        """View package documentation (list / get / search)."""
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    # Click reads the function docstring for short help; the f-string above
    # used to silently evaluate to None (f-strings are not docstrings).
    docs_grp.help = (
        "View package documentation.\n\n"
        "\b\n"
        "Examples:\n"
        f"  {prog} docs list            # List doc pages\n"
        f"  {prog} docs get             # Show available pages\n"
        f"  {prog} docs get api         # Show specific page\n"
        f"  {prog} docs search QUERY    # Search across docs/APIs/CLI/MCP\n"
    )

    @docs_grp.command(
        "list",
        epilog=f"Examples:\n  $ {prog} docs list\n  $ {prog} docs list --json",
    )
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def docs_list(as_json):
        """List available documentation pages."""
        ns = argparse.Namespace(
            list_pages=True,
            page=None,
            as_json=as_json,
            tldr=False,
            format=None,
        )
        _run_docs_command(ns, package=package)

    @docs_grp.command(
        "get",
        epilog=(
            f"Examples:\n"
            f"  $ {prog} docs get                # show overview\n"
            f"  $ {prog} docs get api            # specific page\n"
            f"  $ {prog} docs get api --format json"
        ),
    )
    @click.argument("page_name", required=False, default=None)
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    @click.option("--format", "fmt", type=click.Choice(["html", "json"]), default=None)
    def docs_get(page_name, as_json, fmt):
        """Show documentation. Without PAGE_NAME, shows package overview."""
        if page_name is None:
            # No page given — show available pages
            ns = argparse.Namespace(
                list_pages=True,
                page=None,
                as_json=as_json,
                tldr=False,
                format=None,
            )
        else:
            ns = argparse.Namespace(
                list_pages=False,
                page=page_name,
                as_json=as_json,
                tldr=False,
                format=fmt,
            )
        _run_docs_command(ns, package=package)

    return docs_grp


def skills_click_group(package: str, name: str = "skills"):
    """Create a Click command group for skills (requires Click installed).

    Usage::
        from scitex_dev.cli import skills_click_group
        cli.add_command(skills_click_group(package="scitex-app"))
    """
    try:
        import click
    except ImportError:
        raise ImportError("Click is required. pip install click")

    prog = package.replace("_", "-")

    @click.group(name=name, invoke_without_command=True)
    @click.pass_context
    def skills_grp(ctx):
        """View package skills (workflow-oriented guides)."""
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @skills_grp.command(
        "list",
        epilog=f"Examples:\n  $ {prog} skills list\n  $ {prog} skills list --json",
    )
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def skills_list(as_json):
        """List available skill pages."""
        ns = argparse.Namespace(as_json=as_json)
        _skills_list(ns, package=package)

    @skills_grp.command(
        "get",
        epilog=(
            f"Examples:\n"
            f"  $ {prog} skills get                    # list available\n"
            f"  $ {prog} skills get python-scitex      # show specific\n"
            f"  $ {prog} skills get python-scitex --json"
        ),
    )
    @click.argument("skill_name", required=False, default=None)
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def skills_get(skill_name, as_json):
        """Show a specific skill page."""
        if skill_name is None:
            # No name given — show available skills
            ns = argparse.Namespace(as_json=as_json)
            _skills_list(ns, package=package)
            return
        ns = argparse.Namespace(name=skill_name, as_json=as_json)
        _skills_get(ns, package=package)

    # hook-bypass: line-limit — adding export subcommand; cli.py split
    # refactor tracked in GITIGNORED/REFACTORING.md, follow-up work item.
    @skills_grp.command(
        "export",
        epilog=(
            f"Examples:\n"
            f"  $ {prog} skills export                       # default dest\n"
            f"  $ {prog} skills export --dest /tmp/skills\n"
            f"  $ {prog} skills export --dry-run --json      # preview"
        ),
    )
    @click.option(
        "--dest",
        default=None,
        help="Destination dir (default: ~/.claude/skills/scitex/).",
    )
    @click.option(
        "--source",
        type=click.Choice(["package", "dev", "auto"]),
        default="auto",
        help="Which source to export from.",
    )
    @click.option("--clean", is_flag=True, help="Delete pkg subdir first.")
    @click.option("--dry-run", is_flag=True, help="Preview without writing.")
    @click.option(
        "--yes", "-y", is_flag=True, help="Skip confirmation when overwriting."
    )
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def skills_export(dest, source, clean, dry_run, yes, as_json):
        """Export this package's skills to <dest>."""
        from pathlib import Path as _P

        from .._ecosystem._skills.skills import (
            _get_default_export_dest,
            export_skills,
            list_skills,
        )

        target = _P(dest) if dest else _get_default_export_dest()

        # hook-bypass: line-limit (tracked in GITIGNORED/REFACTORING.md)
        if dry_run:
            sl_by_pkg = list_skills(package=package)
            flat = [s for lst in sl_by_pkg.values() for s in lst]
            if as_json:
                import json as _json

                click.echo(
                    _json.dumps({str(target): [s["name"] for s in flat]}, indent=2)
                )
            else:
                click.echo(
                    f"Would export {len(flat)} files for {package} "
                    f"to {target}/ (source={source})"
                )
                for s in flat:
                    click.echo(f"  - {s['name']}")
            return

        exported = export_skills(target, package=package, clean=clean, source=source)
        if not exported:
            click.echo(f"No skills found to export for {package}.")
            return
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {k: [str(f) for f in v] for k, v in exported.items()},
                    indent=2,
                )
            )
        else:
            total = sum(len(v) for v in exported.values())
            click.echo(f"Exported {total} files for {package} to {target}")

    # `install` is the audit-cli §3 canonical verb name for materialising
    # cached resources to the user's filesystem; we keep `export` as a
    # back-compat alias and bind both to the same callback so existing
    # docs / muscle memory keep working.
    skills_grp.add_command(skills_export, name="install")

    return skills_grp


# =============================================================================
# Skills subcommand (argparse)
# =============================================================================


def register_skills_subcommand(
    subparsers: argparse._SubParsersAction,
    package: str,
) -> argparse.ArgumentParser:
    """Register ``skills`` with ``list`` and ``get`` verb subcommands.

    Usage::
        scitex-stats skills list              # List skill pages
        scitex-stats skills get               # Show main SKILL.md
        scitex-stats skills get test-selection # Show a reference page
    """
    prog = package.replace("_", "-")
    parser = subparsers.add_parser(
        "skills",
        help=f"View skills for {package}",
        description=f"Browse {package} skills (workflow-oriented guides).",
        epilog=(
            f"Examples:\n"
            f"  {prog} skills list\n"
            f"  {prog} skills get test-selection\n"
            f"  {prog} skills export --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--help-recursive",
        action="store_true",
        help="Show help for all subcommands",
    )
    skills_sub = parser.add_subparsers(dest="skills_command", title="Commands")

    # skills list
    list_p = skills_sub.add_parser(
        "list",
        help="List available skill pages",
        epilog=f"Examples:\n  {prog} skills list\n  {prog} skills list --json\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_p.add_argument("--json", action="store_true", dest="as_json")
    list_p.set_defaults(func=lambda args: _skills_list(args, package))

    # skills get [name]
    get_p = skills_sub.add_parser(
        "get",
        help="Show a skill page",
        epilog=(
            f"Examples:\n"
            f"  {prog} skills get                  # list available\n"
            f"  {prog} skills get test-selection   # show specific\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_p.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Skill name (see 'skills list')",
    )
    get_p.add_argument("--json", action="store_true", dest="as_json")
    get_p.set_defaults(func=lambda args: _skills_get(args, package))

    # skills export
    export_p = skills_sub.add_parser(
        "export",
        help="Export skills to ~/.claude/skills/scitex/",
        epilog=(
            f"Examples:\n"
            f"  {prog} skills export                 # default dest\n"
            f"  {prog} skills export --dest /tmp/skills\n"
            f"  {prog} skills export --dry-run --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export_p.add_argument(
        "--dest",
        default=None,
        help="Exact target directory (default: ~/.claude/skills/scitex/)",
    )
    export_p.add_argument(
        "--source",
        choices=["installed", "pypi"],
        default="installed",
        help="local (installed packages) or pypi (download wheels)",
    )
    export_p.add_argument(
        "--clean",
        action="store_true",
        help="Delete package subdirs before exporting",
    )
    export_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be exported without writing",
    )
    export_p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation when overwriting destination",
    )
    export_p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output as JSON",
    )
    export_p.set_defaults(func=lambda args: _skills_export(args, package))

    parser.set_defaults(
        func=lambda args: parser.print_help() if args.skills_command is None else None
    )
    return parser


def _skills_list(args: argparse.Namespace, package: str) -> None:
    import logging

    logging.getLogger("scitex_dev._core.discovery").setLevel(logging.ERROR)
    from .._ecosystem._skills.skills import list_skills

    result = list_skills(package=package)
    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        items = result.get(package, [])
        if not items:
            print(f"No skills found for {package}.")
            return
        print(f"Available skills for {package}:\n")
        for s in items:
            desc = f"  {s['description']}" if s["description"] else ""
            print(f"  {s['name']}")
            if desc:
                print(f"    {s['description']}")
        prog = package.replace("_", "-")
        print(f"\nUsage: {prog} skills get <name>")


def _skills_export(args: argparse.Namespace, package: str) -> None:
    import logging

    logging.getLogger("scitex_dev._core.discovery").setLevel(logging.ERROR)
    from .._ecosystem._skills.skills import export_skills

    from .._ecosystem._skills.skills import _get_default_export_dest

    dest = (
        Path(args.dest) if getattr(args, "dest", None) else _get_default_export_dest()
    )
    source = getattr(args, "source", "installed")
    clean = getattr(args, "clean", False)
    if getattr(args, "dry_run", False):
        from .._ecosystem._skills.skills import list_skills

        result = {
            k: [e["name"] + ".md" for e in v]
            for k, v in list_skills(package=package).items()
        }
        total = sum(len(v) for v in result.values())
        if getattr(args, "as_json", False):
            print(
                json.dumps(
                    {"dest": str(dest), "source": source, "packages": result}, indent=2
                )
            )
        else:
            print(f"Would export {total} files to {dest}/ (source={source})")
            for k, v in sorted(result.items()):
                print(f"  {k}/: {len(v)} files")
        return
    exported = export_skills(dest, package=package, clean=clean, source=source)
    if not exported:
        print(f"No skills found for {package}.", file=sys.stderr)
        sys.exit(2)
    if getattr(args, "as_json", False):
        print(
            json.dumps({k: [str(f) for f in v] for k, v in exported.items()}, indent=2)
        )
    else:
        total = sum(len(v) for v in exported.values())
        print(f"Exported {total} files across {len(exported)} packages")
        for k, v in exported.items():
            print(f"  {k}: {len(v)} files")


def _skills_get(args: argparse.Namespace, package: str) -> None:
    import logging

    logging.getLogger("scitex_dev._core.discovery").setLevel(logging.ERROR)

    # No name given → show available names
    if args.name is None:
        _skills_list(argparse.Namespace(as_json=False), package)
        return

    from .._ecosystem._skills.skills import get_skill

    content = get_skill(package=package, name=args.name)
    if content:
        if args.as_json:
            print(
                json.dumps({"package": package, "name": args.name, "content": content})
            )
        else:
            print(content)
    else:
        print(f"Skill '{args.name}' not found in {package}.", file=sys.stderr)
        print(f"Run: {package} skills list", file=sys.stderr)
        sys.exit(2)
