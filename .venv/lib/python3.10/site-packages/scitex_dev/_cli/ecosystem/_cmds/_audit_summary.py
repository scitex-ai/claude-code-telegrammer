#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem cross-leaf audit commands: `audit-summary`, `list-audit-rules`."""

import json

import click


def register(ecosystem):
    @ecosystem.command(
        "audit-summary",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-summary\n"
            "  $ scitex-dev ecosystem audit-summary --auditor python-apis\n"
            "  $ scitex-dev ecosystem audit-summary --json\n"
            "  $ scitex-dev ecosystem audit-summary --parallel 16\n"
            "\n"
            "Runs each scitex-dev auditor against every ecosystem leaf and\n"
            "prints per-leaf violation counts. Each rule is deterministic, so\n"
            "the same commit gives the same numbers across machines.\n"
            "\n"
            "Excluded by default: scitex (umbrella), scitex-orochi,\n"
            "scitex-hub. Pass --include-meta to include them."
        ),
    )
    @click.option(
        "--auditor",
        "auditors",
        multiple=True,
        type=click.Choice(
            [
                "python-apis",
                "skills",
                "project",
                "cli",
                "mcp-tools",
            ]
        ),
        help="Auditor(s) to run. Repeatable. Default: all five.",
    )
    @click.option(
        "--jobs",
        "-j",
        "parallel",
        default=8,
        type=int,
        show_default=True,
        help="Concurrent leaves audited in parallel (-j auto / -j0 = all CPUs).",
    )
    @click.option(
        "--include-meta",
        is_flag=True,
        help="Include scitex / scitex-orochi / scitex-hub (skipped by default).",
    )
    @click.option(
        "--json",
        "json_out",
        is_flag=True,
        help="Emit structured JSON instead of a table.",
    )
    def ecosystem_audit_summary(auditors, parallel, include_meta, json_out):
        """Cross-leaf, cross-auditor violation summary — one source of truth."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import subprocess
        from ...._ecosystem import ECOSYSTEM

        chosen = (
            list(auditors)
            if auditors
            else ["python-apis", "skills", "project", "cli", "mcp-tools"]
        )

        skip = set() if include_meta else {"scitex", "scitex-orochi", "scitex-hub"}
        leaves = sorted(name for name in ECOSYSTEM.keys() if name not in skip)

        def _audit_one(leaf, auditor):
            """Subprocess one (leaf, auditor); return (leaf, auditor, n_violations)."""
            try:
                proc = subprocess.run(
                    [
                        "scitex-dev",
                        "ecosystem",
                        f"audit-{auditor}",
                        leaf,
                        "--json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                # Auditors return non-zero on violations but still emit JSON.
                # Look for JSON in stdout regardless of exit code.
                payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
                violations = payload.get("violations", [])
                if not isinstance(violations, list):
                    violations = []
                return leaf, auditor, len(violations)
            except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
                return leaf, auditor, -1  # sentinel: error

        # Run all (leaf, auditor) pairs in a thread pool.
        results: dict[str, dict[str, int]] = {leaf: {} for leaf in leaves}
        pairs = [(leaf, a) for leaf in leaves for a in chosen]

        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = [pool.submit(_audit_one, leaf, a) for leaf, a in pairs]
            for fut in as_completed(futures):
                leaf, auditor, n = fut.result()
                results[leaf][auditor] = n

        if json_out:
            click.echo(
                json.dumps(
                    {
                        "auditors": chosen,
                        "leaves": leaves,
                        "violations": results,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        # Pretty table.
        col_w = 30
        click.secho(
            f"\n=== ecosystem audit-summary ({len(leaves)} leaves × {len(chosen)} auditors, parallel={parallel}) ===",
            fg="cyan",
            bold=True,
        )
        header = (
            f"{'PACKAGE':<{col_w}}" + "".join(f"{a:>14}" for a in chosen) + "  TOTAL"
        )
        click.echo(header)
        click.echo("-" * len(header))

        per_auditor_total = dict.fromkeys(chosen, 0)
        per_auditor_clean = dict.fromkeys(chosen, 0)
        leaf_total = 0

        for leaf in leaves:
            row = f"{leaf:<{col_w}}"
            row_total = 0
            row_has_violation = False
            for a in chosen:
                n = results[leaf].get(a, -1)
                if n < 0:
                    row += f"{'ERR':>14}"
                    continue
                row += f"{n:>14}"
                per_auditor_total[a] += n
                if n == 0:
                    per_auditor_clean[a] += 1
                else:
                    row_has_violation = True
                row_total += n
            row += f"  {row_total:>5}"
            leaf_total += row_total
            # Only print rows with violations, mirroring audit_snapshot.sh.
            if row_has_violation:
                click.echo(row)

        click.echo("-" * len(header))
        click.secho(
            f"{'TOTAL':<{col_w}}"
            + "".join(f"{per_auditor_total[a]:>14}" for a in chosen)
            + f"  {leaf_total:>5}",
            fg="yellow",
        )
        click.secho(
            f"{'CLEAN/N':<{col_w}}"
            + "".join(f"{per_auditor_clean[a]:>4}/{len(leaves):<9}" for a in chosen),
            fg="green",
        )

    @ecosystem.command("list-audit-rules")
    @click.option(
        "--auditor",
        type=click.Choice(["api", "project", "skills", "release", "all"]),
        default="all",
        help="Limit output to one auditor's rule corpus.",
    )
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit JSON instead of a table."
    )
    def ecosystem_list_audit_rules(auditor, as_json):
        """List every registered audit rule (id, section, message).

        Walks the four code-side rule registries:

        \b
          api      — PA*  (audit-python-apis)
          project  — PS*  (audit-project)
          skills   — SK*  (audit-skills)
          release  — E5C* (pyproject_lint, surfaces inside audit-project)

        \b
        Examples:
          $ scitex-dev ecosystem list-audit-rules
          $ scitex-dev ecosystem list-audit-rules --auditor project
          $ scitex-dev ecosystem list-audit-rules --json | jq

        Note: audit-cli and audit-mcp-tools use §-numbered violations
        defined inline (no central registry), so they're not listed
        here. Their conventions live in
        `_skills/general/03_interface/02_cli/` and
        `_skills/general/03_interface/03_mcp/`.
        """
        import json as _json

        sources: dict[str, list[dict]] = {}

        def _push(name: str, items):
            if items:
                sources[name] = items

        if auditor in ("api", "all"):
            from ...audit._api._audit import RULES as PA_RULES

            _push(
                "api",
                [
                    {
                        "id": r.code,
                        "slug": getattr(r, "slug", "") or "",
                        "section": r.section,
                        "message": r.message,
                    }
                    for r in PA_RULES.values()
                ],
            )
        if auditor in ("project", "all"):
            from ...audit._project._audit import RULES as PS_RULES

            _push(
                "project",
                [
                    {
                        "id": r.code,
                        "slug": getattr(r, "slug", "") or "",
                        "section": r.section,
                        "message": r.message,
                        "severity": getattr(r, "severity", "?"),
                    }
                    for r in PS_RULES.values()
                ],
            )
        if auditor in ("skills", "all"):
            from ...audit._skills._audit import RULES as SK_RULES

            _push(
                "skills",
                [
                    {
                        "id": r.code,
                        "slug": getattr(r, "slug", "") or "",
                        "section": r.section,
                        "message": r.message,
                    }
                    for r in SK_RULES.values()
                ],
            )
        if auditor in ("release", "all"):
            # pyproject_lint declares E5C* rules implicitly via per-check
            # functions; pull canonical (rule_id, severity, summary) from
            # the module docstring + check_*-name → finding.rule mapping.
            release_rules = [
                {
                    "id": "REL-5",
                    "slug": "implicit-deps-not-declared",
                    "section": "release",
                    "message": "implicit deps not declared",
                },
                {
                    "id": "REL-9",
                    "slug": "skills-not-bundled",
                    "section": "release",
                    "message": "_skills/ ships but build excludes it",
                },
                {
                    "id": "REL-10",
                    "slug": "duplicate-toml-table",
                    "section": "release",
                    "message": "duplicate TOML table",
                },
                {
                    "id": "REL-11",
                    "slug": "license-deprecated-form",
                    "section": "release",
                    "message": "deprecated PEP 621 license form",
                },
                {
                    "id": "REL-12",
                    "slug": "min-version-pin-missing",
                    "section": "release",
                    "message": "dependency missing >= lower bound",
                },
                {
                    "id": "REL-21",
                    "slug": "version-drift",
                    "section": "release",
                    "message": "pyproject ↔ tag ↔ PyPI version drift",
                },
                {
                    "id": "REL-41",
                    "slug": "readme-missing-interfaces-callout",
                    "section": "release",
                    "message": "README missing Interfaces callout",
                },
                {
                    "id": "REL-31",
                    "slug": "internal-api-leak",
                    "section": "release",
                    "message": "internal API leak (private re-exported)",
                },
            ]
            _push("release", release_rules)

        if as_json:
            click.echo(_json.dumps(sources, indent=2))
            return

        for name, items in sources.items():
            click.secho(f"\n=== {name} ({len(items)} rules) ===", fg="cyan")
            for r in items:
                sev = f" [{r['severity']}]" if "severity" in r else ""
                slug = r.get("slug", "")
                slug_str = f"  {slug}" if slug else ""
                click.echo(
                    f"  {r['id']:7} {r['section']:5}{sev}{slug_str:40s}  {r['message']}"
                )
