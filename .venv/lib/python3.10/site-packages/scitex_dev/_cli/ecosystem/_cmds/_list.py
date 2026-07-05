#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `list`, `show-graph` (+ deprecated `graph` alias)."""

import json

import click


def register(ecosystem):
    @ecosystem.command("list")
    @click.option("--package", "-p", multiple=True, help="Specific packages to check.")
    @click.option(
        "--category",
        "-c",
        multiple=True,
        help=(
            "Filter by package category (library, umbrella, dataset, "
            "external-lib, template). Repeatable. Intersected with -p."
        ),
    )
    @click.option("--versions", is_flag=True, help="Include version details.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.option(
        "--names-only",
        "-q",
        is_flag=True,
        help=(
            "Print only the package names, one per line. Pipe-friendly: "
            "`scitex-dev ecosystem list -q | xargs scitex-dev ecosystem audit-all`."
        ),
    )
    def ecosystem_list(package, category, versions, as_json, names_only):
        """List packages in the SciTeX ecosystem.

        \b
        Example:
            $ scitex-dev ecosystem list
            $ scitex-dev ecosystem list --json
            $ scitex-dev ecosystem list -q                # names only
            $ scitex-dev ecosystem list -p scitex-io --versions
            $ scitex-dev ecosystem list -c library        # by category
        """
        from ...._ecosystem import ECOSYSTEM, get_all_packages

        pkgs = list(package) if package else get_all_packages()
        if category:
            cat_set = set(category)
            pkgs = [p for p in pkgs if ECOSYSTEM.get(p, {}).get("category") in cat_set]

        if names_only:
            for pkg in pkgs:
                click.echo(pkg)
            return

        if versions:
            from .... import list_versions
            from ..._utils import wrap_as_cli

            wrap_as_cli(list_versions, as_json=as_json, packages=pkgs)
        elif as_json:
            items = [
                {
                    "name": pkg,
                    "github_repo": ECOSYSTEM.get(pkg, {}).get("github_repo", ""),
                }
                for pkg in pkgs
            ]
            click.echo(json.dumps({"packages": items}))
        else:
            for pkg in pkgs:
                info = ECOSYSTEM.get(pkg, {})
                repo = info.get("github_repo", "")
                click.echo(f"  {pkg:25s} {repo}")

    @ecosystem.command("show-graph")
    @click.option(
        "--format",
        "fmt",
        type=click.Choice(["mermaid", "dot"]),
        default="mermaid",
        help="Output format.",
    )
    @click.option(
        "--output",
        "-o",
        type=click.Path(dir_okay=False, writable=True),
        default=None,
        help="Write graph to FILE instead of stdout.",
    )
    @click.option(
        "--cycles",
        is_flag=True,
        help="Detect dependency cycles; exit 1 if any are found.",
    )
    @click.option(
        "--include-extras/--no-extras",
        default=True,
        help="Include optional-dependencies in the graph (default: include).",
    )
    @click.option(
        "--group-by-tier/--no-group-by-tier",
        default=True,
        help="Group nodes into tier subgraphs (mermaid only).",
    )
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit graph as JSON edges/nodes."
    )
    @click.pass_context
    def ecosystem_graph(
        ctx, fmt, output, cycles, include_extras, group_by_tier, as_json
    ):
        """Emit a current-state ecosystem dependency graph (mermaid/DOT).

        \b
        Example:
            $ scitex-dev ecosystem show-graph
            $ scitex-dev ecosystem show-graph --format dot -o /tmp/eco.dot
            $ scitex-dev ecosystem show-graph --cycles
            $ scitex-dev ecosystem show-graph --json
        """
        from ...._ecosystem import _graph as _eg

        pkgs = _eg.discover_packages()
        graph = _eg.build_graph(pkgs)

        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "nodes": list(graph.keys()),
                        "edges": [
                            {"from": src, "to": dst}
                            for src, deps in graph.items()
                            for dst in deps
                        ],
                        "package_count": len(graph),
                    }
                )
            )
            return

        if cycles:
            found = _eg.find_cycles(graph, include_extras=False)
            if not found:
                click.echo("No dependency cycles detected.")
                ctx.exit(0)
            click.echo(f"Detected {len(found)} cycle(s):", err=True)
            for cyc in found:
                click.echo("  - " + " -> ".join(cyc), err=True)
            ctx.exit(1)

        if fmt == "mermaid":
            text = _eg.to_mermaid(
                graph,
                group_by_tier=group_by_tier,
                include_extras=include_extras,
            )
        else:
            text = _eg.to_dot(graph, include_extras=include_extras)

        if output:
            from pathlib import Path as _P

            _P(output).write_text(text, encoding="utf-8")
            click.echo(f"Wrote {len(graph)}-node graph to {output}", err=True)
        else:
            click.echo(text, nl=False)

    # Deprecated bare-noun alias (§1: leaves must be verbs). Removed in 0.11.0.
    @ecosystem.command(
        "graph",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def _ecosystem_graph_deprecated(ctx):
        """(deprecated) Use `ecosystem show-graph`. Removed in 0.11.0."""
        click.echo(
            "warning: `ecosystem graph` was renamed to `ecosystem show-graph` "
            "(verb-noun per §1).",
            err=True,
        )
        target = ecosystem.get_command(ctx, "show-graph")
        if target is None:
            ctx.exit(2)
        ctx.invoke(target, *ctx.args)
