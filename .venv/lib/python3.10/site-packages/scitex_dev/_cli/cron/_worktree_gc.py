#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``worktree-gc`` cron job — periodic cleanup of stale ``.claude/worktrees``.

Subagents spawned with ``Agent(..., isolation: "worktree")`` create
isolated git worktrees under ``<repo>/.claude/worktrees/<agent-name>/``.
When an agent finishes without modifying files, the harness auto-removes
its worktree; when an agent crashes, is killed, or makes changes the
operator never lands, the worktree is left behind. Over weeks of
fleet-wide agent use these accumulate into thousands of orphaned
checkouts — the operator's host accumulated 56 stale worktrees before
the hand-edited host cron was installed (2026-06-07).

This module formalises that hand-edited host cron as a *managed*
scitex-dev cron job (``scitex-dev cron install worktree-gc``) so the
cleanup ships with the package and installs fleet-wide instead of
living as a per-host script.

Coordination with proj-scitex-agent-container
---------------------------------------------
The agent-container team owns the RELOCATION half — stopping new
``.claude/worktrees`` from being created in the first place (the
canonical path will move to ``.worktrees/`` at the repo root). Until
that lands, the directory continues to grow; this GC job is the
continuous-cleanup loop that keeps it bounded.

Hard guardrails
---------------
The single highest-stakes rule for this job:

  **Only paths whose absolute path contains ``/.claude/worktrees/`` are
  ever passed to ``git worktree remove``. The user's own ``.worktrees/``
  directory (no ``.claude`` prefix) is NEVER touched.**

That rule is enforced in :func:`_is_managed_path`, called before every
removal. A bug elsewhere in the logic can at worst skip a removal; it
cannot reach into the user's own worktrees.

Other guardrails:

  * **mtime-gated.** Worktrees are only candidates for removal once
    their directory's mtime is older than ``MAX_AGE_DAYS`` (default 3).
    Active agents working on a checkout naturally touch its files, so
    "old mtime" is a reliable "abandoned" signal.
  * **git-worktree-aware.** Removal is via ``git worktree remove``
    (which refuses dirty/locked worktrees by default) followed by
    ``git worktree prune``. We never ``rm -rf`` a checkout — that
    leaves the parent repo's ``.git/worktrees`` metadata inconsistent
    and corrupts every shared ``git worktree`` view.
  * **Never force.** A worktree refusing removal (dirty changes,
    locked, in use) is skipped with a logged warning. The operator's
    work is not destroyed by an unattended cleanup loop.
  * **Never crashes the cron.** Every subprocess error is captured and
    returned in the result; the ``exec`` dispatcher exits 0 on partial
    failure so the cron loop keeps ticking. The structured result
    distinguishes "removed", "skipped (not due)", "skipped (refused)",
    and "errored" so the log is greppable.

Seams
-----
``now`` (epoch seconds) and ``git_runner`` (a ``Callable[[list[str]],
subprocess.CompletedProcess]``) are keyword arguments so tests pass
real fakes — no monkeypatching of ``time`` or ``subprocess``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


# The mtime gate. Worktrees idle longer than this are candidates for
# removal. 3 days is conservative for the fleet's typical agent
# lifetime: agents that are still working will touch their files;
# agents that have walked away leave their checkout cold.
DEFAULT_MAX_AGE_DAYS: int = 3

# Search roots from which to walk and find candidate ``.claude/worktrees``
# directories. The default scans the user's home so any project the
# operator works in is covered without per-project configuration.
DEFAULT_ROOTS: tuple[str, ...] = ("~",)

# Directory segment that gates removal. Hard-coded so a bug in env-var
# parsing cannot widen the scope.
MANAGED_SEGMENT: str = "/.claude/worktrees/"

# The "user's own" segment. Never touched — even if a misconfiguration
# routes the scan into it, every removal call goes through
# :func:`_is_managed_path` which rejects anything not under
# ``MANAGED_SEGMENT``.
PROTECTED_SEGMENT: str = "/.worktrees/"

# Path prefixes that are container-local and must NEVER be interpreted by
# a host-side ``git worktree prune``. When a worktree is created from
# inside the agent container (``apptainer exec ... git worktree add ...``)
# its ``.git/worktrees/<name>/gitdir`` file records a container-rooted
# path like ``/work/<branch>/.git``. Running ``git worktree prune`` from
# the HOST checkout fails to resolve that path — the host has no
# ``/work`` — and git's "directory missing → dangling worktree" heuristic
# treats the LIVE container worktree as defunct and prunes it. The fleet
# lost integration-test worktrees twice today to this exact bug class
# (lead-learnings/19, 2026-06-13). Host scripts cannot judge container
# worktree liveness from outside the container; the only safe action is
# to SKIP the prune entirely when any registered worktree's recorded
# gitdir points at a container-only prefix.
CONTAINER_GITDIR_PREFIXES: tuple[str, ...] = ("/work/",)


