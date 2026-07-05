#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XDG-state file + paths for the SciTeX ecosystem supervisor.

The supervisor writes a JSON snapshot every ``state_write_interval`` seconds so
``scitex-dev ecosystem status`` can be a *cheap* read against a static file —
no IPC, no signal-ping, no risk that asking for status perturbs a child. The
read side (the ``status`` CLI) only needs a JSON loader; the write side (the
supervisor) needs an atomic write so a status read mid-write never observes a
half-rendered file.

Path policy
-----------
* State + per-child logs live under ``~/.local/state/scitex-ecosystem/``
  (XDG_STATE_HOME default). Persistent across reboots so a logrotate pass can
  later own per-file rotation; volatile ``/tmp`` would lose the post-crash
  diagnostic trail.
* The state file itself is ``~/.local/state/scitex-ecosystem/state.json``.
* Each child gets ``~/.local/state/scitex-ecosystem/<job.name>.log``; the
  supervisor's own structured logging goes to the journal via
  ``Type=simple`` + ``StandardOutput=journal``.

XDG override
------------
``XDG_STATE_HOME`` is honoured. We deliberately do NOT hard-code
``~/.local/state`` — operators who relocate XDG dirs (rare, but real on
distros that ship XDG-managed home layouts) shouldn't have to patch us.

Test seam
---------
The default-paths are functions, not module-level constants, so tests can
swap ``$HOME`` / ``$XDG_STATE_HOME`` and observe the resolution without
monkey-patching ``Path.home`` or messing with the live filesystem. The
``DEFAULT_STATE_DIR`` / ``DEFAULT_LOG_DIR`` constants are kept for the rare
read-only reference (e.g. logging the default at module import time).
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Subdirectory under XDG_STATE_HOME. Kept short; a fully-qualified path is
# easy to skim in `journalctl --user -u scitex-dev-ecosystem` output.
_STATE_SUBDIR = "scitex-ecosystem"

# Documented default paths — exposed as module constants for diagnostics
# only; production code calls the *function* variants below so a test seam
# (``HOME=`` / ``XDG_STATE_HOME=``) is honoured.
DEFAULT_STATE_DIR = (
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    / _STATE_SUBDIR
)
DEFAULT_LOG_DIR = DEFAULT_STATE_DIR


def default_state_dir() -> Path:
    """Return ``$XDG_STATE_HOME/scitex-ecosystem/`` honouring runtime env.

    Resolution rules (first match wins):

    1. ``$XDG_STATE_HOME/scitex-ecosystem`` — explicit XDG override.
    2. ``$HOME/.local/state/scitex-ecosystem`` — XDG default.

    Both forms call :func:`Path.expanduser` so a literal ``~`` in
    ``XDG_STATE_HOME`` resolves correctly.
    """
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base).expanduser() / _STATE_SUBDIR
    return Path.home() / ".local" / "state" / _STATE_SUBDIR


def default_log_dir() -> Path:
    """Per-child logs live alongside the state file (same XDG dir)."""
    return default_state_dir()


def default_state_path() -> Path:
    """Default JSON snapshot path: ``<state_dir>/state.json``."""
    return default_state_dir() / "state.json"


# --------------------------------------------------------------------------- #
# Serialisable snapshot                                                        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SupervisorState:
    """Frozen snapshot of the supervisor's view of the world.

    Written to ``state.json`` every ``state_write_interval`` seconds (5s by
    default). Read by ``scitex-dev ecosystem status``.

    The schema is deliberately small and explicit (no nested objects beyond
    the per-child dicts) so a hand-written ``status`` reader stays readable
    without a dataclass on the read side. The supervisor's own version is
    stamped in too — if the field set evolves, ``status`` can branch on
    ``schema_version`` instead of crashing on a missing key.
    """

    #: Schema version stamp. Bump when adding required fields so the
    #: ``status`` CLI can detect / fall back gracefully on an old snapshot.
    schema_version: int = 1
    #: Supervisor PID (``os.getpid()`` at snapshot time).
    pid: int = 0
    #: Unix timestamp the supervisor started (``time.time()`` at start).
    started_at: float = 0.0
    #: Unix timestamp this snapshot was written.
    written_at: float = 0.0
    #: ``scitex_dev.__version__`` — diagnostic only.
    scitex_dev_version: str = ""
    #: One dict per child. Keys: name, kind, pid, status, started_at,
    #: restart_count, recent_failure_count, circuit_open, last_exit_code,
    #: log_path, command. ``status`` is one of ``running`` / ``stopped`` /
    #: ``failed`` (circuit-opened) / ``starting``.
    children: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        """Return a stable JSON serialisation (sorted keys, 2-space indent)."""
        return json.dumps(dataclasses.asdict(self), sort_keys=True, indent=2)


def write_state_atomically(state: SupervisorState, path: Path) -> None:
    """Write ``state`` to ``path`` atomically (tmp + rename).

    Same-directory tmp + ``Path.replace`` makes the swap atomic on every
    filesystem the operator's host could plausibly run on (ext4, xfs, zfs,
    btrfs, tmpfs). A status reader observing the file mid-write sees either
    the old snapshot or the new one — never a partial.

    Creates parents of ``path`` if missing so first-run on a fresh host
    doesn't require a pre-touched directory.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # ``delete=False`` + manual replace = portable atomic swap. The default
    # mode ``w`` is text; SupervisorState.to_json returns ``str``.
    fd, tmp_name = tempfile.mkstemp(
        prefix=".state.",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(state.to_json())
            fh.write("\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                # Some FSes (procfs, certain tmpfs) refuse fsync; the
                # rename is still atomic even without it.
                pass
        os.replace(tmp_name, path)
    except Exception:
        # Best-effort cleanup of the tmp file on any failure.
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def read_state(path: Path) -> Optional[SupervisorState]:
    """Read a snapshot from ``path`` if it exists; return ``None`` otherwise.

    Returns ``None`` (rather than raising) for the three "no supervisor"
    diagnostics the ``status`` CLI cares about:

    * the supervisor has never run on this host (file missing),
    * the file exists but is empty (mid-first-write),
    * the file holds malformed JSON (corrupted, partial older write).

    The ``status`` CLI surfaces these cases with a clear diagnostic; a
    crash here would be unhelpful (the operator just wants to know the
    fleet's state).
    """
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    # Be permissive about missing fields — defaults from the dataclass fill
    # in any gap so an older snapshot keeps parsing after a schema bump.
    return SupervisorState(
        schema_version=int(data.get("schema_version", 0)),
        pid=int(data.get("pid", 0)),
        started_at=float(data.get("started_at", 0.0)),
        written_at=float(data.get("written_at", 0.0)),
        scitex_dev_version=str(data.get("scitex_dev_version", "")),
        children=list(data.get("children", [])),
    )


def now() -> float:
    """Indirection over ``time.time`` so tests can freeze the clock."""
    return time.time()


__all__ = [
    "DEFAULT_LOG_DIR",
    "DEFAULT_STATE_DIR",
    "SupervisorState",
    "default_log_dir",
    "default_state_dir",
    "default_state_path",
    "now",
    "read_state",
    "write_state_atomically",
]


# EOF
