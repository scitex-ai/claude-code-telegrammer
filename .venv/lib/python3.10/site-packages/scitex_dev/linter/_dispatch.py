"""Filetype dispatch for ``lint_file``.

Routes paths to the right extractor:
- ``.ipynb``                -> ``_ipynb.lint_ipynb`` (notebook cells)
- ``.md`` / ``.markdown``   -> ``_md.lint_md`` (fenced ``python`` blocks)
- everything else           -> ``lint_source`` on the raw text

Lives outside ``checker.py`` so the orchestrator stays under the line
budget and so each filetype handler can grow independently.
"""

from __future__ import annotations

from pathlib import Path


def lint_file(filepath: str, config=None) -> list:
    """Lint a Python file, Jupyter notebook, or markdown file.

    Returns a list of ``Issue`` objects. Missing files yield ``[]``.
    """
    from .checker import lint_source

    path = Path(filepath)
    if not path.exists() or not path.is_file():
        return []

    suffix = path.suffix.lower()
    if suffix == ".ipynb":
        from ._ipynb import lint_ipynb

        return lint_ipynb(path, config=config)
    if suffix in (".md", ".markdown"):
        from ._md import lint_md

        return lint_md(path, config=config)
    if suffix == ".rst":
        from ._rst import lint_rst

        return lint_rst(path, config=config)

    source = path.read_text(encoding="utf-8")
    return lint_source(source, filepath=str(path), config=config)


# EOF
