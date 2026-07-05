#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev ecosystem bulk` — universal fan-out primitive.

xargs-style substitution. For each selected package:

- If any token in the user's command equals ``{}``, every ``{}`` is replaced
  with the package name (substitution form — the user controls where the
  package name appears).
- Otherwise the package name is appended at the end of the argv (append
  form — convenience for the ``... <pkg>`` shape).

This single primitive replaces the dedicated ``install`` / ``sync`` /
``pull`` / ``checkout`` / ``test-remote`` / ``sync-remote`` subcommands —
those remain available for muscle-memory but their help epilog points
here. ``clone`` is NOT replaceable here because it creates package dirs
that don't exist yet, while ``bulk`` can only iterate already-registered
packages.

Execution model: ``subprocess.run([*argv], shell=False)`` — argv list,
never via ``/bin/sh``. The command runs in the caller's cwd (the
substituted-in path is the explicit handle, e.g. ``git -C ~/proj/{}``).

Equivalent to::

    for pkg in $(scitex-dev ecosystem list --names-only); do
        # substitution form
        <cmd-with-{}-replaced-by-$pkg>
        # OR append form (no {})
        <cmd> [args...] $pkg
    done
"""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import click


def _filter_packages(packages, categories):
    """Resolve the ``(name, info)`` list to run on.

    - ``packages``: tuple/list of package names (empty → all non-archived).
    - ``categories``: tuple/list of category names (empty → no category
      filter). When both filters are given they are intersected.
    """
    from ..._ecosystem._core import ECOSYSTEM

    selected: list[tuple[str, dict]] = []
    pkg_set = set(packages) if packages else None
    cat_set = set(categories) if categories else None
    for name, info in ECOSYSTEM.items():
        if info.get("archived"):
            continue
        if pkg_set is not None and name not in pkg_set:
            continue
        if cat_set is not None and info.get("category") not in cat_set:
            continue
        selected.append((name, info))
    return selected


def _substitute(template: tuple[str, ...] | list[str], pkg: str) -> list[str]:
    """xargs-style substitution.

    If ``{}`` appears anywhere in any token of ``template`` (so both ``"{}"``
    and ``"~/proj/{}"`` qualify), every occurrence of ``{}`` is replaced with
    ``pkg``. Otherwise return ``[*template, pkg]`` (append form).
    """
    if any("{}" in tok for tok in template):
        return [tok.replace("{}", pkg) for tok in template]
    return [*template, pkg]


def _run_one(argv: list[str]) -> tuple[int, str]:
    """Run ``argv`` (no shell); return (rc, combined_output)."""
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, f"command not found: {exc}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def _emit_prefixed(name: str, text: str) -> None:
    if not text:
        return
    for line in text.rstrip("\n").splitlines():
        click.echo(f"[{name}] {line}")


def run_bulk(
    verb_argv: tuple[str, ...],
    *,
    packages: tuple[str, ...] = (),
    categories: tuple[str, ...] = (),
    jobs: int = 4,
    yes: bool = False,
    stop_on_error: bool = False,
) -> int:
    """Run the user's command for each selected package.

    Substitution rules (xargs-style):
      - if any token in ``verb_argv`` equals ``{}``, replace it with ``pkg``;
      - otherwise append ``pkg`` at the end of the argv.

    When ``yes`` is False (default) prints a dry-run plan and returns 0.

    Exit code: 0 if all packages succeed, otherwise the maximum non-zero
    return code observed across packages.
    """
    if not verb_argv:
        click.echo(
            "bulk: missing command (e.g. "
            "`bulk -- scitex-dev ecosystem pull` or `bulk -- git -C ~/proj/{} pull`)",
            err=True,
        )
        return 2

    items = _filter_packages(packages, categories)
    if not items:
        click.echo("no packages matched the filter", err=True)
        return 1

    if not yes:
        click.echo(f"# DRY-RUN — would run for {len(items)} package(s):")
        for name, _info in items:
            argv = _substitute(verb_argv, name)
            click.echo("# " + " ".join(argv))
        click.echo("# pass --yes to actually execute.")
        return 0

    results: dict[str, tuple[int, str]] = {}

    def _task(name: str) -> tuple[str, int, str]:
        argv = _substitute(verb_argv, name)
        rc, out = _run_one(argv)
        return name, rc, out

    if jobs <= 1:
        for name, _info in items:
            n, rc, out = _task(name)
            _emit_prefixed(n, out)
            results[n] = (rc, out)
            if rc != 0 and stop_on_error:
                break
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = {ex.submit(_task, name): name for name, _info in items}
            for fut in as_completed(futs):
                n, rc, out = fut.result()
                _emit_prefixed(n, out)
                results[n] = (rc, out)
                if rc != 0 and stop_on_error:
                    for f in futs:
                        f.cancel()
                    break

    ok = sum(1 for rc, _ in results.values() if rc == 0)
    failed = sum(1 for rc, _ in results.values() if rc != 0)
    click.echo()
    click.echo(f"# summary: {ok} ok / {failed} failed (of {len(results)} run)")
    if failed:
        for name, (rc, _) in results.items():
            if rc != 0:
                click.echo(f"#   FAIL {name} (exit {rc})")
    # max non-zero exit code, or 0 if all good
    return max((rc for rc, _ in results.values() if rc != 0), default=0)


_BULK_EPILOG = """\
Universal per-package fan-out. The command goes after `--`. Use `{}` as an
xargs-style placeholder for the package name; if no `{}` is present, the
package name is appended at the end.

