"""SciTeX-dev CLI: quality / audit subcommands.

- `_check`       — top-level quality audits (audit-docs, audit-scope, audit-lines, lint_pyproject)
- `_frontmatter` — frontmatter shape audits
"""

from . import _check, _frontmatter

__all__ = ["_check", "_frontmatter"]
