#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem git-flavoured commands: `sync`, `clone`, `checkout`, `pull`,
`install`, `sync-remote`."""

import click


def register(ecosystem):
    @ecosystem.command(
        "sync",
        epilog=(
            "Equivalent to `bulk -- pip install -e ~/proj/{}` — "
            "see `ecosystem bulk --help`."
        ),
    )
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--dry-run", is_flag=True, help="Preview without syncing.")
    @click.option(
        "--jobs",
        "-j",
        "jobs",
        default="1",
        show_default=True,
        help="Parallel installs. 1=serial, N=N workers, 0 or 'auto'=all CPUs.",
    )
    @click.option(
        "--quiet",
        "-q",
        is_flag=True,
        help="Suppress per-package progress lines (errors still on stderr).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def ecosystem_sync(package, dry_run, jobs, quiet, as_json, yes):
        """Install ecosystem packages from local clones in editable mode (pip install -e).

        Walks every configured package, runs `pip install -e <local_path>` for
        each. Use `-j N` to install in parallel; progress is streamed to stderr
        unless --json or --quiet is set.

        \b
        Example:
            $ scitex-dev ecosystem sync --dry-run
            $ scitex-dev ecosystem sync -y -j 4
            $ scitex-dev ecosystem sync -p scitex-io --yes
        """
        del yes  # accepted for §2 compliance; sync is non-interactive already
        import sys

        from ..._utils import wrap_as_cli
        from ...._sync import sync_local

        pkgs = list(package) if package else None

        # Resolve --jobs ('auto' or '0' → all CPUs)
        if str(jobs).lower() in ("auto", "0"):
            jobs_n = 0
        else:
            try:
                jobs_n = int(jobs)
            except ValueError:
                click.echo(
                    f"error: --jobs must be int, 'auto', or '0' (got {jobs!r})",
                    err=True,
                )
                sys.exit(2)

        # Per-package progress callback (stderr; off in --json or --quiet mode)
        def _progress(idx, total, name, status, elapsed):
            mark = {"ok": "✓", "error": "✗", "skipped": "·", "dry_run": "·"}.get(
                status, "?"
            )
            click.echo(
                f"[{idx}/{total}] {mark} {name} ({status}, {elapsed:.1f}s)", err=True
            )

        on_progress = None if (as_json or quiet) else _progress

        wrap_as_cli(
            sync_local,
            as_json=as_json,
            packages=pkgs,
            confirm=not dry_run,
            jobs=jobs_n,
            on_progress=on_progress,
        )

    # ---------------------------------------------------------------
    # Bootstrap / cross-machine ops: clone | checkout | pull | install
    # ---------------------------------------------------------------

    def _git_progress(idx, total, name, status, msg):
        mark = {"ok": "✓", "err": "✗", "skip": "·", "dry": "·"}.get(status, "?")
        click.echo(f"[{idx}/{total}] {mark} {name}: {msg}", err=True)

    @ecosystem.command(
        "clone",
        epilog=(
            "Note: `clone` is intentionally separate from `bulk` — it creates "
            "package dirs that don't exist yet, while `bulk` can only iterate "
            "already-registered local packages."
        ),
    )
    @click.option("--dest", default="~/proj", show_default=True, help="Parent dir.")
    @click.option("--branch", default="develop", show_default=True)
    @click.option("--https", is_flag=True, help="Use https:// URLs (default ssh).")
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--jobs", "-j", default=4, show_default=True, type=int)
    @click.option(
        "--dry-run",
        is_flag=True,
        default=True,
        help="(default) Print what would run; do nothing. Pass --yes to apply.",
    )
    @click.option("--json", "as_json", is_flag=True)
    @click.option(
        "--yes", "-y", is_flag=True, help="Apply for real (overrides default dry-run)."
    )
    def ecosystem_clone(dest, branch, https, package, jobs, dry_run, as_json, yes):
        """Clone every ecosystem repo into DEST (default ~/proj/).

        \b
        Default is dry-run — pass --yes to actually clone.

        \b
        Example:
          $ scitex-dev ecosystem clone                # preview (dry-run)
          $ scitex-dev ecosystem clone --yes          # apply
          $ scitex-dev ecosystem clone --dest /scratch/proj --yes
          $ scitex-dev ecosystem clone --https --branch main --yes
          $ scitex-dev ecosystem clone -p scitex-io --yes
        """
        from pathlib import Path as _Path

        from ...._ecosystem._git_ops import clone_all

        # Dry-run is default; --yes overrides to apply for real.
        effective_dry_run = dry_run and not yes
        results = clone_all(
            dest=_Path(dest),
            branch=branch,
            use_ssh=not https,
            packages=list(package) or None,
            jobs=jobs,
            dry_run=effective_dry_run,
            on_progress=None if as_json else _git_progress,
        )
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {k: {"exit": v[0], "msg": v[1]} for k, v in results.items()},
                    indent=2,
                )
            )
        rc = 0 if all(v[0] == 0 for v in results.values()) else 1
        raise SystemExit(rc)

    @ecosystem.command(
        "checkout",
        epilog=(
            "Equivalent to `bulk -- git -C ~/proj/{} checkout BRANCH` — "
            "see `ecosystem bulk --help`."
        ),
    )
    @click.argument("branch")
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=True,
        help="(default) Print what would run; do nothing. Pass --yes to apply.",
    )
    @click.option(
        "--yes", "-y", is_flag=True, help="Apply for real (overrides default dry-run)."
    )
    @click.option("--json", "as_json", is_flag=True)
    def ecosystem_checkout(branch, package, dry_run, yes, as_json):
        """`git checkout <branch>` in every ecosystem clone.

        \b
        Default is dry-run — pass --yes to actually checkout.

        \b
        Example:
          $ scitex-dev ecosystem checkout develop          # preview
          $ scitex-dev ecosystem checkout develop --yes    # apply
          $ scitex-dev ecosystem checkout main -p scitex-io --yes
        """
        from ...._ecosystem._core import ECOSYSTEM as _ECO
        from ...._ecosystem._git_ops import checkout_all

        if dry_run and not yes:
            for n, info in _ECO.items():
                if info.get("archived") or (package and n not in package):
                    continue
                click.echo(f"would run in {info['local_path']}: git checkout {branch}")
            raise SystemExit(0)
        results = checkout_all(
            branch=branch,
            packages=list(package) or None,
            on_progress=None if as_json else _git_progress,
        )
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {k: {"exit": v[0], "msg": v[1]} for k, v in results.items()},
                    indent=2,
                )
            )
        rc = 0 if all(v[0] == 0 for v in results.values()) else 1
        raise SystemExit(rc)

    @ecosystem.command(
        "pull",
        epilog=(
            "Equivalent to `bulk -- git -C ~/proj/{} pull --rebase` — "
            "see `ecosystem bulk --help`."
        ),
    )
    @click.option(
        "--no-rebase", is_flag=True, help="Use plain git pull (default --rebase)."
    )
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--jobs", "-j", default=4, show_default=True, type=int)
    @click.option(
        "--dry-run",
        is_flag=True,
        default=True,
        help="(default) Print what would run; do nothing. Pass --yes to apply.",
    )
    @click.option(
        "--yes", "-y", is_flag=True, help="Apply for real (overrides default dry-run)."
    )
    @click.option("--json", "as_json", is_flag=True)
    def ecosystem_pull(no_rebase, package, jobs, dry_run, yes, as_json):
        """`git pull --rebase` in every ecosystem clone (parallel).

        \b
        Default is dry-run — pass --yes to actually pull.

        \b
        Example:
          $ scitex-dev ecosystem pull              # preview
          $ scitex-dev ecosystem pull --yes        # apply
          $ scitex-dev ecosystem pull --yes -j 8
          $ scitex-dev ecosystem pull -p scitex-io --yes
        """
        from ...._ecosystem._git_ops import pull_all

        if dry_run and not yes:
            from ...._ecosystem._core import ECOSYSTEM as _ECO

            for n, info in _ECO.items():
                if info.get("archived") or (package and n not in package):
                    continue
                cmd = "git pull" + ("" if no_rebase else " --rebase")
                click.echo(f"would run in {info['local_path']}: {cmd}")
            raise SystemExit(0)
        results = pull_all(
            rebase=not no_rebase,
            packages=list(package) or None,
            jobs=jobs,
            on_progress=None if as_json else _git_progress,
        )
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {k: {"exit": v[0], "msg": v[1]} for k, v in results.items()},
                    indent=2,
                )
            )
        rc = 0 if all(v[0] == 0 for v in results.values()) else 1
        raise SystemExit(rc)

    @ecosystem.command(
        "install",
        epilog=(
            "Equivalent to `bulk -- pip install -e ~/proj/{}` — "
            "see `ecosystem bulk --help`. The dedicated `install` command is "
            "kept for the per-package venv plumbing and shell-completion wiring "
            "that `bulk` does not perform."
        ),
    )
    @click.option(
        "--source",
        type=click.Choice(["editable", "pypi"]),
        default="editable",
        show_default=True,
        help="editable: pip install -e <local>; pypi: pip install <name> from PyPI.",
    )
    @click.option("--extras", default="", help="Comma-separated extras (e.g. dev,mcp).")
    @click.option(
        "--venv",
        type=click.Choice(["per-package", "current"]),
        default="per-package",
        show_default=True,
        help=(
            "per-package (DEFAULT): create ~/proj/<pkg>/.venv/ if missing "
            "and install INTO that venv — yields the canonical CI-parity "
            "layout where each package's [dev]/[all] extras are exercised "
            "in isolation. If ~/proj/<pkg>/.venv is a symlink (typically "
            "to ~/.venv from a shared-dev setup), it is REPLACED with a "
            "real venv so the deps don't bleed into the global one. "
            "current (opt-in): install into the running Python (shared "
            "dev venv) — use only when you intentionally want every peer "
            "installed into the same env."
        ),
    )
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--jobs", "-j", default=1, show_default=True, type=int)
    @click.option(
        "--dry-run",
        is_flag=True,
        default=True,
        help="(default) Print what would run; do nothing. Pass --yes to apply.",
    )
    @click.option("--json", "as_json", is_flag=True)
    @click.option(
        "--yes", "-y", is_flag=True, help="Apply for real (overrides default dry-run)."
    )
    @click.option(
        "--with-completions/--no-completions",
        default=True,
        show_default=True,
        help=(
            "After pip install, run `<binary> install-shell-completion --yes` "
            "for every package whose console script lands on PATH. Generates "
            "the per-package cache file under ~/.scitex/<pkg-short>/runtime/"
            "completion/ and a single source line in your rc."
        ),
    )
    @click.option(
        "--completion-shell",
        type=click.Choice(["bash", "zsh", "fish"]),
        default="bash",
        show_default=True,
        help="Shell to wire completions for (used with --with-completions).",
    )
    def ecosystem_install(
        source,
        extras,
        venv,
        package,
        jobs,
        dry_run,
        as_json,
        yes,
        with_completions,
        completion_shell,
    ):
        """`pip install` every ecosystem package.

        \b
        Default is dry-run — pass --yes to actually install.

        \b
        Example:
          $ scitex-dev ecosystem install                              # preview (dry-run, per-package — DEFAULT)
          $ scitex-dev ecosystem install --extras all,dev --yes -j 4  # CI-parity install: per-pkg .venv each
          $ scitex-dev ecosystem install --venv current --yes         # legacy: install everything into running venv
          $ scitex-dev ecosystem install --source pypi --yes
          $ scitex-dev ecosystem install -p scitex-io --extras dev --yes
        """
        from ...._ecosystem._git_ops import install_all, install_completions_all

        # Dry-run is default; --yes overrides to apply for real.
        effective_dry_run = dry_run and not yes
        results = install_all(
            source=source,
            extras=extras,
            venv=venv,
            packages=list(package) or None,
            jobs=jobs,
            dry_run=effective_dry_run,
            on_progress=None if as_json else _git_progress,
        )

        completion_results: dict | None = None
        if with_completions:
            # Only attempt for packages that pip-installed successfully —
            # a binary on PATH for a package whose pip install just failed
            # is at best stale, at worst missing.
            ok_pkgs = [name for name, (rc, _) in results.items() if rc == 0]
            if ok_pkgs:
                if not as_json:
                    click.echo(
                        f"\nWiring shell completions ({completion_shell}) for "
                        f"{len(ok_pkgs)} package(s)…",
                        err=True,
                    )
                completion_results = install_completions_all(
                    shell=completion_shell,
                    packages=ok_pkgs,
                    jobs=jobs,
                    dry_run=effective_dry_run,
                    on_progress=None if as_json else _git_progress,
                )

        if as_json:
            import json as _json

            payload = {k: {"exit": v[0], "msg": v[1]} for k, v in results.items()}
            if completion_results is not None:
                payload = {
                    "install": payload,
                    "completions": {
                        k: {"exit": v[0], "msg": v[1]}
                        for k, v in completion_results.items()
                    },
                }
            click.echo(_json.dumps(payload, indent=2))

        rc = 0 if all(v[0] == 0 for v in results.values()) else 1
        if completion_results is not None and any(
            v[0] != 0 for v in completion_results.values()
        ):
            rc = max(rc, 1)
        raise SystemExit(rc)

    @ecosystem.command(
        "sync-remote",
        hidden=True,
        epilog="Legacy. Prefer `ecosystem bulk` — see `ecosystem bulk --help`.",
    )
    @click.option(
        "--host",
        "-h",
        "hosts",
        multiple=True,
        help="Host name(s). Omit or pass 'all' to sync every enabled host.",
    )
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--dry-run", is_flag=True, help="Preview without syncing.")
    @click.option(
        "--unsafe",
        is_flag=True,
        help="Disable the ahead-check; allow clobbering unpushed remote commits.",
    )
    @click.option(
        "--no-install", is_flag=True, help="Skip pip install -e . after git pull."
    )
    @click.option("--no-stash", is_flag=True, help="Skip git stash / stash pop wrap.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def ecosystem_sync_remote(
        hosts, package, dry_run, unsafe, no_install, no_stash, as_json
    ):
        """(deprecated) Sync ecosystem packages to remote hosts over SSH.

        Replaced by ``ecosystem packages`` (default observation mode,
        ``--dry-run`` preview, ``--apply`` to execute). This alias will
        be removed in the next major release.

        Each package on each host is: ahead-check -> git stash -> git
        pull -> pip install -e . -> git stash pop. Packages whose
        remote working copy has unpushed commits are skipped by
        default (safety).

        Examples:

        \b
            scitex-dev ecosystem sync-remote --dry-run
            scitex-dev ecosystem sync-remote -h mba -h spartan
            scitex-dev ecosystem sync-remote -h all -p scitex-db
        """
        click.echo(
            "warning: `ecosystem sync-remote` is deprecated; "
            "use `ecosystem packages` (default observation, --dry-run preview, "
            "--apply to execute).",
            err=True,
        )
        from ..._utils import wrap_as_cli
        from ...._sync import sync_all

        host_list = list(hosts) if hosts else None
        if host_list == ["all"]:
            host_list = None
        pkgs = list(package) if package else None
        wrap_as_cli(
            sync_all,
            as_json=as_json,
            hosts=host_list,
            packages=pkgs,
            stash=not no_stash,
            install=not no_install,
            safe=not unsafe,
            confirm=not dry_run,
        )
