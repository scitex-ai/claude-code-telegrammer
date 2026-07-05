"""Configuration system for `scitex-dev linter`.

The standalone "scitex-linter" package was merged into scitex-dev in
2026-06; the linter is now invoked as `scitex-dev linter`. The legacy
`[tool.scitex-linter]` pyproject key and `SCITEX_LINTER_*` env-var
prefix are still read for back-compat (a `DeprecationWarning` is
emitted), and the canonical names are `[tool.scitex_dev.linter]` +
`SCITEX_DEV_LINTER_*`.
"""

from __future__ import annotations

__all__ = ["LinterConfig", "load_config"]

import fnmatch
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore


@dataclass
class LinterConfig:
    """Configuration for `scitex-dev linter` behaviour."""

    severity: str = "info"
    exclude_dirs: list[str] = field(
        default_factory=lambda: [
            "__pycache__",
            ".git",
            "node_modules",
            ".tox",
            "venv",
            ".venv",
        ]
    )
    library_patterns: list[str] = field(
        default_factory=lambda: [
            "__*__.py",
            "test_*.py",
            "conftest.py",
            "setup.py",
            "manage.py",
            "settings.py",
            "settings_*.py",
            "urls.py",
            "apps.py",
            "admin.py",
            "models.py",
            "views.py",
            "wsgi.py",
            "asgi.py",
            "conf.py",
        ]
    )
    library_dirs: list[str] = field(
        default_factory=lambda: ["src", "tests", "apps", "config", "docs"]
    )
    script_dirs: list[str] = field(default_factory=lambda: ["scripts"])
    disable: list[str] = field(default_factory=list)
    enable: list[str] = field(default_factory=list)
    per_rule_severity: dict[str, str] = field(default_factory=dict)
    category_severity_override: dict[str, str] = field(default_factory=dict)
    """Category → severity override map, applied after ``per_rule_severity``.

    Populated by :func:`load_config` from the project's
    ``.scitex/dev/config.yaml`` ``project-type`` declaration — research-
    typed projects flip the ``io`` and ``path`` categories from
    ``warning`` to ``error`` so a raw ``pd.read_parquet`` / bare
    ``open()`` blocks rather than just warns. Per the 2026-06-12
    operator directive 12826: research-category scripts must not bypass
    clew/io provenance silently. See Pillar 3 (#TBD).

    Per-rule overrides in ``per_rule_severity`` still win — set a specific
    rule's severity in pyproject.toml ``[tool.scitex-dev.linter.per-rule-
    severity]`` (canonical key; legacy ``[tool.scitex-linter.per-rule-
    severity]`` is also read with a ``DeprecationWarning``) to opt out
    of the category-wide flip for that one rule.
    """
    required_injected: list[str] = field(
        default_factory=lambda: ["CONFIG", "plt", "COLORS", "rngg", "logger"]
    )
    project_types: list[str] = field(default_factory=list)
    """Project types detected from ``.scitex/dev/config.yaml`` ``project-type``.

    Populated once by :func:`load_config` (via
    ``_project_type.detect_scitex_dev_project_types``) so rule code can gate
    on ``"research" in config.project_types`` without re-walking the tree.
    The category/per-rule promotion below reuses the same detection.
    """
    # STX-S009 / STX-S010 — research script-organization knobs (see
    # ``_rules/_script_organization.py``). Research-gated, default WARNING.
    script_domain_min_depth: int = 1
    """Required domain-subdir depth under a ``script_dir`` before STX-S009
    stops firing. 1 (default) means ``scripts/<domain>/foo.py`` passes and a
    flat ``scripts/foo.py`` warns."""
    script_org_exempt: list[str] = field(
        default_factory=lambda: ["__init__.py", "__main__.py", "conftest.py"]
    )
    """Filenames exempt from STX-S009 / STX-S010."""
    script_verb_prefixes: list[str] = field(default_factory=list)
    """Extra verb prefixes accepted as a verb-first script name (STX-S010).
    These EXTEND the primary judge — the bundled WordNet-derived verb lexicon
    in ``_script_organization`` (plus its small built-in tech-verb set) — for
    project-specific coinages the lexicon can't know."""


# =============================================================================
# Configuration Loading
# =============================================================================


