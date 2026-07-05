#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI stats command for scitex-dev — ecosystem statistics."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict

import click


def _run_cmd(cmd: list[str], timeout: int = 30) -> str:
    """Run a command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _run_cmd_json(cmd: list[str], timeout: int = 30) -> Any:
    """Run a command expecting JSON output, return parsed data or None."""
    output = _run_cmd(cmd, timeout=timeout)
    if not output:
        return None
    try:
        return json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return None


def _count_packages() -> int:
    """Count ecosystem packages from the registry."""
    from .._ecosystem import ECOSYSTEM

    return len(ECOSYSTEM)


def _count_cli_commands() -> int:
    """Count CLI commands by parsing scitex --help output.

    Parses the Click help output which lists commands after 'Commands:'.
    """
    output = _run_cmd(["scitex", "--help"])
    if not output:
        return 0
    count = 0
    in_commands = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped == "Commands:":
            in_commands = True
            continue
        if in_commands:
            if not stripped:
                break
            # Each command line in Click help is "  name  description"
            if stripped and not stripped.startswith("-"):
                count += 1
    return count


def _count_mcp_tools() -> int:
    """Count MCP tools from scitex MCP server.

    Uses --json flag and reads the 'total' field for reliability.
    Timeout is longer (120s) since loading all tools takes time.
    """
    data = _run_cmd_json(["scitex", "mcp", "list-tools", "--json"], timeout=120)
    if data and isinstance(data, dict):
        if "total" in data:
            return data["total"]
        if "tools" in data and isinstance(data["tools"], list):
            return len(data["tools"])
    return 0


def _count_skills() -> int:
    """Count skills from scitex dev skills list.

    Uses --json flag: output is {pkg_name: [skills...], ...}.
    """
    data = _run_cmd_json(["scitex", "dev", "skills", "list", "--json"])
    if data and isinstance(data, dict):
        total = 0
        for _pkg, skills in data.items():
            if isinstance(skills, (list, dict)):
                total += len(skills)
        return total
    return 0


def _count_python_apis() -> int:
    """Count public Python APIs via dir(stx)."""
    try:
        import scitex as stx

        public = [name for name in dir(stx) if not name.startswith("_")]
        return len(public)
    except ImportError:
        return 0


def _count_file_formats() -> int:
    """Count supported file formats.

    stx.io.list_formats() returns nested dict:
    {"save": {"builtin": [".csv", ...], "user": [...]}, "load": {...}}
    We count unique extensions across all categories.
    """
    try:
        import scitex as stx

        if hasattr(stx, "io") and hasattr(stx.io, "list_formats"):
            _fn = getattr(stx.io, "list_formats")
            if not callable(_fn):
                return 0
            formats = _fn()
            all_exts: set[str] = set()
            if isinstance(formats, dict):
                for _direction, categories in formats.items():
                    if isinstance(categories, dict):
                        for _cat, exts in categories.items():
                            if isinstance(exts, (list, tuple)):
                                all_exts.update(exts)
                    elif isinstance(categories, (list, tuple)):
                        all_exts.update(categories)
            return len(all_exts)
    except (ImportError, Exception):
        pass
    return 0


def _count_stat_tests() -> int:
    """Count available statistical tests."""
    try:
        import scitex as stx

        if hasattr(stx, "stats"):
            test_funcs = [
                name
                for name in dir(stx.stats)
                if name.startswith("test_") and callable(getattr(stx.stats, name, None))
            ]
            return len(test_funcs)
    except (ImportError, Exception):
        pass
    return 0


def collect_stats() -> Dict[str, Any]:
    """Collect all ecosystem statistics.

    Returns
    -------
    dict
        Keys are stat names, values are counts.
    """
    stats = {}

    stats["packages"] = _count_packages()
    stats["cli_commands"] = _count_cli_commands()
    stats["mcp_tools"] = _count_mcp_tools()
    stats["skills"] = _count_skills()
    stats["python_apis"] = _count_python_apis()
    stats["file_formats"] = _count_file_formats()
    stats["stat_tests"] = _count_stat_tests()

    return stats


def format_stats_text(stats: Dict[str, Any]) -> str:
    """Format stats as human-readable text."""
    lines = []
    lines.append("SciTeX Ecosystem Statistics")
    lines.append("===========================")

    label_map = [
        ("packages", "Packages"),
        ("cli_commands", "CLI Commands"),
        ("mcp_tools", "MCP Tools"),
        ("skills", "Skills"),
        ("python_apis", "Python APIs"),
        ("file_formats", "File Formats"),
        ("stat_tests", "Stat Tests"),
    ]

    for key, label in label_map:
        value = stats.get(key, 0)
        if key == "file_formats" and value > 0:
            lines.append(f"{label + ':':<16}{value}+")
        else:
            lines.append(f"{label + ':':<16}{value}")

    return "\n".join(lines)


def register_stats_command(
    ecosystem_group: click.Group, main_group: click.Group | None = None
) -> None:
    """Register the canonical `ecosystem stats` and a deprecated top-level alias.

    The canonical command lives at ``scitex-dev ecosystem stats`` (matches
    the noun-verb hierarchy: ecosystem is the noun, stats is the verb-ish
    leaf). The legacy ``scitex-dev show-stats`` is kept as a hidden
    deprecation alias for one cycle and removed in 0.11.0.
    """

    @ecosystem_group.command("show-stats")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def show_stats(as_json: bool) -> None:
        """Show SciTeX ecosystem statistics (package counts, CLI commands, MCP tools, …).

        \b
        Example:
            $ scitex-dev ecosystem show-stats
            $ scitex-dev ecosystem show-stats --json
        """
        result = collect_stats()
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(format_stats_text(result))

    # Deprecated bare-noun alias (§1: leaves must be verbs). Removed in 0.11.0.
    @ecosystem_group.command("stats", hidden=True)
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def _stats_bare_deprecated(as_json: bool) -> None:
        """(deprecated) Use `ecosystem show-stats`. Removed in 0.11.0."""
        click.echo(
            "warning: `ecosystem stats` was renamed to `ecosystem show-stats` "
            "(verb-noun per §1).",
            err=True,
        )
        result = collect_stats()
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(format_stats_text(result))

    if main_group is None:
        return

    @main_group.command(
        "show-stats",
        hidden=True,
        context_settings={"ignore_unknown_options": True},
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def show_stats_deprecated(as_json: bool) -> None:
        """(deprecated) Use `scitex-dev ecosystem stats`. Removed in 0.11.0."""
        click.echo(
            "warning: `scitex-dev show-stats` was moved to `scitex-dev ecosystem stats`. "
            "Will be removed in 0.11.0.",
            err=True,
        )
        result = collect_stats()
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(format_stats_text(result))

    @main_group.command(
        "stats",
        hidden=True,
        context_settings={"ignore_unknown_options": True},
    )
    @click.pass_context
    def stats_deprecated(ctx: click.Context) -> None:
        """(deprecated) Use `scitex-dev ecosystem stats`."""
        click.echo(
            "error: `scitex-dev stats` was moved to `scitex-dev ecosystem stats`.",
            err=True,
        )
        ctx.exit(2)
