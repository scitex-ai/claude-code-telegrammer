#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI commands for skills aggregation -- registered on main CLI group."""

import json

import click


def register_skills_commands(main_group):
    """Register skills command group on the main CLI."""

    @main_group.group(invoke_without_command=True)
    @click.pass_context
    def skills(ctx):
        """Manage skills across the SciTeX ecosystem."""
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @skills.command("list")
    @click.option("--package", default=None, help="Filter by package name.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def skills_list(package, as_json):
        """List all skills across installed packages.

        \b
        Example:
            $ scitex-dev skills list
            $ scitex-dev skills list --json
            $ scitex-dev skills list --package scitex-io
        """
        from ..._ecosystem._skills.skills import drift_warning, list_skills

        result = list_skills(package=package)
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            if not result:
                click.echo("No skills found.")
                return
            for pkg, items in result.items():
                version = items[0].get("version", "") if items else ""
                ver_str = f" (v{version})" if version and version != "unknown" else ""
                click.echo(f"\n{pkg}{ver_str}:")
                for s in items:
                    desc = f" -- {s['description']}" if s["description"] else ""
                    click.echo(f"  {s['name']}{desc}")
            # Non-blocking drift signal: cached skills older than the
            # installed package version. Stderr only; never prompts.
            for pkg in result:
                w = drift_warning(pkg)
                if w:
                    click.echo(w, err=True)

    @skills.command("get")
    @click.argument("package")
    @click.argument("name", required=False, default=None)
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit skill as JSON envelope."
    )
    def skills_get(package, name, as_json):
        """Get content of a skill. Use 'all' to dump every skill across the ecosystem.

        \b
        Example:
            $ scitex-dev skills get scitex-io save-and-load
            $ scitex-dev skills get scitex-stats hypothesis-testing --json
            $ scitex-dev skills get all
        """
        from ..._ecosystem._skills.skills import (
            get_skill,
            list_skills,
        )

        if package == "all":
            all_skills = list_skills()
            if not all_skills:
                click.echo("No skills found.", err=True)
                raise SystemExit(1)
            for pkg_name, entries in sorted(all_skills.items()):
                for entry in entries:
                    content = get_skill(
                        package=pkg_name,
                        name=entry["name"] if entry["name"] != "SKILL" else None,
                    )
                    if content:
                        click.echo(f"\n{'=' * 60}")
                        click.echo(f"# {pkg_name}/{entry['name']}")
                        click.echo(f"{'=' * 60}\n")
                        click.echo(content)
            return

        content = get_skill(package=package, name=name)
        if content:
            if as_json:
                import json as _json

                click.echo(
                    _json.dumps({"package": package, "name": name, "content": content})
                )
            else:
                click.echo(content)
            # Non-blocking drift signal: cached skill older than installed.
            # Stderr only; never prompts.
            w = drift_warning(package)
            if w:
                click.echo(w, err=True)
        else:
            target = f"'{name}' in " if name else ""
            click.echo(f"Skill {target}package '{package}' not found.", err=True)
            raise SystemExit(1)

    @skills.command("init")
    @click.option(
        "--package",
        "pip_name",
        required=True,
        help="pip distribution name (e.g. `my-package`).",
    )
    @click.option(
        "--import-name",
        default=None,
        help="Python import name (default: pip-name with `-` → `_`).",
    )
    @click.option(
        "--dest",
        type=click.Path(),
        default=None,
        help="Target directory (default: src/<import>/_skills/<pip-name>/).",
    )
    @click.option(
        "--with-cli/--no-cli", default=True, help="Include 04_cli-reference.md."
    )
    @click.option("--with-mcp/--no-mcp", default=False, help="Include 05_mcp-tools.md.")
    @click.option(
        "--with-http/--no-http", default=False, help="Include 06_http-api.md."
    )
    @click.option("--with-env/--no-env", default=True, help="Include 20_env-vars.md.")
    @click.option("--force", is_flag=True, help="Overwrite existing files.")
    @click.option("--dry-run", is_flag=True, help="Preview without writing.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def skills_init(
        pip_name,
        import_name,
        dest,
        with_cli,
        with_mcp,
        with_http,
        with_env,
        force,
        dry_run,
        as_json,
        yes,
    ):
        """Scaffold a `_skills/<pip-name>/` tree per the standard template.

        \b
        Examples:
          scitex-dev skills init --package my-package
          scitex-dev skills init --package scitex-foo --with-mcp --with-http
          scitex-dev skills init --package my-package --dest /tmp/skills/ --dry-run
        """
        del yes  # accepted for §2 compliance; init honours --dry-run for preview
        import json as _json
        from pathlib import Path

        from ..._ecosystem._skills._scaffold import (
            build_plan,
            scaffold_package_skills,
        )

        imp = import_name or pip_name.replace("-", "_")
        target = Path(dest) if dest else Path("src") / imp / "_skills" / pip_name
        plan = build_plan(
            pip_name=pip_name,
            import_name=imp,
            dest=target,
            with_cli=with_cli,
            with_mcp=with_mcp,
            with_http=with_http,
            with_env=with_env,
        )

        if dry_run:
            payload = {
                "dest": str(plan.dest),
                "files": sorted(plan.files.keys()),
            }
            if as_json:
                click.echo(_json.dumps(payload, indent=2))
            else:
                click.echo(f"Would scaffold {len(plan.files)} files at {plan.dest}/")
                for name in payload["files"]:
                    click.echo(f"  {name}")
            return

        written, skipped = scaffold_package_skills(plan, force=force)
        if as_json:
            click.echo(
                _json.dumps(
                    {
                        "dest": str(plan.dest),
                        "written": [str(p) for p in written],
                        "skipped": [str(p) for p in skipped],
                    },
                    indent=2,
                )
            )
        else:
            click.echo(
                f"Scaffolded {len(written)} files at {plan.dest}/"
                + (
                    f" ({len(skipped)} skipped — use --force to overwrite)"
                    if skipped
                    else ""
                )
            )
            for p in written:
                click.echo(f"  + {p.name}")
            for p in skipped:
                click.echo(f"  . {p.name} (exists)")

    # ----- Canonical: `skills install` (replaces `export` + `collect`) -----
    @skills.command("install")
    @click.option(
        "--dest",
        type=click.Path(),
        default=None,
        help=(
            "Target directory. Default: ~/.scitex/dev/skills/ — the "
            "canonical store, peer to ~/.scitex/{audio,browser,scholar,...}/. "
            "Use --claude-symlink to also expose under ~/.claude/skills/scitex/."
        ),
    )
    @click.option("--package", default=None, help="Install only this package.")
    @click.option(
        "--source",
        type=click.Choice(["installed", "pypi"]),
        default="installed",
        help="installed or pypi.",
    )
    @click.option(
        "--clean", is_flag=True, help="Delete package subdirs before installing."
    )
    @click.option(
        "--link",
        is_flag=True,
        help="Symlink skill files to editable source (source=installed only); "
        "edits propagate live with no re-install.",
    )
    @click.option(
        "--claude-symlink",
        is_flag=True,
        help="After install, ensure ~/.claude/skills/scitex → DEST (idempotent). "
        "For Claude Code consumers; does not affect the source of truth at DEST.",
    )
    @click.option("--dry-run", is_flag=True, help="Preview without copying.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def skills_install(
        dest, package, source, clean, link, claude_symlink, dry_run, as_json, yes
    ):
        """Install skills from installed/PyPI packages into DEST (default: ~/.scitex/dev/skills/).

        \b
        Examples:
          scitex-dev skills install                                     # → ~/.scitex/dev/skills/
          scitex-dev skills install --claude-symlink                    # also → ~/.claude/skills/scitex/
          scitex-dev skills install --dest /tmp/skills --package scitex-writer
          scitex-dev skills install --link                              # editable symlink to source
          scitex-dev skills install --dry-run --json                    # preview
        """
        del yes  # accepted for §2 compliance; install honours --dry-run for preview
        import json as json_mod
        import os as _os
        from pathlib import Path

        from ..._ecosystem._skills.skills import export_skills, list_skills

        # Default to ~/.scitex/dev/skills/ (peer to other ~/.scitex/<pkg>/ stores)
        target = Path(dest) if dest else Path.home() / ".scitex" / "dev" / "skills"

        if dry_run:
            result = {
                k: [e["name"] + ".md" for e in v]
                for k, v in list_skills(package=package).items()
            }
            if as_json:
                click.echo(
                    json_mod.dumps(
                        {"dest": str(target), "source": source, "packages": result},
                        indent=2,
                    )
                )
            else:
                total = sum(len(v) for v in result.values())
                click.echo(
                    f"Would install {total} files to {target}/ (source={source})"
                )
                for k, v in sorted(result.items()):
                    click.echo(f"  {k}/: {len(v)} files")
                if claude_symlink:
                    claude_link = Path.home() / ".claude" / "skills" / "scitex"
                    click.echo(f"Would symlink {claude_link} → {target}")
            return

        target.mkdir(parents=True, exist_ok=True)
        exported = export_skills(
            target, package=package, clean=clean, source=source, link=link
        )

        if claude_symlink:
            claude_link = Path.home() / ".claude" / "skills" / "scitex"
            claude_link.parent.mkdir(parents=True, exist_ok=True)
            # Idempotent: replace stale link, leave non-link contents alone.
            if claude_link.is_symlink() or not claude_link.exists():
                if claude_link.is_symlink():
                    claude_link.unlink()
                _os.symlink(target.resolve(), claude_link)
                click.echo(f"linked: {claude_link} → {target}")
            else:
                click.echo(
                    f"warning: {claude_link} exists and is not a symlink — "
                    "skipping --claude-symlink (move it aside manually if needed).",
                    err=True,
                )

        _print_export_result(exported, target, as_json)

    # ----- Deprecated `export` — same behaviour, default destination differs -----
    @skills.command("export", hidden=True)
    @click.option(
        "--dest",
        type=click.Path(),
        default=None,
        help="Exact target directory (default: ~/.claude/skills/scitex/).",
    )
    @click.option("--package", default=None, help="Export only this package.")
    @click.option(
        "--source",
        type=click.Choice(["installed", "pypi"]),
        default="installed",
        help="installed or pypi.",
    )
    @click.option(
        "--clean", is_flag=True, help="Delete package subdirs before exporting."
    )
    @click.option(
        "--link",
        is_flag=True,
        help="Symlink skill files to editable source (source=installed only); "
        "edits propagate live with no re-export.",
    )
    @click.option("--dry-run", is_flag=True, help="Preview without copying.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def skills_export(dest, package, source, clean, link, dry_run, as_json):
        """Export skills to ~/.claude/skills/scitex/."""
        import json as json_mod
        from pathlib import Path
        from ..._ecosystem._skills.skills import _get_default_export_dest, export_skills

        target = Path(dest) if dest else _get_default_export_dest()
        if dry_run:
            from ..._ecosystem._skills.skills import list_skills

            result = {
                k: [e["name"] + ".md" for e in v]
                for k, v in list_skills(package=package).items()
            }
            if as_json:
                click.echo(
                    json_mod.dumps(
                        {"dest": str(target), "source": source, "packages": result},
                        indent=2,
                    )
                )
            else:
                total = sum(len(v) for v in result.values())
                click.echo(f"Would export {total} files to {target}/ (source={source})")
                for k, v in sorted(result.items()):
                    click.echo(f"  {k}/: {len(v)} files")
            return
        exported = export_skills(
            target, package=package, clean=clean, source=source, link=link
        )
        _print_export_result(exported, target, as_json)

    # scitex-dev#6: explicit-destination alias. `collect` is the recommended
    # command going forward because the destination is always required —
    # callers can't be surprised by a hidden default like `export`'s
    # `~/.claude/skills/scitex/`.
    @skills.command("explain-self")
    @click.argument("distribution")
    @click.option("--model", default="claude-haiku-4-5", help="Claude model id.")
    @click.option(
        "--runs",
        default=1,
        type=int,
        help="Runs per prompt (>1 returns lists).",
    )
    @click.option(
        "--format",
        "out_format",
        type=click.Choice(["json", "markdown"]),
        default="json",
        help="Output format. 'markdown' is README-marker-ready.",
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="(deprecated) Equivalent to --format json. Kept for back-compat.",
    )
    def skills_self_explain(distribution, model, runs, out_format, as_json):
        """Have an agent (mounted with only this package's skills) answer
        'what is this for / what does it solve / how do I use it?'.

        Each invocation spends real Anthropic API credits on your account
        (the mounted container uses ANTHROPIC_API_KEY, not Claude Code
        plan quota). Cost = 4 prompts × --runs.

        \b
        Example:
            $ scitex-dev skills self-explain scitex-io
            $ scitex-dev skills self-explain scitex-stats --runs 3
            $ scitex-dev skills self-explain scitex-io --format markdown >> README.md
        """
        import json as _json

        from ._self_explain import render_markdown, self_explain

        result = self_explain(distribution, model=model, runs_per_prompt=runs)
        # --json is the legacy flag; --format takes precedence when both are set.
        effective = "json" if as_json and out_format == "json" else out_format
        if effective == "markdown":
            click.echo(render_markdown(result), nl=False)
        else:
            click.echo(_json.dumps(result, indent=2))

    # Deprecated alias for backward compatibility.
    @skills.command("self-explain", hidden=True)
    @click.argument("distribution")
    @click.option("--model", default="claude-haiku-4-5", help="Claude model id.")
    @click.option(
        "--runs", default=1, type=int, help="Runs per prompt (>1 returns lists)."
    )
    @click.option(
        "--format",
        "out_format",
        type=click.Choice(["json", "markdown"]),
        default="json",
    )
    @click.option("--json", "as_json", is_flag=True, default=False)
    @click.pass_context
    def skills_self_explain_alias(ctx, distribution, model, runs, out_format, as_json):
        """Deprecated alias for `skills explain-self`.

        \b
        Example:
            $ scitex-dev skills self-explain scitex-io
        """
        ctx.invoke(
            skills_self_explain,
            distribution=distribution,
            model=model,
            runs=runs,
            out_format=out_format,
            as_json=as_json,
        )

    @skills.command("expand-tags")
    @click.argument("tag")
    @click.option(
        "--no-source-tree",
        is_flag=True,
        help="Skip ~/proj/scitex-*/src/*/_skills scan; only use installed packages.",
    )
    def skills_expand_tags(tag, no_source_tree):
        """Print absolute paths of skill files whose frontmatter `tags:` includes <tag>.

        \b
        Examples:
          scitex-dev skills tags-expand scitex-package
          scitex-dev skills tags-expand research
          scitex-dev skills tags-expand scitex-general

        Designed for CLAUDE.md `@<tag>` shorthand resolution. See
        general/06_skills_06_frontmatter-metadata.md §"CLAUDE.md tag shortcuts".
        """
        from ._tags import tags_expand

        raise SystemExit(tags_expand(tag, include_source_tree=not no_source_tree))

    # Deprecated bare-noun-leading alias (§1: leaves must start with verb).
    # Removed in 0.11.0.
    @skills.command("tags-expand", hidden=True)
    @click.argument("tag")
    @click.option("--no-source-tree", is_flag=True)
    def _skills_tags_expand_deprecated(tag, no_source_tree):
        """(deprecated) Use `skills expand-tags`. Removed in 0.11.0."""
        click.echo(
            "warning: `skills tags-expand` was renamed to `skills expand-tags` "
            "(verb-noun per §1).",
            err=True,
        )
        from ._tags import tags_expand

        raise SystemExit(tags_expand(tag, include_source_tree=not no_source_tree))

    @skills.command("collect", hidden=True)
    @click.argument(
        "destination",
        type=click.Path(),
    )
    @click.option("--package", default=None, help="Collect only this package.")
    @click.option(
        "--source",
        type=click.Choice(["installed", "pypi"]),
        default="installed",
        help="Source of skill files (default: installed packages).",
    )
    @click.option(
        "--clean",
        is_flag=True,
        help="Delete package subdirs at destination before collecting.",
    )
    @click.option(
        "--link",
        is_flag=True,
        help="Symlink skill files to editable source (source=installed only).",
    )
    @click.option("--dry-run", is_flag=True, help="Preview without copying.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def skills_collect(destination, package, source, clean, link, dry_run, as_json):
        """Collect skills from installed/PyPI packages into DESTINATION.

        Unlike `export` (which defaults to ~/.claude/skills/scitex/), this
        command REQUIRES the destination argument so callers always know
        exactly where skills will land.

        \b
        Examples:
          scitex-dev skills collect .claude/skills/scitex/
          scitex-dev skills collect ~/.claude/skills/scitex/
          scitex-dev skills collect docs/to_claude/skills/scitex/
          scitex-dev skills collect /some/path --package scitex-writer
        """
        import json as json_mod
        from pathlib import Path

        from ..._ecosystem._skills.skills import export_skills, list_skills

        target = Path(destination)
        if dry_run:
            result = {
                k: [e["name"] + ".md" for e in v]
                for k, v in list_skills(package=package).items()
            }
            if as_json:
                click.echo(
                    json_mod.dumps(
                        {"dest": str(target), "source": source, "packages": result},
                        indent=2,
                    )
                )
            else:
                total = sum(len(v) for v in result.values())
                click.echo(
                    f"Would collect {total} files to {target}/ (source={source})"
                )
                for k, v in sorted(result.items()):
                    click.echo(f"  {k}/: {len(v)} files")
            return
        collected = export_skills(
            target, package=package, clean=clean, source=source, link=link
        )
        _print_export_result(collected, target, as_json)


def _print_export_result(exported, dest_path, as_json=False):
    """Print export results."""
    import json as json_mod

    if not exported:
        click.echo("No skills found to export.")
        return
    if as_json:
        click.echo(
            json_mod.dumps(
                {k: [str(f) for f in v] for k, v in exported.items()}, indent=2
            )
        )
    else:
        total = sum(len(v) for v in exported.values())
        click.echo(
            f"Exported {total} files across {len(exported)} packages to {dest_path}"
        )
        for k, v in sorted(exported.items()):
            click.echo(f"  {k}: {len(v)} files")
