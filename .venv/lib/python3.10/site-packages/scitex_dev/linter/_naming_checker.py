"""Naming convention and hardcoding checks for SciTeX linter.

Rules:
  _lk("STX-S007") — load_configs() result should use UPPER_CASE variable name
  _lk("STX-S008") — Magic number in module scope; consider moving to config/
"""

import ast

from ._rules import lookup as _lk

# Trivial numeric constants that are not magic numbers
_TRIVIAL_NUMBERS = frozenset({0, 1, -1, 0.0, 1.0, -1.0, 2, 0.5, 100})

# Variable names that commonly hold non-config numeric values
_SKIP_NAMES = frozenset(
    {
        "i",
        "j",
        "k",
        "n",
        "x",
        "y",
        "z",
        "idx",
        "count",
        "step",
        "argc",
        "pid",
        "fd",
        "rc",
        "status",
        "exit_code",
        "retval",
    }
)


def check_assignment(checker, node: ast.Assign) -> None:
    """Run all assignment-level checks."""
    check_config_naming(checker, node)
    if checker._is_script:
        check_magic_numbers(checker, node)


def check_config_naming(checker, node: ast.Assign) -> None:
    """Warn when load_configs() result is assigned to a non-UPPER_CASE name."""
    if not isinstance(node.value, ast.Call):
        return

    func = node.value.func
    is_load_configs = False

    # bare load_configs()
    if isinstance(func, ast.Name) and func.id == "load_configs":
        is_load_configs = True
    # stx.io.load_configs() / scitex.io.load_configs() / any.load_configs()
    elif isinstance(func, ast.Attribute) and func.attr == "load_configs":
        is_load_configs = True

    if not is_load_configs:
        return

    for target in node.targets:
        if isinstance(target, ast.Name) and not target.id.isupper():
            line = checker._get_source(node.lineno)
            checker._add(_lk("STX-S007"), node.lineno, node.col_offset, line)


def check_magic_numbers(checker, node: ast.Assign) -> None:
    """Warn on UPPER_CASE = <numeric literal> in module scope (not inside functions).

    Only fires for assignments that look like user-defined constants:
    - UPPER_CASE variable name
    - Numeric literal value (int or float)
    - Module scope only (not inside a function or class body)
    - Not a trivial value (0, 1, -1, etc.)
    """
    # Only at module scope
    if checker._func_depth > 0:
        return

    # Only check simple name targets
    if len(node.targets) != 1:
        return
    target = node.targets[0]
    if not isinstance(target, ast.Name):
        return

    name = target.id

    # Skip non-UPPER_CASE names (lowercase assignments are fine — they're local vars)
    # We specifically want to catch UPPER_CASE = 256 patterns (user-defined constants)
    if not name.isupper() or name.startswith("_"):
        return

    # Skip names that are clearly not config values
    if name in _SKIP_NAMES:
        return

    # Check if value is a numeric literal
    value = node.value
    if not isinstance(value, ast.Constant):
        return
    if not isinstance(value.value, (int, float)):
        return

    # Skip trivial numbers
    if value.value in _TRIVIAL_NUMBERS:
        return

    line = checker._get_source(node.lineno)
    checker._add(_lk("STX-S008"), node.lineno, node.col_offset, line)
