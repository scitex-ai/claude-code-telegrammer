"""Loader + heuristic detector for `.scitex/dev/config.yaml`.

Schema (canonical): see GITIGNORED/RULES_FOR_SCIENTIFIC_PROJECTS.md
§"Project-type config".

```yaml
project-type:
  - pip          # PS-1xx rules apply
  - research     # RP1xx-RP9xx rules apply
audit:
  skip:
    - PS-108
  whitelist: .audit-whitelist.yaml
metadata:
  cohorts: 3
  app:                              # OPTIONAL — app/hub-registry surface.
    category: writer                # free string, e.g. "writer" | "todo" | "figrecipe"
    official: true                  # first-party flag
    pre_installed: true             # ships in hub by default
    is_hub_app: true                # mounts in hub's app shell
    author: "Yusuke Watanabe <ywatanabe@scitex.ai>"
```

Both `project-type` keys can be present at once for hybrid repos
(a tool package whose `examples/` IS the research project).

The `metadata.app` block (operator directive 2026-06-14, lead a2a
`1f135ad4...`) is the SINGLE source-of-truth for app/project metadata
across the ecosystem — hub's app registry, scitex-dev audit, and any
other consumer all read it via :func:`load_config` → :attr:`ProjectConfig.app_metadata`.
No new manifest.json surface; no `[tool.scitex_dev]` duplication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_TYPES = frozenset({"pip", "research", "special", "django", "deferred"})

CONFIG_REL_PATH = Path(".scitex/dev/config.yaml")

# Leaf-side package-type CAPABILITY knob (operator directive 2026-06-22).
#
# A leaf declares what it structurally LACKS so the auditor skips the rules
# that do not fit that package TYPE — with a VISIBLE "skipped (declared
# capability: X)" notice rather than a silent pass or a blanket
# ``audit.skip`` entry. This keeps the skip self-documenting and scoped to a
# real package property (like a plugin/capability flag), not per-rule debt
# suppression. Schema in ``.scitex/dev/config.yaml``::
#
#     audit:
#       capabilities: [no-mcp, no-umbrella]
#
#   no-mcp       — package is an ALIAS / has no first-party MCP surface
#                  (e.g. scitex-plt aliases figrecipe). Skips the §6
#                  MCP ↔ Python-API parity check.
#   no-umbrella  — package is umbrella-free (e.g. scitex-seizure-metrics,
#                  scitex-stats); its examples legitimately do not use
#                  ``@stx.session``. Skips PS-501 / PS-503.
#
# Each capability gates a FIXED, hard-coded set of rule codes (see
# ``CAPABILITY_RULES``) so a declared capability can never silence an
# unrelated rule.
CAPABILITY_RULES: dict[str, frozenset[str]] = {
    "no-mcp": frozenset({"§6"}),
    "no-umbrella": frozenset({"PS-501", "PS-503"}),
}

KNOWN_CAPABILITIES = frozenset(CAPABILITY_RULES)


def capability_for_rule(rule: str) -> str | None:
    """Return the capability whose declaration skips ``rule`` (or None).

    Inverse of :data:`CAPABILITY_RULES`. Used by the auditor to emit the
    ``skipped (declared capability: X)`` notice when a finding is dropped.
    """
    for cap, rules in CAPABILITY_RULES.items():
        if rule in rules:
            return cap
    return None


@dataclass(frozen=True)
class ProjectConfig:
    """Parsed `.scitex/dev/config.yaml`.

    `project_types` is always non-empty. `skip` holds rule codes the user
    pre-approved as exceptions. `whitelist_path` (if set) is resolved
    relative to the project root by callers.
    """

    project_types: frozenset[str]
    skip: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()
    whitelist_path: Path | None = None
    metadata: dict = field(default_factory=dict)
    source: str = "config"  # "config" | "heuristic" | "override"

    def has_capability(self, name: str) -> bool:
        """True iff the project declared the ``name`` capability.

        Capabilities are declared in ``.scitex/dev/config.yaml`` under
        ``audit.capabilities`` (e.g. ``no-mcp``, ``no-umbrella``) and gate a
        FIXED set of rule codes (:data:`CAPABILITY_RULES`). Unlike
        ``audit.skip`` (which silences an arbitrary rule, debt-style), a
        capability is a declared package PROPERTY — the auditor emits a
        visible "skipped (declared capability: X)" notice when it drops a
        finding for it.
        """
        return name in self.capabilities

    @property
    def app_metadata(self) -> dict:
        """Return the `metadata.app` block (or `{}` when absent).

        This is the canonical accessor for app/project metadata across
        the ecosystem — hub's app registry, audit, and any other
        consumer should read app metadata via this property rather than
        re-parsing `.scitex/dev/config.yaml` themselves. Operator
        directive 2026-06-14: no parallel manifest, no
        `[tool.scitex_dev]` duplication.

        Recognised keys (all OPTIONAL):

        * ``category`` (str)       — e.g. ``"writer"``, ``"todo"``.
        * ``official`` (bool)      — first-party flag.
        * ``pre_installed`` (bool) — ships in hub by default.
        * ``is_hub_app`` (bool)    — mounts in hub's app shell.
        * ``author`` (str)         — override of ``project.authors``.

        Unknown keys are returned verbatim so consumers can experiment
        without a loader change (the loader stays minimal; the schema
        evolves at the consumer/doc layer).
        """
        app = self.metadata.get("app")
        return app if isinstance(app, dict) else {}

    def applies(self, code: str) -> bool:
        """True iff a rule code's family is active for this project.

        `special`-typed projects opt out of PS-103 (root-layout
        whitelist) — their unusual root organisation is by design
        (research-style numbered manuscript dirs, CMS content trees,
        etc.). All other PS rules still apply if `pip` is also listed.
        """
        # Three project-types opt out of PS-103 (root whitelist) with
        # different semantic intent:
        #
        #   special  — by-design unconventional layout (research trees,
        #              CMS content, multi-pkg monorepo, npm hybrid).
        #              No future cleanup expected.
        #   django   — Django framework canonical layout (apps/, static/,
        #              media/, templates/, …). Semantic alias of special.
        #   deferred — "I know this is messy; remind me later." The
        #              auditor opts out of the rule but emits a warning
        #              listing what would have fired so the operator has
        #              a TODO list ready when revisiting.
        if code == "PS-103" and self.project_types & {
            "special",
            "django",
            "deferred",
        }:
            return False
        # PS-173 (ADR format) is cross-cutting — ADRs are an ecosystem
        # convention for ALL project kinds (package / research / grant /
        # draft), not just pip packages. It only fires when docs/adr/
        # exists, so applying it everywhere costs nothing for repos
        # without ADRs.
        if code == "PS-173":
            return True
        # PS-PATH-* / PS-CLEW-* / PS-AGENT-* — paper-scitex-clew MVP
        # lint rules (PR #97, operator directive 2026-06-01). They
        # target research-project artifacts (`config/PATH.yaml`,
        # `scripts/agent/*.py`, `clew.add_claim` call sites) but the
        # SciTeX hybrid pattern lets these coexist with `pip` projects
        # too. Each rule is already artifact-gated (only fires when
        # the relevant file exists), so applying it cross-cutting is
        # safe and costs nothing for unrelated repos.
        if (
            code.startswith("PS-PATH-")
            or code.startswith("PS-CLEW-")
            or code.startswith("PS-AGENT-")
        ):
            return True
        prefix = code[:2]
        if prefix == "PS":
            return "pip" in self.project_types
        if prefix == "RP":
            return "research" in self.project_types
        if prefix == "SK":
            return "pip" in self.project_types
        # Cross-cutting (license/CLA helpers etc.) — apply to all.
        return True


def _read_yaml(path: Path) -> dict | None:
    """Tiny YAML reader: returns dict or None if file missing/unreadable.

    Uses PyYAML if available; falls back to a minimal subset parser
    sufficient for this schema (lists of strings, scalar key:value pairs)
    so the auditor doesn't pull a hard dep on PyYAML.
    """
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml  # type: ignore[import-untyped]

        return yaml.safe_load(text) or {}
    except ImportError:
        return _minimal_yaml(text)


def _minimal_yaml(text: str) -> dict:
    """Subset YAML parser for our schema only — list-of-strings + key: value."""
    result: dict = {}
    stack: list[tuple[int, str, list | dict]] = [(0, "", result)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        s = line.strip()
        # Pop stack to current indent
        while stack and indent < stack[-1][0]:
            stack.pop()
        parent = stack[-1][2]
        if s.startswith("- "):
            value = s[2:].strip().strip('"').strip("'")
            if isinstance(parent, list):
                parent.append(value)
        elif ":" in s and isinstance(parent, dict):
            key, _, val = s.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "":
                container: list = []
                parent[key] = container
                stack.append((indent + 2, key, container))
            else:
                parent[key] = val.strip('"').strip("'")
        # Else: ignore (multi-line strings, anchors not supported)
    return result


def detect_project_types(repo: Path) -> frozenset[str]:
    """Heuristic fallback when no config file exists.

    - has pyproject.toml + src/<pkg>/  → pip
    - has scripts/ + data/ + config/   → research
    - has both                          → {pip, research}
    """
    types: set[str] = set()
    if (repo / "pyproject.toml").is_file() and (repo / "src").is_dir():
        if any(
            (repo / "src" / d).is_dir() for d in (repo / "src").iterdir() if d.is_dir()
        ):
            types.add("pip")
    if (
        (repo / "scripts").is_dir()
        and (repo / "data").is_dir()
        and (repo / "config").is_dir()
    ):
        types.add("research")
    if not types:
        # Default: assume pip if there's any sign of a Python package.
        types.add("pip")
    return frozenset(types)


def load_config(
    repo: Path,
    *,
    override_types: list[str] | None = None,
) -> ProjectConfig:
    """Resolve the active config (lookup order matches the spec).

    1. CLI override (`override_types`)
    2. `<repo>/.scitex/dev/config.yaml`
    3. Heuristic detection (warns the caller via `source="heuristic"`)
    """
    if override_types:
        return ProjectConfig(
            project_types=frozenset(override_types),
            source="override",
        )

    cfg_path = repo / CONFIG_REL_PATH
    raw = _read_yaml(cfg_path)
    if raw:
        # `project-type` is OPTIONAL. When absent (or empty/invalid) we still
        # honour the file's `audit` block — `audit.capabilities` / `audit.skip`
        # / `audit.whitelist` apply regardless of whether the project type is
        # spelled out — and fall back to heuristic detection for the types. A
        # config that only declares `audit:` (e.g. an alias package's
        # capability knob or root-whitelist) was previously ignored wholesale.
        types_raw = raw.get("project-type") or []
        if isinstance(types_raw, str):
            types_raw = [types_raw]
        types = frozenset(t for t in types_raw if t in PROJECT_TYPES)
        source = "config"
        if not types:
            types = detect_project_types(repo)
            source = "heuristic"
        audit = raw.get("audit") or {}
        skip = audit.get("skip") or []
        if isinstance(skip, str):
            skip = [skip]
        caps = audit.get("capabilities") or []
        if isinstance(caps, str):
            caps = [caps]
        wl = audit.get("whitelist")
        return ProjectConfig(
            project_types=types,
            skip=frozenset(skip),
            capabilities=frozenset(c for c in caps if c in KNOWN_CAPABILITIES),
            whitelist_path=Path(wl) if wl else None,
            metadata=raw.get("metadata") or {},
            source=source,
        )

    return ProjectConfig(
        project_types=detect_project_types(repo),
        source="heuristic",
    )


def write_config(
    repo: Path,
    *,
    project_types: list[str] | None = None,
    overwrite: bool = False,
) -> Path:
    """Write `<repo>/.scitex/dev/config.yaml` with the heuristic guess
    (or the explicit list). Returns the absolute path written.

    Raises FileExistsError if the file already exists and overwrite=False.
    """
    target = repo / CONFIG_REL_PATH
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    if not project_types:
        project_types = sorted(detect_project_types(repo))

    target.parent.mkdir(parents=True, exist_ok=True)
    body = "# scitex-dev project-type config\n"
    body += "# Drives which rule families the auditor applies.\n"
    body += "# See: scitex-dev ecosystem audit-project --help\n\n"
    body += "project-type:\n"
    for t in project_types:
        body += f"  - {t}\n"
    body += "\n# audit:\n#   skip:\n#     - PS-108\n"
    target.write_text(body)
    return target


__all__ = [
    "PROJECT_TYPES",
    "CONFIG_REL_PATH",
    "CAPABILITY_RULES",
    "KNOWN_CAPABILITIES",
    "capability_for_rule",
    "ProjectConfig",
    "detect_project_types",
    "load_config",
    "write_config",
]
