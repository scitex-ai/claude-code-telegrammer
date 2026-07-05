#!/usr/bin/env bash
# scitex-dev — canonical PostToolUse `run_lint.sh` hook.
# -*- coding: utf-8 -*-
#
# This is the AUTHORITATIVE source for the agent-feedback lint hook.
# Operator projects should NOT carry their own copy that drifts; instead
# either (a) symlink to this file via
#
#     ln -s "$(scitex-dev hooks path run_lint)" \
#         docs/to_claude/hooks/post-tool-use/run_lint.sh
#
# or (b) ship a thin wrapper that execs this script. The 2026-06-12
# Pillar-0 dogfood pinned the recurrence class — every fanned-out copy
# accumulated drift, and the in-tree calls to `scitex-linter` (archived)
# and `scitex linter` (dropped #95 umbrella-thinning) silently no-op'd
# the SciTeX pattern check on every research script edit. THIS file
# uses the LIVE command `scitex-dev linter check-files` so the agent
# feedback surface actually receives the IO0xx / PA0xx / structural
# warnings.
#
# Supported languages: Python (scitex-dev linter + ruff), TypeScript
# /JS (eslint), Emacs Lisp (byte-compile), Shell (shellcheck), HTML
# (htmlhint). Exit codes follow the agent-feedback contract:
#   0  success — no agent-visible action required
#   1  warning — agent sees feedback but continues
#   2  error — agent must fix before continuing
#
# The lead-learnings/11 + lead-learnings/04 recurrence class (fix in
# template doesn't reach deployed copies) is the reason this file
# exists in scitex-dev source tree: future fixes land here and
# every project that symlinks/wraps automatically picks them up.

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_PATH="$THIS_DIR/.$(basename "$0").log"
echo >"$LOG_PATH" 2>/dev/null || true

GRAY='\033[0;90m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo_info() { echo -e "${GRAY}INFO: $1${NC}"; }
echo_success() { echo -e "${GREEN}SUCC: $1${NC}"; }
echo_warning() { echo -e "${YELLOW}WARN: $1${NC}"; }
echo_error() { echo -e "${RED}ERRO: $1${NC}"; }
echo_header() { echo_info "=== $1 ==="; }

# --self-test: verify hook works with sample input.
if [[ "${1:-}" == "--self-test" ]]; then
    echo "=== Self-test: $(basename "$0") ==="
    pass=0
    fail=0
    echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/nonexistent_test_hook_file.py","content":"x=1"},"tool_response":{"stdout":"","stderr":""},"cwd":"/tmp","session_id":"test","tool_use_id":"test-1"}' \
        | "$0" >/dev/null 2>&1 && rc=$? || rc=$?
    if [[ $rc -eq 0 ]]; then
        ((pass++))
        echo "  PASS: non-existent file handled (exit $rc)"
    else
        ((fail++))
        echo "  FAIL: should handle gracefully (exit $rc)"
    fi
    echo "Results: $pass passed, $fail failed"
    [[ $fail -eq 0 ]] && exit 0 || exit 1
fi

set -euo pipefail

# Honour the hook-switch helper if the project provides one.
HELPER_SCRIPT="$(dirname "$THIS_DIR")/project-switch/hook_switch_helper.sh"
if [[ -f "$HELPER_SCRIPT" ]]; then
    # shellcheck source=/dev/null
    source "$HELPER_SCRIPT"
    check_hook_enabled_or_exit "$(basename "$0")"
fi

NPM_GLOBAL_BIN="$HOME/.npm-global/bin"
LOCAL_BIN="$HOME/.local/bin"
GOPATH_BIN="$(go env GOPATH 2>/dev/null || true)/bin"
[ -d "$NPM_GLOBAL_BIN" ] && export PATH="$NPM_GLOBAL_BIN:$PATH"
[ -d "$LOCAL_BIN" ] && export PATH="$LOCAL_BIN:$PATH"
[ -d "$GOPATH_BIN" ] && export PATH="$GOPATH_BIN:$PATH"

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('file_path', '') or '')
" 2>/dev/null || echo "")

[ -n "$FILE_PATH" ] || exit 0
[ -f "$FILE_PATH" ] || exit 0

