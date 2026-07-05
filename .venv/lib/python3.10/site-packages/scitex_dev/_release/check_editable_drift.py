"""Editable-install drift warning.

Fires once per process (CLI invocation, first `import scitex_dev`, MCP
server boot) when:

1. The package is installed editable (`pip install -e .`), AND
2. The working-tree HEAD differs from the latest release tag.

Designed to be **silent and fast** on the hot path:

- Non-editable installs: single `direct_url.json` read (~1ms), then return.
- Editable, cache hit (`.git/HEAD` mtime unchanged since last check):
  read cached result (~1ms).
- Editable, cache miss: run `git describe`/`rev-list` (~30–50ms),
  write cache. Subsequent invocations are cache hits.

Suppressed entirely when env var `SCITEX_DEV_NO_DRIFT_WARN=1` is set
(useful for CI, scripts, or when the warning becomes noise).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


_CACHE_DIR = Path.home() / ".cache" / "scitex" / "dev"
_CACHE_FILE = _CACHE_DIR / "editable-drift.json"
_GIT = shutil.which("git")
_ENV_DISABLE = "SCITEX_DEV_NO_DRIFT_WARN"
# Belt-and-braces: only run the check at most once per N seconds even
# across cache invalidations, so a `git checkout` flurry doesn't thrash.
_MIN_INTERVAL_SECONDS = 30


def _editable_source_dir(distribution: str) -> Path | None:
    """Return the editable-install source directory, or None if not editable.

    Reads `<dist-info>/direct_url.json` per PEP 610.
    """
    try:
        from importlib.metadata import distribution as _dist
    except ImportError:
        return None
    try:
        meta = _dist(distribution)
    except Exception:
        return None
    try:
        raw = meta.read_text("direct_url.json")
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not data.get("dir_info", {}).get("editable"):
        return None
    url = data.get("url", "")
    if url.startswith("file://"):
        return Path(url[len("file://") :])
    return None


def _git_state_mtime(repo: Path) -> float | None:
    """Composite mtime so the cache invalidates on commit moves AND tag fetches.

    `git fetch --tags` updates `.git/packed-refs` (and/or files under
    `.git/refs/tags/`) but does NOT touch `.git/HEAD`. Keying the cache
    only on HEAD's mtime made `git fetch --tags --force` invisible to
    the next drift check — the cache returned the stale "ahead of v0.X"
    line until something else (commit, checkout) bumped HEAD.

    Take max(HEAD, packed-refs, refs/tags/) so any of those three
    bumping invalidates the cache.
    """
    git_dir = repo / ".git"
    if not git_dir.exists():
        return None
    candidates: list[float] = []
    for rel in ("HEAD", "packed-refs"):
        p = git_dir / rel
        if p.is_file():
            try:
                candidates.append(p.stat().st_mtime)
            except OSError:
                pass
    refs_tags = git_dir / "refs" / "tags"
    if refs_tags.is_dir():
        try:
            candidates.append(refs_tags.stat().st_mtime)
        except OSError:
            pass
    return max(candidates) if candidates else None


# Backward-compat alias so any external caller that imports the old name
# keeps working — our own callsite uses _git_state_mtime now.
_git_head_mtime = _git_state_mtime


def _run_git(repo: Path, *args: str) -> str | None:
    if _GIT is None:
        return None
    try:
        result = subprocess.run(
            [_GIT, "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _is_completion_context() -> bool:
    """True when the current process is a Click shell-completion source eval.

    `.bashrc`/`.zshrc` typically embed
        eval "$(_SCITEX_DEV_COMPLETE=bash_source scitex-dev)"
    which runs scitex-dev on every shell startup. Emitting the drift line
    in that path produces an unwanted warning every time the user opens a
    new shell or types `bash`. The Click env var is a reliable signal.
    """
    # Match any `_<PROG>_COMPLETE=...` from `eval "$(_FOO_COMPLETE=bash_source foo)"`
    # — scitex-dev's drift checker is imported transitively whenever any
    # downstream tool (scitex-scholar, scitex-io, …) is invoked, including
    # during their own shell-completion sourcing. Without broad matching,
    # the drift line ends up in the completion candidate list and bash
    # treats it as one of the suggestions (symptom: "TAB needed twice").
    return any(k == "_CLICK_COMPLETE" or k.endswith("_COMPLETE") for k in os.environ)


def _compute_drift(repo: Path) -> str | None:
    """Return a one-line warning, or None if up-to-date / unknown.

    "Ahead-only" returns None — when you're working on develop you are
    *supposed* to be ahead of the latest release tag, so a warning there
    is just noise. We only nudge on "behind" (you should pull) or
    "diverged" (you should rebase / fast-forward).
    """
    # Use `git tag --sort=-v:refname` (highest-semver-first) instead of
    # `git describe --tags`, which only finds tags REACHABLE FROM HEAD.
    # Reachability fails the standard gitflow case where v* tags live
    # on the main branch's merge commit but the user is checked out on
    # develop — develop hasn't been fast-forwarded to include the
    # merge, so describe walks back to the previous on-branch tag.
    # We want "latest published version" regardless of branch topology.
    raw = _run_git(
        repo,
        "tag",
        "--list",
        "v[0-9]*",
        "--sort=-v:refname",
    )
    latest_tag = raw.splitlines()[0].strip() if raw else ""
    head = _run_git(repo, "rev-parse", "--short", "HEAD")
    if not latest_tag or not head:
        return None
    # rev-list --count A..B works fine for non-ancestor tags; it counts
    # commits in B not reachable from A (and vice versa for the reverse).
    ahead = _run_git(repo, "rev-list", "--count", f"{latest_tag}..HEAD")
    behind = _run_git(repo, "rev-list", "--count", f"HEAD..{latest_tag}")
    try:
        n_ahead = int(ahead or "0")
        n_behind = int(behind or "0")
    except ValueError:
        return None
    if n_behind == 0:
        # Quiet on "ahead-only" — develop is *supposed* to be ahead of the
        # latest release tag; warning there is just startup noise. Only
        # the "behind" and "diverged" cases call for action.
        return None
    if n_ahead and n_behind:
        return (
            f"editable scitex-dev: HEAD ({head}) diverged from latest tag "
            f"{latest_tag} (+{n_ahead}/−{n_behind}). `git pull --rebase`?"
        )
    return (
        f"editable scitex-dev: HEAD ({head}) is {n_behind} commit(s) behind "
        f"latest tag {latest_tag} — `git pull` or `pip install -U scitex-dev`."
    )


def _read_cache() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(payload: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(payload))
    except OSError:
        pass


def check(distribution: str = "scitex-dev") -> str | None:
    """Return a one-line warning string, or None.

    Cheap on the hot path: returns None in ~1–2ms for non-editable
    installs and ~1ms for editable installs with a fresh cache.
    """
    if os.environ.get(_ENV_DISABLE):
        return None
    src = _editable_source_dir(distribution)
    if src is None:
        return None
    state_mtime = _git_state_mtime(src)
    if state_mtime is None:
        return None
    cache = _read_cache()
    entry = cache.get(distribution, {})
    now = time.time()
    if (
        entry.get("head_mtime") == state_mtime
        and now - float(entry.get("checked_at", 0)) < 86400
    ):
        return entry.get("warning")
    if now - float(entry.get("checked_at", 0)) < _MIN_INTERVAL_SECONDS:
        # Avoid thrashing when HEAD/tags are being rewritten in a tight loop.
        return entry.get("warning")
    warning = _compute_drift(src)
    cache[distribution] = {
        # Field name kept as 'head_mtime' for backward compat with existing
        # cache files; semantically it now stores the composite git-state mtime.
        "head_mtime": state_mtime,
        "checked_at": now,
        "warning": warning,
    }
    _write_cache(cache)
    return warning


_SUBPROCESS_MARKER = "_SCITEX_DEV_DRIFT_EMITTED"


def emit_if_drift(distribution: str = "scitex-dev") -> None:
    """Print warning to stderr if there is one. Safe to call repeatedly.

    Suppression is two-layered so a parent process emits at most once and
    every subprocess (e.g. each per-leaf auditor spawned by `audit-all`)
    inherits the suppression via env var instead of re-printing the same
    drift line N times:
    - In-process: function-attribute flag.
    - Across processes: `_SCITEX_DEV_DRIFT_EMITTED=1` env var, set after
      the first emit and inherited by every subprocess.
    """
    if getattr(emit_if_drift, "_emitted", False):
        return
    if os.environ.get(_SUBPROCESS_MARKER) == "1":
        emit_if_drift._emitted = True  # type: ignore[attr-defined]
        return
    # Don't emit when invoked as a Click shell-completion source eval
    # (`.bashrc`/`.zshrc` typically embed
    #  `eval "$(_SCITEX_DEV_COMPLETE=bash_source scitex-dev)"`),
    # otherwise every shell startup prints the drift line.
    if _is_completion_context():
        emit_if_drift._emitted = True  # type: ignore[attr-defined]
        return
    emit_if_drift._emitted = True  # type: ignore[attr-defined]
    msg = check(distribution)
    if msg:
        print(f"[scitex-dev] {msg}", file=sys.stderr)
    # Mark for any subprocess we spawn, regardless of whether we printed
    # (no-drift state should also propagate so the env stays consistent).
    os.environ[_SUBPROCESS_MARKER] = "1"
