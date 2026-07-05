"""Import-statement visitors for SciTeXChecker.

Covers the import-hygiene rules (STX-I001/I002/I003/I006/I007), the
no-mock import rules (NM001/NM003), STX-S003 (argparse in scripts), and
STX-I008 (cross-package private-submodule imports).
"""

from __future__ import annotations

import ast
import re

from .. import rules
from .._rules import lookup as _lk

# ---------------------------------------------------------------------------
# STX-I008 — own-package detection + cross-package private-import predicate
# ---------------------------------------------------------------------------

# A top-level scitex distribution package, e.g. ``scitex_gen`` / ``scitex_io``.
# The umbrella ``scitex`` itself is included (``scitex._foo``). We match
# ``scitex`` or ``scitex_<word>`` followed by a ``._<private>`` segment.
_SCITEX_PKG_RE = re.compile(r"^(scitex(?:_[a-zA-Z0-9]+)?)\b")


def own_scitex_package(filepath: str) -> str | None:
    """Return the scitex_* distribution package a file belongs to, else None.

    Derived from the path: the segment immediately following a ``src``
    directory, or otherwise the nearest ancestor directory that is itself
    a ``scitex`` / ``scitex_<word>`` package. Examples::

        src/scitex_io/_save_modules/_csv.py -> "scitex_io"
        scitex_io/io/_save.py              -> "scitex_io"
        tests/test_foo.py                  -> None
    """
    if not filepath or filepath == "<stdin>":
        return None
    from pathlib import Path

    parts = Path(filepath).parts
    # Prefer the package right after a `src/` directory.
    for i, seg in enumerate(parts[:-1]):
        if seg == "src" and i + 1 < len(parts):
            cand = parts[i + 1]
            if _SCITEX_PKG_RE.match(cand) and cand == _SCITEX_PKG_RE.match(cand).group(
                1
            ):
                return cand
    # Fall back to the nearest ancestor dir that is a scitex package.
    for seg in reversed(parts[:-1]):
        m = _SCITEX_PKG_RE.match(seg)
        if m and m.group(1) == seg:
            return seg
    return None


def cross_pkg_private_import(module: str, own_package: str | None) -> str | None:
    """If *module* reaches into a PEER scitex package's private submodule,
    return that peer package name; otherwise return None.

    A match requires:
      - module path starts with ``scitex`` / ``scitex_<word>``;
      - the very next segment is underscore-prefixed (a private submodule);
      - the scitex package differs from *own_package* (same-package private
        imports are allowed).
    """
    if not module:
        return None
    m = _SCITEX_PKG_RE.match(module)
    if not m:
        return None
    pkg = m.group(1)
    rest = module[len(pkg) :]
    # Need a `._<private>` segment immediately after the package.
    if not rest.startswith("."):
        return None
    next_seg = rest[1:].split(".", 1)[0]
    if not next_seg.startswith("_"):
        return None
    # Dunder paths (e.g. scitex.__version__) are public-ish API; skip.
    if next_seg.startswith("__"):
        return None
    if pkg == own_package:
        return None
    return pkg


