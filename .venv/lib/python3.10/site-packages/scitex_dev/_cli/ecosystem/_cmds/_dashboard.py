#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `dashboard` group + `list / start / start-tui / export` subs.

Also hosts the back-compat shims `ecosystem dashboard` (deprecated bare-noun
that prints a redirect and exits 2) and `ecosystem start-dashboard` (web UI
entry point). Both are kept here because they're dashboard-related; they're
intentionally back-compat shims, not new surface.
"""

import click


def _render_remote_dashboard(
    *,
    host: str,
    verbosity: int,
    packages: list,
    jobs: int,
    with_tests: str,
    as_json: bool,
) -> None:
    """Stream `dashboard list --json-stream` from `host`; render live.

    Uses ``--json-stream`` (one JSON snapshot per line, emitted after
    each enricher batch completes) so the local view fills in
    incrementally — same UX as a local `dashboard list`. Without this,
    ssh blocks for the full ~40s while the remote runs every enricher.

    If ``as_json`` is requested, the last (= most complete) snapshot
    is forwarded verbatim.
    """
    import json as _json
    import subprocess

    from rich.console import Console
    from rich.live import Live

    from .._dashboard._render import render_table
    from .._dashboard._state import PackageState

    remote_cmd_parts = [
        "scitex-dev",
        "ecosystem",
        "dashboard",
        "list",
        "--json-stream",
        "-j",
        str(jobs),
        "--with-tests",
        with_tests,
    ]
    if verbosity > 1:
        remote_cmd_parts.append("-" + "v" * (verbosity - 1))
    for p in packages:
        remote_cmd_parts.extend(["-p", p])
    remote_cmd = " ".join(remote_cmd_parts)
    # `bash -lc` so the user's PATH (incl. ~/.env-*/bin) is sourced.
    # `-o BatchMode=yes` avoids interactive password prompts hanging.
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        host,
        f"bash -lc {_shquote(remote_cmd)}",
    ]
    try:
        proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as e:
        raise click.ClickException(f"ssh to {host} failed: {e}")

    last_rows: list = []
    console = Console()

    def _states() -> list:
        return [PackageState.from_dict(r) for r in last_rows]

    if as_json:
        # No live render — just drain to EOF and forward the final snapshot.
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                last_rows = _json.loads(line)
            except _json.JSONDecodeError:
                continue
        proc.wait(timeout=10)
        click.echo(_json.dumps(last_rows, indent=2, default=str))
        return

    with Live(
        render_table([], verbosity=verbosity, host=host),
        console=console,
        refresh_per_second=2,
        transient=False,
        screen=True,
    ) as live:
        live.console.print(
            f"[dim]streaming from {host} over ssh — first snapshot lands "
            f"after the cheap basic-gather batch (~1-2s); full enrichment "
            f"~30-60s on a cold cache[/dim]"
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                last_rows = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            live.update(render_table(_states(), verbosity=verbosity, host=host))
        live.update(render_table(_states(), verbosity=verbosity, host=host))

    try:
        rc = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        rc = -1
    if rc != 0 and not last_rows:
        err = (proc.stderr.read() if proc.stderr else "")[:2000]
        raise click.ClickException(
            f"remote `dashboard list` on {host} exited {rc}:\n--- stderr ---\n{err}"
        )

    console.print(render_table(_states(), verbosity=verbosity, host=host))


def _shquote(s: str) -> str:
    """POSIX shell single-quote a string for embedding in `bash -lc '...'`."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def register(ecosystem):
    # Back-compat shim: the deprecated bare-noun command must be registered
    # BEFORE the live `dashboard` Group below so the Group definition
    # overrides it as the resolved command (Click later-wins on same name).
    @ecosystem.command(
        "dashboard",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def ecosystem_dashboard_deprecated(ctx):
        """(deprecated) Renamed to `start-dashboard`."""
        click.echo(
            "error: `scitex-dev ecosystem dashboard` was renamed to "
            "`scitex-dev ecosystem start-dashboard`.\n"
            "Re-run with: scitex-dev ecosystem start-dashboard [...]",
            err=True,
        )
        ctx.exit(2)

    @ecosystem.group("dashboard")
    def dashboard():
        """Ecosystem health dashboard (TUI / GUI / export).

        \b
        Subcommands:
          list    one-shot snapshot table (good for piping / `watch`)
          start   live-refresh TUI (or --gui for the Dash web view)
          export  machine-readable dump (json / csv / md)

        Verbosity flag (-v / -vv / -vvv) controls column count across
        all three. -vvv pulls every cached field; same data layer feeds
        all surfaces (`gather_ecosystem_state`).
        """

    @dashboard.command(
        "list",
        epilog=(
            "Example:\n"
            "  $ scitex-dev ecosystem dashboard list -vv\n"
            "  $ scitex-dev ecosystem dashboard list --json | jq\n"
        ),
    )
    @click.option(
        "-v",
        "verbosity",
        count=True,
        default=1,
        help="Add -v / -vv / -vvv for more columns.",
    )
    @click.option("--package", "-p", multiple=True, help="Limit to specific packages.")
    @click.option(
        "--jobs",
        "-j",
        "jobs",
        default=16,
        show_default=True,
        type=int,
        help=(
            "Concurrent worker threads. All enrichment tasks "
            "(pypi + deep + ci + audit at -vvv) share one pool — "
            "264 tasks for the full ecosystem. Bump to 32-64 to "
            "shorten -vvv wall-clock; cap by GitHub API rate-limit "
            "(~5000/hr) and local CPU."
        ),
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Emit JSON instead of the Rich table (alias for `dashboard export --format json`).",
    )
    @click.option(
        "--json-stream",
        is_flag=True,
        hidden=True,
        help=(
            "Internal: emit one JSON snapshot per line as enrichers "
            "complete (newline-delimited JSON of the full state list). "
            "Used by `--host` to render remote progress incrementally."
        ),
    )
    @click.option(
        "--with-tests",
        type=click.Choice(["off", "collect", "run"]),
        default="off",
        show_default=True,
        help=(
            "Populate the pytest column with real data:  "
            "`off` (default) shows the cheap test-file count;  "
            "`collect` runs `pytest --collect-only` per pkg "
            "(~3-10s/pkg) and shows the parametrize-aware test count;  "
            "`run` actually runs pytest per pkg (~30-300s each) and "
            "shows `F<failed> (<passed>/<total>)` with the F red on "
            "failures. Both `collect` and `run` invoke pytest INSIDE "
            "each pkg's `<pkg>/.venv/` and skip pkgs whose venv is a "
            "symlink or missing."
        ),
    )
    @click.option(
        "--host",
        default=None,
        help=(
            "SSH host whose ~/proj/ checkouts should be inspected "
            "instead of the local machine's. Useful when active "
            "development has moved to a remote (e.g. Spartan) so the "
            "local clones drift behind. Requires `scitex-dev` "
            "installed on the remote. Implementation: ssh runs "
            "`scitex-dev ecosystem dashboard list --json [flags]` on "
            "the remote, the result is deserialised and rendered with "
            "the local renderer."
        ),
    )
    def dashboard_list(
        verbosity, package, jobs, as_json, json_stream, with_tests, host
    ):
        """Live ecosystem dashboard. Visible columns at the current
        verbosity are always computed (verbosity ≠ depth); cells fill
        in via `rich.live.Live` first-come-first-served as each future
        completes — PyPI HTTP, gh-api CI (one GraphQL batch), audit
        (one `audit-all` subprocess).
        """
        import time

        from .._dashboard import gather_ecosystem_state
        from .._dashboard._render import (
            cols_for_verbosity,
            enrichers_for_cols,
            render_table,
        )

        # --host: shell out to remote scitex-dev for the JSON payload,
        # deserialise into PackageState objects, then render locally.
        # Lets a developer working on Spartan see Spartan's clone state
        # from a local terminal without re-implementing the gatherer
        # over ssh.
        if host:
            _render_remote_dashboard(
                host=host,
                verbosity=verbosity,
                packages=list(package),
                jobs=jobs,
                with_tests=with_tests,
                as_json=as_json,
            )
            return

        cols = cols_for_verbosity(verbosity)
        enrichers = enrichers_for_cols(cols)
        # `--with-tests` opt-ins enrich `tests_collected` / `tests_passed`
        # & `tests_failed` so the pytest column can show the real
        # `F NN (NN/NN)` format instead of just the file count.
        if with_tests == "collect":
            enrichers.add("tests-collect")
        elif with_tests == "run":
            enrichers.add("tests-run")

        # `-p` accepts repeats AND comma-separated values, plus the
        # literal `all` (expands to every registered pkg). Mirrors
        # `audit-all`'s argument style.
        #   -p scitex-io -p scitex-stats     → ["scitex-io", "scitex-stats"]
        #   -p scitex-io,scitex-stats        → ["scitex-io", "scitex-stats"]
        #   -p all                           → None (all pkgs)
        raw_pkgs: list[str] = []
        for entry in package:
            raw_pkgs.extend(p.strip() for p in entry.split(",") if p.strip())
        if "all" in raw_pkgs:
            packages_arg: list[str] | None = None
        elif raw_pkgs:
            seen: set[str] = set()
            packages_arg = []
            for p in raw_pkgs:
                if p not in seen:
                    seen.add(p)
                    packages_arg.append(p)
        else:
            packages_arg = None

        if json_stream:
            # Emit one JSON snapshot per line as enrichers complete.
            # Used by --host to stream remote progress incrementally.
            import json as _json
            import sys as _sys

            def _emit(states):
                _sys.stdout.write(
                    _json.dumps([s.to_dict() for s in states], default=str)
                )
                _sys.stdout.write("\n")
                _sys.stdout.flush()

            gather_ecosystem_state(
                verbosity=verbosity,
                packages=packages_arg,
                workers=jobs,
                on_update=_emit,
                enrichers=enrichers,
            )
            return

        if as_json:
            states = gather_ecosystem_state(
                verbosity=verbosity,
                packages=packages_arg,
                workers=jobs,
                enrichers=enrichers,
            )
            from .._dashboard import _export as exp

            click.echo(exp.to_json(states))
            return

        from rich.console import Console
        from rich.live import Live

        console = Console()

        # Always live-stream. Even at v=0/1 we may have audit/pypi/CI
        # columns visible that need computation; the basic gather is
        # sub-second so Live engagement cost is negligible.
        last_paint = [0.0]
        states_box: list = []

        def _on_update(states):
            states_box[:] = states
            now = time.monotonic()
            if now - last_paint[0] >= 1.0:
                live.update(render_table(states, verbosity=verbosity))
                last_paint[0] = now

        with Live(
            render_table([], verbosity=verbosity),
            console=console,
            refresh_per_second=2,
            transient=False,
            screen=True,
        ) as live:
            gather_ecosystem_state(
                verbosity=verbosity,
                packages=packages_arg,
                workers=jobs,
                on_update=_on_update,
                enrichers=enrichers,
            )
            # Final paint to ensure the last-completion delta lands.
            live.update(render_table(states_box, verbosity=verbosity))

        console.print(render_table(states_box, verbosity=verbosity))

    @dashboard.command(
        "start",
        epilog=(
            "Example:\n"
            "  $ scitex-dev ecosystem dashboard start -vv\n"
            "  $ scitex-dev ecosystem dashboard start --gui   # web view (deferred)\n"
            "  $ scitex-dev ecosystem dashboard start --interval 10\n"
        ),
    )
    @click.option("-v", "verbosity", count=True, default=1)
    @click.option(
        "--gui", is_flag=True, help="Launch the Dash web view at 127.0.0.1:8050."
    )
    @click.option(
        "--interval", type=float, default=5.0, help="TUI refresh interval (seconds)."
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print refresh plan (verbosity, interval, package count) and exit without rendering.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="No-op confirmation flag retained for §2 audit-cli compliance.",
    )
    def dashboard_start(verbosity, gui, interval, dry_run, yes):
        """Live-refresh dashboard. TUI by default; --gui for the web view."""
        if dry_run:
            click.echo(
                f"would render: verbosity={verbosity} interval={interval}s "
                f"gui={'yes' if gui else 'no'}"
            )
            return
        del yes  # accepted for compliance; nothing to confirm
        if gui:
            click.echo(
                "error: --gui (Dash web view) is not yet wired into the v0 dashboard.\n"
                "       Use `dashboard list` for a snapshot or `dashboard export` for a dump.",
                err=True,
            )
            raise SystemExit(2)

        from rich.console import Console
        from rich.live import Live

        from .._dashboard import gather_ecosystem_state
        from .._dashboard._render import render_table

        console = Console()
        try:
            with Live(
                render_table(
                    gather_ecosystem_state(verbosity=verbosity), verbosity=verbosity
                ),
                console=console,
                refresh_per_second=4,
                screen=False,
            ) as live:
                import time

                while True:
                    time.sleep(interval)
                    live.update(
                        render_table(
                            gather_ecosystem_state(verbosity=verbosity),
                            verbosity=verbosity,
                        )
                    )
        except KeyboardInterrupt:
            click.echo("\nstopped.", err=True)

    @dashboard.command(
        "start-tui",
        epilog=(
            "Keys:\n"
            "  /          start filter\n"
            "  Escape     clear filter\n"
            "  r          refresh data\n"
            "  q          quit\n"
            "  j/k ↓/↑    navigate rows\n"
            "  g / G      jump to top / bottom\n"
            "\n"
            "Example:\n"
            "  $ scitex-dev ecosystem dashboard start-tui\n"
            "  $ scitex-dev ecosystem dashboard start-tui -p scitex-io,scitex-stats\n"
            "  $ scitex-dev ecosystem dashboard start-tui -vv\n"
        ),
    )
    @click.option(
        "-v",
        "verbosity",
        count=True,
        default=1,
        help="Add -v / -vv / -vvv for more columns.",
    )
    @click.option(
        "--package",
        "-p",
        multiple=True,
        help="Limit to specific packages (comma-separated or repeat the flag).",
    )
    @click.option(
        "--jobs",
        "-j",
        default=16,
        show_default=True,
        type=int,
        help="Concurrent worker threads for enrichment.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print plan (verbosity, package count) and exit without launching the TUI.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="No-op confirmation flag retained for §2 audit-cli compliance.",
    )
    def dashboard_tui(verbosity, package, jobs, dry_run, yes):
        """htop-style TUI with live keystroke filter.

        Requires the optional `textual` package. Install with:
          pip install textual
        """
        raw_pkgs: list[str] = []
        for entry in package:
            raw_pkgs.extend(p.strip() for p in entry.split(",") if p.strip())
        if "all" in raw_pkgs:
            packages_arg: list[str] | None = None
        elif raw_pkgs:
            seen: set[str] = set()
            packages_arg = []
            for p in raw_pkgs:
                if p not in seen:
                    seen.add(p)
                    packages_arg.append(p)
        else:
            packages_arg = None

        del yes  # accepted for §2 compliance
        if dry_run:
            n = len(packages_arg) if packages_arg else "all"
            click.echo(
                f"would launch TUI: verbosity={verbosity} packages={n} jobs={jobs}"
            )
            return

        try:
            from .._dashboard._tui import run_tui
        except ImportError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(2)

        try:
            run_tui(verbosity=verbosity, packages=packages_arg, workers=jobs)
        except ImportError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(2)

    @dashboard.command(
        "export",
        epilog=(
            "Example:\n"
            "  $ scitex-dev ecosystem dashboard export --format json | jq\n"
            "  $ scitex-dev ecosystem dashboard export --format csv > state.csv\n"
            "  $ scitex-dev ecosystem dashboard export --format md   # paste into README\n"
            "  $ scitex-dev ecosystem dashboard export --format org > report.org\n"
            "  $ scitex-dev ecosystem dashboard export --format pdf -o report.pdf\n"
        ),
    )
    @click.option(
        "--format",
        "fmt",
        type=click.Choice(["json", "csv", "md", "org", "pdf"]),
        default="json",
        help=(
            "Output format. `org` emits a ywatanabe-convention Org-mode "
            "report (the 'usual PDF' source); `pdf` runs the org→pdf "
            "convert via pandoc / `emacs --batch` and writes the .pdf "
            "(+ .org sidecar) to the path given by --output."
        ),
    )
    @click.option(
        "-v",
        "verbosity",
        count=True,
        default=3,
        help="Default -vvv (all columns) for export.",
    )
    @click.option("--package", "-p", multiple=True)
    @click.option(
        "--output",
        "-o",
        "output",
        default=None,
        type=click.Path(),
        help=(
            "Output file path (required for --format pdf; optional for "
            "other formats — defaults to stdout). For pdf the .org "
            "sidecar is written next to the .pdf with the same stem."
        ),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print row count + format that would be emitted; no payload written.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="No-op confirmation flag retained for §2 audit-cli compliance.",
    )
    def dashboard_export(fmt, verbosity, package, output, dry_run, yes):
        """Machine-readable dump of the dashboard state."""
        from pathlib import Path

        from .._dashboard import _export as exp
        from .._dashboard import gather_ecosystem_state
        from .._dashboard._render import (
            cols_for_verbosity,
            enrichers_for_cols,
        )

        # Make sure the gh-release enricher always runs for org/pdf/md
        # exports so the RELEASE column has real data. The export CLI
        # defaults to -vvv, but `gather_ecosystem_state`'s verbosity →
        # enrichers heuristic doesn't include `gh-release` (it's only
        # added by `dashboard list` based on visible columns). Without
        # this, reports always show N/C for GH-Release, defeating the
        # point of the column.
        enrichers = enrichers_for_cols(cols_for_verbosity(verbosity))
        if fmt in ("md", "org", "pdf"):
            enrichers.add("gh-release")
            if verbosity < 2:
                enrichers.add("pypi")  # PYPI column also needs network

        states = gather_ecosystem_state(
            verbosity=verbosity,
            packages=list(package) or None,
            enrichers=enrichers,
        )
        if dry_run:
            click.echo(
                f"would emit: format={fmt} rows={len(states)} "
                f"verbosity={verbosity}"
                + (f" output={output}" if output else "")
            )
            return
        del yes

        # PDF follows the ywatanabe "usual PDF" convention: the .org
        # is the canonical source and the .pdf is rendered from it by
        # pandoc or `emacs --batch`. PDF therefore needs a filesystem
        # path; everything else can go to stdout if no -o is given.
        if fmt == "pdf":
            if not output:
                # Timestamped default so the operator always gets
                # something usable, even from a redirected stdout.
                from datetime import datetime as _dt

                output = str(
                    Path(
                        f"scitex-ecosystem-"
                        f"{_dt.now().strftime('%Y%m%d-%H%M%S')}.pdf"
                    ).resolve()
                )
            result = exp.to_pdf(states, output)
            if result["status"] == "ok":
                click.echo(
                    f"wrote {result['pdf']} (org sidecar: {result['org']}) "
                    f"via {result['tool']}"
                )
            elif result["status"] == "org_only":
                # Exit 0 — the .org file is still a usable artefact.
                # The 2026-05-27 instructions explicitly say "do not
                # block" when the host lacks the converter.
                click.echo(
                    f"wrote {result['org']} but could not produce PDF: "
                    f"{result['reason']}",
                    err=True,
                )
            else:
                click.echo(
                    f"wrote {result['org']} but {result['tool']} failed: "
                    f"{result.get('error', 'unknown error')}",
                    err=True,
                )
                raise SystemExit(2)
            return

        if fmt == "org":
            text = exp.to_org(states)
        elif fmt == "json":
            text = exp.to_json(states)
        elif fmt == "csv":
            text = exp.to_csv(states)
        elif fmt == "md":
            text = exp.to_markdown(states)
        else:  # pragma: no cover — click.Choice prevents this
            raise click.ClickException(f"unknown format: {fmt}")

        if output:
            Path(output).expanduser().resolve().write_text(text, encoding="utf-8")
            click.echo(f"wrote {output}")
        else:
            click.echo(text)

    # Back-compat shim: web UI entry point. Kept here because it's
    # dashboard-related; the `start-dashboard` name predates the
    # `dashboard` group and is preserved for external scripts/CI.
    @ecosystem.command("start-dashboard")
    @click.option("--port", default=8050, type=int, help="Port to serve on.")
    @click.option("--host", default="0.0.0.0", help="Host to bind to.")
    @click.option("--debug", is_flag=True, help="Enable debug/reload mode.")
    @click.option(
        "--no-browser", is_flag=True, help="Do not open browser automatically."
    )
    @click.option("--force", is_flag=True, help="Kill existing process on the port.")
    @click.option(
        "--background", is_flag=True, help="Run dashboard in a background process."
    )
    @click.option(
        "--dry-run", is_flag=True, help="Print what would be done; do not start."
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def ecosystem_start_dashboard(
        port, host, debug, no_browser, force, background, dry_run, yes
    ):
        """Launch the ecosystem dashboard web UI.

        \b
        Example:
            $ scitex-dev ecosystem start-dashboard
            $ scitex-dev ecosystem start-dashboard --port 9000 --background
            $ scitex-dev ecosystem start-dashboard --dry-run
        """
        del yes  # accepted for §2; dashboard launch is non-interactive
        if dry_run:
            click.echo(
                f"would launch dashboard on {host}:{port} "
                f"(background={background}, debug={debug}, force={force})"
            )
            return
        if background:
            # Delegate to run_background so log + pid land under
            # ~/.scitex/dev/runtime/ per 01_arch_06_local-state-directories.md.
            from ....dashboard.app import run_background

            run_background(host=host, port=port, force=force)
            click.echo(f"Dashboard started in background on {host}:{port}")
        else:
            from ....dashboard import run_dashboard

            run_dashboard(
                port=port,
                host=host,
                debug=debug,
                open_browser=not no_browser,
                force=force,
            )
