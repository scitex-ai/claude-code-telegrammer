"""Auto-fix SciTeX pattern issues in Python source code.

Currently handles:
  - S006: Insert missing INJECTED parameters into @stx.session functions.
  - IO001-IO003, IO007: Replace np.save/load, pd.read_csv, savefig with stx.io.
"""

__all__ = ["fix_file", "fix_source"]

import ast
import re
from pathlib import Path

# The 5 required INJECTED parameters (in canonical order) — default fallback
REQUIRED_INJECTED = ["CONFIG", "plt", "COLORS", "rngg", "logger"]

# Canonical default value for injected params
_INJECTED_DEFAULT = "stx.session.INJECTED"


# =========================================================================
# AST helpers
# =========================================================================


def _has_session_decorator(node: ast.FunctionDef) -> bool:
    """Return True if function has @stx.session or @session decorator."""
    for deco in node.decorator_list:
        if isinstance(deco, ast.Attribute):
            if (
                isinstance(deco.value, ast.Name)
                and deco.value.id in ("stx", "scitex")
                and deco.attr == "session"
            ):
                return True
        if isinstance(deco, ast.Name) and deco.id == "session":
            return True
    return False


def _declared_params(node: ast.FunctionDef) -> list:
    """Return list of parameter names declared in the function signature."""
    return [arg.arg for arg in node.args.args]


def _missing_injected(declared: list, required: list = None) -> list:
    """Return INJECTED param names not yet declared, preserving canonical order."""
    required = required if required is not None else REQUIRED_INJECTED
    declared_set = set(declared)
    return [p for p in required if p not in declared_set]


def _is_injected_value(default_node: ast.expr) -> bool:
    """Check if a default value is stx.session.INJECTED or stx.INJECTED."""
    # stx.session.INJECTED
    if isinstance(default_node, ast.Attribute) and default_node.attr == "INJECTED":
        inner = default_node.value
        if isinstance(inner, ast.Attribute):
            if (
                isinstance(inner.value, ast.Name)
                and inner.value.id in ("stx", "scitex")
                and inner.attr == "session"
            ):
                return True
        # stx.INJECTED
        if isinstance(inner, ast.Name) and inner.id in ("stx", "scitex"):
            return True
    return False


def _is_canonical_injected(default_node: ast.expr) -> bool:
    """Check if a default value is the canonical stx.session.INJECTED form."""
    if isinstance(default_node, ast.Attribute) and default_node.attr == "INJECTED":
        inner = default_node.value
        if isinstance(inner, ast.Attribute):
            if (
                isinstance(inner.value, ast.Name)
                and inner.value.id in ("stx", "scitex")
                and inner.attr == "session"
            ):
                return True
    return False


def _has_non_canonical_injected(node: ast.FunctionDef, required: list = None) -> bool:
    """Check if any INJECTED param uses stx.INJECTED instead of stx.session.INJECTED."""
    args = node.args.args
    defaults = node.args.defaults
    n_positional = len(args) - len(defaults)
    injected_set = set(required if required is not None else REQUIRED_INJECTED)

    for i, arg in enumerate(args):
        if arg.arg not in injected_set:
            continue
        default_idx = i - n_positional
        if default_idx >= 0:
            default = defaults[default_idx]
            if _is_injected_value(default) and not _is_canonical_injected(default):
                return True
    return False


# =========================================================================
# Source-level fix for S006
# =========================================================================


def _find_def_line_range(lines: list, func_node: ast.FunctionDef) -> tuple:
    """Find the line range (0-indexed) of the 'def ...:' signature.

    Returns (start_line_idx, colon_line_idx) where:
      - start_line_idx is the line containing 'def '
      - colon_line_idx is the line containing the closing '):'
    """
    start = func_node.lineno - 1  # 0-indexed

    # Walk forward from start to find the colon that opens the body
    # The body starts at func_node.body[0].lineno
    body_start = func_node.body[0].lineno - 1 if func_node.body else start + 1

    # The colon line is somewhere between start and body_start
    # Scan backwards from body_start to find the line with ':'
    colon_line = start
    for i in range(body_start - 1, start - 1, -1):
        stripped = lines[i].rstrip()
        if stripped.endswith(":"):
            colon_line = i
            break

    return start, colon_line