@dataclass(frozen=True)
class WorktreeRemoval:
    """One worktree's outcome from this GC pass."""

    path: str
    parent_repo: str
    age_days: float
    action: str  # "removed" | "skipped-fresh" | "skipped-refused" | "errored"
    detail: str = ""


@dataclass(frozen=True)
class WorktreeGCResult:
    """Aggregate outcome of one ``worktree-gc`` exec-body invocation."""

    scanned: int
    removed: int
    skipped_fresh: int
    skipped_refused: int
    errored: int
    per_worktree: tuple[WorktreeRemoval, ...] = field(default_factory=tuple)
    error: str | None = None


def _is_managed_path(path: str) -> bool:
    """Hard guardrail: only paths under ``.claude/worktrees/`` are managed.

    The operator's own ``.worktrees/`` (no ``.claude`` prefix) is the
    PROTECTED area — never touched by this GC regardless of mtime or
    git registration. We compare on the absolute, normalized path with
    leading slash so ``/.claude/worktrees/`` cannot be matched by a
    substring like ``foo.claude/worktrees`` (no leading slash).
    """
    abs_path = os.path.abspath(path)
    # Normalize separators on the off-chance we ever run somewhere odd —
    # MANAGED_SEGMENT uses forward slashes; on POSIX that's the only
    # form abspath produces. Be explicit so the intent is unmissable.
    return MANAGED_SEGMENT in abs_path and PROTECTED_SEGMENT not in abs_path.replace(
        MANAGED_SEGMENT, "/__claude_managed__/"
    )


def _expand_roots(raw: Iterable[str]) -> list[str]:
    """Expand ``~`` / env vars and drop non-existing roots silently."""
    out: list[str] = []
    for r in raw:
        expanded = os.path.expandvars(os.path.expanduser(r))
        if os.path.isdir(expanded):
            out.append(expanded)
    return out


def _find_repos_with_managed_worktrees(roots: list[str]) -> list[str]:
    """Return absolute paths of repos that have a ``.claude/worktrees``
    subdirectory.

    A worktree directory may exist without any registered worktrees
    (empty leftover dir); we report the parent repo regardless so the
    caller can do a single ``git worktree list`` per repo.

    Performance: the walk skips ``node_modules`` / ``.venv`` / ``venv``
    / ``__pycache__`` / ``.git`` to avoid descending into vendored
    trees. The cron tick is not latency-sensitive but a multi-hour walk
    would overlap the next tick.
    """
    SKIP = {
        ".git",
        ".hg",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        "dist",
        "build",
        # NEVER descend into ``.worktrees`` — even if we somehow ended
        # up scanning the user's protected area, this prevents
        # accidental discovery of paths we should not touch.
        ".worktrees",
    }
    found: list[str] = []
    seen: set[str] = set()
    for root in roots:
        for dirpath, dirnames, _ in os.walk(root, followlinks=False):
            # Prune skip dirs in-place so os.walk doesn't descend.
            dirnames[:] = [d for d in dirnames if d not in SKIP]
            base = os.path.basename(dirpath)
            if (
                base == "worktrees"
                and os.path.basename(os.path.dirname(dirpath)) == ".claude"
            ):
                # The repo root is the dirname of ``.claude``.
                repo = os.path.dirname(os.path.dirname(dirpath))
                # De-dup repos found via multiple search roots.
                repo_abs = os.path.abspath(repo)
                if repo_abs not in seen:
                    seen.add(repo_abs)
                    found.append(repo_abs)
    return found


