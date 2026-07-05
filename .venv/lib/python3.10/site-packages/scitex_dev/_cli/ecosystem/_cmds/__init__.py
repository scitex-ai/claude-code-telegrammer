"""Per-area subcommand modules for `scitex-dev ecosystem`.

Each module exports a ``register(ecosystem_group)`` callable that wires its
Click commands onto the shared ``ecosystem`` group. Split out of
``_registry.py`` to keep that file under the line-limit hook; see
GITIGNORED/REFACTORING.md (2026-05-16 entry).
"""