def load_config(start_path: str | None = None) -> LinterConfig:
    """
    Load configuration from defaults, pyproject.toml, and environment variables.

    Priority: env vars > pyproject.toml > defaults

    Args:
        start_path: File or directory to start pyproject.toml search from.
            If a file path, searches from its parent directory.
            Defaults to cwd.

    Returns:
        Merged configuration
    """
    # Start with defaults
    config_dict = {}

    # Load from pyproject.toml — resolve file paths to their directory
    if start_path:
        start_dir = Path(start_path).resolve()
        if start_dir.is_file():
            start_dir = start_dir.parent
    else:
        start_dir = Path.cwd()
    pyproject_config = _load_pyproject(start_dir)
    config_dict.update(pyproject_config)

    # Load from environment variables (highest priority)
    env_config = _load_env()
    config_dict.update(env_config)

    # Pillar 3 (#TBD, 2026-06-12 operator directive 12826): when the
    # project is research-typed (declared in .scitex/dev/config.yaml as
    # `project-type: research`), flip the io / path category severities
    # from "warning" to "error" so a raw `pd.read_parquet` / bare
    # `open()` BLOCKS the script-edit hook rather than just warning the
    # agent. Per-rule overrides in `per_rule_severity` still win — the
    # category map is the floor, not the ceiling. Walk-up + YAML parse
    # lives in `_project_type.py` (src↔tests 1:1 mirror invariant).
    from ._project_type import detect_scitex_dev_project_types

    _project_types = detect_scitex_dev_project_types(start_dir)
    # Surface the detected types so rule code (e.g. STX-S009/S010) can gate on
    # `"research" in config.project_types` without re-walking the tree.
    config_dict["project_types"] = list(_project_types)

    if "research" in _project_types:
        existing = config_dict.get("category_severity_override", {}) or {}
        # Figure-family promotion v1 (PR #264, operator directive 2026-06-28):
        # figrecipe owns the DETECTION of figure-bypass patterns; here we
        # promote the EXISTING figure-family rules to ERROR in research
        # projects so the post-edit hook (run_lint.sh, exit 2) deterministically
        # BLOCKS figure-bypass code. The v1 set spans TWO categories:
        #   - "figure": FM001-FM011 + FIG001
        #   - "plot":   P001-P009
        # (verified against figrecipe's _linter_plugin.py rule objects).
        # As always, per-rule `per_rule_severity` overrides WIN — the category
        # map is the floor, not the ceiling. `# stx-allow: STX-<ID>` per-line
        # comments remain the opt-out (handled in each checker's _add/_emit).
        merged = {
            "io": "error",
            "path": "error",
            "figure": "error",
            "plot": "error",
            **existing,
        }
        config_dict["category_severity_override"] = merged

        # Raw-external-library IMPORT promotion v1 (operator directive
        # 2026-06-30, mirroring PR #264's figure/plot promotion): research
        # projects must use the stx umbrella (`stx.plt` / `stx.stats` /
        # `stx.io`) instead of importing the raw third-party library
        # directly. The relevant import rules — STX-I001 (matplotlib.pyplot),
        # STX-I002 (scipy.stats), STX-I009 (seaborn) — already FIRE in
        # research mode but only as WARNINGS, so e.g. `import matplotlib`
        # warns-without-blocking the post-edit hook. We promote them to
        # ERROR so the hook (run_lint.sh, exit 2) deterministically BLOCKS.
        #
        # MECHANISM — per_rule_severity, NOT a category override: all of
        # STX-I001..I009 share the SINGLE category "import", which also
        # carries rules that must STAY warn-only — STX-I003 (pickle),
        # STX-I006/I007 (`random`/`logging` injection hygiene), and
        # STX-I008 (cross-package private-submodule import, a DIFFERENT
        # concern). Promoting the whole "import" category would over-promote
        # those. So we target the exact raw-extlib import IDs by rule.
        # per_rule_severity WINS over the category floor (see checker._add
        # and _severity_promotion.py), so an operator pin in pyproject for
        # any of these still takes precedence. The `# stx-allow: STX-<ID>`
        # per-line opt-out is unaffected (handled in checker._add before
        # severity is assigned — a suppressed line never reaches here).
        _existing_per_rule = config_dict.get("per_rule_severity", {}) or {}
        config_dict["per_rule_severity"] = {
            "STX-I001": "error",
            "STX-I002": "error",
            "STX-I009": "error",
            **_existing_per_rule,
        }

        # FM category auto-enable for research projects (neurovista
        # elevation 2026-06-14): figure provenance / clew chaining
        # matters for research outputs, so figrecipe's figure-style
        # rules (STX-FM0xx, STX-P00x) become opt-OUT, not opt-IN.
        # Operator can still disable per-category via pyproject's
        # ``disable`` list — this only sets the floor.
        _existing_enable = config_dict.get("enable", []) or []
        if "FM" not in _existing_enable:
            config_dict["enable"] = [*_existing_enable, "FM"]

    # Build LinterConfig with merged values
    return LinterConfig(**config_dict)