def _fix_s006_in_source(source: str, filepath: str, config=None) -> str:
    """Fix S006 violations: add missing INJECTED params to @stx.session functions."""
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return source

    required = config.required_injected if config else REQUIRED_INJECTED

    lines = source.splitlines(keepends=True)
    # Ensure the last line has a newline
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    # Collect all session functions that need fixing (process in reverse order
    # so line indices remain valid after edits)
    fixes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _has_session_decorator(node):
                declared = _declared_params(node)
                missing = _missing_injected(declared, required)
                needs_normalize = _has_non_canonical_injected(node, required)
                if missing or needs_normalize:
                    fixes.append((node, missing))

    # Sort by line number descending so we edit from bottom to top
    fixes.sort(key=lambda x: x[0].lineno, reverse=True)

    for func_node, missing in fixes:
        lines = _apply_s006_fix(lines, func_node, missing, required)

    return "".join(lines)


def _get_def_indent(line: str) -> str:
    """Extract the leading whitespace from a 'def' line."""
    match = re.match(r"^(\s*)", line)
    return match.group(1) if match else ""


def _apply_s006_fix(
    lines: list,
    func_node: ast.FunctionDef,
    missing: list,
    required_injected: list = None,
) -> list:
    """Apply S006 fix to a single function in the source lines.

    Strategy:
    1. Find the def line range (from 'def' to the closing ':')
    2. Determine if it's single-line or multi-line
    3. Extract user params and existing injected params from source text
    4. Rebuild the signature with all params
    """
    if required_injected is None:
        required_injected = REQUIRED_INJECTED
    start_idx, colon_idx = _find_def_line_range(lines, func_node)
    def_indent = _get_def_indent(lines[start_idx])
    param_indent = def_indent + "    "

    # Determine if async
    is_async = isinstance(func_node, ast.AsyncFunctionDef)
    keyword = "async def" if is_async else "def"

    # Extract the function name
    func_name = func_node.name

    # Get all existing params with their source text
    # Join the def signature lines
    sig_text = "".join(lines[start_idx : colon_idx + 1])

    # Extract content between parentheses
    paren_open = sig_text.index("(")
    # Find the matching close paren (searching backward from the colon)
    paren_close = sig_text.rindex(")")
    params_text = sig_text[paren_open + 1 : paren_close].strip()

    # Parse individual parameter strings from the source text
    existing_param_strings = _split_params(params_text)

    # Classify params: user params vs injected params
    injected_names = set(required_injected)
    user_param_strings = []
    existing_injected_strings = []

    for ps in existing_param_strings:
        pname = ps.strip().split("=")[0].split(":")[0].strip()
        if pname in injected_names:
            existing_injected_strings.append(ps)
        elif pname:
            user_param_strings.append(ps)

    # Build new parameter lines
    new_param_lines = []

    # User params first (preserve original text)
    for ps in user_param_strings:
        new_param_lines.append(f"{param_indent}{ps.strip()},\n")

    # All INJECTED params in canonical order (existing + missing)
    existing_injected_names = set()
    for ps in existing_injected_strings:
        pname = ps.strip().split("=")[0].split(":")[0].strip()
        existing_injected_names.add(pname)

    for p in required_injected:
        if p in existing_injected_names or p in missing:
            new_param_lines.append(f"{param_indent}{p}={_INJECTED_DEFAULT},\n")

    # Build the new def statement
    new_lines = []
    new_lines.append(f"{def_indent}{keyword} {func_name}(\n")
    new_lines.extend(new_param_lines)
    new_lines.append(f"{def_indent}):\n")

    # Replace old def lines with new ones
    lines[start_idx : colon_idx + 1] = new_lines

    return lines


def _split_params(params_text: str) -> list:
    """Split a parameter string respecting nested parentheses and brackets.

    Handles cases like:
      'x=1, y="hello, world"'
      'x=dict(a=1, b=2), y=3'
    """
    if not params_text.strip():
        return []

    params = []
    depth = 0
    current = []
    in_string = None

    for ch in params_text:
        if in_string:
            current.append(ch)
            if ch == in_string:
                in_string = None
            continue

        if ch in ('"', "'"):
            in_string = ch
            current.append(ch)
            continue

        if ch in ("(", "[", "{"):
            depth += 1
            current.append(ch)
        elif ch in (")", "]", "}"):
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            param = "".join(current).strip()
            if param:
                params.append(param)
            current = []
        else:
            current.append(ch)

    # Last param
    param = "".join(current).strip()
    if param:
        params.append(param)

    return params


