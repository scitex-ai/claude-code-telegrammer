"""`scitex-dev ecosystem audit-brand <pkg>` subcommand.

Lives outside ``_registry.py`` because that file is already at its
size cap. The command is attached to the ecosystem group via
``register_audit_brand_command(ecosystem_group)`` called from
``ecosystem/__init__.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import click


def register_audit_brand_command(ecosystem_group):
    """Attach `audit-brand` to the given Click ecosystem group."""

    @ecosystem_group.command("audit-brand")
    @click.argument("brand_key")
    @click.option(
        "--path",
        "pkg_path",
        type=click.Path(exists=True, file_okay=False, path_type=str),
        default=None,
        help=(
            "Path to the package's local checkout. "
            "Defaults to $SCITEX_PROJECTS_ROOT/<brand>, then ~/proj/<brand>."
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.pass_context
    def ecosystem_audit_brand(ctx, brand_key, pkg_path, as_json):
        """Audit a branded package against PS-2xx rules.

        \b
        Rules:
          PS-201 no-local-brand-glue
          PS-202 umbrella-brand-symmetry
          PS-203 method-prefix-pair

        \b
        Example:
            $ scitex-dev ecosystem audit-brand figrecipe
            $ scitex-dev ecosystem audit-brand socialia
        """
        from ..._branding._audit import (
            audit_brand_package,
            find_package_root,
        )

        if pkg_path is None:
            try:
                root = find_package_root(brand_key)
            except FileNotFoundError as exc:
                click.echo(f"error: {exc}", err=True)
                ctx.exit(2)
                return
        else:
            root = Path(pkg_path)

        violations = audit_brand_package(root, brand_key)

        if as_json:
            click.echo(
                json.dumps({"brand": brand_key, "violations": violations}, indent=2)
            )
        else:
            if not violations:
                click.secho(f"audit-brand {brand_key}: clean ({root})", fg="green")
            else:
                click.secho(
                    f"audit-brand {brand_key}: {len(violations)} violation(s)",
                    fg="red",
                )
                for v in violations:
                    loc = f" [{v.get('file')}]" if v.get("file") else ""
                    click.echo(f"  {v['code']} {v['brand']}{loc}: {v['message']}")

        ctx.exit(1 if violations else 0)
