"""PS-139 + PS-140 — umbrella-dep ban + cross-package integration gate.

PS-139: standalone packages must not list `scitex` (the umbrella) in
runtime / extras dependencies. Codified after the 2026-05-06 HPC NFS
slow-import investigation surfaced 35+ standalones that pulled the
umbrella as a transitive dep.

PS-140: any package whose source has cross-package imports
(`scitex_<X>` peer or `scitex.<X>` umbrella) must ship a runtime
gate at `tests/integration/test_cross_package_imports.py` listing
every cross-package module name. Without it, renames/moves in peer
standalones surface as silent ModuleNotFoundError at user runtime
(this is exactly how the `scitex_io._load_cache` rename slipped past
CI for weeks).
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


_UMBRELLA_DEP_RE = re.compile(r"^\s*scitex(\[[^\]]*\])?\s*([<>=!~,].*)?$")


def _own_import_name(repo: Path) -> str:
    """Canonical import name for the package at repo (scitex-foo -> scitex_foo).

    Prefer the distribution name declared in [project].name over the
    checkout directory name. Agents and the operator routinely audit from
    git-worktree checkouts whose dir is <pkg>-<suffix> (e.g.
    scitex-dev-rel); deriving the own-name from the dir there yields
    scitex_dev_rel, so the package own scitex_dev.* imports stop
    matching the own-name filter in _collect_cross_package_imports and
    fire as bogus PS-140 missing-from-gate cross-package violations.
    [project].name is worktree-path-independent and fixes this.
    """
    dist = _pyproject_distribution_name(repo)
    if dist:
        return dist.replace("-", "_")
    return repo.name.replace("-", "_")


def _main_worktree_root(repo: Path) -> Path | None:
    """Return the *main* working-tree root if `repo` is a git worktree.

    The umbrella's canonical clone is `~/proj/scitex-python`; agents and
    the operator routinely audit from sibling `git worktree add` checkouts
    living at `<repo>/.worktrees/<name>` (or `<repo>/.claude/worktrees/...`).
    Those carry a different `repo.resolve()` path, so an exact-path match
    against the ECOSYSTEM `local_path` misses — the umbrella exemption then
    silently breaks and PS-139/PS-140 fire ~77 false positives on the
    umbrella's recursive `scitex[<extra>]` self-references.

    `git worktree list --porcelain` reports the main working tree first;
    its path is the registry-canonical one. Returns `None` when `repo` is
    not inside a git checkout (callers fall back to the plain path).
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        # The first "worktree <path>" line is always the main working tree.
        if line.startswith("worktree "):
            return Path(line[len("worktree ") :].strip())
    return None


def _pyproject_distribution_name(repo: Path) -> str | None:
    """Return `[project].name` from `repo/pyproject.toml`, or `None`."""
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    name = data.get("project", {}).get("name")
    return name if isinstance(name, str) else None


def _matches_umbrella_registry(repo: Path) -> bool:
    """True iff `repo`'s resolved path equals the umbrella's `local_path`."""
    try:
        from scitex_dev._ecosystem._core import ECOSYSTEM
    except ImportError:
        return False
    repo_resolved = repo.resolve()
    for dist, info in ECOSYSTEM.items():
        local = info.get("local_path")
        if not local:
            continue
        if Path(local).expanduser().resolve() == repo_resolved:
            return info.get("category") == "umbrella" or dist == "scitex"
    return False


def _is_umbrella(repo: Path) -> bool:
    """True if `repo` is the SciTeX umbrella package (distribution `scitex`).

    Cannot rely on the directory basename alone — the umbrella's local
    clone is `~/proj/scitex-python/`, so `repo.name` is `scitex-python`
    not `scitex`. Resolve the canonical distribution name from the
    ECOSYSTEM registry by matching `local_path` resolved.

    Three signals, any of which identifies the umbrella:

      1. `repo` itself matches the registry `local_path` (canonical clone).
      2. `repo` is a *git worktree* whose **main** working tree matches the
         registry (`.worktrees/<name>` and `.claude/worktrees/...` checkouts
         resolve to a different path than the registered clone — without
         this the exemption breaks for every worktree-based audit).
      3. The repo's own `pyproject.toml` declares `[project].name == "scitex"`
         — a path-independent backstop so the exemption survives clones at
         non-registered locations (CI checkouts, fresh `gh repo clone`, …).
    """
    if _matches_umbrella_registry(repo):
        return True
    main_wt = _main_worktree_root(repo)
    if main_wt is not None and main_wt.resolve() != repo.resolve():
        if _matches_umbrella_registry(main_wt):
            return True
    if _pyproject_distribution_name(repo) == "scitex":
        return True
    # Fallback: import name `scitex` (rare — would mean repo basename
    # matches the umbrella distribution name).
    return repo.name == "scitex"


