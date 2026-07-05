#!/usr/bin/env bash
# scitex-dev — canonical pytest-testmon warm-cache wrapper.
# -*- coding: utf-8 -*-
#
# This is the AUTHORITATIVE source for the testmon pre-commit hook
# wrapper. It makes pytest-testmon worktree-resilient via a persistent
# per-repo warm cache.
#
# THE PROBLEM IT SOLVES
# ---------------------
# Every SciTeX release runs in a FRESH git worktree (forced by the
# develop-pin hook), so the worktree's ``.testmondata`` is always COLD.
# testmon then has no impact graph and re-runs the FULL ~2500-test suite
# (~2h) instead of only the tests touched by the diff. A persistent
# cache shared across worktrees fixes this: we seed-copy a warm
# ``.testmondata`` into the worktree before pytest runs, then write the
# updated DB back to the cache afterwards.
#
# (repo, pyXY) KEYING
# -------------------
# testmon invalidates its DB whenever the interpreter / dependency
# fingerprint changes, so we MUST NOT let two python versions share one
# file. The cache path is keyed by both repo name and ``py<major><minor>``
# (e.g. ``py312``) so each (repo, interpreter) pair owns its own DB.
#
# CACHE ROOT
# ----------
# ``SCITEX_TESTMON_CACHE_ROOT`` is injected by the sac container
# (=/home/agent/.cache/scitex-testmon). The ``$HOME/.cache/...`` default
# covers local / non-container dev.
#
# WIRING
# ------
# Repos reference this script from ``.pre-commit-config.yaml`` via:
#
#     entry: bash $(scitex-dev hooks print-path run_testmon)
#
# so future fixes land here and every project picks them up.

set -euo pipefail

# --self-test: verify the cache-path resolution logic runs without a real
# pytest by short-circuiting before the RUN stage. Mirrors run_lint.sh.
if [[ "${1:-}" == "--self-test" ]]; then
    echo "=== Self-test: $(basename "$0") ==="
    pass=0
    fail=0

    GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    REPO="$(basename "$GIT_ROOT")"
    PYXY="$(python3 -c 'import sys;print(f"py{sys.version_info.major}{sys.version_info.minor}")')"
    CACHE_ROOT="${SCITEX_TESTMON_CACHE_ROOT:-$HOME/.cache/scitex-testmon}"
    CACHE_DIR="$CACHE_ROOT/$REPO/$PYXY"

    if [[ -n "$REPO" ]]; then
        pass=$((pass + 1))
        echo "  PASS: repo resolved ($REPO)"
    else
        fail=$((fail + 1))
        echo "  FAIL: repo did not resolve"
    fi
    if [[ "$PYXY" =~ ^py[0-9]+$ ]]; then
        pass=$((pass + 1))
        echo "  PASS: interpreter key resolved ($PYXY)"
    else
        fail=$((fail + 1))
        echo "  FAIL: interpreter key malformed ($PYXY)"
    fi
    if [[ "$CACHE_DIR" == */"$REPO"/"$PYXY" ]]; then
        pass=$((pass + 1))
        echo "  PASS: cache dir keyed by (repo, pyXY) ($CACHE_DIR)"
    else
        fail=$((fail + 1))
        echo "  FAIL: cache dir not keyed correctly ($CACHE_DIR)"
    fi

    echo "Results: $pass passed, $fail failed"
    [[ $fail -eq 0 ]] && exit 0 || exit 1
fi

# Resolve the worktree root, repo name, and interpreter key.
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
REPO="$(basename "$GIT_ROOT")"
PYXY="$(python3 -c 'import sys;print(f"py{sys.version_info.major}{sys.version_info.minor}")')"

CACHE_ROOT="${SCITEX_TESTMON_CACHE_ROOT:-$HOME/.cache/scitex-testmon}"
CACHE_DIR="$CACHE_ROOT/$REPO/$PYXY"
CACHE_FILE="$CACHE_DIR/.testmondata"
LOCAL_FILE="$GIT_ROOT/.testmondata"

# SEED-IN: warm the worktree's cold DB from the persistent cache.
if [[ -f "$CACHE_FILE" ]]; then
    cp -f "$CACHE_FILE" "$LOCAL_FILE" 2>/dev/null || true
fi

# RUN: pytest returns non-zero on test failures; capture the code WITHOUT
# letting `set -e` abort before the write-back stage runs.
set +e
python3 -m pytest --testmon "$@"
rc=$?
set -e

# WRITE-BACK: persist the freshly-updated DB only when tests actually ran
# (rc 0 = all pass, rc 1 = test failures — both yield a valid DB). rc>=2
# means interrupted / usage / internal error, so we skip to never cache a
# broken state.
if [[ -f "$LOCAL_FILE" && "$rc" -lt 2 ]]; then
    mkdir -p "$CACHE_DIR" 2>/dev/null || true
    cp -f "$LOCAL_FILE" "$CACHE_FILE" 2>/dev/null || true
fi

exit $rc

# EOF
