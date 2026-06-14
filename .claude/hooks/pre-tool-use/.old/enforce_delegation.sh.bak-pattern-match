#!/bin/bash
# -*- coding: utf-8 -*-
# Timestamp: "2026-03-26 (ywatanabe)"
# File: ~/.claude/hooks/pre-tool-use/enforce_delegation.sh

# Description: Warns when a Bash command is likely to take more than 7 seconds.
# Reminds the master agent to delegate long-running tasks to subagents instead.
# Only active when CLAUDE_ORCHESTRATOR=1 (master agent context).
# Does NOT block any commands (exit 0 always). Warning only.
#
# Patterns flagged: sleep, wait, docker restart/build/compose,
# make, npm install/ci/build, pytest, pip install, yarn, cargo build,
# apt install, wget/curl download, git clone, ssh.

# --self-test: verify hook works with sample input
if [[ "${1:-}" == "--self-test" ]]; then
    echo "=== Self-test: $(basename "$0") ==="
    pass=0
    fail=0

    # Export orchestrator flag so inner "$0" calls activate the hook
    export CLAUDE_ORCHESTRATOR=1

    # Test 1: short command - no warning
    result=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"ls -la"},"cwd":"/tmp","session_id":"test","tool_use_id":"t1"}' | "$0" 2>&1)
    if [[ -z "$result" ]]; then
        ((pass++))
        echo "  PASS: short command - no warning"
    else
        ((fail++))
        echo "  FAIL: short command produced unexpected output: $result"
    fi

    # Test 2: sleep command - should block (exit 2)
    result=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"sleep 10"},"cwd":"/tmp","session_id":"test","tool_use_id":"t2"}' | "$0" 2>&1) && rc=$? || rc=$?
    if [[ $rc -eq 2 ]] && echo "$result" | grep -q "subagent"; then
        ((pass++))
        echo "  PASS: sleep command - blocked (exit $rc)"
    else
        ((fail++))
        echo "  FAIL: sleep command - expected block exit 2, got: exit $rc"
    fi

    # Test 3: make command - should block (exit 2)
    result=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"make all"},"cwd":"/tmp","session_id":"test","tool_use_id":"t3"}' | "$0" 2>&1) && rc=$? || rc=$?
    if [[ $rc -eq 2 ]]; then
        ((pass++))
        echo "  PASS: make command - blocked (exit $rc)"
    else
        ((fail++))
        echo "  FAIL: make command - expected block exit 2, got: exit $rc"
    fi

    # Test 4: npm install - should block (exit 2)
    result=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"npm install"},"cwd":"/tmp","session_id":"test","tool_use_id":"t4"}' | "$0" 2>&1) && rc=$? || rc=$?
    if [[ $rc -eq 2 ]]; then
        ((pass++))
        echo "  PASS: npm install - blocked (exit $rc)"
    else
        ((fail++))
        echo "  FAIL: npm install - expected block exit 2, got: exit $rc"
    fi

    # Test 5: non-Bash tool - no warning
    result=$(printf '%s' '{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.txt","content":"hello"},"cwd":"/tmp","session_id":"test","tool_use_id":"t5"}' | "$0" 2>&1)
    if [[ -z "$result" ]]; then
        ((pass++))
        echo "  PASS: non-Bash tool - no warning"
    else
        ((fail++))
        echo "  FAIL: non-Bash tool produced unexpected output: $result"
    fi

    # Test 6: docker restart - should block (exit 2)
    result=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"docker restart mycontainer"},"cwd":"/tmp","session_id":"test","tool_use_id":"t6"}' | "$0" 2>&1) && rc=$? || rc=$?
    if [[ $rc -eq 2 ]]; then
        ((pass++))
        echo "  PASS: docker restart - blocked (exit $rc)"
    else
        ((fail++))
        echo "  FAIL: docker restart - expected block exit 2, got: exit $rc"
    fi

    # Test 7: without CLAUDE_ORCHESTRATOR, no warning (subagents are not warned)
    unset CLAUDE_ORCHESTRATOR
    result=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"make all"},"cwd":"/tmp","session_id":"test","tool_use_id":"t7"}' | "$0" 2>&1)
    if [[ -z "$result" ]]; then
        ((pass++))
        echo "  PASS: without CLAUDE_ORCHESTRATOR, no warning"
    else
        ((fail++))
        echo "  FAIL: without CLAUDE_ORCHESTRATOR, should be silent, got: $result"
    fi

    echo "Results: $pass passed, $fail failed"
    [[ $fail -eq 0 ]] && exit 0 || exit 1
