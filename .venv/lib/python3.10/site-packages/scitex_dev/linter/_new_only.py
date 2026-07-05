"""NEW-ONLY baseline gate for ``check-files`` (safety pair for #265).

Research-mode severity promotion (PR #264 / #265) flips figure / io /
import-family rules to ``error`` so the post-edit hook (``run_lint.sh``,
exit 2) BLOCKS the edit. But research repos carry large PRE-EXISTING
backlogs (NeuroVista: ~1000 violations across 207 files). If the
promotion blocked EVERY violation, an agent editing one legacy line
would be wedged on violations it never introduced.

This module owns the **new-only** classification: given the linter
findings on the CURRENT file content and on a BASELINE git ref, only
NEWLY-introduced findings keep their (possibly promoted) ``error``
severity — those still block. PRE-EXISTING findings are CAPPED to
``warning`` so they stay VISIBLE but non-blocking.

It mirrors the design of ``scitex_dev._cli.audit._diff`` (PR #261's
diff-aware ``ecosystem audit-all`` gate): a frozen, **line-number-
agnostic** identity so a finding survives unrelated line shifts. The
two differ in what they consume — ``_diff`` parses aggregated auditor
*stdout text* and stages whole worktrees; this module works on the
in-process ``Issue`` objects of ONE file and pulls the baseline via
``git show <ref>:<relpath>`` (no worktree needed). The identity rule
is the same one #261 documents: drop line numbers, key on rule + content.

Identity here is ``(rule_id, normalized source-line text)`` — the task
contract for check-files. Matching on the source-line CONTENT (not the
line number) is what makes the gate survive a docstring tweak above a
flagged construct: the construct moves down a few lines but keys the
same, so it stays classified as pre-existing.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

__all__ = [
    "FindingKey",
    "apply_new_only",
    "baseline_source",
    "finding_key",
    "git_repo_root",
]


@dataclass(frozen=True)
class FindingKey:
    """Line-number-agnostic identity for one linter finding.

    Two findings collide iff they come from the same rule on a line with
    the same NORMALIZED source text. Line numbers are deliberately NOT
    part of the identity (mirrors #261's ``ViolationKey``): a finding
    shifted down by an unrelated edit above it keys identically and so
    stays classified as pre-existing.
    """

    rule_id: str
    line_text: str


def _normalize_line(text: str) -> str:
    """Collapse a source line to a whitespace-stable comparison key.

    Strips a trailing ``# stx-allow`` / inline comment is intentionally
    NOT done — a suppression comment changes the meaning of the line, so
    two lines that differ only by a comment are genuinely different. We
    only normalise leading/trailing whitespace and internal runs so
    reindentation (e.g. a construct moved inside a new ``if`` block) does
    not spuriously re-key the finding as new.
    """
    return " ".join(text.split())


def finding_key(issue) -> FindingKey:
    """Build the line-stable identity for an ``Issue``."""
    return FindingKey(
        rule_id=issue.rule.id,
        line_text=_normalize_line(issue.source_line or ""),
    )


def git_repo_root(start: Path) -> Path | None:
    """Return the git work-tree root containing ``start``, or ``None``.

    Used to compute the path of ``start`` RELATIVE to the repo so the
    ``git show <ref>:<relpath>`` pathspec resolves. ``start`` may be a
    file or a directory; we resolve from its parent when it's a file.
    """
    anchor = start if start.is_dir() else start.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(anchor), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    root = out.stdout.strip()
    return Path(root) if root else None


def baseline_source(path: Path, ref: str) -> str | None:
    """Return the content of ``path`` at git ``ref``, or ``None``.

    ``None`` means the file is untracked / absent in the baseline (a new
    file, or a path outside any git repo). The caller treats a ``None``
    baseline as EMPTY findings, so every current finding is "new".

    Resolves the repo root and the repo-relative path so the pathspec
    ``<ref>:<relpath>`` is correct regardless of the caller's CWD.
    """
    root = git_repo_root(path)
    if root is None:
        return None
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        # File lives outside the discovered repo root — treat as new.
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "show", f"{ref}:{rel.as_posix()}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        # Untracked / not present at ref → no baseline.
        return None
    return out.stdout


def apply_new_only(current_issues: list, baseline_issues: list) -> list:
    """Cap PRE-EXISTING errors to warnings; leave NEW findings untouched.

    A current finding is PRE-EXISTING when a baseline finding shares its
    ``FindingKey`` (rule_id + normalized line text). Pre-existing findings
    whose severity is ``error`` are downgraded to ``warning`` so they
    stay visible but do NOT trip the hook's exit-2 error gate. New
    findings keep their (possibly research-promoted) severity verbatim —
    a new error stays an error and blocks.

    Pre-existing warn/info are left as-is (already non-blocking). The
    returned list preserves order and length of ``current_issues``.
    """
    baseline_keys = {finding_key(i) for i in baseline_issues}
    out = []
    for issue in current_issues:
        if finding_key(issue) in baseline_keys and issue.rule.severity == "error":
            # Pre-existing error → cap to warning (visible, non-blocking).
            capped_rule = replace(issue.rule, severity="warning")
            out.append(replace(issue, rule=capped_rule))
        else:
            out.append(issue)
    return out


# EOF
