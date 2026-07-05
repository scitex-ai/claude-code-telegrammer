"""Markdown (`*.md`) linting — extract fenced ``python`` code blocks
and lint each one.

Mirrors the shape of ``_ipynb.py``. Each fenced block is linted as if
it were its own file; the reported filepath is suffixed
``::block-N`` so downstream tooling can map back to source.

Structural rules (missing main guard, missing module docstring, etc.)
do not apply to README snippets, so the same skip set used for
notebook cells is applied here.
"""

from __future__ import annotations

import re
from pathlib import Path

# Same skip set as `_ipynb.py`. Notebook cells and README snippets are
# *interactive examples*, not scripts, so structural rules are noise.
_SNIPPET_SKIP_RULES = {
    "STX-S001",  # Missing shebang
    "STX-S002",  # Missing `if __name__ == '__main__'` guard
    "STX-S003",  # Missing module docstring
    "STX-S004",  # Missing EOF marker
    "STX-S005",  # Missing timestamp
}

# Match fenced blocks tagged ``python`` or ``py`` (case-insensitive).
# Captures (lang, body, start_line) so issue line numbers remain
# meaningful relative to the original markdown file.
_FENCE_RE = re.compile(
    r"^([ \t]{0,3})```[ \t]*(python|py)\b[^\n]*\n(.*?)^[ \t]{0,3}```",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _iter_python_blocks(text: str):
    """Yield ``(block_index, fence_line, body)`` for each python fence.

    ``fence_line`` is 1-indexed and points at the line *after* the
    opening fence so issue line numbers map back to source.
    """
    for idx, match in enumerate(_FENCE_RE.finditer(text)):
        body = match.group(3)
        # Lines before the body — the fence opens on its own line, so
        # body's first character is on (lines_before_match + 2).
        lines_before = text.count("\n", 0, match.start())
        yield idx, lines_before + 2, body


def lint_md(path: Path, config=None) -> list:
    """Lint a markdown file's fenced ``python`` blocks.

    Issue filepaths are tagged ``"/path/to/README.md::block-N"``.
    """
    from .checker import lint_source

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    issues: list = []
    for idx, fence_line, body in _iter_python_blocks(text):
        if not body.strip():
            continue
        fake_path = f"{path}::block-{idx}"
        block_issues = lint_source(body, filepath=fake_path, config=config)
        # Filter snippet-irrelevant rules and shift line numbers so the
        # report points back at the markdown file's actual line.
        for iss in block_issues:
            if iss.rule.id in _SNIPPET_SKIP_RULES:
                continue
            iss.line = fence_line + (iss.line - 1)
            issues.append(iss)
    return issues


# EOF