def _default_git_runner(argv: list[str]) -> subprocess.CompletedProcess:
    """Real ``git ...`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["git", *argv],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _list_registered_worktrees(
    repo: str,
    git_runner: Callable[[list[str]], subprocess.CompletedProcess],
) -> list[str]:
    """Parse ``git -C <repo> worktree list --porcelain`` for absolute paths.

    Only worktrees whose path is under ``MANAGED_SEGMENT`` are returned;
    the main worktree and any user-owned worktrees are filtered out
    here, before the mtime / removal logic sees them.
    """
    r = git_runner(["-C", repo, "worktree", "list", "--porcelain"])
    if r.returncode != 0:
        return []
    paths: list[str] = []
    for line in (r.stdout or "").splitlines():
        if line.startswith("worktree "):
            p = line[len("worktree ") :].strip()
            if _is_managed_path(p):
                paths.append(p)
    return paths


def _gc_one_worktree(
    repo: str,
    path: str,
    now_epoch: float,
    max_age_seconds: float,
    git_runner: Callable[[list[str]], subprocess.CompletedProcess],
    dry_run: bool,
) -> WorktreeRemoval:
    """GC a single registered worktree, observing every guardrail.

    Order of checks (defence in depth):
      1. ``_is_managed_path`` — refuse to act on anything outside
         ``.claude/worktrees``.
      2. Path exists — if the directory is already gone (orphaned
         metadata), prune the parent repo and skip with "errored:
         missing-path".
      3. mtime gate — skip if fresh.
      4. ``git worktree remove`` — let git refuse dirty / locked / in-use
         worktrees; on refusal, "skipped-refused".
    """
    # Defence-in-depth: re-check the guardrail at the per-worktree
    # boundary even though _list_registered_worktrees already filtered.
    if not _is_managed_path(path):
        return WorktreeRemoval(
            path=path,
            parent_repo=repo,
            age_days=0.0,
            action="errored",
            detail="not under .claude/worktrees — guardrail rejected",
        )

    try:
        mtime = os.path.getmtime(path)
    except OSError as exc:
        return WorktreeRemoval(
            path=path,
            parent_repo=repo,
            age_days=0.0,
            action="errored",
            detail=f"stat failed: {exc}",
        )

    age = now_epoch - mtime
    age_days = age / 86400.0
    if age < max_age_seconds:
        return WorktreeRemoval(
            path=path,
            parent_repo=repo,
            age_days=age_days,
            action="skipped-fresh",
            detail=f"mtime {age_days:.1f}d < threshold",
        )

    if dry_run:
        return WorktreeRemoval(
            path=path,
            parent_repo=repo,
            age_days=age_days,
            action="removed",
            detail="dry-run (would remove)",
        )

    r = git_runner(["-C", repo, "worktree", "remove", path])
    if r.returncode == 0:
        return WorktreeRemoval(
            path=path,
            parent_repo=repo,
            age_days=age_days,
            action="removed",
            detail="git worktree remove OK",
        )

    # Non-zero rc: git refused (dirty/locked/in-use) or some other
    # transient. Never force — leave the worktree for the operator.
    stderr = (r.stderr or "").strip()
    return WorktreeRemoval(
        path=path,
        parent_repo=repo,
        age_days=age_days,
        action="skipped-refused",
        detail=f"git refused: {stderr[:200]}",
    )


def _gitdir_targets_container(gitdir_file: Path) -> bool:
    """True iff the worktree's recorded gitdir points at a container-only
    prefix (e.g. ``/work/<branch>/.git``).

    Git stores the back-link from a registered worktree to the main repo
    in ``<main_repo>/.git/worktrees/<name>/gitdir``. The file contains
    the absolute path of the WORKTREE's ``.git`` (one line, trailing
    newline). When that path lives under a container bind-mount root
    (``/work/`` is the agent-container convention), the host cannot
    resolve the directory — but the worktree is alive in the container.
    Treat the gitdir as a container target so the caller skips the prune
    rather than destroying the live worktree.

    Defensive: any OSError reading the file → False (caller behaves as
    pre-fix; we only ADD a skip, never remove one).
    """
    try:
        recorded = gitdir_file.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return any(recorded.startswith(p) for p in CONTAINER_GITDIR_PREFIXES)


def _has_container_worktree(repo: str) -> bool:
    """True iff ``<repo>/.git/worktrees/*/gitdir`` lists a container path.

    Walks the main repo's worktree-registry directory and checks each
    entry's recorded gitdir. Existing host-only worktrees still let the
    prune through; one container entry is enough to disable the prune
    for the whole repo (defensive — a single false positive matters far
    more than a missed cleanup).
    """
    registry = Path(repo) / ".git" / "worktrees"
    if not registry.is_dir():
        return False
    try:
        entries = list(registry.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.is_dir():
            continue
        if _gitdir_targets_container(entry / "gitdir"):
            return True
    return False


def _safe_prune(
    repo: str,
    git_runner: Callable[[list[str]], subprocess.CompletedProcess],
    out=None,
) -> bool:
    """Run ``git worktree prune`` ONLY when no container-worktrees are
    registered on this repo.

    Returns True iff the prune was actually invoked. When skipped, logs
    a one-line warning to ``out`` so a fleet operator can grep for
    "worktree-gc: skip prune" and see exactly which repos were spared.

    Why "wholesale skip" rather than "prune just the host-only entries":
    git's ``worktree prune`` is all-or-nothing — it scans the registry
    and removes every entry whose gitdir doesn't resolve from the
    invoking process. There is no per-entry flag; the only way to keep
    a container entry alive when running from the host is to NOT prune
    at all. The cost is that a host worktree that's genuinely defunct
    will linger one cron tick longer (until the container entry is
    cleaned up or the repo no longer has container worktrees) — far
    cheaper than destroying live integration-test work.
    """
    if _has_container_worktree(repo):
        if out is not None:
            print(
                f"worktree-gc: skip prune {repo} — registry contains a "
                f"container worktree (gitdir under /work/); host cannot "
                f"judge its liveness. See lead-learnings/19.",
                file=out,
            )
        return False
    git_runner(["-C", repo, "worktree", "prune"])
    return True


def run_once(
    *,
    roots: Iterable[str] | None = None,
    max_age_days: float | None = None,
    now: Callable[[], float] | None = None,
    git_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    dry_run: bool = False,
    out=None,
) -> WorktreeGCResult:
    """Run one ``worktree-gc`` pass: discover repos, GC stale worktrees,
    prune.

    The search roots default to :data:`DEFAULT_ROOTS` (``~``) but can be
    overridden by:

      * the ``roots`` parameter (tests / direct calls), or
      * the ``SCITEX_WORKTREE_GC_ROOTS`` env var (colon-separated; one
        path per root). Useful for CI runners or per-host policy.

    The mtime threshold defaults to :data:`DEFAULT_MAX_AGE_DAYS` but can
    be overridden by:

      * the ``max_age_days`` parameter, or
      * the ``SCITEX_WORKTREE_GC_MAX_AGE_DAYS`` env var.

    Returns a :class:`WorktreeGCResult` summarising the pass; prints a
    one-line summary + per-worktree action lines to ``out`` so the cron
    log records every decision.
    """
    if out is None:
        out = sys.stdout

    if roots is None:
        env_roots = os.environ.get("SCITEX_WORKTREE_GC_ROOTS")
        roots = tuple(env_roots.split(":")) if env_roots else DEFAULT_ROOTS

    if max_age_days is None:
        env_age = os.environ.get("SCITEX_WORKTREE_GC_MAX_AGE_DAYS")
        try:
            max_age_days = float(env_age) if env_age else float(DEFAULT_MAX_AGE_DAYS)
        except ValueError:
            max_age_days = float(DEFAULT_MAX_AGE_DAYS)

    clock = now or time.time
    runner = git_runner or _default_git_runner

    expanded = _expand_roots(roots)
    if not expanded:
        msg = f"no usable search roots in {list(roots)}"
        print(f"worktree-gc: skip — {msg}", file=out)
        return WorktreeGCResult(
            scanned=0,
            removed=0,
            skipped_fresh=0,
            skipped_refused=0,
            errored=0,
            error=msg,
        )

    now_epoch = clock()
    max_age_seconds = max_age_days * 86400.0
    repos = _find_repos_with_managed_worktrees(expanded)

    per_worktree: list[WorktreeRemoval] = []
    for repo in repos:
        worktrees = _list_registered_worktrees(repo, runner)
        for wt in worktrees:
            outcome = _gc_one_worktree(
                repo=repo,
                path=wt,
                now_epoch=now_epoch,
                max_age_seconds=max_age_seconds,
                git_runner=runner,
                dry_run=dry_run,
            )
            per_worktree.append(outcome)
            print(
                f"worktree-gc: {outcome.action:<18} {outcome.path} "
                f"({outcome.age_days:.1f}d) — {outcome.detail}",
                file=out,
            )

        # After any removals in this repo, prune the metadata so
        # ``git worktree list`` stays accurate. Best-effort; a prune
        # failure does not abort the loop. Uses ``_safe_prune`` to skip
        # the prune wholesale when ANY registered worktree's gitdir
        # points at a container-only prefix (``/work/``) — bare prune
        # from the host would destroy live container worktrees, see
        # lead-learnings/19 (2026-06-13) for the fleet incident.
        if not dry_run:
            _safe_prune(repo, runner, out=out)

    removed = sum(1 for o in per_worktree if o.action == "removed")
    skipped_fresh = sum(1 for o in per_worktree if o.action == "skipped-fresh")
    skipped_refused = sum(1 for o in per_worktree if o.action == "skipped-refused")
    errored = sum(1 for o in per_worktree if o.action == "errored")
    print(
        f"worktree-gc: pass complete — {removed} removed, "
        f"{skipped_fresh} fresh, {skipped_refused} refused, "
        f"{errored} errored across {len(repos)} repo(s)",
        file=out,
    )

    return WorktreeGCResult(
        scanned=len(per_worktree),
        removed=removed,
        skipped_fresh=skipped_fresh,
        skipped_refused=skipped_refused,
        errored=errored,
        per_worktree=tuple(per_worktree),
    )


# EOF