fi

set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_PATH="$THIS_DIR/.$(basename "$0").log"
echo >"$LOG_PATH" 2>/dev/null || true

# Check if hook is enabled via switch.yaml
HELPER_SCRIPT="$(dirname "$THIS_DIR")/project-switch/hook_switch_helper.sh"
if [[ -f "$HELPER_SCRIPT" ]]; then
    # shellcheck source=/dev/null
    source "$HELPER_SCRIPT"
    check_hook_enabled_or_exit "$(basename "$0")"
fi

# Only warn in master agent (orchestrator) context.
# Subagents are allowed to run long commands directly.
# Check env var or file-based flag (for mid-session activation)
if [[ "${CLAUDE_ORCHESTRATOR:-}" != "1" ]] && [[ ! -f /tmp/.claude_orchestrator_flag ]]; then
    exit 0
fi

# Read input from stdin
INPUT="$(cat)"

# Allow bypass with comment: # hook-bypass: delegation
if echo "$INPUT" | grep -qF 'hook-bypass: delegation'; then
    exit 0
fi

# Parse tool name and command from JSON input using python3
PARSED="$(echo "$INPUT" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    tool = d.get("tool_name", "")
    ti = d.get("tool_input", {}) or {}
    cmd = ti.get("command", "") or ""
    cmd_flat = " ; ".join(cmd.splitlines())
    sys.stdout.write(tool + "\t" + cmd_flat + "\n")
except Exception:
    sys.stdout.write("\t\n")
' 2>/dev/null)" || true

TOOL_NAME="$(echo "$PARSED" | cut -f1)"
COMMAND="$(echo "$PARSED" | cut -f2-)"

# Only check Bash tool
[[ "$TOOL_NAME" == "Bash" ]] || exit 0

# Exit if no command
[[ -n "$COMMAND" ]] || exit 0

# Check if command matches long-running patterns
MATCHED_PATTERN=""
if echo "$COMMAND" | grep -qE '(^|[;&| ])sleep[[:space:]]+[0-9]'; then
    MATCHED_PATTERN="sleep"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])wait[[:space:]]+'; then
    MATCHED_PATTERN="wait"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])docker[[:space:]]+(restart|build|compose|pull|run)'; then
    MATCHED_PATTERN="docker restart/build/compose/pull/run"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])make([[:space:]]|$)'; then
    MATCHED_PATTERN="make"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])npm[[:space:]]+(install|ci|build|run|test)'; then
    MATCHED_PATTERN="npm install/ci/build"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])yarn([[:space:]]|$)'; then
    MATCHED_PATTERN="yarn"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])pytest'; then
    MATCHED_PATTERN="pytest"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])pip[[:space:]]+install'; then
    MATCHED_PATTERN="pip install"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])pip3[[:space:]]+install'; then
    MATCHED_PATTERN="pip3 install"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])apt[[:space:]]+(install|upgrade|update)'; then
    MATCHED_PATTERN="apt install/upgrade"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])cargo[[:space:]]+(build|test|run)'; then
    MATCHED_PATTERN="cargo build/test"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])git[[:space:]]+clone'; then
    MATCHED_PATTERN="git clone"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])(wget|curl)[[:space:]].*-[oO]'; then
    MATCHED_PATTERN="wget/curl download"
elif echo "$COMMAND" | grep -qE '(^|[;&| ])ssh[[:space:]]'; then
    MATCHED_PATTERN="ssh"
fi

# If a long-running pattern was found, BLOCK the command
if [[ -n "$MATCHED_PATTERN" ]]; then
    echo "BLOCKED: Orchestrator must delegate '$MATCHED_PATTERN' to a subagent." >&2
    echo "" >&2
    echo "Command: ${COMMAND:0:120}" >&2
    echo "" >&2
    echo "Orchestrators must not run long commands (>7s) directly." >&2
    echo "Use the Agent tool to delegate. Example:" >&2
    echo "" >&2
    echo "  Agent(prompt=\"Run: ${COMMAND:0:80}\", subagent_type=\"general-purpose\", run_in_background=true)" >&2
    echo "" >&2
    echo "Bypass: # hook-bypass: delegation" >&2
    exit 2
fi

exit 0

# EOF
