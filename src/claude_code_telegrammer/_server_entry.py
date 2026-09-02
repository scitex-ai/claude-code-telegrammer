#!/usr/bin/env python3
"""Resolve the canonical TypeScript server entry (``ts/telegram-server.ts``).

The Python package is a thin launcher: every command it offers ends in
``execv``-ing ``bun`` on ``ts/telegram-server.ts``. So the path to that file is
a load-bearing declaration, and a declaration that cannot be honoured must
FAIL, not evaporate.

It used to evaporate. ``_cli.py`` computed the entry as
``Path(__file__).resolve().parents[2] / "ts" / "telegram-server.ts"``, which is
only correct for a source checkout laid out as
``<repo>/src/claude_code_telegrammer/_cli.py``. Installed as a wheel into
``site-packages`` the same arithmetic lands on ``.../lib/python3.12``, and the
wheel did not ship ``ts/`` at all — so the CLI and the MCP server were both
structurally dead on every non-editable install, and said so only at first use
(``server entry not found at /opt/venv-sac/lib/python3.12/ts/telegram-server.ts``).

Resolution order, first hit wins:

1. ``$CCT_SERVER_ENTRY`` — an explicit operator override. If it is set it is
   AUTHORITATIVE: a value that does not name a readable file raises rather
   than silently falling through to a different server than the one asked
   for. Pointing somewhere wrong must be louder than not pointing at all.
2. The packaged resource ``claude_code_telegrammer/ts/telegram-server.ts``,
   located with :mod:`importlib.resources` against the installed package —
   never by ``__file__``-relative parent arithmetic.
3. The source-tree location ``<repo>/ts/telegram-server.ts``, walking up from
   this file, so an editable install or a plain checkout keeps working.

When nothing resolves, :class:`ServerEntryNotFound` names every path that was
tried and what to do about each one.
"""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

#: Environment variable that overrides server-entry resolution entirely.
ENV_SERVER_ENTRY = "CCT_SERVER_ENTRY"

#: Basename of the canonical TS entry point, relative to the ``ts`` directory.
SERVER_ENTRY_NAME = "telegram-server.ts"


class ServerEntryNotFound(RuntimeError):
    """Raised when no candidate resolves to a readable server entry.

    Carries the ordered list of attempted paths so the failure names what was
    tried instead of only what was missing.
    """

    def __init__(self, attempts: list[tuple[str, Path | None]]) -> None:
        self.attempts = list(attempts)
        super().__init__(self._render())

    def _render(self) -> str:
        headline = (
            "claude-code-telegrammer: the TypeScript server entry "
            f"({SERVER_ENTRY_NAME}) could not be resolved."
        )
        remedies = (
            f"    - point ${ENV_SERVER_ENTRY} at an existing ts/{SERVER_ENTRY_NAME}, or",
            (
                "    - reinstall claude-code-telegrammer from a wheel that"
                " ships the ts/ directory as package data, or"
            ),
            f"    - run from a source checkout that contains ts/{SERVER_ENTRY_NAME}.",
        )
        lines = [headline, "  tried, in order:"]
        for source, path in self.attempts:
            where = str(path) if path is not None else "(not set)"
            lines.append(f"    - {source}: {where}")
        lines.append("  what to do:")
        lines.extend(remedies)
        return "\n".join(lines)


def _override_candidate() -> Path | None:
    raw = os.environ.get(ENV_SERVER_ENTRY)
    if raw is None or not raw.strip():
        return None
    return Path(os.path.expanduser(raw.strip())).resolve()


def _packaged_candidate() -> Path | None:
    """Locate ``ts/telegram-server.ts`` shipped inside the installed package."""
    try:
        root = resources.files(__package__)
    except (ModuleNotFoundError, TypeError):  # pragma: no cover - defensive
        return None
    candidate = root / "ts" / SERVER_ENTRY_NAME
    try:
        # A wheel installed normally is an ordinary directory on disk, which is
        # what bun needs — a zipimport-backed Traversable has no filesystem
        # path and could not be exec'd anyway, so str() is the honest probe.
        return Path(str(candidate))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _source_tree_candidate() -> Path:
    """``<repo>/ts/telegram-server.ts`` for an editable install or checkout."""
    # <repo>/src/claude_code_telegrammer/_server_entry.py -> <repo>
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "ts" / SERVER_ENTRY_NAME


def candidate_paths() -> list[tuple[str, Path | None]]:
    """Return the ordered ``(source, path)`` candidates, resolved or not.

    Exposed so the failure message and the caller's diagnostics agree by
    construction rather than by two hand-maintained lists.
    """
    return [
        (f"${ENV_SERVER_ENTRY} override", _override_candidate()),
        ("packaged resource", _packaged_candidate()),
        ("source tree", _source_tree_candidate()),
    ]


def resolve_server_entry() -> Path:
    """Return the absolute path to ``telegram-server.ts``.

    :raises ServerEntryNotFound: when no candidate names a readable file. The
        exception message lists every path tried.
    """
    attempts = candidate_paths()

    override_source, override_path = attempts[0]
    if override_path is not None:
        if override_path.is_file():
            return override_path
        # An override that cannot be honoured is a hard stop: falling back
        # would run a DIFFERENT server than the operator named, silently.
        raise ServerEntryNotFound([(override_source, override_path)])

    for _source, path in attempts[1:]:
        if path is not None and path.is_file():
            return path

    raise ServerEntryNotFound(attempts)
