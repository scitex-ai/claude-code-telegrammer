#!/bin/bash
# Persistent GitHub Actions self-hosted runner — runs on the HPC compute node.
#
# This script is started ON the lease's compute node by `scitex-dev ci runner
# up`, which ssh's straight to the node (ProxyJump through a login node) and
# detaches it with `setsid nohup`. There is intentionally NO wrapping
# `srun --overlap` here: a persistent login-node srun CLIENT is exactly the
# stdio tether the SSH-vector fix removed (2026-06-17 admin incident, ~20
# srun/login-node ceiling). The runner shares the compute node the lease already
# holds, so it needs no allocation of its own and adds zero login-node srun.
#
# Designed to:
#   * Download + cache the actions-runner tarball ONCE (persistent project
#     storage, NOT user home — home is typically quota-limited on HPC).
#   * Mint a registration token from a caller-provided GH_TOKEN env var.
#   * Run a PERSISTENT runner with `./run.sh` (NOT --ephemeral) so the
#     same agent survives across CI jobs — startup cost amortised, queue
#     latency near zero.
#   * Re-launch ./run.sh on crash with exponential backoff, capped.
#   * Clean-deregister on TERM/INT so the GitHub UI never shows a stale
#     "offline" entry after lease-job death.
#
# Env contract (exported by the compute-node run script in _up.py):
#   GH_TOKEN       operator PAT, scoped repo:admin on the trial repo
#   GH_REPO        e.g. <OWNER>/<REPO>
#   RUNNER_NAME    e.g. scitex-ci-runner-01
#   RUNNER_LABELS  comma list, e.g. self-hosted,scitex-ci
#   RUNNER_HOME    persistent project storage dir for the runner workdir
#
# Logs to $RUNNER_HOME/runner.log; never to stdout (the launching ssh detaches
# immediately, so stdout has nowhere to go).

set -u
LOGF="${RUNNER_HOME}/runner.log"
log() { printf '[%s] %s\n' "$(date -Iseconds)" "$*" >>"$LOGF"; }

trap 'cleanup' INT TERM
cleanup() {
    log "trap: deregistering runner $RUNNER_NAME"
    if [ -f "$RUNNER_HOME/.runner" ]; then
        REMOVE_TOKEN=$(curl -fsS -X POST \
            -H "Authorization: token $GH_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/$GH_REPO/actions/runners/remove-token" |
            python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' \
                2>>"$LOGF" || echo "")
        if [ -n "$REMOVE_TOKEN" ]; then
            (cd "$RUNNER_HOME" && ./config.sh remove --token "$REMOVE_TOKEN" >>"$LOGF" 2>&1) || true
        fi
    fi
    log "trap: clean exit"
    exit 0
}

mkdir -p "$RUNNER_HOME"
cd "$RUNNER_HOME" || {
    log "FATAL: cannot cd to RUNNER_HOME=$RUNNER_HOME"
    exit 1
}

# Cache the runner tarball in the parent dir's cache/ so we don't re-fetch.
# Pin the version so updates are deliberate.
RUNNER_VERSION="${RUNNER_VERSION:-2.328.0}"
TARBALL="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
CACHE_DIR="$(dirname "$RUNNER_HOME")/cache"
mkdir -p "$CACHE_DIR"
if [ ! -f "$CACHE_DIR/$TARBALL" ]; then
    log "fetching runner ${RUNNER_VERSION}"
    curl -fsSL -o "$CACHE_DIR/$TARBALL" \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}" \
        >>"$LOGF" 2>&1
fi

# Extract if not already.
if [ ! -x "$RUNNER_HOME/run.sh" ]; then
    log "extracting runner into $RUNNER_HOME"
    tar -xzf "$CACHE_DIR/$TARBALL" -C "$RUNNER_HOME"
fi

# Register if not already configured (presence of .runner is the marker).
if [ ! -f "$RUNNER_HOME/.runner" ]; then
    log "minting registration token"
    REG_TOKEN=$(curl -fsS -X POST \
        -H "Authorization: token $GH_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/$GH_REPO/actions/runners/registration-token" |
        python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
    if [ -z "$REG_TOKEN" ]; then
        log "FATAL: empty registration token; aborting"
        exit 1
    fi
    log "configuring runner $RUNNER_NAME labels=$RUNNER_LABELS"
    ./config.sh \
        --url "https://github.com/$GH_REPO" \
        --token "$REG_TOKEN" \
        --name "$RUNNER_NAME" \
        --labels "$RUNNER_LABELS" \
        --work _work \
        --unattended \
        --replace \
        >>"$LOGF" 2>&1
fi

# Persistent run loop. Exponential backoff up to 5 minutes if run.sh
# fails repeatedly — covers transient GitHub API outages without
# hammering them.
backoff=5
max_backoff=300
while true; do
    log "starting ./run.sh"
    if ./run.sh >>"$LOGF" 2>&1; then
        log "./run.sh exited cleanly"
        backoff=5
    else
        rc=$?
        log "./run.sh exited rc=$rc; backoff ${backoff}s"
        sleep "$backoff"
        backoff=$((backoff * 2))
        [ "$backoff" -gt "$max_backoff" ] && backoff=$max_backoff
    fi
done
