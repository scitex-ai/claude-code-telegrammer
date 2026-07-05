"""reStructuredText (`*.rst`) linting — extract Python code-block
directives and lint each one.

Mirrors the shape of ``_md.py`` / ``_ipynb.py``. Recognised directives:

- ``.. code-block:: python`` (Sphinx)
- ``.. code:: python``       (docutils)
- ``.. sourcecode:: python`` (docutils)
- ``.. ipython:: python``    (Sphinx ipython)

Directive options (``:linenos:``, ``:emphasize-lines:``, …) are
skipped, then the contiguous indented block is captured, dedented, and
linted.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from ._md import _SNIPPET_SKIP_RULES

_DIRECTIVE_RE = re.compile(
    r"^(?P<indent>[ \t]*)\.\. (?:code-block|code|sourcecode|ipython)::"
    r"[ \t]*(?:python|py)\b[^\n]*\n",
    re.IGNORECASE,
)


def _iter_python_blocks(text: str):
    """Yield ``(block_index, start_line, body)`` for each python directive.

    ``start_line`` is 1-indexed and points at the first body line so
    issue line numbers map back to source.
    """
    lines = text.splitlines(keepends=True)
    block_idx = 0
    i = 0
    while i < len(lines):
        m = _DIRECTIVE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        directive_indent = len(m.group("indent"))
        i += 1
        # Skip directive options (``:linenos:`` etc.) and the mandatory
        # blank line that separates the directive from the body.
        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped or stripped.startswith(":"):
                i += 1
                continue
            break
        # Capture body: contiguous lines indented strictly more than
        # the directive itself (blank lines preserved within the block).
        body_start = i
        body_lines: list = []
        while i < len(lines):
            line = lines[i]
            if line.strip() == "":
                body_lines.append(line)
                i += 1
                continue
            line_indent = len(line) - len(line.lstrip(" \t"))
            if line_indent <= directive_indent:
                break
            body_lines.append(line)
            i += 1
        # Trim trailing blank lines from the captured body.
        while body_lines and body_lines[-1].strip() == "":
            body_lines.pop()
        if not body_lines:
            continue
        body = textwrap.dedent("".join(body_lines))
        yield block_idx, body_start + 1, body
        block_idx += 1


def lint_rst(path: Path, config=None) -> list:
    """Lint Python ``code-block`` directives inside an RST file.

    Issue filepaths are tagged ``"/path/to/index.rst::block-N"``.
    """
    from .checker import lint_source

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    issues: list = []
    for idx, start_line, body in _iter_python_blocks(text):
        if not body.strip():
            continue
        fake_path = f"{path}::block-{idx}"
        block_issues = lint_source(body, filepath=fake_path, config=config)
        for iss in block_issues:
            if iss.rule.id in _SNIPPET_SKIP_RULES:
                continue
            iss.line = start_line + (iss.line - 1)
            issues.append(iss)
    return issues


# EOF
