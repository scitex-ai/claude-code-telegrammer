#!/usr/bin/env python3
# Timestamp: 2026-04-28
# File: scitex_dev/_pyproject_lint.py

"""Lint a pyproject.toml against ecosystem invariants.

Codifies the regressions caught during the 2026-04-28 audit pass so an
agent doesn't have to rediscover them by re-running the full audit
script every time. Each rule has a stable id (`REL-5`, `REL-9`, …) keyed
to the §-numbers in `general/09_quality/02_checklist.md` so findings
join the same triage flow.

Rules
-----
- ``REL-5_implicit_deps`` — every ecosystem package imported anywhere
  under ``src/<pkg>/`` must appear in
  ``[project].dependencies``. Caught the 2026-04-28 class-action where
  6 packages broke on PyPI by importing ``scitex_config._ecosystem``
  without declaring ``scitex-config``.
- ``REL-9_skill_bundling`` — if ``src/<pkg>/_skills/`` exists, the build
  must (a) include ``_skills/**/*.md`` in package-data and (b) register
  the ``scitex_dev.skills`` entry-point. Caught packages whose SKILL.md
  was on disk but never shipped on PyPI.
- ``REL-10_duplicate_table`` — TOML 1.0 forbids declaring the same
  table twice; setuptools is silent about it but tomllib raises. Caught
  scitex-resource and scitex-capture this session.
- ``REL-11_invalid_pep639_license`` — `license = "AGPL-3.0-only"` is the
  ecosystem standard. Caught packages still using
  `license = {text = "..."}` (deprecated PEP 621 form).
- ``REL-21_dirty_release_state`` — pyproject version, latest git tag, and
  PyPI latest must agree (within drift tolerance). Caught the
  scitex-stats / scitex-hub / scitex-orochi tag-vs-PyPI drift.

Each check returns a list of ``LintFinding`` records. The CLI maps them
to ``scitex-dev quality lint-pyproject [--fix] [--strict]``.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Map import_name → pip name. Used by REL-5 to recognise an import as
# "this is an ecosystem package".
ECOSYSTEM_IMPORTS_TO_DIST: dict[str, str] = {
    "scitex_config": "scitex-config",
    "scitex": "scitex",  # the umbrella distribution
    "scitex_io": "scitex-io",
    "scitex_dev": "scitex-dev",
    "scitex_logging": "scitex-logging",
    "scitex_path": "scitex-path",
    "scitex_types": "scitex-types",
    "scitex_str": "scitex-str",
    "scitex_dict": "scitex-dict",
    "scitex_dt": "scitex-datetime",
    "scitex_datetime": "scitex-datetime",
    "scitex_decorators": "scitex-decorators",
    "scitex_repro": "scitex-repro",
    "scitex_compat": "scitex-compat",
    "scitex_session": "scitex-session",
    "scitex_context": "scitex-context",
    "scitex_os": "scitex-os",
    "scitex_sh": "scitex-sh",
    "scitex_git": "scitex-git",
    "scitex_introspect": "scitex-introspect",
    "scitex_stats": "scitex-stats",
    "scitex_pd": "scitex-pd",
    "scitex_dsp": "scitex-dsp",
    "scitex_nn": "scitex-nn",
    "scitex_linalg": "scitex-linalg",
    "scitex_cv": "scitex-cv",
    "scitex_audio": "scitex-audio",
    "scitex_capture": "scitex-capture",
    "scitex_db": "scitex-db",
    "scitex_dataset": "scitex-dataset",
    "scitex_scholar": "scitex-scholar",
    "scitex_seizure_metrics": "scitex-seizure-metrics",
    "scitex_writer": "scitex-writer",
    "scitex_msword": "scitex-msword",
    "scitex_tex": "scitex-tex",
    "scitex_web": "scitex-web",
    "scitex_security": "scitex-security",
    "scitex_resource": "scitex-resource",
    "scitex_orochi": "scitex-orochi",
    "scitex_events": "scitex-events",
    "scitex_hpc": "scitex-hpc",
    "scitex_clew": "scitex-clew",
    "scitex_hub": "scitex-hub",
    "scitex_browser": "scitex-browser",
    "scitex_app": "scitex-app",
    "scitex_ui": "scitex-ui",
    "scitex_container": "scitex-container",
    "scitex_ssh": "scitex-ssh",
    "scitex_agent_container": "scitex-agent-container",
    "scitex_template": "scitex-template",
    "scitex_audit": "scitex-audit",
    "scitex_math": "scitex-math",
    "scitex_repl": "scitex-repl",
    "scitex_etc": "scitex-etc",
    "scitex_gists": "scitex-gists",
    "scitex_parallel": "scitex-parallel",
    "scitex_plt": "scitex-plt",
    "scitex_notification": "scitex-notification",
    "scitex_benchmark": "scitex-benchmark",
    "scitex_bridge": "scitex-bridge",
    "figrecipe": "figrecipe",
    "socialia": "socialia",
}


@dataclass
class LintFinding:
    rule: str
    severity: str  # CRITICAL / HIGH / MEDIUM / LOW
    message: str
    detail: str = ""
    fix_hint: str = ""

    def render(self) -> str:
        out = f"[{self.severity:8s}] {self.rule}: {self.message}"
        if self.detail:
            out += f"\n    {self.detail}"
        if self.fix_hint:
            out += f"\n    fix: {self.fix_hint}"
        return out


@dataclass
class LintReport:
    package: str
    pyproject: Path
    findings: list[LintFinding] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "CRITICAL" for f in self.findings)

    @property
    def has_high(self) -> bool:
        return any(f.severity in ("CRITICAL", "HIGH") for f in self.findings)


def _load_pyproject(path: Path) -> dict[str, Any] | None:
    """Parse pyproject.toml; return None on parse error (caller flags it).

    tomllib is stdlib on 3.11+; fall back to tomli on 3.10. CI runs the
    matrix on 3.10 / 3.11 / 3.12 / 3.13, so the import dance matters.
    """
    try:
        try:
            import tomllib  # type: ignore[import-not-found]
        except ImportError:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except Exception:
        return None


def _src_dir(repo: Path, import_name: str) -> Path:
    return repo / "src" / import_name


def _scan_imports(src_dir: Path) -> set[str]:
    """Top-level module names UNCONDITIONALLY imported under src_dir.

    AST-based so we can distinguish optional imports (wrapped in
    ``try: import x; except ImportError``) from hard ones. Optional
    imports legitimately don't require a declared dep — they fall back
    to a stub when the package is missing — and the lint must NOT flag
    them. Hard imports (anywhere outside a try-block, including inside
    function bodies) are flagged.

    Returns the set of *top-level module roots* (e.g. `scitex_config`,
    not `scitex_config._ecosystem`). False negatives via
    ``importlib.import_module(...)`` are accepted; document in the rule.
    """
    import ast

    if not src_dir.is_dir():
        return set()

    out: set[str] = set()
    for py in src_dir.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError:
            continue

        class V(ast.NodeVisitor):
            def __init__(self):
                self.guard_depth = 0

            def visit_Try(self, node: ast.Try):  # noqa: N802
                # Only the body of a try-block counts as guarded; the
                # except/finally blocks shouldn't grant immunity to
                # imports written there (rare but real).
                self.guard_depth += 1
                for stmt in node.body:
                    self.visit(stmt)
                self.guard_depth -= 1
                for handler in node.handlers:
                    for stmt in handler.body:
                        self.visit(stmt)
                for stmt in node.orelse:
                    self.visit(stmt)
                for stmt in node.finalbody:
                    self.visit(stmt)

            def visit_If(self, node: ast.If):  # noqa: N802
                # Imports inside any of these conditional branches don't run
                # at module import time, so they're not runtime hard deps:
                #   - if TYPE_CHECKING:           — typing-only
                #   - if False:                   — disabled branch
                #   - if __name__ == "__main__":  — script-only entry-point
                test = node.test
                is_type_checking = (
                    isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
                ) or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
                is_constant_false = (
                    isinstance(test, ast.Constant) and test.value is False
                )
                # `if __name__ == "__main__":` and `if "__main__" == __name__:`
                is_main_guard = (
                    isinstance(test, ast.Compare)
                    and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.Eq)
                    and (
                        (
                            isinstance(test.left, ast.Name)
                            and test.left.id == "__name__"
                            and isinstance(test.comparators[0], ast.Constant)
                            and test.comparators[0].value == "__main__"
                        )
                        or (
                            isinstance(test.comparators[0], ast.Name)
                            and test.comparators[0].id == "__name__"
                            and isinstance(test.left, ast.Constant)
                            and test.left.value == "__main__"
                        )
                    )
                )
                guarded = is_type_checking or is_constant_false or is_main_guard
                if guarded:
                    self.guard_depth += 1
                for stmt in node.body:
                    self.visit(stmt)
                if guarded:
                    self.guard_depth -= 1
                for stmt in node.orelse:
                    self.visit(stmt)

            def _add(self, name: str | None):
                if name and self.guard_depth == 0:
                    out.add(name.split(".")[0])

            def visit_Import(self, node: ast.Import):  # noqa: N802
                for alias in node.names:
                    self._add(alias.name)
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
                if node.module:
                    self._add(node.module)
                self.generic_visit(node)

        V().visit(tree)
    return out


def _parse_req(spec: str):
    """PEP 508 parse; returns Requirement or None on malformed input.

    Centralised so every rule that walks dependency strings handles
    extras, markers, and version specifiers identically. Falls back to
    the legacy regex split only when packaging.Requirement raises —
    keeps REL-5 working on packages that ship deliberately-funky strings
    (e.g. relative paths) we'd rather flag elsewhere.
    """
    try:
        from packaging.requirements import InvalidRequirement, Requirement
    except ImportError:  # pragma: no cover — packaging is a setuptools dep
        return None
    try:
        return Requirement(spec)
    except InvalidRequirement:
        return None


def _declared_runtime_deps(data: dict[str, Any]) -> set[str]:
    raw = (data.get("project") or {}).get("dependencies") or []
    result = set()
    for d in raw:
        req = _parse_req(d)
        if req is not None:
            result.add(req.name)
            continue
        # Fallback: legacy regex split for malformed specs.
        name = re.split(r"[\[<>=!~ ;]", d, maxsplit=1)[0].strip()
        if name:
            result.add(name)
    return result


def _iter_dep_specs(data: dict[str, Any]):
    """Yield (group, spec_string) for every declared dep + optional dep.

    `group` is "dependencies" for runtime deps or the extra name (e.g.
    "dev", "cli") for optional deps. Used by REL-12_min_version_pin so a
    single walker covers both surfaces.
    """
    project = data.get("project") or {}
    for spec in project.get("dependencies") or []:
        yield "dependencies", spec
    for extra, specs in (project.get("optional-dependencies") or {}).items():
        for spec in specs or []:
            yield f"optional-dependencies.{extra}", spec


def check_min_version_pin(
    pyproject_data: dict[str, Any],
) -> list[LintFinding]:
    self_name = (pyproject_data.get("project") or {}).get("name") or ""
    """Rule REL-12 — every declared dep must carry a `>=` (or `~=`) lower bound.

    Bare ``"pkg"`` accepts any historic version (including pre-1.0
    breakage); upper-only pins like ``"pkg<2"`` likewise let stale
    wheels satisfy the spec. Allow ``>=`` (the canonical SciTeX choice)
    and ``~=`` (compatible release, equivalent lower bound). Exact ``==``
    pins are flagged separately by the release-alignment rule and pass
    here so a deliberate freeze isn't double-counted.

    Handles extras and environment markers correctly via
    ``packaging.requirements.Requirement``: e.g. ``pkg[extra]>=1.0;
    python_version >= "3.10"`` parses, the extras list is preserved,
    and the marker is ignored for the pin check.
    """
    findings: list[LintFinding] = []
    for group, spec in _iter_dep_specs(pyproject_data):
        req = _parse_req(spec)
        if req is None:
            findings.append(
                LintFinding(
                    rule="REL-12_min_version_pin",
                    severity="HIGH",
                    message=f"[{group}] `{spec}`: not a valid PEP 508 spec",
                    detail="packaging.requirements.Requirement could not parse",
                    fix_hint="quote env-marker correctly, or use canonical `pkg>=X.Y.Z` form",
                )
            )
            continue
        if req.name == self_name:
            continue  # self-referential extra (e.g. `pkg[cli]` in `[all]`)
        ops = {s.operator for s in req.specifier}
        if ops & {">=", "~=", "=="}:
            continue  # has a usable lower bound (or deliberate ==)
        # Surviving cases: empty specifier, only `<`/`!=`/`>`/`<=`.
        extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
        findings.append(
            LintFinding(
                rule="REL-12_min_version_pin",
                severity="HIGH",
                message=(
                    f"[{group}] `{req.name}{extras}`: missing `>=` lower bound "
                    f"(spec: `{spec}`)"
                ),
                detail=(
                    "without a lower bound, pip can resolve a years-old "
                    "incompatible wheel that import-fails at runtime"
                ),
                fix_hint=f'replace with `"{req.name}{extras}>=<min>"` '
                "(pick the oldest version you actually test against)",
            )
        )
    return findings


def check_implicit_deps(
    repo: Path, pyproject_data: dict[str, Any], package_name: str
) -> list[LintFinding]:
    """Rule REL-5 — codifies the 2026-04-28 class-action."""
    findings: list[LintFinding] = []
    import_name = package_name.replace("-", "_")
    imports = _scan_imports(_src_dir(repo, import_name))
    declared = _declared_runtime_deps(pyproject_data)
    for mod in sorted(imports):
        dist = ECOSYSTEM_IMPORTS_TO_DIST.get(mod)
        if not dist or dist == package_name:
            continue
        if dist in declared:
            continue
        findings.append(
            LintFinding(
                rule="REL-5_implicit_deps",
                severity="CRITICAL",
                message=f"src imports `{mod}` but pyproject does not declare `{dist}`",
                detail="fresh-venv install will fail at import time with ModuleNotFoundError",
                fix_hint=f'add `"{dist}>=<min>"` to [project].dependencies',
            )
        )
    return findings


def _has_entry_point(data: dict[str, Any], group: str, key: str) -> bool:
    eps = (data.get("project") or {}).get("entry-points") or {}
    return key in (eps.get(group) or {})


def _skill_bundled(data: dict[str, Any], import_name: str) -> bool:
    """True iff the build will ship ``_skills/**/*.md`` for this import name.

    Backend-aware:

    - **setuptools** (``setuptools.build_meta``) needs explicit
      ``[tool.setuptools.package-data]`` because ``packages.find`` only
      keeps Python files. No glob → not bundled.
    - **hatchling** ships every file inside the package directory by
      default. We only flag when an explicit ``exclude`` drops
      ``_skills/`` or when an explicit ``include`` list omits it.
    - **unknown backend**: be conservative; assume bundled (avoid false
      positives — we'd rather miss a real bug than warn on every
      package).
    """
    tool = data.get("tool") or {}
    build_backend = (data.get("build-system") or {}).get("build-backend", "")

    if "setuptools" in build_backend:
        pkg_data = (tool.get("setuptools") or {}).get("package-data") or {}
        globs = pkg_data.get(import_name) or pkg_data.get("*") or []
        return any("_skills" in g for g in globs)

    if "hatch" in build_backend:
        wheel = (
            ((tool.get("hatch") or {}).get("build") or {}).get("targets") or {}
        ).get("wheel") or {}
        if any("_skills" in pat for pat in (wheel.get("exclude") or [])):
            return False
        if any("_skills" in src for src in (wheel.get("force-include") or {})):
            return True
        includes = wheel.get("include")
        if includes is not None:
            return any("_skills" in inc for inc in includes)
        # Default hatchling: everything in the package dir is shipped.
        return True

    # Unknown backend — don't make noise.
    return True


def check_skill_bundling(
    repo: Path, pyproject_data: dict[str, Any], package_name: str
) -> list[LintFinding]:
    """Rule REL-9 — _skills/ on disk implies bundling + entry-point."""
    findings: list[LintFinding] = []
    import_name = package_name.replace("-", "_")
    skills_dir = _src_dir(repo, import_name) / "_skills"
    if not skills_dir.is_dir():
        return findings
    if not _skill_bundled(pyproject_data, import_name):
        findings.append(
            LintFinding(
                rule="REL-9_skill_bundling",
                severity="HIGH",
                message="_skills/ on disk but package-data does not ship `_skills/**/*.md`",
                detail=f"PyPI users won't see {skills_dir.name}/<pkg>/SKILL.md",
                fix_hint=f'[tool.setuptools.package-data]\n    {import_name} = ["_skills/**/*.md"]',
            )
        )
    if not _has_entry_point(pyproject_data, "scitex_dev.skills", package_name):
        findings.append(
            LintFinding(
                rule="REL-9_skill_bundling",
                severity="HIGH",
                message="_skills/ on disk but no `scitex_dev.skills` entry-point",
                detail="agents won't discover the package via importlib.metadata",
                fix_hint=f'[project.entry-points."scitex_dev.skills"]\n    {package_name} = "{import_name}"',
            )
        )
    return findings


_DUP_TABLE_RE = re.compile(r"^\s*\[(?:tool|project)[\w.\-]*\]", re.MULTILINE)


def check_duplicate_tables(pyproject: Path) -> list[LintFinding]:
    """Rule REL-10 — surface 'cannot declare twice' errors before they bite."""
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return []
    seen: dict[str, int] = {}
    findings: list[LintFinding] = []
    for m in _DUP_TABLE_RE.finditer(text):
        header = m.group(0).strip()
        seen[header] = seen.get(header, 0) + 1
    for header, count in seen.items():
        if count > 1:
            findings.append(
                LintFinding(
                    rule="REL-10_duplicate_table",
                    severity="HIGH",
                    message=f"TOML table declared {count}× — {header}",
                    detail="setuptools accepts only the LAST declaration; tomllib refuses outright",
                    fix_hint="merge keys into a single table",
                )
            )
    return findings


def check_version_drift(
    repo: Path, pyproject_data: dict[str, Any], package_name: str
) -> list[LintFinding]:
    """Rule REL-31 — `__version__` literal in src/__init__.py must match pyproject.

    Two acceptable patterns:

    - Dynamic via ``importlib.metadata`` (preferred — no drift possible).
    - Literal string. If literal, MUST equal ``[project].version``.

    Caught the scitex-stats v0.2.8 vs pyproject 0.2.11 vs PyPI 0.2.10
    drift earlier this session.
    """
    findings: list[LintFinding] = []
    py_ver = (pyproject_data.get("project") or {}).get("version")
    if not py_ver:
        return findings
    import_name = package_name.replace("-", "_")
    init_py = repo / "src" / import_name / "__init__.py"
    if not init_py.is_file():
        return findings
    try:
        text = init_py.read_text(encoding="utf-8")
    except OSError:
        return findings
    # Bail when version is sourced from importlib.metadata (dynamic, can't drift).
    if "importlib.metadata" in text and re.search(
        r"__version__\s*=\s*(?:[\w.]+\.)?(?:version|_v)\s*\(",
        text,
    ):
        return findings
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        return findings
    src_ver = m.group(1)
    if src_ver != py_ver:
        findings.append(
            LintFinding(
                rule="REL-31_version_drift",
                severity="MEDIUM",
                message=f"__init__.py __version__ = {src_ver!r} ≠ pyproject {py_ver!r}",
                detail=f"{init_py.relative_to(repo)}",
                fix_hint=(
                    "either update the literal, or switch to dynamic resolution: "
                    "from importlib.metadata import version as _v; "
                    f'__version__ = _v("{package_name}")'
                ),
            )
        )
    return findings


def check_readme_interfaces_callout(
    repo: Path, package_name: str = ""
) -> list[LintFinding]:  # noqa: ARG001
    """Rule REL-41 — README must mirror SKILL.md's Interfaces callout.

    The convention (general/02_repo_04_quality.md, 06_skills_05) is that
    every package's README opens with a ``> **Interfaces:** ...`` line so
    consumers see the primary interface ratings without opening SKILL.md.

    LOW severity — cosmetic, but consistent ecosystem-wide signalling
    matters for agent discovery.
    """
    readme = repo / "README.md"
    if not readme.is_file():
        return []
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return []
    # Allow on first 60 lines (skip badges block).
    head = "\n".join(text.splitlines()[:80])
    if re.search(r"^>\s*\*\*Interfaces:\*\*", head, re.MULTILINE):
        return []
    # Skip very-short READMEs (placeholders).
    if len(text) < 500:
        return []
    return [
        LintFinding(
            rule="REL-41_readme_interfaces_callout",
            severity="LOW",
            message="README.md missing `> **Interfaces:**` callout",
            detail="convention from general/02_repo_04_quality.md §SciTeX-Specific README Rules",
            fix_hint="Add `> **Interfaces:** Python ⭐⭐⭐ · CLI ⭐ · MCP — · Skills ⭐⭐ · Hook — · HTTP —`",
        )
    ]


def check_license(pyproject_data: dict[str, Any]) -> list[LintFinding]:
    """Rule REL-11 — AGPL-3.0-only as PEP 639 SPDX expression."""
    proj = pyproject_data.get("project") or {}
    lic = proj.get("license")
    if isinstance(lic, str):
        if lic.strip() == "AGPL-3.0-only":
            return []
        return [
            LintFinding(
                rule="REL-11_invalid_pep639_license",
                severity="MEDIUM",
                message=f"license is `{lic!r}`, expected SPDX `AGPL-3.0-only`",
                fix_hint='license = "AGPL-3.0-only"',
            )
        ]
    if isinstance(lic, dict):
        return [
            LintFinding(
                rule="REL-11_invalid_pep639_license",
                severity="MEDIUM",
                message="license uses deprecated table form (PEP 621 pre-639)",
                detail=f"got {lic!r}",
                fix_hint='license = "AGPL-3.0-only"   # PEP 639 SPDX expression',
            )
        ]
    return [
        LintFinding(
            rule="REL-11_invalid_pep639_license",
            severity="LOW",
            message="no license field in [project]",
            fix_hint='license = "AGPL-3.0-only"',
        )
    ]


def check_internal_api_leak(repo: Path, package_name: str) -> list[LintFinding]:
    """Rule E5F2 — flag cross-package imports of private modules.

    Pattern that bites:
        from scitex_stats._utils import p2stars

    The umbrella ``scitex.stats`` shim re-exports the public API of
    ``scitex_stats``, but private modules (``_utils``, ``_internal``)
    are NOT part of the namespace contract and may break without
    notice. Worse, when a downstream installs only the standalone
    (``scitex-stats``) without the umbrella, ``scitex.stats._utils``
    is unimportable even though ``scitex_stats._utils`` works.

    Caught scitex-bridge on 2026-04-28 (used
    ``scitex.stats._utils.p2stars``; standalone CI broke).

    The fix is always the same: import directly from the standalone
    distribution instead — `scitex_stats._utils` (still private, but
    at least the import path is honest about coupling).

    Severity HIGH because cross-package private imports survive
    until the upstream's private layout changes; then they break in
    the wild without a deprecation cycle.
    """
    findings: list[LintFinding] = []
    # The umbrella package is allowed to use private paths under its own
    # namespace (alias-shim mechanics).
    if package_name == "scitex":
        return findings
    import_name = package_name.replace("-", "_")
    src = repo / "src" / import_name
    if not src.is_dir():
        return findings
    # Compatibility shims (figrecipe's _scitex_compat/, packages' own
    # _compat/_legacy/) intentionally bridge old umbrella paths.
    SKIP_SEGMENTS = ("_compat", "_scitex_compat", "_legacy", "compat_")
    import ast

    def _is_umbrella_private(module: str | None) -> bool:
        # scitex.X._private  ↔  scitex.X.Y._private  etc.
        if not module:
            return False
        parts = module.split(".")
        if parts[0] != "scitex":
            return False
        return any(p.startswith("_") for p in parts[1:])

    seen: set[tuple[str, str]] = set()
    for py in src.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        if any(seg in str(py) for seg in SKIP_SEGMENTS):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=str(py))
        except (OSError, SyntaxError):
            continue

        # Walk with try/except + TYPE_CHECKING + __main__ guard awareness so
        # `try: from scitex.io.bundle._x import Y; except ImportError: ...`
        # is NOT flagged — it's an explicit fallback path.
        class V(ast.NodeVisitor):
            def __init__(self):
                self.depth = 0

            def visit_Try(self, node: ast.Try):  # noqa: N802
                self.depth += 1
                for s in node.body:
                    self.visit(s)
                self.depth -= 1
                for h in node.handlers:
                    for s in h.body:
                        self.visit(s)
                for s in node.orelse:
                    self.visit(s)
                for s in node.finalbody:
                    self.visit(s)

            def visit_If(self, node: ast.If):  # noqa: N802
                t = node.test
                guarded = (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (
                    isinstance(t, ast.Compare)
                    and len(t.ops) == 1
                    and isinstance(t.ops[0], ast.Eq)
                    and (
                        isinstance(t.left, ast.Name)
                        and t.left.id == "__name__"
                        and isinstance(t.comparators[0], ast.Constant)
                        and t.comparators[0].value == "__main__"
                    )
                )
                if guarded:
                    self.depth += 1
                for s in node.body:
                    self.visit(s)
                if guarded:
                    self.depth -= 1
                for s in node.orelse:
                    self.visit(s)

            def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
                if self.depth > 0:
                    return
                if not _is_umbrella_private(node.module):
                    return
                line = f"from {node.module} import ..."
                key = (str(py.relative_to(repo)), line)
                if key in seen:
                    return
                seen.add(key)
                findings.append(
                    LintFinding(
                        rule="E5F2_internal_api_leak",
                        severity="HIGH",
                        message=f"reaches into umbrella's private namespace: `from {node.module} import ...`",
                        detail=f"{py.relative_to(repo)}:{node.lineno}",
                        fix_hint=(
                            "import the same symbol from the standalone "
                            "distribution (e.g. `scitex_stats._utils` instead "
                            "of `scitex.stats._utils`), or wrap with "
                            "`try: ... except ImportError:` if the umbrella is "
                            "an optional fallback"
                        ),
                    )
                )

        V().visit(tree)
    return findings


def check_orphan_license_classifier(
    pyproject_data: dict[str, Any],
) -> list[LintFinding]:
    """Rule E5C13 — PEP 639 SPDX + legacy License classifier are incompatible.

    setuptools 80+ raises ``InvalidConfigError`` when ``[project].license``
    is the SPDX expression form AND ``[project].classifiers`` still
    contains a ``License :: OSI Approved :: ...`` row. This breaks
    `pip install -e .` and `pip wheel`. Caught by socialia's CI on the
    pre-commit-build step on 2026-04-28.

    Fix: drop the classifier; the SPDX expression is now authoritative.
    """
    proj = pyproject_data.get("project") or {}
    lic = proj.get("license")
    classifiers = proj.get("classifiers") or []
    has_spdx = isinstance(lic, str) and lic.strip()
    has_legacy = any(
        isinstance(c, str) and c.startswith("License :: OSI Approved")
        for c in classifiers
    )
    if has_spdx and has_legacy:
        return [
            LintFinding(
                rule="E5C13_orphan_license_classifier",
                severity="HIGH",
                message="legacy `License :: OSI Approved :: ...` classifier present alongside SPDX expression",
                detail="setuptools 80+ refuses to build the package",
                fix_hint="remove the License classifier(s) from [project].classifiers",
            )
        ]
    return []


def _pypi_version(name: str) -> str | None:
    try:
        import urllib.request
        import json

        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/json", timeout=10
        ) as fh:
            data = json.load(fh)
        return data["info"]["version"]
    except Exception:
        return None


def _latest_tag(repo: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "tag", "--list", "v*"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    tags = [t.strip() for t in out.splitlines() if t.strip()]
    if not tags:
        return None

    def keyer(t: str) -> tuple:
        m = re.match(r"v(\d+)\.(\d+)\.(\d+)", t)
        if not m:
            return (0, 0, 0, t)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), t)

    return sorted(tags, key=keyer)[-1]


def _publish_trigger(repo: Path) -> str | None:
    """Return 'release', 'tags', or None.

    Detects whether the publish-pypi workflow fires on GH release publish
    or on git-tag push. Used by REL-21 to give a more actionable fix-hint
    and by E5L2 to flag the workflow-specific footgun.
    """
    wf = repo / ".github" / "workflows" / "publish-pypi.yml"
    if not wf.is_file():
        return None
    try:
        text = wf.read_text(encoding="utf-8")
    except OSError:
        return None
    if re.search(r"^\s*release:\s*$", text, re.MULTILINE):
        return "release"
    if re.search(r"^\s*tags:\s*$", text, re.MULTILINE):
        return "tags"
    return None


def check_release_alignment(
    repo: Path, pyproject_data: dict[str, Any], package_name: str
) -> list[LintFinding]:
    """Rule REL-21 — pyproject ↔ tag ↔ PyPI alignment.

    When pyproject is ahead of PyPI AND the publish workflow fires on
    ``release: published``, the fix-hint includes the
    ``gh release create`` step that operators routinely forget.
    """
    findings: list[LintFinding] = []
    py_ver = (pyproject_data.get("project") or {}).get("version")
    if not py_ver:
        return findings
    tag = _latest_tag(repo)
    pypi = _pypi_version(package_name)
    trigger = _publish_trigger(repo)
    if tag and tag.lstrip("v") != py_ver:
        if trigger == "release":
            hint = (
                f"git tag v{py_ver} && git push --tags && "
                f"gh release create v{py_ver} (workflow uses release:published)"
            )
        else:
            hint = f"git tag v{py_ver} && git push --tags"
        findings.append(
            LintFinding(
                rule="REL-21_dirty_release_state",
                severity="LOW",
                message=f"latest git tag `{tag}` ≠ pyproject version `{py_ver}`",
                fix_hint=hint,
            )
        )
    if pypi and pypi != py_ver:
        if trigger == "release":
            detail = (
                "release in flight, or tag pushed without `gh release create` "
                "(workflow uses release:published — tag-push alone won't publish)"
            )
        else:
            detail = "release in flight, or release stale"
        findings.append(
            LintFinding(
                rule="REL-21_dirty_release_state",
                severity="LOW",
                message=f"PyPI latest `{pypi}` ≠ pyproject version `{py_ver}`",
                detail=detail,
            )
        )
    return findings


def check_cla_workflow_exists(repo: Path) -> list[LintFinding]:
    """Rule REL-12 — every scitex-* repo must ship a CLA gate workflow.

    The canonical location is `.github/workflows/cla.yml`. See
    `_skills/general/01_ecosystem/07_license-and-cla.md` for the workflow
    template and the maintainer-allowlist convention.

    Missing → external contributors can't be gated; the project loses CLA
    coverage. Bot accounts and the maintainer should still be allowlisted
    in the workflow itself (`bot*,ywatanabe1989`).
    """
    cla_yml = repo / ".github" / "workflows" / "cla.yml"
    if not cla_yml.is_file():
        return [
            LintFinding(
                rule="REL-12_missing_cla_workflow",
                severity="MEDIUM",
                message=".github/workflows/cla.yml is missing",
                detail=(
                    "every scitex-* repo gates contributions via the CLA action; "
                    "see _skills/general/01_ecosystem/07_license-and-cla.md"
                ),
                fix_hint=(
                    "copy the workflow template from a sibling repo (e.g. scitex-io) "
                    "and ensure `allowlist: bot*,ywatanabe1989`"
                ),
            )
        ]
    return []


def check_cla_signatures_shape(repo: Path) -> list[LintFinding]:
    """Rule E5C14 — `signatures/cla.json` on `cla-signatures` branch must be
    a JSON object with key `signedContributors`, not a bare array.

    A bare-array file (`[]`) makes ``contributor-assistant/github-action@v2.6.1``
    crash on startup with ``Cannot read properties of undefined (reading 'some')``.
    Hit on scitex-dev and scitex-audio in 2026-04.

    Uses `git show cla-signatures:signatures/cla.json` to fetch the file
    content without checking out the branch. Skipped (no finding) if the
    branch doesn't exist locally — that's a healthy "fresh repo" state where
    the action will bootstrap correctly on first PR.
    """
    import json as _json
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", "cla-signatures:signatures/cla.json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, FileNotFoundError):
        return []
    if result.returncode != 0:
        # branch or file absent — fresh repo or never-bootstrapped state, OK.
        return []
    raw = result.stdout
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError:
        return [
            LintFinding(
                rule="E5C14_malformed_cla_signatures",
                severity="HIGH",
                message="cla-signatures:signatures/cla.json is not valid JSON",
                detail=raw[:200],
                fix_hint='replace with `{"signedContributors": []}`',
            )
        ]
    if not isinstance(parsed, dict) or "signedContributors" not in parsed:
        return [
            LintFinding(
                rule="E5C14_malformed_cla_signatures",
                severity="HIGH",
                message=(
                    "cla-signatures:signatures/cla.json is not an object with "
                    "key `signedContributors` (action will crash on startup)"
                ),
                detail=f"shape: {type(parsed).__name__}; content: {raw[:120]}",
                fix_hint=(
                    'PUT `{"signedContributors": []}` to that path on '
                    "the cla-signatures branch — see "
                    "_skills/general/01_ecosystem/07_license-and-cla.md repair recipe"
                ),
            )
        ]
    return []


def check_umbrella_ssot_drift(
    repo: Path,
    pyproject_data: dict[str, Any],
    package_name: str,
) -> list[LintFinding]:
    """Rule REL-50 — umbrella pyproject must match the ECOSYSTEM resolver.

    Fires only when auditing the umbrella ``scitex`` package. Compares
    ``[project.optional-dependencies].all`` against
    :func:`scitex_dev._ecosystem._umbrella.expected_all_extras` (with
    :data:`HAND_CURATED_EXTRAS` filtered out on both sides) and emits
    HIGH-severity findings for each missing or extra ``scitex[<extra>]``
    self-reference.

    The lazy_attrs / EXTERNAL_REEXPORTS surfaces aren't covered here —
    they live in ``src/scitex/__init__.py`` and ``re_export.py``
    respectively, which need a Python-source-level audit; that lands as
    a separate rule alongside the marker-based ``--write`` extension.

    Caught the 2026-06-07 drift batch: 7 ECOSYSTEM peers
    (core/hpc/math/newb/seizure-metrics/ssh/todo) were live but missing
    from the umbrella's ``[all]`` aggregator; the archived
    ``scitex-bridge`` / ``scitex-linter`` were still present.

    Non-umbrella packages: returns ``[]`` (no-op) — drift only makes
    sense relative to the registry-driven aggregator.
    """
    if package_name != "scitex":
        return []
    try:
        from .._umbrella import HAND_CURATED_EXTRAS, expected_all_extras
    except Exception as e:  # noqa: BLE001
        # scitex-dev not importable from its own audit path → degrade
        # gracefully (the test_audit pipeline runs against installed pkg
        # form; we never want the importer to crash the auditor).
        return [
            LintFinding(
                rule="REL-50_umbrella_ssot_drift",
                severity="LOW",
                message=f"could not import _umbrella resolver: {e}",
                detail="REL-50 check skipped",
            )
        ]
    opt = (pyproject_data.get("project") or {}).get("optional-dependencies") or {}
    actual = set()
    for spec in opt.get("all") or []:
        m = re.match(r"^\s*scitex\[([\w.-]+)\]", spec)
        if m and m.group(1) not in HAND_CURATED_EXTRAS:
            actual.add(f"scitex[{m.group(1)}]")
    expected = set(expected_all_extras())
    findings: list[LintFinding] = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    for spec in missing:
        findings.append(
            LintFinding(
                rule="REL-50_umbrella_ssot_drift",
                severity="HIGH",
                message=f"[all] missing `{spec}` (registry-derived)",
                detail="umbrella's [all] aggregator is out of sync with ECOSYSTEM",
                fix_hint=(
                    "run `scitex-dev ecosystem audit-umbrella --write` "
                    "OR manually add the entry to [project.optional-dependencies].all"
                ),
            )
        )
    for spec in extra:
        findings.append(
            LintFinding(
                rule="REL-50_umbrella_ssot_drift",
                severity="HIGH",
                message=f"[all] has `{spec}` but ECOSYSTEM does not (or it's archived)",
                detail="archived peers should be removed from the umbrella's [all]",
                fix_hint=(
                    "run `scitex-dev ecosystem audit-umbrella --write` "
                    "OR manually drop the entry from [project.optional-dependencies].all"
                ),
            )
        )
    _ = repo  # unused — kept for signature parity with siblings
    return findings


def lint_pyproject(repo: Path, package_name: str | None = None) -> LintReport:
    """Run every rule against `repo/pyproject.toml`. Used by CLI + tests."""
    pyproject = repo / "pyproject.toml"
    rep = LintReport(package=package_name or repo.name, pyproject=pyproject)
    if not pyproject.is_file():
        rep.findings.append(
            LintFinding(
                rule="E5C1_missing_pyproject",
                severity="HIGH",
                message="pyproject.toml not found at repo root",
            )
        )
        return rep
    rep.findings.extend(check_duplicate_tables(pyproject))
    data = _load_pyproject(pyproject)
    if data is None:
        rep.findings.append(
            LintFinding(
                rule="REL-10_duplicate_table",
                severity="HIGH",
                message="pyproject.toml fails to parse with tomllib",
                detail="usually a duplicate table; see REL-10 finding above for the offender",
            )
        )
        return rep
    pkg = package_name or (data.get("project") or {}).get("name")
    rep.package = pkg or repo.name
    rep.findings.extend(check_implicit_deps(repo, data, rep.package))
    rep.findings.extend(check_min_version_pin(data))
    rep.findings.extend(check_skill_bundling(repo, data, rep.package))
    rep.findings.extend(check_internal_api_leak(repo, rep.package))
    rep.findings.extend(check_license(data))
    rep.findings.extend(check_orphan_license_classifier(data))
    rep.findings.extend(check_release_alignment(repo, data, rep.package))
    rep.findings.extend(check_version_drift(repo, data, rep.package))
    rep.findings.extend(check_readme_interfaces_callout(repo, rep.package))
    rep.findings.extend(check_cla_workflow_exists(repo))
    rep.findings.extend(check_cla_signatures_shape(repo))
    rep.findings.extend(check_umbrella_ssot_drift(repo, data, rep.package))
    return rep


__all__ = [
    "ECOSYSTEM_IMPORTS_TO_DIST",
    "LintFinding",
    "LintReport",
    "lint_pyproject",
    "check_implicit_deps",
    "check_skill_bundling",
    "check_version_drift",
    "check_readme_interfaces_callout",
    "check_duplicate_tables",
    "check_license",
    "check_release_alignment",
    "check_cla_workflow_exists",
    "check_cla_signatures_shape",
    "check_umbrella_ssot_drift",
]