class ImportChecksMixin:
    """Import / from-import visitors. Expects host to provide ``_add``,
    ``_get_source``, ``_imports``, ``_is_script``, ``_own_package``,
    ``_has_stx_import``."""

    # Mock-related module / symbol names. The no-mock rule is intentionally
    # exception-free: any presence of these in a SciTeX codebase is a
    # violation.
    _MOCK_MODULES = frozenset({"mock", "unittest.mock", "pytest_mock"})
    _MOCK_SYMBOLS = frozenset(
        {
            "Mock",
            "MagicMock",
            "AsyncMock",
            "NonCallableMock",
            "NonCallableMagicMock",
            "PropertyMock",
            "patch",
            "mock_open",
            "create_autospec",
            "sentinel",
            "ANY",
            "MockerFixture",
        }
    )
    _MOCK_FIXTURE_PARAMS = frozenset({"mocker", "monkeypatch"})

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self._imports[name] = alias.name

            if alias.name == "scitex":
                self._has_stx_import = True

            self._check_import(alias.name, node)

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            name = alias.asname or alias.name
            full = f"{module}.{alias.name}"
            self._imports[name] = full

        self._check_import_from(module, node)
        self.generic_visit(node)

    def _check_import(self, module_name: str, node: ast.Import) -> None:
        """Check bare `import X` statements."""
        line = self._get_source(node.lineno)

        # import matplotlib.pyplot as plt
        if "matplotlib.pyplot" in module_name:
            self._add(_lk("STX-I001"), node.lineno, node.col_offset, line)

        if module_name == "argparse" and self._is_script:
            self._add(_lk("STX-S003"), node.lineno, node.col_offset, line)

        if module_name == "pickle":
            self._add(_lk("STX-I003"), node.lineno, node.col_offset, line)

        if module_name == "random":
            self._add(_lk("STX-I006"), node.lineno, node.col_offset, line)

        if module_name == "logging":
            self._add(_lk("STX-I007"), node.lineno, node.col_offset, line)

        # STX-I009 — prohibit direct seaborn import (use stx.plt /
        # figrecipe wrappers instead). Per neurovista elevation 2026-06-14.
        # Matches both `import seaborn` and `import seaborn as sns`. The
        # bare module-name compare is enough — Python's import machinery
        # collapses dotted-vs-dotless for the top-level name.
        if module_name == "seaborn":
            self._add(_lk("STX-I009"), node.lineno, node.col_offset, line)

        # STX-P010 — record a top-level figrecipe import (`import figrecipe`
        # / `import figrecipe as fr` / `import figrecipe.sub`). Whether it
        # actually flags is decided in get_issues() once we know the module
        # is @stx.session-decorated — at this point the session `def main`
        # further down may not be visited yet. We match the top-level name
        # (incl. dotted submodule imports) so e.g. `import figrecipe.style`
        # is also recorded.
        if module_name == "figrecipe" or module_name.startswith("figrecipe."):
            self._figrecipe_usages.append((node.lineno, node.col_offset, line))

        # NM001 — no-mock imports (no exceptions)
        if module_name in self._MOCK_MODULES:
            self._add(rules.NM001, node.lineno, node.col_offset, line)

        # I008 — cross-package private-submodule import (e.g.
        # `import scitex_io._save`)
        if cross_pkg_private_import(module_name, self._own_package):
            self._add(_lk("STX-I008"), node.lineno, node.col_offset, line)

    def _check_import_from(self, module: str, node: ast.ImportFrom) -> None:
        """Check `from X import Y` statements."""
        line = self._get_source(node.lineno)

        # from matplotlib import pyplot / from matplotlib.pyplot import *
        if module == "matplotlib":
            for alias in node.names:
                if alias.name == "pyplot":
                    self._add(_lk("STX-I001"), node.lineno, node.col_offset, line)
                    break
        elif module and "matplotlib.pyplot" in module:
            self._add(_lk("STX-I001"), node.lineno, node.col_offset, line)

        # from scipy import stats / from scipy.stats import *
        if module in ("scipy", "scipy.stats"):
            if module == "scipy":
                for alias in node.names:
                    if alias.name == "stats":
                        self._add(_lk("STX-I002"), node.lineno, node.col_offset, line)
                        break
            else:
                self._add(_lk("STX-I002"), node.lineno, node.col_offset, line)

        # from argparse import *
        if module == "argparse" and self._is_script:
            self._add(_lk("STX-S003"), node.lineno, node.col_offset, line)

        # STX-P010 — `from figrecipe import subplots` (and friends). Recorded
        # for the get_issues() session-gated emit, same as the bare-import
        # case in _check_import. Covers `figrecipe` and any submodule
        # (`from figrecipe.style import ...`).
        if module == "figrecipe" or (module or "").startswith("figrecipe."):
            self._figrecipe_usages.append((node.lineno, node.col_offset, line))

        # NM001 — no-mock imports (no exceptions)
        if module in self._MOCK_MODULES:
            self._add(rules.NM001, node.lineno, node.col_offset, line)
        elif module == "unittest":
            for alias in node.names:
                if alias.name == "mock":
                    self._add(rules.NM001, node.lineno, node.col_offset, line)
                    break

        # NM003 — mock symbols imported by name (Mock, MagicMock, patch, ...).
        for alias in node.names:
            if alias.name in self._MOCK_SYMBOLS:
                self._add(rules.NM003, node.lineno, node.col_offset, line)
                break

        # I008 — cross-package private-submodule import. Two shapes:
        #   from scitex_io._save import save     (module is private)
        #   from scitex_io import _save           (importing a private name)
        if cross_pkg_private_import(module, self._own_package):
            self._add(_lk("STX-I008"), node.lineno, node.col_offset, line)
        else:
            m = _SCITEX_PKG_RE.match(module or "")
            if m and m.group(1) == module and module != self._own_package:
                # `from scitex_io import _private_name`
                for alias in node.names:
                    if alias.name.startswith("_") and not alias.name.startswith("__"):
                        self._add(_lk("STX-I008"), node.lineno, node.col_offset, line)
                        break