def _strip_specifier(spec: str) -> str:
    """`scitex>=2.0` → `scitex`, `scitex[all]>=2.19` → `scitex`."""
    s = spec.strip().strip('"').strip("'")
    s = re.split(r"[<>=!~,;\[\s]", s, maxsplit=1)[0]
    return s.strip()


def _scan_pyproject_for_umbrella(pyproject: Path) -> list[str]:
    """Return human descriptions of each `scitex` (umbrella) entry found."""
    findings: list[str] = []
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return findings
    project = data.get("project", {})
    for spec in project.get("dependencies", []) or []:
        name = _strip_specifier(spec)
        if name == "scitex":
            findings.append(f"[project.dependencies] -> {spec!r}")
    for extra, members in (project.get("optional-dependencies", {}) or {}).items():
        for spec in members or []:
            name = _strip_specifier(spec)
            if name == "scitex":
                findings.append(f"[project.optional-dependencies.{extra}] -> {spec!r}")
    return findings


def _collect_cross_package_imports(src_root: Path, own_import: str) -> set[str]:
    """Mirror `/tmp/write-integration-tests.py` so the gate stays in sync."""
    seen: set[str] = set()
    for py in src_root.rglob("*.py"):
        if any(s in py.parts for s in ("__pycache__", "build", "dist", ".tox")):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if (
                    mod == "scitex"
                    or mod.startswith("scitex.")
                    or mod.startswith("scitex_")
                ):
                    if mod == own_import or mod.startswith(own_import + "."):
                        continue
                    seen.add(mod)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if (
                        name == "scitex"
                        or name.startswith("scitex.")
                        or name.startswith("scitex_")
                    ):
                        if name == own_import or name.startswith(own_import + "."):
                            continue
                        seen.add(name)
    return seen


def _read_declared_imports(test_file: Path) -> set[str]:
    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    for node in ast.walk(tree):
        # Plain `CROSS_PACKAGE_IMPORTS = [...]`.
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "CROSS_PACKAGE_IMPORTS":
                    if isinstance(node.value, ast.List):
                        return {
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant)
                            and isinstance(elt.value, str)
                        }
        # Annotated form `CROSS_PACKAGE_IMPORTS: list[str] = [...]`.
        elif isinstance(node, ast.AnnAssign):
            tgt = node.target
            if (
                isinstance(tgt, ast.Name)
                and tgt.id == "CROSS_PACKAGE_IMPORTS"
                and isinstance(node.value, ast.List)
            ):
                return {
                    elt.value
                    for elt in node.value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                }
    return set()


def check_ps139_umbrella_dep(repo: Path, violation_cls: type, out: list) -> None:
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        return
    # Exempt the umbrella package itself — `scitex[<extra>]` self-references
    # in scitex-python's own pyproject are how the umbrella aggregates peer
    # standalones, not "umbrella drag." Resolve from the registry because
    # the umbrella's clone dir is `scitex-python` (not `scitex`), so the
    # legacy `_own_import_name(repo) == "scitex"` check never matched.
    if _is_umbrella(repo):
        return
    findings = _scan_pyproject_for_umbrella(pyproject)
    for f in findings:
        out.append(
            violation_cls(
                "PS-139",
                str(pyproject),
                f"`scitex` (umbrella) listed at {f}; replace with peer "
                "standalone(s) to avoid the umbrella drag.",
            )
        )


def check_ps140_integration_gate(
    repo: Path, distribution: str, violation_cls: type, out: list
) -> None:
    # Umbrella's `src/scitex/` is intentionally a giant cross-import graph
    # (every shim re-exports a peer); a literal cross-package gate listing
    # all those imports would be self-defeating. Skip the umbrella outright.
    if _is_umbrella(repo):
        return
    own = _own_import_name(repo)
    src_root = repo / "src"
    if not src_root.exists():
        return
    expected = _collect_cross_package_imports(src_root, own)
    if not expected:
        return  # No cross-package imports — gate not required.
    test_file = repo / "tests" / "integration" / "test_cross_package_imports.py"
    if not test_file.exists():
        out.append(
            violation_cls(
                "PS-140",
                str(repo),
                (
                    f"source has {len(expected)} cross-package import(s) "
                    f"(e.g. {sorted(expected)[:3]}) but no "
                    "`tests/integration/test_cross_package_imports.py` "
                    "runtime gate."
                ),
            )
        )
        return
    declared = _read_declared_imports(test_file)
    missing = expected - declared
    extra = declared - expected
    if missing or extra:
        msg_parts = []
        if missing:
            msg_parts.append(
                f"missing from gate: {sorted(missing)[:5]}"
                + ("…" if len(missing) > 5 else "")
            )
        if extra:
            msg_parts.append(
                f"stale in gate: {sorted(extra)[:5]}" + ("…" if len(extra) > 5 else "")
            )
        out.append(
            violation_cls(
                "PS-140",
                str(test_file),
                "; ".join(msg_parts) + ". Regenerate the gate.",
            )
        )
