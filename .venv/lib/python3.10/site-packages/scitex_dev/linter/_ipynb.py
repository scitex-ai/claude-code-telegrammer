"""Jupyter notebook (.ipynb) linting support — extract code cells and lint.

Scholar-linter Phase 1 for issue #7. Phase 2 (notebook-specific rules
like `NB001`: raw-matplotlib in code cell) to follow in a dedicated
checker class.

Uses stdlib `json` — no nbformat dependency. Each code cell is linted
independently by reusing `lint_source`; the reported filepath is
suffixed `::cell-N` so downstream tooling can parse cell locations
back.
"""

from __future__ import annotations

import json
from pathlib import Path

# Rules that don't make sense per-cell in a notebook context.
# Notebooks are interactive; they have no `__main__` guard, no shebang,
# and rarely a top-level docstring per cell.
_NOTEBOOK_SKIP_RULES = {
    "STX-S001",  # Missing shebang
    "STX-S002",  # Missing `if __name__ == '__main__'` guard
    "STX-S003",  # Missing module docstring
    "STX-S004",  # Missing EOF marker
    "STX-S005",  # Missing timestamp
}


def lint_ipynb(path: Path, config=None) -> list:
    """Lint a Jupyter notebook by extracting code cells and running
    `lint_source` on each. Returns a flat list of Issue objects.

    Issue filepaths are of the form ``"/path/to/notebook.ipynb::cell-N"``.
    """
    from .checker import lint_source

    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    issues: list = []
    cells = nb.get("cells", []) or []
    for i, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue
        src_val = cell.get("source", "")
        source = "".join(src_val) if isinstance(src_val, list) else src_val
        if not source.strip():
            continue
        fake_path = f"{path}::cell-{i}"
        cell_issues = lint_source(source, filepath=fake_path, config=config)
        issues.extend(
            iss for iss in cell_issues if iss.rule.id not in _NOTEBOOK_SKIP_RULES
        )
    return issues


# EOF
