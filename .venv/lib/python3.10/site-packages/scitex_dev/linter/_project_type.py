"""Walk-up loader for ``.scitex/dev/config.yaml`` ``project-type``.

Used by :mod:`scitex_dev.linter.config` to detect whether the linter is
running under a research-typed project, which in turn drives the
Pillar-3 (#TBD, operator directive 12826) category-severity flip
(``io`` and ``path`` rules go warning→error).

Lives in its own module so:

* the test mirror path ``tests/scitex_dev/linter/test__project_type.py``
  satisfies the PS-204 src↔tests 1:1 mirror invariant audit-project
  enforces (config.py's broader tests are too coarse a home);
* downstream callers can re-use the same walk-up + YAML parsing
  without pulling LinterConfig into their import graph.

The schema is intentionally a SUBSET of the canonical
``.scitex/dev/config.yaml`` schema that the audit-project loader
parses (see ``scitex_dev._cli.audit._config._loader``); we only read
``project-type`` here. The two loaders are kept independent on
purpose — audit-project's loader pulls in ProjectConfig + the broader
schema and we want the linter to stay minimal.
"""

from __future__ import annotations

import re
from pathlib import Path


CONFIG_REL = Path(".scitex") / "dev" / "config.yaml"


def detect_scitex_dev_project_types(start_dir: Path) -> frozenset[str]:
    """Walk up from ``start_dir`` looking for ``.scitex/dev/config.yaml``.

    Returns the declared ``project-type`` set, or ``frozenset()`` when no
    config is found or the file does not declare ``project-type``.

    Mirrors the parent-walk loop used by ``LinterConfig._load_pyproject``
    so the linter's two config-resolution paths see the same root (one
    source of truth per repo).
    """
    current = start_dir
    while True:
        candidate = current / CONFIG_REL
        if candidate.is_file():
            return parse_project_types_from_yaml(candidate)
        parent = current.parent
        if parent == current:
            return frozenset()
        current = parent


def parse_project_types_from_yaml(path: Path) -> frozenset[str]:
    """Read ``path`` and return the ``project-type`` set.

    Schema-tolerant: handles scalar (``project-type: research``), inline
    list (``project-type: [research, pip]``), and block-list
    (``project-type:\\n  - research``) forms. Prefers PyYAML; falls back
    to a small regex parser sufficient for those three shapes so the
    linter does NOT take a hard PyYAML dep.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return frozenset()
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text) or {}
    except ImportError:
        return _parse_without_pyyaml(text)
    value = data.get("project-type")
    return _coerce_to_frozenset(value)


def _parse_without_pyyaml(text: str) -> frozenset[str]:
    """Regex fallback for the three admitted ``project-type`` shapes.

    Kept narrow on purpose — anything fancier than the three shapes
    documented in :func:`parse_project_types_from_yaml` should land on
    PyYAML, which the linter installs as a soft dep via the
    ``[skills]`` extra (and which is present in every CI matrix slot).
    """
    inline = re.search(r"^project-type\s*:\s*(.+)$", text, re.MULTILINE)
    if inline:
        return _coerce_inline_yaml(inline.group(1).strip())
    items: list[str] = []
    in_block = False
    for line in text.splitlines():
        if re.match(r"^project-type\s*:\s*$", line):
            in_block = True
            continue
        if in_block:
            match = re.match(r"^\s+-\s*(\S+)\s*$", line)
            if match:
                items.append(match.group(1))
            else:
                break
    return frozenset(items)


def _coerce_inline_yaml(raw: str) -> frozenset[str]:
    """Coerce a single-line YAML value into a frozenset of strings."""
    if raw.startswith("[") and raw.endswith("]"):
        return frozenset(
            item.strip().strip('"').strip("'")
            for item in raw[1:-1].split(",")
            if item.strip()
        )
    return frozenset({raw.strip().strip('"').strip("'")})


def _coerce_to_frozenset(value) -> frozenset[str]:
    """Coerce a PyYAML-parsed value into a frozenset of strings.

    Empty / missing → empty set. String → singleton. List/tuple/set →
    set of stringified items. Anything else → empty set (defensive — we
    do not want a malformed schema to crash the linter).
    """
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(str(v) for v in value)
    return frozenset()


__all__ = [
    "CONFIG_REL",
    "detect_scitex_dev_project_types",
    "parse_project_types_from_yaml",
]