def _load_pyproject(start_dir: Path) -> dict:
    """
    Walk up directories to find pyproject.toml with the linter config.

    Canonical key: ``[tool.scitex-dev.linter]`` (post-2026-06 merge).
    Legacy key: ``[tool.scitex-linter]`` is still read for back-compat
    when the canonical key is absent — a ``DeprecationWarning`` is
    emitted so the operator knows to migrate.

    Args:
        start_dir: Starting directory for search

    Returns:
        Configuration dict from the linter table, or empty dict if not found
    """
    if tomllib is None:
        return {}

    current = start_dir
    while True:
        pyproject_path = current / "pyproject.toml"
        if pyproject_path.exists():
            try:
                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)
                    tool_root = data.get("tool", {})
                    # Canonical key first; legacy as fallback.
                    tool_config = tool_root.get("scitex-dev", {}).get("linter", {})
                    if not tool_config:
                        legacy = tool_root.get("scitex-linter", {})
                        if legacy:
                            import warnings as _w

                            _w.warn(
                                f"{pyproject_path}: [tool.scitex-linter] is "
                                "the legacy key; the canonical key is "
                                "[tool.scitex-dev.linter]. Both are read "
                                "for back-compat (canonical wins on "
                                "conflict).",
                                DeprecationWarning,
                                stacklevel=2,
                            )
                            tool_config = legacy
                    if tool_config:
                        # Flatten nested sections
                        config = {}
                        for key, value in tool_config.items():
                            if key == "per-rule-severity":
                                config["per_rule_severity"] = value
                            elif key == "session":
                                # Handle [tool.scitex-dev.linter.session]
                                # (or its legacy [tool.scitex-linter.session]
                                # alias — same loader handles both).
                                if "required_injected" in value:
                                    config["required_injected"] = value[
                                        "required_injected"
                                    ]
                            else:
                                # Convert kebab-case to snake_case
                                config[key.replace("-", "_")] = value
                        return config
            except Exception:
                pass

        # Move up one directory
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent

    return {}


_ENV_PREFIX_NEW = "SCITEX_DEV_LINTER_"
_ENV_PREFIX_OLD = "SCITEX_LINTER_"

# Per-suffix mapping: canonical (new) → list of legacy aliases. The first
# matching env var wins; any legacy hit emits a one-time DeprecationWarning.
# Add aliases here when an env var is renamed; do NOT silently drop them
# — a one-release deprecation window is the soft-migration policy.
_ENV_RENAMES: dict[str, list[str]] = {
    # Renamed for clarity — the dirs in question hold *non-script* code (no
    # @stx.session decorator / __main__ guard expected). The old name
    # "LIBRARY_DIRS" was ambiguous against EXCLUDE_DIRS.
    "NON_SCRIPT_DIRS": ["LIBRARY_DIRS"],
}

_warned_aliases: set = set()


def _read_env(suffix: str) -> str | None:
    """Read an env var, preferring the new prefix + canonical name.

    Falls back to: (1) new prefix + legacy alias, (2) old prefix + canonical
    name, (3) old prefix + legacy alias. Any legacy hit emits a one-time
    DeprecationWarning naming the canonical replacement.
    """
    aliases = [suffix] + _ENV_RENAMES.get(suffix, [])
    for prefix, prefix_label in (
        (_ENV_PREFIX_NEW, "new"),
        (_ENV_PREFIX_OLD, "old"),
    ):
        for alias in aliases:
            name = prefix + alias
            if name in os.environ:
                canonical = _ENV_PREFIX_NEW + suffix
                if name != canonical and name not in _warned_aliases:
                    import warnings

                    warnings.warn(
                        f"Env var {name!r} is deprecated; use {canonical!r}.",
                        DeprecationWarning,
                        stacklevel=4,
                    )
                    _warned_aliases.add(name)
                return os.environ[name]
    return None


def _read_env_csv(suffix: str) -> list | None:
    raw = _read_env(suffix)
    if raw is None:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


def _load_env() -> dict:
    """Load configuration from `SCITEX_DEV_LINTER_*` environment variables.

    The legacy `SCITEX_LINTER_*` prefix is also accepted for the soft-migration
    window and emits a `DeprecationWarning`.

    Returns:
        Configuration dict with snake_case keys
    """
    config: dict = {}

    severity = _read_env("SEVERITY")
    if severity is not None:
        config["severity"] = severity

    for suffix, key in (
        ("DISABLE", "disable"),
        ("ENABLE", "enable"),
        ("EXCLUDE_DIRS", "exclude_dirs"),
        ("NON_SCRIPT_DIRS", "library_dirs"),
        ("SCRIPT_DIRS", "script_dirs"),
        ("LIBRARY_PATTERNS", "library_patterns"),
        ("REQUIRED_INJECTED", "required_injected"),
    ):
        values = _read_env_csv(suffix)
        if values is not None:
            config[key] = values

    return config


# =============================================================================
# Utility Functions
# =============================================================================


def matches_library_pattern(filename: str, config: LinterConfig) -> bool:
    """
    Check if filename matches any library pattern in config.

    Args:
        filename: Filename to check (e.g., "__init__.py", "test_foo.py")
        config: Linter configuration

    Returns:
        True if filename matches any pattern
    """
    for pattern in config.library_patterns:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False
