#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `test-remote` — rsync local checkouts to HOST, then pytest."""

import click


def register(ecosystem):
    @ecosystem.command(
        "test-remote",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem test-remote --host bm198 scitex-io\n"
            "  $ scitex-dev ecosystem test-remote --host bm198 --all --audit-only\n"
            "  $ scitex-dev ecosystem test-remote --host bm198 --dry-run scitex-stats\n"
            "\n"
            "rsync local checkouts to HOST, SSH in, install (`pip install -e .[dev]`),\n"
            "run pytest with `-n auto` (xdist when available), stream output, and\n"
            "propagate the exit code. Excludes `.git/`, `__pycache__/`, `*.egg-info/`,\n"
            "`_sphinx_html/`, `GITIGNORED/`, `.scitex/`. With `--all`, fans out across\n"
            "every non-archived ECOSYSTEM package in parallel; failed packages are\n"
            "summarised at the end. Use this to offload heavy parallel runs to a host\n"
            "with spare cores when the local box is loaded.\n"
            "\n"
            "Legacy: simple SSH-based fan-out can also be expressed via "
            "`ecosystem bulk -- ssh HOST ...` — see `ecosystem bulk --help`. "
            "This command is kept for its rsync + venv-bootstrap + xdist-pytest plumbing."
        ),
    )
    @click.argument("packages", nargs=-1)
    @click.option(
        "--host",
        required=True,
        help="SSH host alias (e.g. `bm198`, `spartan-bm198`). Must be reachable "
        "via `ssh <host>` non-interactively (use ~/.ssh/config).",
    )
    @click.option(
        "--all",
        "all_packages",
        is_flag=True,
        help="Run on every non-archived ECOSYSTEM package (ignores PACKAGES).",
    )
    @click.option(
        "--audit-only",
        is_flag=True,
        help="Only run `tests/develop/test_audit.py`, not the full test tree.",
    )
    @click.option(
        "--jobs",
        "-j",
        type=int,
        default=4,
        show_default=True,
        help="Max packages to run concurrently when --all is set.",
    )
    @click.option(
        "--remote-base",
        default="~/.scitex/dev/test-remote",
        show_default=True,
        help=(
            "Parent directory on HOST where each package is rsynced. "
            "Default is a sandbox under ~/.scitex/ so HOST's own "
            "~/proj/<pkg> working checkouts are never touched."
        ),
    )
    @click.option(
        "--remote-prelude",
        default="",
        help=(
            "Shell snippet executed on HOST before `python3 -m venv` "
            "runs. Use to source environment files or load modules "
            "(e.g. `module load Python/3.11.3` on Spartan)."
        ),
    )
    @click.option(
        "--remote-python",
        default="python3",
        show_default=True,
        help="Python binary on HOST used for `-m venv`. Override when the "
        "default `python3` resolves to <3.11 (e.g. `python3.11`).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the rsync + ssh commands that would run; don't execute.",
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def ecosystem_test_remote(
        packages,
        host,
        all_packages,
        audit_only,
        jobs,
        remote_base,
        remote_prelude,
        remote_python,
        dry_run,
        yes,
    ):
        """Run pytest on HOST against rsynced local checkouts."""
        del yes  # non-destructive on local; remote installs are idempotent
        import shlex
        import subprocess as _sp
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from ...._ecosystem import ECOSYSTEM, get_local_path

        if all_packages:
            targets = [n for n, info in ECOSYSTEM.items() if not info.get("archived")]
        else:
            if not packages:
                click.echo("error: no PACKAGES given (and --all not set)", err=True)
                raise SystemExit(2)
            targets = list(packages)
            for n in targets:
                if n not in ECOSYSTEM:
                    click.echo(f"error: '{n}' not in ECOSYSTEM", err=True)
                    raise SystemExit(2)

        # rsync exclusions — keep payload small and avoid shipping build artefacts
        # that would confuse a fresh install on the remote.
        rsync_excludes = [
            ".git/",
            "__pycache__/",
            "*.egg-info/",
            "_sphinx_html/",
            "GITIGNORED/",
            ".scitex/",
            ".pytest_cache/",
            ".mypy_cache/",
            ".ruff_cache/",
            "build/",
            "dist/",
            "*.pyc",
        ]
        excl_args = []
        for e in rsync_excludes:
            excl_args.extend(["--exclude", e])

        test_path = "tests/develop/" if audit_only else "tests/"

        def _run_one(pkg: str) -> tuple[str, int, str]:
            local = get_local_path(pkg)
            if local is None or not local.exists():
                return pkg, 2, f"local checkout missing: {local}"
            # Per-package layout on HOST. Source and venv live in sibling
            # subtrees so rsync --delete on `src/` never wipes the venv.
            #   <remote_base>/<pkg>/src/     ← rsync target (working tree)
            #   <remote_base>/<pkg>/.venv/   ← persistent per-package venv
            remote_root = f"{remote_base}/{pkg}"
            remote_src = f"{remote_root}/src"
            remote_venv = f"{remote_root}/.venv"
            # Don't quote remote paths — single-quoting kills tilde expansion
            # (`'~/foo'` → literal `~/foo`). Internal-controlled values, no
            # spaces in defaults; if a custom --remote-base contains shell
            # specials the user owns the breakage.
            ssh_mkdir = ["ssh", host, f"mkdir -p {remote_src}"]
            rsync_cmd = [
                "rsync",
                "-az",
                "--delete",
                *excl_args,
                f"{local}/",
                f"{host}:{remote_src}/",
            ]
            # Remote one-liner:
            #   1. create the per-package venv if missing,
            #   2. activate it,
            #   3. `pip install -e .[dev]` (with bare-`.` fallback) +
            #      scitex-dev[cli-audit] for the audit gate,
            #   4. pytest -n auto when xdist is available, otherwise serial.
            prelude = (remote_prelude + "; ") if remote_prelude else ""
            # Tilde-bearing paths intentionally left UNQUOTED so the remote
            # shell expands `~` to $HOME. Internal-controlled, no spaces.
            # SCITEX_DEV_REGISTRY exported so audit-project / audit-cli
            # read the bootstrap-written override YAML, not HOST's
            # bundled ECOSYSTEM (which would point at HOST's own
            # ~/proj/<pkg>).
            remote_script = (
                f"set -e; "
                f"export SCITEX_DEV_REGISTRY={registry_remote}; "
                f"{prelude}"
                f"if [ ! -f {remote_venv}/bin/activate ]; then "
                f"  {remote_python} -m venv {remote_venv}; "
                f"fi; "
                f". {remote_venv}/bin/activate; "
                f"cd {remote_src}; "
                f"python -m pip install --quiet --upgrade pip; "
                f"python -m pip install -e '.[dev]' --quiet || "
                f"python -m pip install -e . --quiet; "
                # Install scitex-dev editable from the bootstrap-synced
                # local copy so the audit corpus on HOST matches the
                # version running locally (no PyPI drift). Two-step
                # to dodge pip's editable-with-extras parsing of `~`:
                # editable install first (path-only), then non-editable
                # extras install against the same path picks up the
                # cli-audit dependencies.
                f"python -m pip install -e {scitex_dev_remote} --quiet; "
                f"python -m pip install {scitex_dev_remote}[cli-audit] --quiet; "
                f"python -m pip install pytest-xdist --quiet || true; "
                f"if python -c 'import xdist' 2>/dev/null; then "
                f"  python -m pytest -n auto --tb=short {test_path}; "
                f"else "
                f"  python -m pytest --tb=short {test_path}; "
                f"fi"
            )
            ssh_cmd = ["ssh", host, "bash", "-lc", shlex.quote(remote_script)]

            if dry_run:
                lines = [
                    "# " + " ".join(shlex.quote(a) for a in ssh_mkdir),
                    "# " + " ".join(shlex.quote(a) for a in rsync_cmd),
                    "# " + " ".join(shlex.quote(a) for a in ssh_cmd),
                ]
                return pkg, 0, "\n".join(lines)

            # mkdir + rsync (sequential — required before ssh)
            for cmd in (ssh_mkdir, rsync_cmd):
                r = _sp.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    return pkg, r.returncode, r.stderr.strip() or r.stdout.strip()
            # pytest run — capture output for the parallel summary
            r = _sp.run(ssh_cmd, capture_output=True, text=True)
            tail = (r.stdout + r.stderr).strip().splitlines()
            tail = "\n".join(tail[-25:]) if len(tail) > 25 else "\n".join(tail)
            return pkg, r.returncode, tail

        if dry_run:
            for pkg in targets:
                _, _, out = _run_one(pkg)
                click.echo(f"--- {pkg} ---")
                click.echo(out)
            return

        click.echo(
            f"# test-remote: host={host}, packages={len(targets)}, "
            f"jobs={jobs}, audit_only={audit_only}"
        )

        # Bootstrap: sync the local scitex-dev checkout once, before any
        # per-package run. Each per-package venv installs scitex-dev
        # editable from this synced copy so the audit corpus on HOST
        # exactly matches what's running locally — no PyPI version drift.
        scitex_dev_local = get_local_path("scitex-dev")
        if scitex_dev_local is None or not scitex_dev_local.exists():
            click.echo("error: local scitex-dev checkout missing", err=True)
            raise SystemExit(2)
        scitex_dev_remote = f"{remote_base}/scitex-dev/src"
        click.echo("# bootstrap: rsync local scitex-dev → HOST")
        boot_mkdir = _sp.run(
            ["ssh", host, f"mkdir -p {scitex_dev_remote}"],
            capture_output=True,
            text=True,
        )
        if boot_mkdir.returncode != 0:
            click.echo(f"error: bootstrap mkdir failed: {boot_mkdir.stderr}", err=True)
            raise SystemExit(boot_mkdir.returncode)
        boot_rsync = _sp.run(
            [
                "rsync",
                "-az",
                "--delete",
                *excl_args,
                f"{scitex_dev_local}/",
                f"{host}:{scitex_dev_remote}/",
            ],
            capture_output=True,
            text=True,
        )
        if boot_rsync.returncode != 0:
            click.echo(f"error: bootstrap rsync failed: {boot_rsync.stderr}", err=True)
            raise SystemExit(boot_rsync.returncode)

        # Bootstrap (continued): write a registry override YAML on HOST
        # so audit-all reads paths under our sandbox, not HOST's own
        # ~/proj/<pkg> working checkouts. Without this, audit-project
        # (PS-134/PS-210/...) reads HOST-local paths and audits the wrong
        # files. The override flows in via SCITEX_DEV_REGISTRY in the
        # remote_script env (per scitex-dev's §6b cascade).
        import yaml as _yaml

        override = {}
        for nm, info in ECOSYSTEM.items():
            ov = dict(info)
            ov["local_path"] = f"{remote_base}/{nm}/src"
            override[nm] = ov
        registry_remote = f"{remote_base}/.ecosystem-override.yaml"
        registry_yaml = _yaml.safe_dump(override, sort_keys=False)
        write_cmd = ["ssh", host, f"cat > {registry_remote}"]
        write_proc = _sp.run(
            write_cmd, input=registry_yaml, capture_output=True, text=True
        )
        if write_proc.returncode != 0:
            click.echo(
                f"error: registry override write failed: {write_proc.stderr}",
                err=True,
            )
            raise SystemExit(write_proc.returncode)
        click.echo(f"# bootstrap: wrote registry override to {registry_remote}")
        results: dict[str, tuple[int, str]] = {}
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            futures = {pool.submit(_run_one, p): p for p in targets}
            for f in as_completed(futures):
                pkg, code, tail = f.result()
                status = "ok" if code == 0 else f"FAIL({code})"
                click.echo(f"[{status:>8}] {pkg}")
                results[pkg] = (code, tail)

        failed = [(p, c, t) for p, (c, t) in results.items() if c != 0]
        click.echo("")
        click.echo(f"# summary: {len(results) - len(failed)} ok, {len(failed)} failed")
        for p, c, t in failed:
            click.echo(f"\n--- {p} (exit {c}) ---")
            click.echo(t)
        raise SystemExit(0 if not failed else 1)
