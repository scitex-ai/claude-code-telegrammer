#!/usr/bin/env bash
# post-merge-pull.sh — fast-forward every scitex-* in-tree clone from its
# tracked upstream (origin/develop on the fleet checkouts).
#
# Designed to run under cron once a minute on each fleet host so the host
# checkouts stay current and nobody has to pull by hand.
# Scope: ~/proj/<repo> only.  ~/forks/ and workspace clones are skipped.
# Remote-agnostic: uses each branch's configured upstream — no hardcoded
# remote name or URL.  Only ever touches a checkout that is on `develop`
# with a clean working tree; feature-branch / dirty checkouts are left alone.
#
# Usage:
#   crontab: * * * * * ~/.scitex/agent-container/runtime/cron/post-merge-pull.sh \
#              >> ~/.scitex/agent-container/runtime/logs/post-merge-pull.$(hostname -s).cron.log 2>&1

set -euo pipefail

HOST="$(hostname -s)"
LOG_DIR="${HOME}/.scitex/agent-container/runtime/logs"
LOG_FILE="${LOG_DIR}/post-merge-pull.${HOST}.log"
LOCK_FILE="/tmp/post-merge-pull.${HOST}.lock"

mkdir -p "${LOG_DIR}"

_ts() { date '+%Y-%m-%dT%H:%M:%S'; }
_info() { echo "$(_ts) [INFO] $*" | tee -a "${LOG_FILE}"; }
_warn() { echo "$(_ts) [WARN] $*" | tee -a "${LOG_FILE}" >&2; }

# Acquire exclusive lock — abort if another run is still active.
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
    _warn "Another instance is running (${LOCK_FILE}). Exiting."
    exit 0
fi

# ---------------------------------------------------------------------------
# Repo allowlist: canonical scitex repo names.  Each resolves to ~/proj/<name>
# and is pulled via its tracked upstream (origin/develop) — no remote URL is
# hardcoded here.  A name whose dir is absent is skipped.
# ---------------------------------------------------------------------------
REPOS=(
    "scitex-agent-container"
    "scitex-orochi"
    "scitex-resource"
    "scitex-ssh"
    "scitex-hpc"
    "scitex"
)

_pull_repo() {
    local name="$1"
    local repo_path="${HOME}/proj/${name}"

    [[ -d "${repo_path}" ]] || {
        _info "SKIP ${name}: not found at ${repo_path}"
        return 0
    }

    # Must be an actual git repo.
    if ! git -C "${repo_path}" rev-parse --git-dir &>/dev/null; then
        _info "SKIP ${name}: not a git repository at ${repo_path}"
        return 0
    fi

    # Only ever touch a checkout that is on develop — never disturb a
    # feature-branch checkout.
    local branch
    branch="$(git -C "${repo_path}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    if [[ "${branch}" != "develop" ]]; then
        _info "SKIP ${name}: on '${branch}', not 'develop'"
        return 0
    fi

    # Skip repos with uncommitted local changes (contributor workspace guard).
    local dirty
    dirty="$(git -C "${repo_path}" status --porcelain 2>/dev/null || true)"
    if [[ -n "${dirty}" ]]; then
        _warn "SKIP ${name}: has uncommitted changes — not pulling"
        return 0
    fi

    # Fast-forward only, via the branch's configured upstream (origin/develop).
    local before_sha after_sha
    before_sha="$(git -C "${repo_path}" rev-parse HEAD)"

    if ! git -C "${repo_path}" pull --ff-only 2>>"${LOG_FILE}"; then
        _warn "FAIL ${name}: pull --ff-only failed (non-fast-forward or no upstream?)"
        return 0
    fi

    after_sha="$(git -C "${repo_path}" rev-parse HEAD)"
    if [[ "${before_sha}" == "${after_sha}" ]]; then
        _info "OK ${name}: already at ${after_sha:0:12} (no new commits)"
    else
        _info "OK ${name}: ${before_sha:0:12} → ${after_sha:0:12}"
    fi
}

_info "--- post-merge-pull start (host=${HOST}) ---"
for repo_name in "${REPOS[@]}"; do
    _pull_repo "${repo_name}"
done
_info "--- post-merge-pull done ---"
