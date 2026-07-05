#!/usr/bin/env python3
# Timestamp: 2026-06-07
# File: scitex_dev/_cli/audit/_diff.py

"""Diff-aware audit helpers (lead task #40 part b).

When run from a worktree on a feature branch, the per-leaf audits today
fail on *inherited* violations the agent didn't introduce — debt that was
already in ``develop`` before the branch forked. That blocks every new
PR on tech debt unrelated to the change at hand (the scitex-todo
5-iteration loop, agent-container's develop, etc.).

This module owns the **net-new** comparison: given the audit output at
HEAD and at the merge base, report ONLY findings present at HEAD that
were absent at base. Pre-existing violations stop blocking new PRs
while anything the PR actually introduces still trips CI.

Design:

1. **Worktree-detach** the base ref via ``git worktree add`` into a
   tmpdir so the caller's HEAD never moves. Cleans up via try/finally
   even on failure.
2. Run ``scitex-dev ecosystem audit-all`` twice (HEAD path, base path)
   via the existing ``--path PATH`` plumbing landed in PR #137.
3. Parse each auditor's output into a stable **violation key** —
   ``(rule_code, file, normalized_message[:60])`` — that survives
   trivial reformatting AND unrelated line shifts but distinguishes
   genuinely-different findings.
4. Net-new = HEAD-keys − BASE-keys. Re-emit only the matching lines.

Line-stable identity (2026-06-13, lead-directed refinement)
------------------------------------------------------------

The identity intentionally drops line numbers from both the file
component (no ``file:line``, just ``file``) and the normalized message
(any ``test.py:NN`` / ``line NN`` / ``:NN:`` substrings are scrubbed).
Reason: line numbers shift on every unrelated edit — a one-line
docstring tweak above a flagged construct would re-key every finding
in that file as "new", churning the ratchet and creating false
"regression" CI failures on patches that introduced zero violations.

The trade-off is that a file with N findings of the same rule is
keyed as ONE entry, so adding a new finding of that rule in the SAME
file with the SAME message stays invisible to the ratchet. We accept
that — it's the same trade lead documented in the spec ("a baseline
can only ever SHRINK; adding a new finding of an existing key class
in the same file is debt that the strict full audit still catches").
"Moved to evade" — moving a flagged construct to a different file —
still flips the file component and is correctly detected as new.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


# Matches a single auditor finding line emitted by ``audit-cli`` /
# ``audit-project`` / siblings. Example shapes:
#
#   ERRO:   [PA-306 §3 no-mocks] scitex-dev: tests/.../file.py:43: STX-TQ007: ...
#   ERRO:   [PS-202 §2 src-tests-mirror] scitex-io: src/scitex_io/foo.py:NNN: ...
#   ERRO:   scitex-dev: scitex-dev ecosystem regen-umbrella: leaf token ...
#
# The captured groups are: level, rule_code, distribution, file_and_line,
# message. file_and_line is optional (some §1 rules are repo-level).
_FINDING_RE = re.compile(
    r"^(?P<level>ERRO|WARN|INFO):\s+"
    r"\[(?P<rule>[A-Z0-9\-§]+)[^\]]*\]\s+"
    r"(?P<dist>[\w\-]+):\s+"
    r"(?:(?P<file_line>[^:]+(?::\d+)?):\s+)?"
    r"(?P<msg>.+?)\s*$"
)

# Strips trailing ``:NN`` line-number suffix from a file-path token.
# Anchored at end-of-string so a colon inside the path (Windows drives,
# URL-shaped paths) cannot mis-fire.
_TRAILING_LINENO_RE = re.compile(r":\d+$")

# Strips line-number-shaped substrings from the message excerpt so a
# rule whose detail embeds ``... at line NN ...`` or ``tests/foo.py:NN:``
# keys identically across unrelated line shifts. We deliberately match
# only digit runs that look like line refs — bare numbers in prose
# (``2 mocks found``) are preserved so two genuinely-distinct findings
# don't collide.
_MSG_LINENO_PATTERNS = (
    re.compile(r":\d+(?=:|$|\s)"),  # ``...py:43`` or ``foo:88 ``
    re.compile(r"\bline\s+\d+\b", re.I),  # ``at line 88``
)


def _strip_trailing_lineno(file_token: str) -> str:
    """Drop the trailing ``:NN`` from a file-path token, if present.

    Used to derive the line-stable file component of the identity.
    A bare ``foo/bar.py`` round-trips unchanged; ``foo/bar.py:43`` →
    ``foo/bar.py``; ``some:thing:42`` → ``some:thing`` (only the
    trailing decimal suffix is stripped).
    """
    return _TRAILING_LINENO_RE.sub("", file_token)


def _normalize_message(msg: str) -> str:
    """Strip line-number substrings from a finding's message.

    Ratchet stability depends on the identity not embedding line
    references that shift on unrelated edits. The message excerpt is
    the loosest component (any rule can put arbitrary text there), so
    we additionally scrub two common shapes: trailing ``:NN``-style
    file/line refs and ``at line NN`` prose.

    Leaves all other content intact — a rule whose detail mentions
    ``2 mocks found in tests/conftest.py`` keeps the file mention,
    because that's part of WHAT changed, not a line-shift artefact.
    """
    out = msg
    for pat in _MSG_LINENO_PATTERNS:
        out = pat.sub("", out)
    # Collapse the whitespace gaps the substitutions can leave behind
    # so ``foo  bar`` doesn't collide-or-not-collide with ``foo bar``.
    return " ".join(out.split())


@dataclass(frozen=True)
class ViolationKey:
    """Identity that stays stable under whitespace, ANSI re-coloring,
    AND unrelated line shifts.

    Two findings collide iff they come from the same auditor rule on
    the same file with the same normalized message prefix. Line numbers
    are deliberately NOT part of the identity — see the module
    docstring's "line-stable identity" section for the rationale and
    the trade-off (debt of the same rule code in the same file with
    the same message keys as one entry; "moved to evade" — moving the
    flagged construct to a different file — still flips the identity).

    Field name carries forward ``file_line`` for ON-WIRE compatibility
    with any pickled / cached ViolationKey sets; the VALUE no longer
    contains the line number.
    """

    rule: str
    file_line: str  # file path with NO trailing ``:NN`` — name kept for compat
    message_excerpt: str


def extract_violation_keys(
    audit_stdout: str,
    *,
    distribution_filter: str | None = None,
) -> set[ViolationKey]:
    """Parse a per-auditor stdout stream into a set of violation keys.

    ``distribution_filter`` keeps only findings reported for the named
    dist (audit-all is polyrepo-capable; the filter avoids cross-leaf
    bleed when one stdout contains multiple distributions).
    """
    keys: set[ViolationKey] = set()
    for line in audit_stdout.splitlines():
        m = _FINDING_RE.match(line.strip())
        if m is None:
            continue
        if distribution_filter and m.group("dist") != distribution_filter:
            continue
        rule = m.group("rule")
        file_token = _strip_trailing_lineno(m.group("file_line") or "")
        msg_norm = _normalize_message(m.group("msg") or "")
        keys.add(
            ViolationKey(
                rule=rule,
                file_line=file_token,
                message_excerpt=msg_norm[:60],
            )
        )
    return keys


def compute_net_new(
    head_stdout: str,
    base_stdout: str,
    *,
    distribution: str | None = None,
) -> set[ViolationKey]:
    """Return the set of violation keys present at HEAD but absent at BASE.

    Net-new ≠ "things the PR added". A refactor that shifts every line
    flags every finding as new (line is part of the identity). Good
    enough for the first cut — refine when the false-positive rate
    becomes a problem.
    """
    head = extract_violation_keys(head_stdout, distribution_filter=distribution)
    base = extract_violation_keys(base_stdout, distribution_filter=distribution)
    return head - base


def filter_to_net_new_lines(
    audit_stdout: str,
    net_new: set[ViolationKey],
    *,
    distribution: str | None = None,
) -> str:
    """Re-emit only those output lines whose key is in ``net_new``.

    Preserves non-finding lines (auditor banner / summary / disclaimer)
    so the caller still sees the audit's framing, but the violation
    bullets are restricted to net-new findings.
    """
    kept: list[str] = []
    for line in audit_stdout.splitlines():
        m = _FINDING_RE.match(line.strip())
        if m is None:
            kept.append(line)
            continue
        if distribution and m.group("dist") != distribution:
            kept.append(line)
            continue
        rule = m.group("rule")
        # Key reconstruction MUST mirror `extract_violation_keys`'s
        # line-stripping or this filter would re-add inherited debt.
        key = ViolationKey(
            rule=rule,
            file_line=_strip_trailing_lineno(m.group("file_line") or ""),
            message_excerpt=_normalize_message(m.group("msg") or "")[:60],
        )
        if key in net_new:
            kept.append(line)
        # else: drop — inherited debt that BASE also reports
    return "\n".join(kept)


# --------------------------------------------------------------------- #
# Worktree-detach context manager                                        #
# --------------------------------------------------------------------- #


class DiffAwareSetupError(RuntimeError):
    """Raised when the base-ref worktree cannot be staged."""


@contextmanager
def worktree_at(repo: Path, ref: str) -> Iterator[Path]:
    """Stage ``ref`` as a temporary git worktree; yield its path.

    The caller's HEAD never moves — ``git worktree add`` clones the
    on-disk index of ``ref`` into a fresh dir under ``$TMPDIR``. On exit
    (success or failure) we always run ``git worktree remove --force``
    so the staging dir doesn't leak and the worktree registry stays
    clean.

    Raises ``DiffAwareSetupError`` on add failure (e.g. ref not found,
    locked worktree, dirty index) so the diff-aware caller can degrade
    gracefully (fall back to strict audit + a warning).
    """
    if not (repo / ".git").exists():
        raise DiffAwareSetupError(
            f"{repo} is not a git repository — diff-aware audit needs one."
        )
    stage = Path(tempfile.mkdtemp(prefix="audit-base-"))
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(stage), ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise DiffAwareSetupError(
                f"`git worktree add {ref}` failed (rc={r.returncode}): "
                f"{r.stderr.strip()}"
            )
        yield stage
    finally:
        # Best-effort teardown: --force survives a working tree with
        # local changes (the auditor occasionally writes pytest cache
        # files into the worktree). Worktree registry is reaped via
        # `prune` so a missed remove doesn't accumulate stubs.
        try:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(stage)],
                capture_output=True,
                check=False,
            )
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "prune"],
                capture_output=True,
                check=False,
            )


__all__ = [
    "DiffAwareSetupError",
    "ViolationKey",
    "compute_net_new",
    "extract_violation_keys",
    "filter_to_net_new_lines",
    "worktree_at",
]


# EOF
