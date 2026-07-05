"""Static auditor for SciTeX `_skills/<pip-name>/` directories — engine + rules.

Rules cover the automatable items from
`scitex-python/src/scitex/_skills/general/03_interface/04_skills/12_quality-checklist.md`.

Numbering: `SK<§><idx>` (e.g. SK-101 = §1 rule 01). Mirrors the `PA<n>` /
`M<n>` rule-numbering used by the sibling `_cli_audit_api` and
`_cli_audit/_mcp_audit` modules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import click

from .._emit import emit as _emit
from ...._ecosystem._skills import skills_audit_core as _core
from . import _audit_v2 as _v2


@dataclass(frozen=True)
class Rule:
    code: str
    section: str
    message: str
    slug: str = ""  # short kebab-case human-readable name


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # §1 Directory structure
        Rule("SK-101", "§1", "no `_skills/` directory found in package source"),
        Rule("SK-102", "§1", "missing `_skills/<pip-name>/SKILL.md` index file"),
        Rule(
            "SK-103",
            "§1",
            "forbidden subdirectory inside `_skills/` (`legacy/` / `.old/`)",
        ),
        Rule(
            "SK-104",
            "§1",
            "duplicate index file (e.g. `SKILL_INDEX.md`); only one `SKILL.md` per dir",
        ),
        Rule(
            "SK-105",
            "§1",
            "`MANIFEST.md` is forbidden — `SKILL.md` is the single canonical "
            "index of every skill tree. Distribution / update mechanics belong "
            "in a numbered leaf (e.g. `99_distribution.md`) or in the package "
            "README, not in a sibling top-level file that duplicates SKILL.md's "
            "intent.",
        ),
        # §2 File naming & ordering
        Rule(
            "SK-201",
            "§2",
            "leaf `.md` lacks a 2-digit zero-padded numeric prefix (e.g. `01_`)",
        ),
        Rule("SK-202", "§2", "`SKILL.md` must not carry a numeric prefix"),
        Rule("SK-203", "§2", "filename is not kebab-case after the numeric prefix"),
        # §2a Frontmatter must be first bytes (no header/footer)
        Rule(
            "SK-210",
            "§2a",
            "file starts with HTML-comment banner (e.g. `<!-- --- Timestamp: ... --- -->`); "
            "frontmatter must be at byte 0",
        ),
        Rule(
            "SK-211",
            "§2a",
            "file ends with `<!-- EOF -->` or similar trailing marker",
        ),
        # §3 SKILL.md as index only
        Rule("SK-301", "§3", "`SKILL.md` exceeds the size budget (~120 lines / ~6 KB)"),
        Rule(
            "SK-302",
            "§3",
            "sibling leaf `.md` is not linked from `SKILL.md` (orphan or dead link)",
        ),
        # §4 Leaf file size — no monolith
        Rule(
            "SK-401", "§4", "leaf `.md` exceeds the size budget (~10 KB / ~200 lines)"
        ),
        # §FM Frontmatter required fields (rule SK-210 is separate — about position)
        Rule(
            "SK-701", "§FM", "file is missing YAML frontmatter (`---` block at line 1)"
        ),
        Rule("SK-702", "§FM", "frontmatter is missing required field `name`"),
        Rule("SK-703", "§FM", "frontmatter is missing required field `description`"),
        Rule("SK-704", "§FM", "frontmatter is missing recommended field `tags`"),
        # §6 No contradictions with general/
        Rule(
            "SK-601",
            "§6",
            "skill text uses `import scitex as stx`; ecosystem rule is bare "
            "`import scitex`",
        ),
    ]
}
# Merge spec-v2 rules (SK-105–SK-111, SK-705–SK-711) — kept in `_audit_v2.py`
# to preserve `_audit.py`'s size budget.
for _r in _v2.V2_RULES.values():
    RULES[_r.code] = Rule(_r.code, _r.section, _r.message)


# Backfill kebab-case slugs across the SK corpus. Surfaced inline in audit
# output as `[SKxxx §X slug] …`. Missing entries fall back to the bare form;
# new rules SHOULD include `slug=...` from definition.
_SLUGS: dict[str, str] = {
    "SK-101": "skills-dir-missing",
    "SK-102": "skill-md-missing",
    "SK-103": "forbidden-skills-subdir",
    "SK-104": "duplicate-skill-index",
    # SK-105 in v2 means "missing 01_installation.md" (overrides the legacy
    # "MANIFEST.md forbidden" rule via the V2 merge above).
    "SK-105": "leaf-installation-missing",
    "SK-106": "leaf-quick-start-missing",
    "SK-107": "leaf-python-api-missing",
    "SK-108": "leaf-cli-reference-missing",
    "SK-109": "leaf-mcp-tools-missing",
    "SK-110": "leaf-http-api-missing",
    "SK-111": "leaf-skill-table-missing",
    "SK-705": "frontmatter-name-mismatch",
    "SK-706": "frontmatter-description-too-short",
    "SK-707": "frontmatter-tags-empty",
    "SK-708": "frontmatter-tags-not-kebab",
    "SK-709": "frontmatter-tags-pkg-prefix-missing",
    "SK-710": "frontmatter-tags-canonical-mismatch",
    "SK-711": "frontmatter-extra-fields",
    "SK-201": "leaf-missing-numeric-prefix",
    "SK-202": "skill-md-with-numeric-prefix",
    "SK-203": "filename-not-kebab-case",
    "SK-210": "frontmatter-not-at-start",
    "SK-211": "trailing-eof-marker",
    "SK-301": "skill-md-over-budget",
    "SK-302": "leaf-not-linked-from-skill-md",
    "SK-401": "leaf-over-budget",
    "SK-601": "scitex-as-stx-import",
    "SK-701": "frontmatter-missing",
    "SK-702": "frontmatter-name-missing",
    "SK-703": "frontmatter-description-missing",
    "SK-704": "frontmatter-tags-missing",
}
RULES = {
    code: (
        Rule(rule.code, rule.section, rule.message, _SLUGS.get(code, ""))
        if not rule.slug and code in _SLUGS
        else rule
    )
    for code, rule in RULES.items()
}


@dataclass
class Violation:
    rule: str
    where: str
    detail: str

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        slug = f" {r.slug}" if r and r.slug else ""
        return f"  [{self.rule} {section}{slug}] {self.where}: {self.detail}"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _import_name(distribution: str) -> str:
    """Mirror `_cli_audit_api`: dist -> import name (`-` -> `_`)."""
    return distribution.replace("-", "_")


def _locate_skills_dir(distribution: str) -> Path | None:
    """Return `<pkg>/_skills/<pip-name>/` if it exists, else None.

    Resolution order (each step proceeds to the next on miss, so a package
    that is *neither* pip-installed *nor* registered still returns None and
    the caller can fire SK-101 confidently):

    1. **Installed package.** Import via ``importlib.util.find_spec``; walk
       each search location to ``_skills/<distribution>/`` and fall back
       to flat ``_skills/`` for legacy layouts.
    2. **On-disk source tree (registry fallback).** When the package is
       NOT installed in the auditor's venv (e.g. running ``audit-skills``
       against an ecosystem peer the developer has cloned locally but not
       ``pip install``-ed), look up ``distribution`` in
       ``scitex_dev._ecosystem._registry.ECOSYSTEM`` and probe
       ``<local_path>/src/<import_name>/_skills/<distribution>/`` (sub-skill
       layout) then ``<local_path>/src/<import_name>/_skills/`` (flat).

    Without step 2 every non-installed peer fires SK-101 even when its
    on-disk skill tree is perfectly valid — a phantom-violation class the
    journal kept tripping over (registry SK-* tallies on packages like
    ``scitex-events`` / ``scitex-etc`` were entirely install-availability
    artefacts of step 1, not real layout debt).

    Fallback to flat ``_skills/`` is preserved in both code paths so the
    caller can still distinguish SK-101 (no skills tree at all) from
    SK-102 (skills tree exists but missing the canonical sub-pip-name
    directory).
    """
    import importlib.util

    import_name = _import_name(distribution)

    # 1. Installed package.
    spec = importlib.util.find_spec(import_name)
    if spec is not None and spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
            candidate = Path(loc) / "_skills" / distribution
            if candidate.is_dir():
                return candidate
            flat = Path(loc) / "_skills"
            if flat.is_dir():
                return flat

    # 2. On-disk source tree via the ecosystem registry. Defensive — a
    # stale / partial registry import must never break the per-package
    # audit; fall through to None and let SK-101 fire as before.
    try:
        from ...._ecosystem._registry import ECOSYSTEM
    except Exception:  # pragma: no cover — defensive
        return None
    info = ECOSYSTEM.get(distribution) or {}
    local_path = info.get("local_path")
    if not local_path:
        return None
    try:
        root = Path(local_path).expanduser()
    except (RuntimeError, OSError):  # pragma: no cover — defensive
        return None
    if not root.is_dir():
        return None
    src_pkg = root / "src" / import_name
    candidate = src_pkg / "_skills" / distribution
    if candidate.is_dir():
        return candidate
    flat = src_pkg / "_skills"
    if flat.is_dir():
        return flat
    return None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FRONTMATTER_KEY_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*):", re.MULTILINE)
_HTML_HEADER_RE = re.compile(r"\A<!-- ---")
_HTML_FOOTER_RE = re.compile(r"<!-- EOF -->\s*\Z")
_MAX_SKILL_MD_BYTES = 6 * 1024
_MAX_SKILL_MD_LINES = 120
_MAX_LEAF_BYTES = 10 * 1024
_MAX_LEAF_LINES = 200
_NAMING_EXEMPT = {"TODO.md", "DRIFT_REPORT.md"}


def _check_layout(
    skills_dir: Path | None,
    distribution: str,
    out: list[Violation],
) -> Path | None:
    """SK-101 / SK-102 / SK-103 / SK-104 — directory structure.

    Returns the canonical sub-skill dir (`_skills/<pip-name>/`) for downstream
    checks, or None if SK-101/SK-102 made further checks impossible.
    """
    if skills_dir is None:
        out.append(Violation("SK-101", distribution, "no `_skills/` directory found"))
        return None
    # SK-102 — distinguish flat `_skills/` vs `_skills/<pip-name>/`.
    if skills_dir.name == "_skills":
        # flat layout — index missing
        out.append(
            Violation(
                "SK-102",
                str(skills_dir),
                f"expected `_skills/{distribution}/SKILL.md`",
            )
        )
        return None
    skill_md = skills_dir / "SKILL.md"
    if not skill_md.is_file():
        out.append(
            Violation(
                "SK-102",
                str(skills_dir),
                "missing `SKILL.md` index",
            )
        )
        return None
    # SK-103 — forbidden subdirs
    for sub in _core.find_forbidden_subdirs(skills_dir):
        out.append(
            Violation("SK-103", str(sub), f"forbidden subdirectory: {sub.name}/")
        )
    # SK-104 — duplicate index files
    aliases = ("SKILL_INDEX.md", "INDEX.md", "README.md")
    for alias_path in _core.find_alias_indexes(skills_dir, aliases):
        out.append(
            Violation(
                "SK-104",
                str(alias_path),
                f"alias index `{alias_path.name}` shadows the canonical `SKILL.md`",
            )
        )
    # SK-105 — MANIFEST.md is forbidden. The canonical index is SKILL.md;
    # distribution / update mechanics belong in a numbered leaf or the
    # package README.
    manifest = skills_dir / "MANIFEST.md"
    if manifest.is_file():
        out.append(
            Violation(
                "SK-105",
                str(manifest),
                "`MANIFEST.md` is forbidden — fold its content into a "
                "numbered leaf (e.g. `99_distribution.md`) or the README; "
                "`SKILL.md` is the single canonical index",
            )
        )
    return skills_dir


def _check_naming(skills_dir: Path, out: list[Violation]) -> None:
    """SK-201 / SK-202 / SK-203 — file naming."""
    for f in skills_dir.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        name = f.name
        if name == "SKILL.md":
            continue
        if name in _NAMING_EXEMPT:
            # Project-management leaves are exempt from the prefix rule.
            continue
        if not _core.has_numeric_prefix(name):
            out.append(Violation("SK-201", str(f), "missing `NN_` numeric prefix"))
            continue
        if name.startswith("SKILL"):
            out.append(
                Violation("SK-202", str(f), "`SKILL.md` must not carry a prefix")
            )
        if not _core.is_kebab_after_prefix(name):
            out.append(
                Violation(
                    "SK-203",
                    str(f),
                    "filename should be `NN_kebab-case.md` lowercase",
                )
            )


def _check_header_footer(path: Path, out: list[Violation]) -> None:
    """SK-210 / SK-211 — banned header/footer markers."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if _HTML_HEADER_RE.match(text):
        out.append(
            Violation("SK-210", str(path), "remove `<!-- --- ... --- -->` banner")
        )
    if _HTML_FOOTER_RE.search(text):
        out.append(Violation("SK-211", str(path), "remove trailing `<!-- EOF -->`"))


