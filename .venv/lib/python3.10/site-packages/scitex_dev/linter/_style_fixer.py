"""AST-based fixes for style-override rules and non-reproducible calls.

Targets a specific class of safe edits — pure deletions, no substitutions
— so a regex-style `linewidth=0.8` cannot be partially eaten the way
non-greedy regex does.

Rules covered:
- ``STX-FM002`` — drops standalone ``plt.tight_layout()`` lines
- ``STX-P004``  — drops standalone ``plt.show()`` lines
- ``STX-P006``  — drops ``s=`` kwarg in ``scatter`` / ``stx_scatter`` calls
- ``STX-P007``  — drops ``fontsize=`` kwarg from any call
- ``STX-P008``  — drops ``figsize=`` kwarg from any call
- ``STX-P009``  — drops ``linewidth=`` / ``lw=`` kwarg from any call

If applying the deletions produces a syntax-invalid result, the fixer
rolls back and returns the original source. The caller never sees a
broken file.
"""

from __future__ import annotations

import ast

_DROP_KWARGS = ("fontsize", "figsize", "linewidth", "lw")
_SCATTER_NAMES = ("scatter", "stx_scatter")
_DROP_LINE_CALLS = (
    ("plt", "tight_layout"),
    ("plt", "show"),
)


def _line_offsets(source: str) -> list:
    """Map 1-based lineno → byte index of that line's start."""
    out = [0]
    for i, ch in enumerate(source):
        if ch == "\n":
            out.append(i + 1)
    return out


def _pos_to_offset(offsets: list, lineno: int, col: int) -> int:
    return offsets[lineno - 1] + col


def _find_kwarg_deletions(tree: ast.AST, source: str, offsets: list) -> list:
    """Return list of ``(start_offset, end_offset)`` ranges to delete."""
    deletions: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            fname = node.func.attr
        elif isinstance(node.func, ast.Name):
            fname = node.func.id
        else:
            fname = ""
        for kw in node.keywords:
            if kw.arg is None:
                continue
            target = kw.arg in _DROP_KWARGS or (
                kw.arg == "s" and fname in _SCATTER_NAMES
            )
            if not target:
                continue
            kw_value_start = _pos_to_offset(
                offsets, kw.value.lineno, kw.value.col_offset
            )
            name_offset = source.rfind(kw.arg, 0, kw_value_start)
            if name_offset < 0:
                continue
            value_end = _pos_to_offset(
                offsets,
                kw.value.end_lineno or kw.value.lineno,
                kw.value.end_col_offset or kw.value.col_offset,
            )
            del_start, del_end = name_offset, value_end
            # Swallow preceding `,` or trailing `,` depending on which
            # delimiter borders the kwarg.
            i = del_start - 1
            while i >= 0 and source[i] in " \t":
                i -= 1
            if i >= 0 and source[i] == ",":
                del_start = i
            elif i >= 0 and source[i] == "(":
                k = del_end
                while k < len(source) and source[k] in " \t":
                    k += 1
                if k < len(source) and source[k] == ",":
                    del_end = k + 1
                    while del_end < len(source) and source[del_end] in " \t":
                        del_end += 1
            deletions.append((del_start, del_end))
    return deletions


def _find_line_call_deletions(tree: ast.AST, source: str, offsets: list) -> list:
    """Return ``(start_offset, end_offset)`` whole-line ranges for FM002/P004."""
    deletions: list = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        if not isinstance(func.value, ast.Name):
            continue
        if (func.value.id, func.attr) not in _DROP_LINE_CALLS:
            continue
        start = _pos_to_offset(offsets, node.lineno, 0)
        end_line = node.end_lineno or node.lineno
        end = offsets[end_line] if end_line < len(offsets) else len(source)
        deletions.append((start, end))
    return deletions


def fix_style(source: str) -> str:
    """Apply all style-override deletions. Returns the new source.

    On any failure (parse error in input, parse error after edits) the
    original ``source`` is returned unchanged.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    offsets = _line_offsets(source)
    dels = _find_kwarg_deletions(tree, source, offsets) + _find_line_call_deletions(
        tree, source, offsets
    )
    if not dels:
        return source
    dels.sort(key=lambda r: r[0], reverse=True)
    out = source
    for start, end in dels:
        out = out[:start] + out[end:]
    try:
        ast.parse(out)
    except SyntaxError:
        return source
    return out


# EOF