\b
Examples:
    # Append form (no {}):
    scitex-dev ecosystem bulk -- scitex-dev ecosystem audit-all

\b
    # Substitution form ({}):
    scitex-dev ecosystem bulk -- git -C ~/proj/{} pull --rebase
    scitex-dev ecosystem bulk -- pip install -e ~/proj/{}
    scitex-dev ecosystem bulk -j 8 -c cli-tool -- scitex-dev ecosystem audit-cli

\b
Replaces these legacy subcommands:
    install   →  bulk -- pip install -e ~/proj/{}
    pull      →  bulk -- git -C ~/proj/{} pull --rebase
    checkout  →  bulk -- git -C ~/proj/{} checkout BRANCH
"""


def register_bulk_command(ecosystem_group):
    """Attach the `bulk` subcommand to the passed-in click group."""

    @ecosystem_group.command(
        "bulk",
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
        epilog=_BULK_EPILOG,
    )
    @click.argument("verb_and_args", nargs=-1, type=click.UNPROCESSED, required=True)
    @click.option(
        "--package",
        "-p",
        multiple=True,
        help="Restrict to specific package name(s). Repeatable.",
    )
    @click.option(
        "--category",
        "-c",
        multiple=True,
        help=(
            "Restrict to package(s) with the given category. Repeatable. "
            "Intersected with -p."
        ),
    )
    @click.option(
        "--jobs",
        "-j",
        default=4,
        show_default=True,
        type=int,
        help="Parallel workers.",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help="Actually run; otherwise print a dry-run plan.",
    )
    @click.option(
        "--continue-on-error/--stop-on-error",
        default=True,
        show_default=True,
        help="Keep going past failures (default) or stop at the first one.",
    )
    def ecosystem_bulk(verb_and_args, package, category, jobs, yes, continue_on_error):
        """Run a command in (or for) every ecosystem package.

        \b
        Universal fan-out primitive. The command appears AFTER `--`:
          scitex-dev ecosystem bulk [opts] -- CMD [ARGS...]
        If any token equals `{}` it is replaced with the package name;
        otherwise the package name is appended at the end (xargs-style).
        Executed via subprocess with shell=False (argv list, never /bin/sh).

        \b
        Examples:
          $ scitex-dev ecosystem bulk -- scitex-dev ecosystem audit-all
          $ scitex-dev ecosystem bulk -- git -C ~/proj/{} pull --rebase
          $ scitex-dev ecosystem bulk -- pip install -e ~/proj/{}
          $ scitex-dev ecosystem bulk -j 8 -c cli-tool -- scitex-dev ecosystem audit-cli
        """
        # When `ignore_unknown_options=True`, click leaves a leading `--`
        # in the argv if the user used it as a separator. Strip it.
        argv = tuple(verb_and_args)
        if argv and argv[0] == "--":
            argv = argv[1:]
        rc = run_bulk(
            argv,
            packages=tuple(package),
            categories=tuple(category),
            jobs=jobs,
            yes=yes,
            stop_on_error=not continue_on_error,
        )
        raise SystemExit(rc)

    return ecosystem_bulk


__all__ = ["register_bulk_command", "run_bulk"]
