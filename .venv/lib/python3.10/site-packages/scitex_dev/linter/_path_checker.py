"""Path argument checks for stx.io.save() / stx.io.load() calls."""

import ast

from . import rules


def check_stx_io_path(checker, node: ast.Call) -> None:
    """Check path arguments in stx.io.save() / stx.io.load() calls."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return

    func_name = func.attr

    # Determine which positional arg holds the path
    # stx.io.save(obj, path, ...) -> index 1
    # stx.io.load(path, ...) -> index 0
    if func_name == "save":
        path_idx = 1
    elif func_name == "load":
        path_idx = 0
    else:
        return

    # Check if this is stx.io.save/load (not stx.plt.save, etc.)
    is_stx_io = False
    if isinstance(func.value, ast.Attribute):
        if (
            isinstance(func.value.value, ast.Name)
            and func.value.value.id in ("stx", "scitex", "scitex_io")
            and func.value.attr == "io"
        ):
            is_stx_io = True
    elif isinstance(func.value, ast.Name):
        # scitex_io.save(...) — bare top-level package call
        if func.value.id == "scitex_io":
            is_stx_io = True
        else:
            # io.save(...) if io was imported from stx
            resolved = checker._imports.get(func.value.id, "")
            if "scitex" in resolved and "io" in resolved:
                is_stx_io = True

    if not is_stx_io:
        return

    # Extract path string from positional args or 'path' kwarg
    path_str = None
    if len(node.args) > path_idx:
        arg = node.args[path_idx]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            path_str = arg.value
    else:
        for kw in node.keywords:
            if kw.arg == "path":
                if isinstance(kw.value, ast.Constant) and isinstance(
                    kw.value.value, str
                ):
                    path_str = kw.value.value
                break

    if path_str is None:
        return

    line = checker._get_source(node.lineno)

    # PA-001: absolute path
    if path_str.startswith("/"):
        checker._add(rules.PA001, node.lineno, node.col_offset, line)
    # PA-005: missing ./ prefix (bare relative path)
    elif not path_str.startswith("./") and not path_str.startswith("../"):
        checker._add(rules.PA005, node.lineno, node.col_offset, line)
