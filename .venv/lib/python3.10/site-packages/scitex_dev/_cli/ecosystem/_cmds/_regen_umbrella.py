#!/usr/bin/env python3
# Timestamp: 2026-06-07
# File: scitex_dev/_cli/ecosystem/_cmds/_regen_umbrella.py

"""``scitex-dev ecosystem regen-umbrella`` — check umbrella SSoT drift.

The umbrella's hand-maintained surfaces (``[project.optional-dependencies]``,
``[all]``, ``EXTERNAL_REEXPORTS``, ``__init__.py`` lazy_attrs) are
*supposed* to be derivable from the ECOSYSTEM registry. This command
reads the live umbrella tree and reports drift vs the
:mod:`scitex_dev._ecosystem._umbrella` resolver's expected shape.

``--check`` (default) is read-only — never writes the umbrella. It
exits ``0`` on no-drift, ``1`` on drift, and prints an actionable
diff. ``--write`` is intentionally not implemented in this PR (the
operator's local scitex-python tree is the SSoT for hand-curated
extras; the resolver's writes need a separate review path).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click

from ...._ecosystem._registry import ECOSYSTEM
from ...._ecosystem._umbrella import (
    HAND_CURATED_EXTRAS,
    IN_TREE_SHIM_LAZY_ATTRS,
    expected_all_extras,
    expected_external_reexports,
    expected_lazy_attrs,
)


def _umbrella_root() -> Path:
    """Resolve the local scitex-python checkout root."""
    return Path(ECOSYSTEM["scitex"]["local_path"]).expanduser()


def _load_pyproject(root: Path) -> dict:
    """Parse the umbrella's pyproject.toml or raise click.ClickException."""
    pp = root / "pyproject.toml"
    if not pp.is_file():
        raise click.ClickException(f"scitex umbrella pyproject not found: {pp}")
    try:
        try:
            import tomllib  # type: ignore[import-not-found]
        except ImportError:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        with pp.open("rb") as fh:
            return tomllib.load(fh)
    except Exception as e:  # noqa: BLE001
        raise click.ClickException(f"failed to parse {pp}: {e}") from e


_LAZY_RE = re.compile(
    r'^(\w+)\s*=\s*_(?:Lazy|CallableModuleWrapper)\w*\(\s*"(\w+)"'
    r'(?:[^)]*?external\s*=\s*"([^"]+)")?',
    re.MULTILINE,
)


def _read_lazy_attrs(root: Path) -> dict[str, str | None]:
    """Extract ``<short> = _LazyModule("<short>", external="<peer>")`` pairs.

    Returns ``{short: external|None}``. Read by regex — the umbrella's
    ``__init__.py`` mixes generated and hand-written code, so we avoid
    importing scitex to keep the check side-effect-free.
    """
    init = root / "src" / "scitex" / "__init__.py"
    if not init.is_file():
        raise click.ClickException(f"scitex umbrella __init__ not found: {init}")
    text = init.read_text(encoding="utf-8")
    out: dict[str, str | None] = {}
    for m in _LAZY_RE.finditer(text):
        var, short, external = m.group(1), m.group(2), m.group(3) or None
        if var != short:
            # Skip alias-assignment lines like `dt = datetime`; those
            # are captured by AUX_MOUNTS in the resolver, not here.
            continue
        out[short] = external
    return out


def _read_all_extras(data: dict) -> set[str]:
    """Extract the ``[all]`` aggregator's ``scitex[<x>]`` self-references.

    Hand-curated extras (``[heavy]``, ``[dev]``, ``[docs]`` etc., listed
    in :data:`HAND_CURATED_EXTRAS`) are filtered out so the drift report
    only flags drift in the SSoT-derivable subset.
    """
    opt = (data.get("project") or {}).get("optional-dependencies") or {}
    all_specs = opt.get("all") or []
    out: set[str] = set()
    for spec in all_specs:
        m = re.match(r"^\s*scitex\[([\w.-]+)\]", spec)
        if m and m.group(1) not in HAND_CURATED_EXTRAS:
            out.add(f"scitex[{m.group(1)}]")
    return out


