#!/usr/bin/env python3
# Timestamp: 2026-06-07
# File: scitex_dev/_ecosystem/_umbrella_write.py

"""``--write`` side of ``scitex-dev ecosystem audit-umbrella``.

Regenerates the umbrella's
``[project.optional-dependencies].all`` block from the ECOSYSTEM
registry's resolver (:mod:`scitex_dev._ecosystem._umbrella`). Uses
``tomlkit`` to preserve TOML formatting (comments + whitespace) so the
operator's hand-curated extras and explanatory comments survive the
regen unmodified.

Scope (PR-A2): pyproject.toml ``[all]`` aggregator ONLY. The lazy_attrs
(``src/scitex/__init__.py``) and ``EXTERNAL_REEXPORTS``
(``src/scitex/re_export.py``) edits are intentionally out of scope —
those need marker-based replacement to safely preserve surrounding
code, and the safer pattern is to land them as a follow-on (PR-A3).
The drift detector still REPORTS those surfaces so the lead can apply
them by hand alongside this PR's auto-regen.

Safety:

- Refuses to write if the umbrella git checkout has uncommitted edits
  (the operator-edited local-SSoT rule from lead 2026-06-07).
- Refuses if the resolver's expected_all_extras is empty (defensive —
  almost certainly an import error).
- Always re-reads the file after writing so the caller sees the
  same bytes the next ``--check`` would.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a single ``--write`` pass."""

    modified: bool
    summary: str
    pyproject_path: Path


class UmbrellaWriteError(RuntimeError):
    """Raised when the safety gate refuses a write."""


def _safety_gate(repo: Path) -> None:
    """Refuse to write if the umbrella tree has unstaged edits.

    Looks for any porcelain output from ``git status -s`` restricted to
    the two files this writer can touch — ``pyproject.toml`` (the one
    we modify) plus anything under ``src/scitex/`` (so we never write
    while the operator is mid-rename or mid-extraction). Anything outside
    that scope (``.scitex/clew/runtime/``, ``.worktrees/``, etc.) is
    ignored: those are gitignored runtime artifacts.
    """
    if not (repo / ".git").exists():
        raise UmbrellaWriteError(
            f"{repo} is not a git repository — cannot enforce the "
            "operator-edited local-SSoT safety gate."
        )
    try:
        r = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "status",
                "-s",
                "--",
                "pyproject.toml",
                "src/scitex",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError as e:  # noqa: BLE001
        raise UmbrellaWriteError(f"git status failed: {e}") from e
    if r.returncode != 0:
        raise UmbrellaWriteError(
            f"git status returned non-zero in {repo}:\n{r.stderr.strip()}"
        )
    dirty = [ln for ln in r.stdout.splitlines() if ln.strip()]
    if dirty:
        raise UmbrellaWriteError(
            "Umbrella tree has uncommitted edits to pyproject.toml or "
            "src/scitex/ — refusing to write (operator-edited "
            "local-SSoT). Commit or stash first:\n  "
            + "\n  ".join(dirty)
        )


def _load_tomlkit():
    """Return the ``tomlkit`` module or raise ``UmbrellaWriteError``."""
    try:
        import tomlkit
    except ImportError as e:  # pragma: no cover — tomlkit is in the dev extra
        raise UmbrellaWriteError(
            "`tomlkit` is required for --write (preserves comments + "
            "whitespace in pyproject.toml). Install with: "
            "pip install tomlkit"
        ) from e
    return tomlkit


def _build_all_array(tomlkit, exp_all: set[str]):
    """Build a tomlkit array for the new ``[all]`` value.

    Sorted, one-per-line for clean diffs. ``exp_all`` is a set of
    ``"scitex[<extra>]"`` strings already filtered for the
    HAND_CURATED_EXTRAS allowlist (the caller does that filter).
    """
    arr = tomlkit.array()
    for spec in sorted(exp_all):
        arr.append(spec)
    arr.multiline(True)
    return arr


def _merge_all_extras(
    tomlkit,
    existing: list[str] | None,
    exp_all: set[str],
) -> tuple[list[str], list[str], list[str]]:
    """Compute (final_list, added, removed) for ``[all]``.

    The merge preserves the operator's hand-curated extras (``scitex[heavy]``,
    ``scitex[dev]``, etc. — anything in :data:`_HAND_CURATED_PRESERVE`)
    while replacing the SSoT-derivable subset with the resolver's view.
    """
    from ._umbrella import HAND_CURATED_EXTRAS

    existing = list(existing or [])
    # Items the operator hand-curated (keep verbatim regardless of resolver).
    hand_keep: list[str] = []
    # Items currently in [all] that we recognise as SSoT-derivable.
    ssot_slots: set[str] = set()
    for spec in existing:
        # spec is like `"scitex[stats]"` or a free-form 3rd-party require —
        # both stay if the inner extra name is hand-curated.
        m = _SCITEX_EXTRA_RE.match(spec)
        if m and m.group(1) in HAND_CURATED_EXTRAS:
            hand_keep.append(spec)
            continue
        if m:
            ssot_slots.add(spec)
            continue
        # Non-scitex-self-ref entries (rare but legal) stay too.
        hand_keep.append(spec)
    new_ssot = sorted(exp_all)
    final = sorted(set(hand_keep) | set(new_ssot))
    added = sorted(set(new_ssot) - ssot_slots)
    removed = sorted(ssot_slots - set(new_ssot))
    return final, added, removed


import re

_SCITEX_EXTRA_RE = re.compile(r'^scitex\[([\w.-]+)\]$')


def write_umbrella(
    repo: Path,
    *,
    exp_all: set[str],
) -> WriteResult:
    """Regenerate the umbrella's ``[all]`` block in place.

    Args:
        repo: scitex-python checkout root.
        exp_all: set of ``"scitex[<extra>]"`` strings the resolver
                 expects in ``[all]`` (SSoT-derivable subset).

    Returns:
        :class:`WriteResult` carrying a human-readable summary and a
        ``modified`` flag so the caller can decide whether to commit.

    Raises:
        UmbrellaWriteError: safety gate refused, or tomlkit missing.
    """
    _safety_gate(repo)
    tomlkit = _load_tomlkit()
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        raise UmbrellaWriteError(f"pyproject.toml not found at {pp}")
    text = pp.read_text(encoding="utf-8")
    doc = tomlkit.parse(text)
    opt = (doc.get("project") or {}).get("optional-dependencies")
    if opt is None:
        raise UmbrellaWriteError(
            "pyproject.toml has no [project.optional-dependencies] — "
            "umbrella shape unrecognised; refusing to write."
        )
    existing_all = list(opt.get("all") or [])
    final, added, removed = _merge_all_extras(tomlkit, existing_all, exp_all)
    if final == existing_all:
        return WriteResult(
            modified=False,
            summary="[all] aggregator already matches the resolver — no write.",
            pyproject_path=pp,
        )
    opt["all"] = _build_all_array(tomlkit, set(final))
    new_text = tomlkit.dumps(doc)
    pp.write_text(new_text, encoding="utf-8")
    lines = ["Rewrote pyproject.toml [project.optional-dependencies].all"]
    if added:
        lines.append("  + ADDED:")
        for s in added:
            lines.append(f"      {s}")
    if removed:
        lines.append("  - REMOVED:")
        for s in removed:
            lines.append(f"      {s}")
    return WriteResult(
        modified=True,
        summary="\n".join(lines),
        pyproject_path=pp,
    )


__all__ = [
    "UmbrellaWriteError",
    "WriteResult",
    "write_umbrella",
]


# EOF