lint_python() {
    local file="$1"

    # SciTeX pattern check — LIVE command. Replaces the archived
    # `scitex-linter` / dropped `scitex linter` chain. If
    # `scitex-dev` is not installed in the agent env, emit a
    # fail-loud notice (mirrors the L1 stderr notice the linter
    # itself emits when the IO plugin is missing — Pillar 0) so
    # the agent sees what's missing instead of a silent skip.
    if command -v scitex-dev &>/dev/null; then
        # BLOCKING pass: --new-only so only NEWLY-introduced errors (vs the
        # HEAD baseline) trip exit 2. Research-mode severity promotion (#264/
        # #265) flips figure/io/import-family rules to ERROR; without this
        # gate an agent editing a legacy file with a large PRE-EXISTING
        # backlog (NeuroVista: ~1000 violations across 207 files) would be
        # wedged on violations it never introduced. Pre-existing errors are
        # capped to warning by --new-only, so they stay visible in the
        # warning pass below but do NOT block. This is the SAFETY PAIR for
        # the promotion: the two must ship together.
        scitex-dev linter check-files "$file" --severity error --no-color \
            --new-only --baseline HEAD >&2 || exit 2
        # Non-blocking pass: show ALL findings at warning+ (no --new-only) so
        # the agent still sees the full legacy backlog as feedback.
        scitex-dev linter check-files "$file" --severity warning --no-color >&2 || true
    elif command -v scitex-linter &>/dev/null; then
        # Defensive fallback for 2026-pre-Q2 deployments. The standalone
        # `scitex-linter` is archived but may still be on PATH on some
        # hosts; honour it so the hook does not regress.
        scitex-linter check "$file" --severity error --no-color >&2 || exit 2
        scitex-linter check "$file" --severity warning --no-color >&2 || true
    else
        echo_warning "scitex-dev not on PATH — SciTeX pattern checks SKIPPED for $file." >&2
        echo_warning "Install: pip install scitex-dev. (See scitex-dev #TBD — Pillar 0.)" >&2
    fi

    # Standard linting.
    if command -v ruff &>/dev/null; then
        local preview
        preview=$(ruff check --diff "$file" 2>/dev/null || true)
        if echo "$preview" | grep -q "^-.*import" 2>/dev/null; then
            echo "HINT: ruff --fix will remove import(s) from $file." >&2
            echo "If you added an import for code you haven't written yet," >&2
            echo "add both import and usage in a single edit to prevent removal." >&2
        fi
        ruff check --fix "$file" 2>&1
        return $?
    elif command -v flake8 &>/dev/null; then
        flake8 "$file" 2>&1
        return $?
    fi
    return 0
}

lint_js_ts() {
    local file="$1"
    if command -v eslint &>/dev/null; then
        eslint --fix "$file" 2>&1
        return $?
    fi
    return 0
}

lint_elisp() {
    local file="$1"
    local exit_code=0
    if command -v emacs &>/dev/null; then
        emacs --batch \
            --eval "(setq byte-compile-error-on-warn t)" \
            --eval "(byte-compile-file \"$file\")" \
            2>&1
        exit_code=$?
        rm -f "${file}c" 2>/dev/null || true
    fi
    return $exit_code
}

lint_shell() {
    local file="$1"
    if command -v shellcheck &>/dev/null; then
        shellcheck "$file" >&2
        return $?
    fi
    return 0
}

lint_html() {
    local file="$1"
    if command -v htmlhint &>/dev/null; then
        htmlhint "$file" 2>&1
        return $?
    fi
    return 0
}

case "$FILE_PATH" in
*.py)
    lint_python "$FILE_PATH" || exit 2
    ;;
*.ts | *.tsx | *.js | *.jsx)
    lint_js_ts "$FILE_PATH" || exit 2
    ;;
*.el)
    lint_elisp "$FILE_PATH" || exit 2
    ;;
*.sh | *.src | *.bash)
    lint_shell "$FILE_PATH" || exit 2
    ;;
*.html | *.htm)
    lint_html "$FILE_PATH" || exit 2
    ;;
esac

exit 0

# EOF
