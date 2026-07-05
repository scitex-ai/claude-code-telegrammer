#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `clean-root` — move PS-103 root violations into quarantine."""

import click


def register(ecosystem):
    @ecosystem.command(
        "clean-root",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem clean-root figrecipe                  # preview\n"
            "  $ scitex-dev ecosystem clean-root figrecipe --yes            # move\n"
            "  $ scitex-dev ecosystem clean-root all -j 8                   # preview all\n"
            "  $ scitex-dev ecosystem clean-root scitex-io,figrecipe --yes  # bulk\n"
            "\n"
            "Moves every PS-103 root violation in DISTRIBUTIONS into\n"
            "<repo>/.scitex/dev/runtime/root-violations/<YYYYmmdd-HHMMSS>/.\n"
            "Non-destructive: nothing is deleted. The quarantine dir is\n"
            "gitignored via the standard `.scitex/*/runtime/*` rule. To\n"
            "permanently delete after review, `rm -rf` the timestamped\n"
            "subdir. To restore, `mv` the entries back.\n"
            "\n"
            "Default is dry-run; pass --yes to apply. Use --keep-screenshots\n"
            "etc. (or per-pkg `audit.root-whitelist` in .scitex/dev/config.yaml)\n"
            "to whitelist legitimate roots before cleaning."
        ),
    )
    @click.argument("distributions", nargs=-1, required=True)
    @click.option(
        "--dry-run",
        is_flag=True,
        default=True,
        help="(default) Print what would move; do nothing. Pass --yes to apply.",
    )
    @click.option(
        "--yes", "-y", is_flag=True, help="Apply for real (overrides default dry-run)."
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--jobs",
        "-j",
        default=1,
        show_default=True,
        type=int,
        help="Run packages in parallel.",
    )
    def ecosystem_clean_root(distributions, dry_run, yes, as_json, jobs):
        """Move PS-103 root violations into <repo>/.scitex/dev/runtime/root-violations/<ts>/."""
        import json as _json
        import sys as _sys
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from pathlib import Path

        from ...._ecosystem._core import ECOSYSTEM
        from ...audit._project._root_whitelist import clean_root_violations

        raw: list[str] = []
        for d in distributions:
            raw.extend(p.strip() for p in d.split(",") if p.strip())
        if "all" in raw:
            pkgs = list(ECOSYSTEM.keys())
        else:
            pkgs = []
            for name in raw:
                if name not in pkgs:
                    pkgs.append(name)

        effective_dry_run = dry_run and not yes

        def _clean_one(pkg: str) -> tuple[str, dict]:
            info = ECOSYSTEM.get(pkg)
            if info is None:
                return pkg, {"exit": 2, "error": "unknown package"}
            repo = Path(info["local_path"]).expanduser()
            if not repo.is_dir():
                return pkg, {"exit": 2, "error": f"local_path missing: {repo}"}
            try:
                target, viols = clean_root_violations(repo, dry_run=effective_dry_run)
            except Exception as e:
                return pkg, {"exit": 1, "error": str(e)}
            return pkg, {
                "exit": 0,
                "count": len(viols),
                "target": str(target) if target else None,
                "moved": [{"name": n, "kind": k} for n, k in viols],
                "dry_run": effective_dry_run,
            }

        all_results: dict[str, dict] = {}
        if jobs <= 1 or len(pkgs) <= 1:
            for d in pkgs:
                name, res = _clean_one(d)
                all_results[name] = res
        else:
            with ThreadPoolExecutor(max_workers=jobs) as ex:
                futs = {ex.submit(_clean_one, d): d for d in pkgs}
                for f in as_completed(futs):
                    name, res = f.result()
                    all_results[name] = res

        total = sum(r.get("count", 0) for r in all_results.values())
        worst = max((r.get("exit", 0) for r in all_results.values()), default=0)

        if as_json:
            click.echo(
                _json.dumps(
                    {
                        "distributions": pkgs,
                        "dry_run": effective_dry_run,
                        "total_violations": total,
                        "results": all_results,
                    },
                    indent=2,
                )
            )
            _sys.exit(worst)

        action = "would move" if effective_dry_run else "moved"
        for pkg in pkgs:
            res = all_results[pkg]
            if res.get("error"):
                click.echo(f"  err   {pkg}: {res['error']}", err=True)
                continue
            cnt = res["count"]
            if cnt == 0:
                click.echo(f"  ok    {pkg}: no root violations")
                continue
            tgt = res.get("target") or ""
            click.echo(f"  {action:9} {pkg}: {cnt} entries → {tgt}")
            for entry in res.get("moved", []):
                click.echo(f"      {entry['kind']:4}  {entry['name']}")

        click.echo("")
        if effective_dry_run:
            click.echo(
                f"Preview: {total} entries across {len(pkgs)} package(s). "
                "Re-run with --yes to apply.",
                err=True,
            )
        else:
            click.echo(
                f"Moved: {total} entries across {len(pkgs)} package(s) "
                "into per-repo .scitex/dev/runtime/root-violations/<ts>/.",
                err=True,
            )
        _sys.exit(worst)