# =========================================================================
# Source-level fix for IO rules (IO001-IO003, IO007)
# =========================================================================


def _source_offset(source: str, lineno: int, col_offset: int) -> int:
    """Convert (lineno, col_offset) to byte offset in source string."""
    lines = source.splitlines(keepends=True)
    offset = sum(len(lines[i]) for i in range(lineno - 1))
    return offset + col_offset


def _fix_io_in_source(source: str, filepath: str = "<stdin>") -> str:
    """Fix IO violations: savefig->stx.io.save, np.save/load, pd.read_csv."""
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return source

    replacements = []  # (start_offset, end_offset, new_text)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        func = node.func
        fname = func.attr
        if not isinstance(func.value, ast.Name):
            continue
        obj = func.value.id
        if obj in ("stx", "scitex"):
            continue

        seg = ast.get_source_segment(source, node)
        if seg is None:
            continue

        new = None
        if fname == "savefig" and node.args:
            arg0 = ast.get_source_segment(source, node.args[0])
            if arg0:
                new = f"stx.io.save({obj}, {arg0})"
        elif fname == "save" and obj in ("np", "numpy") and len(node.args) >= 2:
            arg0 = ast.get_source_segment(source, node.args[0])
            arg1 = ast.get_source_segment(source, node.args[1])
            if arg0 and arg1:
                new = f"stx.io.save({arg1}, {arg0})"
        elif fname == "load" and obj in ("np", "numpy") and node.args:
            arg0 = ast.get_source_segment(source, node.args[0])
            if arg0:
                new = f"stx.io.load({arg0})"
        elif fname == "read_csv" and obj in ("pd", "pandas") and node.args:
            arg0 = ast.get_source_segment(source, node.args[0])
            if arg0:
                new = f"stx.io.load({arg0})"

        if new:
            start = _source_offset(source, node.lineno, node.col_offset)
            replacements.append((start, start + len(seg), new))

    if not replacements:
        return source

    # Apply in reverse offset order to preserve positions
    replacements.sort(key=lambda x: x[0], reverse=True)
    for start, end, new in replacements:
        source = source[:start] + new + source[end:]

    # Ensure `import scitex as stx` is present if fixes were applied
    if "import scitex" not in source:
        source = "import scitex as stx\n" + source

    return source


# =========================================================================
# Public API
# =========================================================================


def fix_source(source: str, filepath: str = "<stdin>", config=None) -> str:
    """Auto-fix SciTeX issues in source code. Returns fixed source."""
    from ._style_fixer import fix_style

    source = _fix_s006_in_source(source, filepath, config=config)
    source = _fix_io_in_source(source, filepath)
    source = fix_style(source)
    return source


def _fix_notebook(path: Path, write: bool, config=None) -> tuple:
    import json

    nb = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        src_list = cell.get("source", [])
        src = "".join(src_list) if isinstance(src_list, list) else src_list
        new_src = fix_source(src, filepath=str(path), config=config)
        if new_src != src:
            cell["source"] = new_src.splitlines(keepends=True)
            changed = True
    if write and changed:
        path.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    return (nb, changed)


def fix_file(filepath: str, write: bool = True, config=None) -> tuple:
    """Fix a file in place. Returns (fixed_source, changed).

    Supports ``.py`` and ``.ipynb``. Notebooks are dispatched to
    ``_fix_notebook``; the returned ``fixed_source`` is the parsed
    notebook dict in that case.
    """
    path = Path(filepath)
    if not path.exists() or not path.is_file():
        return ("", False)

    if path.suffix == ".ipynb":
        return _fix_notebook(path, write=write, config=config)

    original = path.read_text(encoding="utf-8")
    fixed = fix_source(original, filepath=str(path), config=config)
    changed = fixed != original

    if write and changed:
        path.write_text(fixed, encoding="utf-8")

    return (fixed, changed)
