"""PS-103 root-pollution whitelist — single source of truth.

Rule: anything at repo root must be either (a) in the strict
SciTeX baseline below, (b) hidden (starts with `.`), or (c) explicitly
whitelisted in the project's `.scitex/dev/config.yaml` or the user's
global `~/.scitex/dev/config.yaml`.

The baseline matches the canonical clean layout (see `~/proj/scitex-stats`
as reference) plus a few content-friendly conventions (`data/`,
`externals/`).

Two consumers call into this module:

  * `audit-project` (PS-103) — flags every existing root child that
    fails `is_allowed_at_root()`.
  * `~/.claude/hooks/pre-tool-use/inhibit_project_root_pollution.sh`
    (or its replacement) — checks at write-time before Claude creates
    a new root file.

Keeping a single Python implementation prevents the two consumers
from drifting on what counts as "allowed".
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path


# Strict baseline. Every SciTeX package root may carry these without
# any per-project config — the scitex-stats clean layout.
SPEC_DEFAULT_FILES: frozenset[str] = frozenset(
    {
        # Required community / packaging files (also enforced by other
        # PS rules: PS-133 / PS-134 / PS-135 / PS-137 / PS-138 / PS-101)
        "README.md",
        "LICENSE",
        "LICENSE.md",  # PEP-639 variants
        "LICENSE.txt",
        "CHANGELOG.md",
        "CLA.md",
        "CONTRIBUTING.md",
        "SECURITY.md",  # GitHub community-health file (sibling of CONTRIBUTING)
        "pyproject.toml",
        "Makefile",
        # Codecov config — canonical location is repo root (see
        # `_skills/general/02_package/11_ci-and-codecov.md`). Without
        # this entry the canonical CI wiring trips PS-103.
        "codecov.yml",
        # Node-ecosystem canonical manifests for any pkg shipping a
        # frontend (scitex-ui, hybrids). Like `pyproject.toml` but for
        # npm — no canonical alternative location.
        "package.json",
        "package-lock.json",
        # Optional agent context. Canonical location is `.claude/CLAUDE.md`
        # (auto-allowed by the hidden-pattern), but root `CLAUDE.md` is
        # tolerated for backwards compatibility — should be gitignored
        # since it carries machine-local agent state.
        "CLAUDE.md",
    }
)

SPEC_DEFAULT_DIRS: frozenset[str] = frozenset(
    {
        "src",
        "tests",
        "docs",
        "examples",
        "scripts",
        "data",  # examples / fixtures / dataset products
        "externals",  # vendored third-party content for examples
        "dist",  # build artifacts (sdist / wheel)
        "build",  # hatch/setuptools temp build dir (sibling of dist)
        "GITIGNORED",  # convention: user scratch
    }
)


def _global_config_path() -> Path:
    """User-level overrides: `~/.scitex/dev/config.yaml`.

    Honours `$SCITEX_DIR` per local-state-directories §6 — moving
    `~/.scitex/` relocates the global config too.
    """
    base = Path(os.environ.get("SCITEX_DIR", os.path.expanduser("~/.scitex")))
    return base / "dev" / "config.yaml"


def _whitelist_from_config(repo: Path | None) -> dict:
    """Merge global + project `audit.root-whitelist` blocks.

    Project entries STACK ON TOP of global entries (both contribute);
    nothing is replaced. Returns a dict with three sets/lists:

        files:    {basename, ...}     exact match
        patterns: ["pat-*", ...]      fnmatch globs
        dirs:     {basename, ...}     exact match (directories)
    """
    files: set[str] = set()
    patterns: list[str] = []
    dirs: set[str] = set()

    sources: list[Path] = [_global_config_path()]
    if repo is not None:
        sources.append(repo / ".scitex" / "dev" / "config.yaml")

    for cfg_path in sources:
        if not cfg_path.is_file():
            continue
        # Reuse the same minimal parser that `_config.load_config` uses
        # via `_loader._read_yaml`. We keep the import lazy so the
        # auditor module stays light.
        from .._config._loader import _read_yaml  # type: ignore[attr-defined]

        raw = _read_yaml(cfg_path) or {}
        block = (raw.get("audit") or {}).get("root-whitelist") or {}
        for f in block.get("files", []) or []:
            files.add(str(f))
        for p in block.get("patterns", []) or []:
            patterns.append(str(p))
        for d in block.get("dirs", []) or []:
            dirs.add(str(d))

    return {"files": files, "patterns": patterns, "dirs": dirs}


def is_allowed_at_root(
    repo: Path | None,
    basename: str,
    *,
    is_dir: bool | None = None,
) -> bool:
    """True iff `basename` is allowed at `repo`'s root.

    Hidden entries (starting with `.`) are always allowed — that
    covers .git, .github, .scitex, .dev, .gitignore, .dockerignore,
    .env.example, .pre-commit-config.yaml, .readthedocs.yaml, etc.

    `is_dir` lets callers disambiguate when the same name could
    apply to either a file or a dir. When None, both forms are
    consulted (file-list ∪ dir-list).
    """
    if not basename or basename in (".", ".."):
        return True
    if basename.startswith("."):
        return True

    wl = _whitelist_from_config(repo)

    if is_dir is True:
        if basename in SPEC_DEFAULT_DIRS or basename in wl["dirs"]:
            return True
        # Patterns can apply to dirs too (e.g. "release-*" tracking dir).
        return any(fnmatch.fnmatch(basename, p) for p in wl["patterns"])

    if is_dir is False:
        if basename in SPEC_DEFAULT_FILES or basename in wl["files"]:
            return True
        return any(fnmatch.fnmatch(basename, p) for p in wl["patterns"])

    # Unknown — accept if either side matches.
    if (
        basename in SPEC_DEFAULT_FILES
        or basename in SPEC_DEFAULT_DIRS
        or basename in wl["files"]
        or basename in wl["dirs"]
    ):
        return True
    return any(fnmatch.fnmatch(basename, p) for p in wl["patterns"])


def list_violations(repo: Path) -> list[tuple[str, str]]:
    """Return [(basename, kind), ...] for every disallowed entry at repo root.

    `kind` is "file" or "dir". Used by PS-103 in `_audit._check_top_level`
    and by `scitex-dev internal allowed-at-root` for the hook.
    """
    out: list[tuple[str, str]] = []
    if not repo.is_dir():
        return out
    for child in sorted(repo.iterdir()):
        kind = "dir" if child.is_dir() else "file"
        if not is_allowed_at_root(repo, child.name, is_dir=child.is_dir()):
            out.append((child.name, kind))
    return out


def _suggest_relocation(basename: str, kind: str) -> str:
    """Hint for where a disallowed entry probably belongs.

    Used in the violation message and by the pre-write hook to give
    actionable feedback.
    """
    name = basename.lower()
    suffix = Path(basename).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return "./docs/assets/  (if referenced from README/docs) or ./.dev/screenshots/  (if scratch) or delete"
    if suffix in {".log", ".tmp", ".bak"}:
        return "./.dev/  or delete"
    if suffix in {".yaml", ".yml"} and (
        "snapshot" in name or "state" in name or "test" in name or "debug" in name
    ):
        return "./.dev/  (scratch) or delete"
    if suffix in {".py", ".ipynb"} and (
        name.startswith(("tmp", "scratch", "quick", "untitled"))
    ):
        return "./.dev/<category>/  or delete"
    if kind == "dir":
        return (
            "either move into ./src/<pkg>/ (if it ships in the wheel), "
            "into ./.dev/ (if scratch), or whitelist via "
            "<repo>/.scitex/dev/config.yaml `audit.root-whitelist.dirs:`"
        )
    return (
        "move under an existing baseline dir, or whitelist via "
        "<repo>/.scitex/dev/config.yaml `audit.root-whitelist.files:`"
    )


def quarantine_dir(repo: Path) -> Path:
    """Return the timestamped quarantine path for moved root violations.

    Lives under the gitignored project-scope `runtime/` subtree
    (local-state-directories §4b). Each invocation gets a fresh
    `<YYYYmmdd-HHMMSS>/` so repeated runs accumulate.
    """
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return repo / ".scitex" / "dev" / "runtime" / "root-violations" / ts


def clean_root_violations(
    repo: Path,
    *,
    dry_run: bool = True,
) -> tuple[Path | None, list[tuple[str, str]]]:
    """Move every PS-103 violation under repo root into a quarantine dir.

    Returns ``(quarantine_path, [(basename, kind), ...])``. The
    quarantine path is None when there are no violations, or when
    ``dry_run`` is True (caller previews the would-be path).

    Non-destructive by design: every entry is `shutil.move`d, never
    deleted. The quarantine dir is created lazily and only if there
    is at least one violation.
    """
    import shutil

    violations = list_violations(repo)
    if not violations:
        return None, []

    target = quarantine_dir(repo)
    if dry_run:
        return target, violations

    target.mkdir(parents=True, exist_ok=True)
    for basename, _kind in violations:
        src = repo / basename
        dst = target / basename
        # If a same-named entry already exists in the quarantine
        # (rare — only on sub-second double-runs), append a suffix
        # so we don't blow away earlier evidence.
        if dst.exists():
            i = 1
            while True:
                dst = target / f"{basename}.{i}"
                if not dst.exists():
                    break
                i += 1
        shutil.move(str(src), str(dst))
    return target, violations


__all__ = [
    "SPEC_DEFAULT_FILES",
    "SPEC_DEFAULT_DIRS",
    "is_allowed_at_root",
    "list_violations",
    "quarantine_dir",
    "clean_root_violations",
]
