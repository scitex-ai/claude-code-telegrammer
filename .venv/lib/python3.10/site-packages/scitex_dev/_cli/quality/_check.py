"""Quality audit subcommand: `scitex-dev quality audit-<subcmd>`."""

import subprocess
import sys
from pathlib import Path

from ..._ecosystem._release.pyproject_lint import lint_pyproject
from ..._release.publisher import publish_release
from ..._release.rtd_onboard import onboard_rtd

SCRIPTS = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "quality"


def audit_docs(projects_root: str | None = None):
    """Run doc-example auditor."""
    args = [sys.executable, str(SCRIPTS / "audit_doc_examples.py")]
    if projects_root:
        args += ["--projects-root", projects_root]
    return subprocess.call(args)


def audit_scope(projects_root: str | None = None):
    """Run test-scope auditor."""
    args = [sys.executable, str(SCRIPTS / "audit_test_scope.py")]
    if projects_root:
        args += ["--projects-root", projects_root]
    return subprocess.call(args)


def audit_lines():
    """Run line-limit auditor."""
    return subprocess.call([sys.executable, str(SCRIPTS / "audit_line_limits.py")])


def lint_pyproject_cli(repo_root: str | None = None, strict: bool = False) -> int:
    """Lint a single repo's pyproject.toml against the codified rules.

    Returns 0 if no findings; 1 if any HIGH/CRITICAL; 2 if MEDIUM/LOW only and
    --strict is set.
    """
    repo = Path(repo_root or ".").resolve()
    rep = lint_pyproject(repo)
    if not rep.findings:
        print(f"{rep.package}: clean")
        return 0
    print(f"{rep.package}  ({rep.pyproject})")
    for f in rep.findings:
        print(f"  {f.render()}")
    if rep.has_high:
        return 1
    return 2 if strict else 0


def rtd_onboard_cli(repo_root: str | None = None, dry_run: bool = False) -> int:
    """Scaffold a minimal Read the Docs setup. Idempotent."""
    repo = Path(repo_root or ".").resolve()
    rep = onboard_rtd(repo, dry_run=dry_run)
    print(rep.render())
    return 0 if not rep.failed else 1


def release_publish_cli(
    repo_root: str | None = None,
    version: str | None = None,
    notes: str | None = None,
    dry_run: bool = False,
) -> int:
    """Smart `git tag -> push -> gh release create` (per workflow trigger).

    Auto-detects whether the repo's publish-pypi.yml fires on
    ``release: published`` or ``push: tags`` and runs the right
    sequence. Idempotent: skips an existing tag or release.
    """
    repo = Path(repo_root or ".").resolve()
    if not version:
        # Default to pyproject.toml version if not specified.
        try:
            import tomllib  # type: ignore[import-not-found]
        except ImportError:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        with (repo / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
        version = (data.get("project") or {}).get("version")
    if not version:
        print(
            "error: --version required (and pyproject.toml has none)", file=sys.stderr
        )
        return 1
    rep = publish_release(repo, version, notes=notes, dry_run=dry_run)
    print(rep.render())
    return 0 if not rep.failed else 1


def audit_ecosystem(
    projects_root: str | None = None,
    out: str | None = None,
    categories: str = "umbrella,library,external-lib",
):
    """Run the ecosystem-wide static auditor."""
    args = [sys.executable, str(SCRIPTS / "audit_ecosystem.py"), "--quiet"]
    if projects_root:
        args += ["--projects-root", projects_root]
    if out:
        args += ["--out", out]
    if categories:
        args += ["--categories", categories]
    return subprocess.call(args)


import click


@click.group(name="_check")
def _main_group():
    """Minimal Click dispatcher: `python -m scitex_dev._cli.quality._check <cmd>`."""


@_main_group.command("audit_docs", help="Run doc-example auditor")
@click.option("--projects-root", default=None)
def _cmd_audit_docs(projects_root):
    sys.exit(audit_docs(projects_root=projects_root) or 0)


@_main_group.command("audit_scope", help="Run test-scope auditor")
@click.option("--projects-root", default=None)
def _cmd_audit_scope(projects_root):
    sys.exit(audit_scope(projects_root=projects_root) or 0)


@_main_group.command("audit_lines", help="Run line-limit auditor")
def _cmd_audit_lines():
    sys.exit(audit_lines() or 0)


def _main(argv=None):
    """Backwards-compatible callable for `python -m ...`."""
    _main_group.main(args=argv, standalone_mode=False)


if __name__ == "__main__":
    _main_group()
