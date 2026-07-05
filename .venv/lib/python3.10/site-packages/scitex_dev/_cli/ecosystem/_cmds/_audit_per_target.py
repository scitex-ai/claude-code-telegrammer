#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem per-target audit commands: `audit-cli`, `audit-mcp-tools`,
`audit-python-apis`, `audit-skills`, `audit-project`, `audit-django`,
`init-config`."""

import click

try:
    # SSOT for valid project types; keeps `init-config --project-type`
    # choices in sync with the loader instead of a hand-maintained list.
    from ...audit._config._loader import PROJECT_TYPES as _PROJECT_TYPES

    _PROJECT_TYPE_CHOICES = sorted(_PROJECT_TYPES)
except Exception:  # pragma: no cover - defensive fallback
    _PROJECT_TYPE_CHOICES = ["deferred", "django", "pip", "research", "special"]


def _audit_cli_epilog() -> str:
    """Build a dynamic --help epilog showing the registry cascade + entries."""
    try:
        from ...audit._summary._audit import REGISTRY_CASCADE_DOC, _load_registry
    except Exception:
        return ""
    registry, provenance = _load_registry(None)
    # Group by category
    from collections import defaultdict

    groups: dict[str, list[str]] = defaultdict(list)
    for name, info in registry.items():
        groups[info.get("category", "uncategorized")].append(name)

    # Click rewraps epilog paragraphs; prefix each preserved paragraph
    # with `\b` so Click leaves whitespace alone.
    lines: list[str] = ["\b", REGISTRY_CASCADE_DOC.rstrip(), ""]
    lines.append("\b")
    lines.append(f"Resolved registry source: {provenance}")
    lines.append("")
    lines.append("\b")
    lines.append("Registry contents (used by --all):")
    for cat in sorted(groups):
        lines.append(f"  [{cat}] ({len(groups[cat])})")
        for n in sorted(groups[cat]):
            lines.append(f"    {n}")
    lines.append("")
    lines.append("\b")
    lines.append("Examples:")
    lines.append("  $ scitex-dev ecosystem audit-cli scitex-plt")
    lines.append("  $ scitex-dev ecosystem audit-cli scitex-plt --behavioral")
    lines.append("  $ scitex-dev ecosystem audit-cli --all")
    lines.append("  $ scitex-dev ecosystem audit-cli --all --json > drift.json")
    lines.append(
        "  $ scitex-dev ecosystem audit-cli --all --dry-run   # list targets only"
    )
    return "\n".join(lines)


def register(ecosystem):
    @ecosystem.command(
        "audit-cli",
        epilog=_audit_cli_epilog(),
    )
    @click.argument("package", required=False)
    @click.option(
        "--all",
        "audit_all",
        is_flag=True,
        help="Audit every package in the resolved registry (see epilog for the cascade).",
    )
    @click.option(
        "--behavioral",
        is_flag=True,
        help="Run subprocess-based checks (§1a -v ladder, §3 exit codes, §8 --json stdout). Slow.",
    )
    @click.option(
        "--json",
        "output_json",
        is_flag=True,
        help="Machine-readable JSON output on stdout (per §2 / §8).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="With --all: list the targets that would be audited; do nothing else.",
    )
    @click.option(
        "--registry",
        "registry_path",
        default=None,
        type=click.Path(dir_okay=False),
        help="Override the registry source (highest precedence in the cascade).",
    )
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Only report violations of this rule (e.g. --rule §1a). Repeatable.",
    )
    @click.option(
        "--exclude",
        "exclude_rules",
        multiple=True,
        help="Suppress this rule (e.g. --exclude §4). Repeatable.",
    )
    @click.option(
        "--severity",
        "min_severity",
        type=click.Choice(["info", "warn", "error"], case_sensitive=False),
        default=None,
        help="Only report violations at or above this severity.",
    )
    @click.option(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-package subprocess timeout (seconds) for behavioral checks.",
    )
    def ecosystem_audit_cli(
        package,
        audit_all,
        behavioral,
        output_json,
        dry_run,
        registry_path,
        rules,
        exclude_rules,
        min_severity,
        timeout,
    ):
        """Check a package's CLI against the noun-verb convention (warn-only).

        Requires the `cli-audit` extra: pip install 'scitex-dev[cli-audit]'

        The package list for --all is resolved via the registry cascade
        documented in the epilog below.
        """
        from ...audit import _summary as _cli_audit

        raise SystemExit(
            _cli_audit.audit_cli(
                package=package,
                behavioral=behavioral,
                output_json=output_json,
                audit_all=audit_all,
                dry_run=dry_run,
                registry_path=registry_path,
                rules=tuple(rules),
                exclude=tuple(exclude_rules),
                min_severity=min_severity,
                timeout=timeout,
            )
        )

    # ------------------------------------------------------------------ #
    # audit-mcp-tools — companion to audit-cli for MCP servers           #
    # ------------------------------------------------------------------ #

    @ecosystem.command(
        "audit-mcp-tools",
        epilog=(
            "\b\nRules audited (per scitex `_skills/general/03_interface/03_mcp/`):\n"
            "\b\n"
            "  §1  server registration (single FastMCP, mount pattern, no double prefix)\n"
            "  §2  tool naming `<pkg>_<verb>_<noun>` snake_case\n"
            "  §3  required `mcp` subcommands (start | doctor | list-tools | show-installation)\n"
            "  §4  `mcp list-tools` -v|-vv|-vvv + --json (behavioral)\n"
            "  §5  `<pkg>_skills_list` and `<pkg>_skills_get` present\n"
            "  §6  Python-API ↔ MCP-tool parity\n"
            "\n"
            "\b\nExamples:\n"
            "  $ scitex-dev ecosystem audit-mcp-tools scitex-hub\n"
            "  $ scitex-dev ecosystem audit-mcp-tools scitex-hub --behavioral\n"
            "  $ scitex-dev ecosystem audit-mcp-tools --all --json > mcp-drift.json"
        ),
    )
    @click.argument("package", required=False)
    @click.option(
        "--all",
        "audit_all",
        is_flag=True,
        help="Audit every MCP-bearing package in the resolved registry.",
    )
    @click.option(
        "--behavioral",
        is_flag=True,
        help="Run subprocess-based checks (§3 mcp subcommands, §4 ladder + --json). Slow.",
    )
    @click.option(
        "--json",
        "output_json",
        is_flag=True,
        help="Machine-readable JSON output on stdout.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="With --all: list the targets that would be audited; do nothing else.",
    )
    @click.option(
        "--registry",
        "registry_path",
        default=None,
        type=click.Path(dir_okay=False),
        help="Override the registry source (highest precedence in the cascade).",
    )
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Only report violations of this rule (e.g. --rule §2). Repeatable.",
    )
    @click.option(
        "--exclude",
        "exclude_rules",
        multiple=True,
        help="Suppress this rule (e.g. --exclude §6). Repeatable.",
    )
    @click.option(
        "--severity",
        "min_severity",
        type=click.Choice(["info", "warn", "error"], case_sensitive=False),
        default=None,
        help="Only report violations at or above this severity.",
    )
    @click.option(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-package subprocess timeout (seconds) for behavioral checks.",
    )
    def ecosystem_audit_mcp_tools(
        package,
        audit_all,
        behavioral,
        output_json,
        dry_run,
        registry_path,
        rules,
        exclude_rules,
        min_severity,
        timeout,
    ):
        """Check a package's MCP server against the canonical convention (warn-only).

        Requires the `cli-audit` extra: pip install 'scitex-dev[cli-audit]'

        The package list for --all is resolved via the same registry cascade
        used by `audit-cli` (see that command's --help).
        """
        from ...audit._summary._mcp_audit import run_audit_mcp, run_audit_mcp_all

        if audit_all:
            raise SystemExit(
                run_audit_mcp_all(
                    behavioral=behavioral,
                    output_json=output_json,
                    dry_run=dry_run,
                    registry_path=registry_path,
                    rules=tuple(rules),
                    exclude=tuple(exclude_rules),
                    min_severity=min_severity,
                    timeout=timeout,
                )
            )
        if package is None:
            click.echo("error: PACKAGE is required (or pass --all)", err=True)
            raise SystemExit(2)
        raise SystemExit(
            run_audit_mcp(
                package,
                behavioral=behavioral,
                output_json=output_json,
                rules=tuple(rules),
                exclude=tuple(exclude_rules),
                min_severity=min_severity,
                timeout=timeout,
            )
        )

    # ------------------------------------------------------------------ #
    # audit-python-apis — companion to audit-cli / audit-mcp-tools for    #
    # the Python API surface (mirrors `list-python-apis` introspection)   #
    # ------------------------------------------------------------------ #

    @ecosystem.command(
        "audit-python-apis",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-python-apis scitex-io\n"
            "  $ scitex-dev ecosystem audit-python-apis scitex-io --json\n"
            "  $ scitex-dev ecosystem audit-python-apis scitex-io --rule PA-101 --rule PA-202\n"
            "\n"
            "Foundation rules (PA<§><idx>): PA-101–104 (§1 naming/visibility),\n"
            "PA-201–203 (§2 version), PA-301 (§3 lazy imports), PA-501 (§5 future\n"
            "annotations). See general/03_interface/01_python-api/12_audit-checklist.md."
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--path",
        "--repo",
        "repo_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
        default=None,
        help=(
            "Repo root to audit (defaults to the registry's local_path or "
            "the installed package's location). Use `--path` when running "
            "from a git worktree so the audit sees the worktree's source "
            "instead of the editable install — lets worktree agents "
            "self-verify before pushing. `--repo` is a legacy alias."
        ),
    )
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Restrict to specific rule codes (e.g. --rule PA-101). Repeatable.",
    )
    def ecosystem_audit_python_apis(distribution, repo_path, json_out, rules):
        """Check a package's Python API against the §1–§5 audit checklist.

        Honours per-project rule scoping the same way `audit-project` does:
        `.scitex/dev/config.yaml` `audit.skip` defers specific PA rules (e.g.
        PA-306/PA-307) and a `django` project-type relaxes PA-306 (no-mocks)
        to a warning. The repo root is taken from `--repo`, else the
        registry's `local_path`.
        """
        from pathlib import Path

        from ...._ecosystem import ECOSYSTEM
        from ...audit import _api as _cli_audit_api

        repo = Path(repo_path).expanduser() if repo_path else None
        if repo is None:
            local = ECOSYSTEM.get(distribution, {}).get("local_path")
            if local:
                cand = Path(local).expanduser()
                if cand.is_dir():
                    repo = cand

        raise SystemExit(
            _cli_audit_api.audit_api(
                distribution,
                json_out=json_out,
                rules=set(rules) if rules else None,
                repo_root=repo,
            )
        )

    # ------------------------------------------------------------------ #
    # audit-skills — companion to audit-cli / audit-mcp-tools / audit-   #
    # python-apis for the `_skills/<pip-name>/` tree                      #
    # ------------------------------------------------------------------ #

    @ecosystem.command(
        "audit-skills",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-skills scitex-io\n"
            "  $ scitex-dev ecosystem audit-skills scitex-io --json\n"
            "  $ scitex-dev ecosystem audit-skills scitex-io --rule SK-210 --rule SK-211\n"
            "\n"
            "Foundation rules (SK<§><idx>): SK-101–104 (§1 layout), SK-201–203\n"
            "(§2 naming), SK-210–211 (§2a no header/footer above frontmatter),\n"
            "SK-301–302 (§3 SKILL.md as index), SK-401 (§4 leaf size), SK-601\n"
            "(§6 no `import scitex as stx`), SK-701–704 (frontmatter required\n"
            "fields). See general/03_interface/04_skills/12_quality-checklist.md."
        ),
    )
    @click.argument("distribution")
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Restrict to specific rule codes (e.g. --rule SK-210). Repeatable.",
    )
    @click.option(
        "--fix",
        is_flag=True,
        help=(
            "Auto-fix mechanically resolvable rules (SK-705/SK-709/SK-710). "
            "Rewrites only frontmatter; idempotent."
        ),
    )
    def ecosystem_audit_skills(distribution, json_out, rules, fix):
        """Check a package's `_skills/<pip-name>/` against the §1–§FM checklist."""
        from ...audit import _skills as _cli_audit_skills

        raise SystemExit(
            _cli_audit_skills.audit_skills(
                distribution,
                json_out=json_out,
                rules=set(rules) if rules else None,
                fix=fix,
            )
        )

    @ecosystem.command(
        "audit-project",
        epilog=(
            "Project-structure auditor.\n"
            "\n"
            "Foundation rules (PS<§><idx>):\n"
            "  PS-101–104  §1 top-level layout (pyproject, forbidden dirs, junk)\n"
            "  PS-201–206  §2 src ↔ tests mirror (parent, mirror, prefix, orphan, placeholder)\n"
            "  PS-301–303  §3 tests/ subdir convention (htmlcov, unknown subdirs, examples)\n"
            "  PS-401–402  §4 docs/ structure (to_claude gitignored, assets location)\n"
            "\n"
            "See _skills/general/02_package/01_project-structure-root.md for the\n"
            "full convention; ditto _skills/scientific/02_research-project_01_project-structure-root.md\n"
            "for research-project layout. Templates and datasets are exempt from §2."
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--path",
        "--repo",
        "repo_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
        default=None,
        help=(
            "Repo root to audit (defaults to the registry's local_path or "
            "the installed package's location). Use `--path` when running "
            "from a git worktree so the audit sees the worktree's source "
            "instead of the editable install — lets worktree agents "
            "self-verify before pushing. `--repo` is a legacy alias."
        ),
    )
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Restrict to specific rule codes (e.g. --rule PS-201). Repeatable.",
    )
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default="error",
        show_default=True,
        help=(
            "Minimum severity floor. 'error' prints E findings only and exits 1 "
            "iff ≥1 E. 'warning' prints E+W. 'info' prints everything. "
            "W/I findings never fail CI on their own."
        ),
    )
    def ecosystem_audit_project(distribution, repo_path, json_out, rules, severity):
        """Check a package's project-structure against the canonical layout.

        \b
        Example:
            $ scitex-dev ecosystem audit-project scitex-io
            $ scitex-dev ecosystem audit-project scitex-dev --json
            $ scitex-dev ecosystem audit-project scitex-stats --rule PS-108
            $ scitex-dev ecosystem audit-project scitex-io --severity warning
        """
        from pathlib import Path

        from ...audit import _project as _cli_audit_project
        from ...._ecosystem import ECOSYSTEM

        repo = Path(repo_path).expanduser() if repo_path else None
        if repo is None:
            local = ECOSYSTEM.get(distribution, {}).get("local_path")
            if local:
                cand = Path(local).expanduser()
                if cand.is_dir():
                    repo = cand

        raise SystemExit(
            _cli_audit_project.audit_project(
                distribution,
                repo=repo,
                json_out=json_out,
                rules=set(rules) if rules else None,
                severity=severity,
            )
        )

    # ------------------------------------------------------------------ #
    # audit-django — companion to audit-project for Django apps. Checks  #
    # the repo against ADR 0002 (scitex-django-app-standard); scitex-hub #
    # is the green reference. Non-Django packages are skipped cleanly.   #
    # ------------------------------------------------------------------ #
    @ecosystem.command(
        "audit-django",
        epilog=(
            'Django "apps and config" auditor (ADR 0002).\n'
            "\n"
            "Foundation rules (DJ<§><idx>):\n"
            "  DJ-101-110  §1 Django project in `config/` (settings package +\n"
            "              env-loader, urls, asgi/wsgi, manage.py default)\n"
            "  DJ-201-204  §2 apps under `apps/` (infra/workspace, AppConfig)\n"
            "  DJ-301-302  §3 project `templates/` + `static/`\n"
            "  DJ-401-402  §4 `src/scitex_<name>/` pip package sibling (not nested)\n"
            "  DJ-501-502  §5 web stack in the `[all]` extra (no `[django]` sub-extra)\n"
            "\n"
            "scitex-hub is the reference implementation and passes by\n"
            "definition. Non-Django packages (no `manage.py`) are skipped.\n"
            "See docs/adr/0002-scitex-django-app-standard.md in scitex-hub.\n"
            "\n"
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-django scitex-hub\n"
            "  $ scitex-dev ecosystem audit-django scitex-hub --json\n"
            "  $ scitex-dev ecosystem audit-django scitex-orochi --severity warning\n"
            "  $ scitex-dev ecosystem audit-django scitex-hub --rule DJ-101"
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--path",
        "--repo",
        "repo_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
        default=None,
        help=(
            "Repo root to audit (defaults to the registry's local_path or "
            "the installed package's location). Use `--path` when running "
            "from a git worktree so the audit sees the worktree's source "
            "instead of the editable install — lets worktree agents "
            "self-verify before pushing. `--repo` is a legacy alias."
        ),
    )
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Restrict to specific rule codes (e.g. --rule DJ-101). Repeatable.",
    )
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default="error",
        show_default=True,
        help=(
            "Minimum severity floor. 'error' prints E findings only and exits 1 "
            "iff >=1 E. 'warning' prints E+W. 'info' prints everything. "
            "W/I findings never fail CI on their own."
        ),
    )
    def ecosystem_audit_django(distribution, repo_path, json_out, rules, severity):
        """Check a Django app against the canonical "apps and config" layout.

        \b
        Example:
            $ scitex-dev ecosystem audit-django scitex-hub
            $ scitex-dev ecosystem audit-django scitex-orochi --json
            $ scitex-dev ecosystem audit-django scitex-hub --rule DJ-101
        """
        from pathlib import Path

        from ...._ecosystem import ECOSYSTEM
        from ...audit import _django as _cli_audit_django

        repo = Path(repo_path).expanduser() if repo_path else None
        if repo is None:
            local = ECOSYSTEM.get(distribution, {}).get("local_path")
            if local:
                cand = Path(local).expanduser()
                if cand.is_dir():
                    repo = cand

        raise SystemExit(
            _cli_audit_django.audit_django(
                distribution,
                repo=repo,
                json_out=json_out,
                rules=set(rules) if rules else None,
                severity=severity,
            )
        )

    # ------------------------------------------------------------------ #
    # init-config — write a `.scitex/dev/config.yaml` from the heuristic #
    # so the user can confirm + commit the project's type.               #
    # ------------------------------------------------------------------ #
    @ecosystem.command("init-config")
    @click.option(
        "--repo",
        "repo_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
        default=".",
        show_default=True,
        help="Project root (defaults to cwd).",
    )
    @click.option(
        "--project-type",
        "project_types",
        multiple=True,
        type=click.Choice(_PROJECT_TYPE_CHOICES),
        help=(
            "Override the heuristic guess. Repeatable for hybrid repos "
            "(e.g. a Django app that is also a pip package: "
            "`--project-type pip --project-type django`)."
        ),
    )
    @click.option(
        "--force",
        is_flag=True,
        help="Overwrite an existing .scitex/dev/config.yaml.",
    )
    @click.option("--yes", "-y", is_flag=True, help="Confirm destructive write.")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the target path and detected project types without writing.",
    )
    def ecosystem_init_config(repo_path, project_types, force, yes, dry_run):
        """Write `.scitex/dev/config.yaml` from the heuristic guess.

        \b
        Example:
            $ scitex-dev ecosystem init-config
            $ scitex-dev ecosystem init-config --project-type research --yes
            $ scitex-dev ecosystem init-config --project-type pip --project-type research
            $ scitex-dev ecosystem init-config --dry-run
        """
        del yes  # accepted for §2 compliance; --force gates overwrite
        from pathlib import Path

        from ...audit._config import detect_project_types, write_config

        repo = Path(repo_path).expanduser().resolve()
        types = (
            list(project_types) if project_types else sorted(detect_project_types(repo))
        )
        if dry_run:
            target = repo / ".scitex" / "dev" / "config.yaml"
            click.echo(f"# would write: {target}  (project-type: {', '.join(types)})")
            return
        try:
            written = write_config(repo, project_types=types, overwrite=force)
        except FileExistsError as e:
            click.echo(
                f"refuse: {e} already exists; pass --force to overwrite.",
                err=True,
            )
            raise SystemExit(1)
        click.echo(f"wrote: {written}  (project-type: {', '.join(types)})")
