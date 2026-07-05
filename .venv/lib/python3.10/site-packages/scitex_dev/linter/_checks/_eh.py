"""Try/except error-handling visitor for SciTeXChecker (STX-EH001)."""

from __future__ import annotations

import ast

from .. import rules


class ErrorHandlingMixin:
    """try/except EH001 visitor. Expects host ``_add`` / ``_get_source``."""

    # Stdlib modules where ImportError is the only realistic failure mode.
    # These are skipped to avoid false positives.
    _EH001_STDLIB_SKIP = frozenset(
        {
            "tomllib",
            "tomli",
            "importlib",
            "importlib.metadata",
            "importlib.resources",
            "typing_extensions",
            "typing",
            "zoneinfo",
            "backports",
            "argparse",
            "dataclasses",
            "pathlib",
            "asyncio",
            "contextlib",
            "functools",
            "itertools",
            "collections",
            "collections.abc",
            "enum",
            "json",
            "os",
            "sys",
            "re",
            "subprocess",
        }
    )

    def visit_Try(self, node: ast.Try) -> None:
        self._check_eh001(node)
        self.generic_visit(node)

    def _check_eh001(self, node: ast.Try) -> None:
        # Body must be exactly one statement: an Import / ImportFrom.
        if len(node.body) != 1:
            return
        stmt = node.body[0]
        if isinstance(stmt, ast.Import):
            mod_names = [alias.name for alias in stmt.names]
        elif isinstance(stmt, ast.ImportFrom):
            mod_names = [stmt.module] if stmt.module else []
        else:
            return

        # Skip stdlib-only imports (where narrow ImportError is correct).
        if mod_names and all(
            (m or "").split(".")[0] in self._EH001_STDLIB_SKIP for m in mod_names
        ):
            return

        if not node.handlers:
            return

        # Collect all exception types listed in handlers.
        narrow_only = True
        for handler in node.handlers:
            exc = handler.type
            names = self._extract_exc_names(exc)
            # Bare `except:` (exc is None) — broad, do not fire.
            if exc is None:
                return
            for n in names:
                # If any handler catches Exception/BaseException, rule does
                # not fire — already broad enough.
                if n in ("Exception", "BaseException"):
                    return
                if n not in ("ImportError", "ModuleNotFoundError"):
                    # Some other narrow exception is in play (e.g. OSError).
                    # Treat as not-purely-import-narrow; still fire only if
                    # the only types are ImportError/ModuleNotFoundError.
                    narrow_only = False

        if not narrow_only:
            return

        line = self._get_source(stmt.lineno)
        self._add(rules.EH001, stmt.lineno, stmt.col_offset, line)

    @staticmethod
    def _extract_exc_names(exc) -> list:
        """Flatten an exception type expression into a list of bare names."""
        if exc is None:
            return []
        if isinstance(exc, ast.Name):
            return [exc.id]
        if isinstance(exc, ast.Attribute):
            return [exc.attr]
        if isinstance(exc, ast.Tuple):
            out = []
            for elt in exc.elts:
                out.extend(ErrorHandlingMixin._extract_exc_names(elt))
            return out
        return []
