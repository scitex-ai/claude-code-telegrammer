"""CLI convention auditor — optional feature (install via `scitex-dev[cli-audit]`).

Checks a package's Click command tree against the noun-verb convention in
`_skills/general/03_interface/02_cli/SKILL.md`. Warn-only.

Resolution order per token:
    1. Custom dict — `<project>/.scitex/dev/cli-audit-dict.yaml`
    2. Custom dict — `~/.scitex/dev/cli-audit-dict.yaml`
    3. Bundled §1c catalog — `CATALOG` below
    4. Moby POS — vendored dictionary (transitive/intransitive distinction)
    5. `unknown` — warning, add to custom dict

`AVAILABLE` is True when the Moby data ships with the install. Optional
NLP backends may land under the `cli-audit` extra later.
"""

from __future__ import annotations

from importlib import resources

try:
    _MOBY_REF = resources.files(__name__).joinpath("data", "mobypos.txt.gz")
    AVAILABLE = _MOBY_REF.is_file()
except (ModuleNotFoundError, FileNotFoundError):
    AVAILABLE = False

__all__ = ["AVAILABLE", "audit_cli", "CATALOG"]

# §1c canonical catalog — shadows Moby for overloaded tokens (`list`, `start`).
CATALOG: dict[str, set[str]] = {
    # Nouns (domain categories)
    **{
        w: {"noun"}
        for w in [
            "package",
            "project",
            "module",
            "script",
            "example",
            "template",
            "manifest",
            "release",
            "config",
            "profile",
            "preset",
            "env-var",
            "skill",
            "doc",
            "docs",
            "readme",
            "changelog",
            "guideline",
            "dataset",
            "file",
            "path",
            "cache",
            "db",
            "index",
            "record",
            "bibentry",
            "figure",
            "table",
            "paper",
            "claim",
            "host",
            "machine",
            "remote",
            "tunnel",
            "container",
            "image",
            "server",
            "service",
            "process",
            "job",
            "task",
            "run",
            "ecosystem",
            "api",
            "mcp",
            "tool",
            "plugin",
            "hook",
            "command",
            "event",
            "log",
            "user",
            "account",
            "token",
            "key",
            "secret",
            "role",
            "session",
            "completion",
            # Shell names — surface as final positional of `completion <shell>`
            "bash",
            "zsh",
            "fish",
            "powershell",
            "pwsh",
            "stats",
            "quality",
            "installation",
            # Plurals (`packages`, `jobs`, `bibentries`, …) are auto-recognised
            # via the singularizer in `_audit._singular_candidates` — no need
            # to seed them explicitly.
            # Domain-specific nouns (container backends, ecosystem jargon)
            "apptainer",
            "singularity",
            "docker",
            "podman",
            "sandbox",
            "backend",
            "sms",
            "template",
            "templates",
            "mount",
            "mounts",
            "snapshot",
            "snapshots",
            # Scientific dataset sources (neuro, chem, bio)
            "openneuro",
            "dandi",
            "physionet",
            "zenodo",
            "figshare",
            "openml",
            "moleculenet",
            "chembl",
            "clinicaltrials",
            "geo",
            "allen",
            "pubmed",
            "crossref",
            "openalex",
            # Plotting / figure-specific nouns
            "hitmap",
            "heatmap",
            "gui",
            "fonts",
            "font",
            "presets",
            "preset",
            "backends",
            "backend",
            # Cloud/infra domain nouns
            "gitea",
            "github",
            "gitlab",
            "cloud",
            "workspace",
            "workspaces",
            "sdk",
            "prefs",
            "preferences",
            "cli",
            "context",
            # §1e introspection objects
            "python-api",
            "python-apis",
            "tools",
        ]
    },
    # Transitive verbs — need an object
    **{
        w: {"verb-t"}
        for w in [
            "list",
            "show",
            "get",
            "find",
            "search",
            "describe",
            "inspect",
            "diff",
            "tail",
            "create",
            "add",
            "init",
            "generate",
            "scaffold",
            "clone",
            "copy",
            "import",
            "register",
            "update",
            "edit",
            "rename",
            "move",
            "merge",
            "patch",
            "reset",
            "restore",
            "rollback",
            "delete",
            "remove",
            "purge",
            "clean",
            "archive",
            "revoke",
            "start",
            "stop",
            "restart",
            "pause",
            "resume",
            "enable",
            "disable",
            "install",
            "uninstall",
            "setup",
            "bootstrap",
            "exists",
            "exist",
            "login",
            "logout",
            "eval",
            "execute",
            "exec",
            # `run` is intentionally noun-only per §1c — use `start-run` /
            # `submit-run` for the verb action.
            "kill",
            "ps",
            "build",
            "compile",
            "publish",
            "deploy",
            "tag",
            "ship",
            "load",
            "save",
            "read",
            "write",
            "fetch",
            "download",
            "upload",
            "export",
            "convert",
            "render",
            "parse",
            "validate",
            "check",
            "test",
            "lint",
            "format",
            "audit",
            "verify",
            "benchmark",
            "sync",
            "pull",
            "push",
            "checkout",
            "clone",
            "commit",
            "stash",
            "apply",
            "reconcile",
            "send",
            "notify",
            "broadcast",
            "subscribe",
        ]
    },
    # Intransitive verbs — may be flat keepers per §1a
    **{w: {"verb-i"} for w in ["doctor", "repl", "shell"]},
    # Polysemous noun+verb tokens — "show me X" pattern. Treated as
    # both noun and verb-i, so they pass §1's leaf-must-be-verb check
    # under a noun group (e.g., `<cli> agent status`, `<cli> job logs`),
    # while still being unacceptable as a bare top-level leaf (caught
    # by §1 because they have a noun label and no compound).
    **{
        w: {"noun", "verb-i"}
        for w in [
            "status",
            "logs",
            "log",
            "info",
            "health",
            "summary",
            "report",
        ]
    },
    # Allowed flat-keeper exceptions
    "version": {"flat-keeper"},
}

FLAT_KEEPERS = {"doctor", "repl", "shell", "version"}


def audit_cli(
    package: str | None = None,
    behavioral: bool = False,
    output_json: bool = False,
    audit_all: bool = False,
    dry_run: bool = False,
    registry_path: str | None = None,
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Audit a package's installed CLI; return exit code (always 0 — warn-only).

    - `package` is required unless `audit_all=True`.
    - `audit_all=True` runs the audit across every entry in the registry
      (resolved via the §6b cascade: --registry > $SCITEX_DEV_REGISTRY >
      project YAML > user YAML > bundled dict).
    - `dry_run=True` (with `audit_all=True`) lists targets without auditing.
    """
    if not AVAILABLE:
        import click

        click.echo(
            "scitex-dev[cli-audit] is not installed or data is missing. "
            "Install with: pip install 'scitex-dev[cli-audit]'",
            err=True,
        )
        return 2

    from ._audit import run_audit, run_audit_all

    if audit_all:
        return run_audit_all(
            behavioral=behavioral,
            output_json=output_json,
            dry_run=dry_run,
            registry_path=registry_path,
            rules=rules,
            exclude=exclude,
            min_severity=min_severity,
            timeout=timeout,
        )
    if package is None:
        import click

        click.echo("error: PACKAGE is required (or pass --all)", err=True)
        return 2
    return run_audit(
        package,
        behavioral=behavioral,
        output_json=output_json,
        rules=rules,
        exclude=exclude,
        min_severity=min_severity,
        timeout=timeout,
    )