def _read_external_reexports(root: Path) -> dict[str, str]:
    """Extract the ``EXTERNAL_REEXPORTS = {...}`` literal from re_export.py."""
    rx = root / "src" / "scitex" / "re_export.py"
    if not rx.is_file():
        # Not strictly required — older umbrella layouts kept the map
        # inline in __init__.py. Empty means "no drift detection here".
        return {}
    text = rx.read_text(encoding="utf-8")
    m = re.search(
        r"EXTERNAL_REEXPORTS\s*(?::\s*[^=]+?)?=\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    if not m:
        return {}
    body = m.group(1)
    out: dict[str, str] = {}
    for line_m in re.finditer(r'"(\w+)"\s*:\s*"([^"]+)"', body):
        out[line_m.group(1)] = line_m.group(2)
    return out


def _diff_sets(label: str, expected: set, actual: set) -> list[str]:
    """Render a ``--- expected\\n+++ actual`` style diff for set-typed views."""
    lines = [f"== {label} =="]
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if not missing and not extra:
        lines.append("  (no drift)")
        return lines
    for v in missing:
        lines.append(f"  - MISSING from umbrella: {v}")
    for v in extra:
        lines.append(f"  + EXTRA in umbrella (not in registry): {v}")
    return lines


def _diff_lazy_attrs(
    expected: list[tuple[str, str | None]],
    actual: dict[str, str | None],
) -> list[str]:
    """Render lazy_attr drift: missing aliases + wrong externals + extras.

    Suppresses two classes of false-positive drift:

    - ``external`` mismatches for shorts in :data:`IN_TREE_SHIM_LAZY_ATTRS`
      (the umbrella ships ``scitex.<short>`` as an in-tree dir with no
      peer ``external="…"``; the registry's expected external is the
      *eventual* externalization target, not a drift).
    - ``EXTRA in umbrella`` for in-tree shim shorts (canvas/cli/fts/…)
      that have no peer at all.
    """
    lines = ["== lazy_attrs (scitex/__init__.py) =="]
    exp_map = dict(expected)
    drift = False
    for short, ext in expected:
        if short not in actual:
            lines.append(f"  - MISSING declaration: {short} (expected external={ext})")
            drift = True
            continue
        if actual[short] != ext and short not in IN_TREE_SHIM_LAZY_ATTRS:
            lines.append(
                f"  ~ external mismatch for `{short}`: "
                f"expected={ext!r}, actual={actual[short]!r}"
            )
            drift = True
    for short, ext in actual.items():
        if short in exp_map:
            continue
        if short in IN_TREE_SHIM_LAZY_ATTRS:
            continue
        lines.append(
            f"  + EXTRA declaration (not in registry): "
            f"{short} (external={ext!r})"
        )
        drift = True
    if not drift:
        lines.append("  (no drift)")
    return lines


def register(ecosystem):
    @ecosystem.command(
        # Named ``audit-umbrella`` (verb prefix) to satisfy audit-cli §1
        # leaf-token verb rule. The `--write` follow-up will add a sibling
        # ``regen-umbrella`` action (verb form unambiguous when paired
        # with the audit-only command above).
        "audit-umbrella",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-umbrella --check\n"
            "  $ scitex-dev ecosystem audit-umbrella --check --json\n"
            "  $ scitex-dev ecosystem audit-umbrella --write\n"
            "\n"
            "Drift detector between ECOSYSTEM (the registry) and the local\n"
            "scitex-python checkout (umbrella pyproject + __init__).\n"
            "\n"
            "Exits 0 on no-drift, 1 on drift (--check), or 0 on successful\n"
            "regen (--write). --write only regenerates the [all] aggregator\n"
            "block; lazy_attrs and EXTERNAL_REEXPORTS edits are still\n"
            "surfaced via --check (apply by hand until the marker-based\n"
            "Python-source regen lands)."
        ),
    )
    @click.option(
        "--check",
        "mode",
        flag_value="check",
        default="check",
        help="Read-only drift check (default).",
    )
    @click.option(
        "--write",
        "mode",
        flag_value="write",
        help="Regenerate [project.optional-dependencies].all in the "
        "umbrella's pyproject.toml in-place. The umbrella checkout MUST "
        "be clean against origin/develop (safety gate). Lazy_attrs and "
        "EXTERNAL_REEXPORTS edits are still surfaced via --check and "
        "must be applied by hand.",
    )
    @click.option("--json", "json_out", is_flag=True, help="Machine-readable JSON.")
    def audit_umbrella(mode, json_out):
        """Audit umbrella surfaces against the ECOSYSTEM registry SSoT."""
        root = _umbrella_root()
        if not root.is_dir():
            raise click.ClickException(
                f"scitex-python checkout not found at {root}; "
                "drift check needs the umbrella source locally."
            )
        data = _load_pyproject(root)
        actual_all = _read_all_extras(data)
        actual_lazy = _read_lazy_attrs(root)
        actual_ext = _read_external_reexports(root)
        exp_all = set(expected_all_extras())
        exp_lazy = expected_lazy_attrs()
        exp_ext = expected_external_reexports()

        # Strip in-tree shims from the EXTERNAL_REEXPORTS drift surface —
        # those shorts are legitimately absent from the EXTERNAL_REEXPORTS
        # map (they're in-tree dirs, not external aliases).
        exp_ext_clean = {
            k: v for k, v in exp_ext.items() if k not in IN_TREE_SHIM_LAZY_ATTRS
        }
        actual_ext_clean = {
            k: v for k, v in actual_ext.items() if k not in IN_TREE_SHIM_LAZY_ATTRS
        }

        if mode == "write":
            from ...._ecosystem._umbrella_write import write_umbrella

            result = write_umbrella(root, exp_all=exp_all)
            click.echo(result.summary)
            if result.modified:
                click.echo(
                    "\n[NOTE] Only [project.optional-dependencies].all is "
                    "regenerated by --write in PR-A2. The lazy_attrs "
                    "(src/scitex/__init__.py) and EXTERNAL_REEXPORTS "
                    "(src/scitex/re_export.py) edits are still surfaced via "
                    "--check; apply them by hand from the --check output "
                    "until the marker-based --write lands in a follow-up."
                )
            return

        if json_out:
            import json as _json

            payload = {
                "all_extras": {
                    "expected": sorted(exp_all),
                    "actual": sorted(actual_all),
                    "missing": sorted(exp_all - actual_all),
                    "extra": sorted(actual_all - exp_all),
                },
                "lazy_attrs": {
                    "expected": exp_lazy,
                    "actual": sorted(actual_lazy.items()),
                },
                "external_reexports": {
                    "expected": sorted(exp_ext_clean.items()),
                    "actual": sorted(actual_ext_clean.items()),
                },
            }
            click.echo(_json.dumps(payload, indent=2, sort_keys=True))
        else:
            for line in _diff_sets("[all] aggregator", exp_all, actual_all):
                click.echo(line)
            for line in _diff_lazy_attrs(exp_lazy, actual_lazy):
                click.echo(line)
            for line in _diff_sets(
                "EXTERNAL_REEXPORTS",
                set(exp_ext_clean.items()),
                set(actual_ext_clean.items()),
            ):
                click.echo(line)
        # Drift exit code: 1 iff any of the three has drift, allowlists honoured.
        any_drift = (
            exp_all != actual_all
            or any(
                actual_lazy.get(s) != e
                for s, e in exp_lazy
                if s not in IN_TREE_SHIM_LAZY_ATTRS
            )
            or any(
                s not in dict(exp_lazy) and s not in IN_TREE_SHIM_LAZY_ATTRS
                for s in actual_lazy
            )
            or exp_ext_clean != actual_ext_clean
        )
        sys.exit(1 if any_drift else 0)


# EOF