def _check_frontmatter(
    path: Path, out: list[Violation], *, is_skill_md: bool = True
) -> dict[str, str] | None:
    """SK-701 / SK-702 / SK-703 / SK-704 — frontmatter required fields.

    SK-702 (`name:` required) only fires for SKILL.md; leaves are governed by
    SK-705 (must NOT carry `name:`).

    Returns the parsed key->raw-value dict for downstream rule reuse, or None
    if frontmatter is missing entirely.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        out.append(Violation("SK-701", str(path), "no `---` frontmatter block"))
        return None
    block = m.group(1)
    keys = set(_FRONTMATTER_KEY_RE.findall(block))
    if is_skill_md and "name" not in keys:
        out.append(Violation("SK-702", str(path), "missing `name:` field"))
    if "description" not in keys:
        out.append(Violation("SK-703", str(path), "missing `description:` field"))
    if "tags" not in keys:
        out.append(Violation("SK-704", str(path), "missing `tags:` field"))
    return {k: "" for k in keys}


def _check_skill_md_size(skill_md: Path, out: list[Violation]) -> None:
    """SK-301 — SKILL.md size budget."""
    nbytes, nlines = _core.file_size(skill_md)
    if nbytes > _MAX_SKILL_MD_BYTES or nlines > _MAX_SKILL_MD_LINES:
        out.append(
            Violation(
                "SK-301",
                str(skill_md),
                f"{nbytes} bytes / {nlines} lines (budget: "
                f"{_MAX_SKILL_MD_BYTES} / {_MAX_SKILL_MD_LINES})",
            )
        )


def _check_leaf_size(leaf: Path, out: list[Violation]) -> None:
    """SK-401 — leaf size budget."""
    nbytes, nlines = _core.file_size(leaf)
    if nbytes > _MAX_LEAF_BYTES or nlines > _MAX_LEAF_LINES:
        out.append(
            Violation(
                "SK-401",
                str(leaf),
                f"{nbytes} bytes / {nlines} lines (budget: "
                f"{_MAX_LEAF_BYTES} / {_MAX_LEAF_LINES})",
            )
        )


def _check_index_links(skill_md: Path, skills_dir: Path, out: list[Violation]) -> None:
    """SK-302 — every sibling leaf is referenced from SKILL.md (no orphans)."""
    for orphan in _core.find_orphan_leaves(skill_md, skills_dir):
        out.append(
            Violation(
                "SK-302",
                str(orphan),
                "leaf is not referenced from `SKILL.md`",
            )
        )


def _check_import_alias(path: Path, out: list[Violation]) -> None:
    """SK-601 — skill text must not say `import scitex as stx`."""
    text = path.read_text()
    if re.search(r"\bimport\s+scitex\s+as\s+stx\b", text):
        out.append(
            Violation(
                "SK-601",
                str(path),
                "use bare `import scitex` (per general/01_ecosystem rule)",
            )
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _collect_violations(distribution: str, canonical_dir: Path) -> list[Violation]:
    """Run all per-file rules on a fully-discovered `_skills/<dist>/` dir."""
    violations: list[Violation] = []
    skill_md = canonical_dir / "SKILL.md"

    # SKILL.md checks.
    _check_header_footer(skill_md, violations)
    _check_frontmatter(skill_md, violations, is_skill_md=True)
    _check_skill_md_size(skill_md, violations)
    _check_index_links(skill_md, canonical_dir, violations)
    _check_import_alias(skill_md, violations)
    for code, where, detail in _v2.check_skill_md_frontmatter(skill_md, distribution):
        violations.append(Violation(code, where, detail))

    # File-presence (SK-105–SK-111).
    for code, where, detail in _v2.check_file_presence(canonical_dir, distribution):
        violations.append(Violation(code, where, detail))

    # Naming check covers the whole directory at once.
    _check_naming(canonical_dir, violations)

    # Per-leaf checks.
    for leaf in sorted(canonical_dir.iterdir()):
        if not leaf.is_file() or leaf.suffix != ".md" or leaf.name == "SKILL.md":
            continue
        _check_header_footer(leaf, violations)
        _check_frontmatter(leaf, violations, is_skill_md=False)
        _check_leaf_size(leaf, violations)
        _check_import_alias(leaf, violations)
        for code, where, detail in _v2.check_leaf_frontmatter(leaf, distribution):
            violations.append(Violation(code, where, detail))

    return violations


_FIXABLE = {"SK-705", "SK-709", "SK-710"}


def _apply_fixes(
    distribution: str, canonical_dir: Path, violations: list[Violation]
) -> dict[str, set[str]]:
    """Apply fixes; return {file_path: {codes_fixed}}."""
    by_file: dict[Path, set[str]] = {}
    for v in violations:
        if v.rule not in _FIXABLE:
            continue
        by_file.setdefault(Path(v.where), set()).add(v.rule)
    fixed_log: dict[str, set[str]] = {}
    skill_md = canonical_dir / "SKILL.md"
    for path, codes in by_file.items():
        if path == skill_md:
            done = _v2.fix_skill_md(path, distribution, codes)
        else:
            done = _v2.fix_leaf(path, distribution, codes)
        if done:
            fixed_log[str(path)] = done
    return fixed_log


def audit_skills(
    distribution: str,
    *,
    json_out: bool = False,
    rules: set[str] | None = None,
    fix: bool = False,
    skills_dir: Path | None = None,
) -> int:
    """Audit `<distribution>` against the skills checklist. Warn-only.

    Parameters
    ----------
    distribution : str
        Distribution name (e.g. ``"scitex-io"``).
    json_out : bool
        Emit machine-readable output on stdout.
    rules : set of str, optional
        If given, only run these rule codes.

    Returns
    -------
    int
        Exit code: 0 = no violations, 1 = violations, 2 = could not locate.
    """
    # Category-aware skip — see `should_skip_audit` in _ecosystem._core.
    try:
        from ...._ecosystem import should_skip_audit
    except ImportError:
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(distribution, "audit-skills")
    if skip:
        if json_out:
            import json

            click.echo(
                json.dumps(
                    {
                        "distribution": distribution,
                        "skills_dir": None,
                        "skipped": reason,
                        "violations": [],
                    },
                    indent=2,
                )
            )
        else:
            _emit("skip", f"{distribution}: {reason}")
        return 0

    if skills_dir is None:
        skills_dir = _locate_skills_dir(distribution)
    violations: list[Violation] = []

    canonical_dir = _check_layout(skills_dir, distribution, violations)

    if canonical_dir is not None:
        violations.extend(_collect_violations(distribution, canonical_dir))

        # --fix: apply auto-fixable rules and re-collect.
        if fix:
            fixed_log = _apply_fixes(distribution, canonical_dir, violations)
            for path_str, codes in sorted(fixed_log.items()):
                click.echo(f"fixed {path_str}: {', '.join(sorted(codes))}")
            # Re-run checks after fixes.
            violations = []
            canonical_dir2 = _check_layout(skills_dir, distribution, violations)
            if canonical_dir2 is not None:
                violations.extend(_collect_violations(distribution, canonical_dir2))

    if rules:
        violations = [v for v in violations if v.rule in rules]

    if json_out:
        import json

        click.echo(
            json.dumps(
                {
                    "distribution": distribution,
                    "skills_dir": str(skills_dir) if skills_dir else None,
                    "violations": [
                        {"rule": v.rule, "where": v.where, "detail": v.detail}
                        for v in violations
                    ],
                },
                indent=2,
            )
        )
        return 0 if not violations else 1

    if skills_dir is None:
        # Same as audit-api: not every package ships a `_skills/` directory,
        # and audit-all may run before `pip install -e .`. Skip rather than
        # fail.
        _emit(
            "info",
            f"{distribution}: no `_skills/` directory found — skipped.",
            err=True,
        )
        return 0

    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    if not violations:
        _emit("success", f"{distribution}: no skills violations")
        emit_disclaimer()
        return 0

    _emit("warning", f"{distribution}: {len(violations)} violation(s)")
    for v in violations:
        _emit("warning", v.format())
    emit_disclaimer()
    emit_skill_hints()
    return 1
