#!/usr/bin/env bash
# hook-bypass: branch-guard
# (this file lives under GITIGNORED/ which is not tracked; safe to edit on develop)
#
# claude-code-telegrammer — host-side orphan-poller cleanup (#37 PART 1)
#
# Run from the HOST (lead's tmux claude shell, ppid 12222 area — anywhere
# with host PID namespace). Walks every bun process whose argv matches
# telegram-server.{ts,js}, reads /proc/<pid>/environ for the bot token,
# groups STRICTLY by token-hash, and emits a kill plan. Pass --apply to
# actually send SIGTERM.
#
# Classification rules (revised 2026-06-07 per lead review):
#   - A process counts as a POLLER iff CCT_BOT_TOKEN
#     is readable from /proc/<pid>/environ. Launcher-parents (bun fork+exec
#     parents that hand off to the real poller-child) carry NO env on the
#     parent — the env lives on the child. These are NOT pollers and are
#     SKIPPED entirely (logged "skip: launcher-parent, no token in environ").
#   - Group strictly by token-hash. Two processes with the SAME bot token
#     will 409 against each other on Telegram getUpdates; that's the only
#     duplicate that matters. AGENT_ID is preserved in the diagnostic
#     columns for readability but is NOT part of the dedup key.
#   - Older-sibling-same-token = KILL (the new takeover protocol in PR #23
#     handles this automatically going forward; this script is the one-shot
#     cleanup for orphans from BEFORE #37 deployed).
#   - Orphan = ppid==1 AND token-readable = KILL (no living agent to feed).
#
# Safety:
#   - DRY-RUN by default. No signals sent until --apply.
#   - SKIPS pid 12222 (lead's tmux claude per spec) and all its descendants.
#   - SKIPS pid 1 (init), our own pid, and the shell that ran us.
#   - SKIPS any process without a readable bot token (launcher-parents).
#
# Usage:
#   ./cleanup-orphan-pollers.sh           # dry-run, prints the plan only
#   ./cleanup-orphan-pollers.sh --apply   # actually SIGTERM the kill list

set -euo pipefail

APPLY="${1:-}"
SELF_PID=$$
LEAD_PID=12222

# Per-token state: SEEN_GROUPS[token_hash] = "winner_pid:winner_starttime".
declare -A SEEN_GROUPS
declare -a KILL_PIDS=()
declare -a KEEP_PIDS=()

is_descendant_of() {
  # returns 0 if $1 is a (transitive) descendant of $2
  local pid=$1 ancestor=$2
  while [ "$pid" != 0 ] && [ "$pid" != 1 ]; do
    if [ "$pid" = "$ancestor" ]; then return 0; fi
    pid=$(awk '{print $4}' "/proc/$pid/stat" 2>/dev/null || echo 0)
  done
  return 1
}

# Find every bun process whose command line references telegram-server
# (covers both `bun run ts/telegram-server.ts` and a hypothetical
# `bun ts/dist/telegram-server.js` invocation).
mapfile -t PIDS < <(pgrep -f "telegram-server\.(ts|js)" || true)

if [ "${#PIDS[@]}" -eq 0 ]; then
  echo "no telegram-server.{ts,js} processes found — nothing to do"
  exit 0
fi

echo "found ${#PIDS[@]} telegram-server.{ts,js} processes (will classify each)"
printf "%-8s %-8s %-12s %-30s %-10s %s\n" PID PPID STARTTIME AGENT_ID TOKEN_HASH ACTION
echo "──────────────────────────────────────────────────────────────────────────────────────────"

for pid in "${PIDS[@]}"; do
  # skip ourselves + the shell that ran us + init
  if [ "$pid" = "$SELF_PID" ] || [ "$pid" = "$PPID" ] || [ "$pid" = "1" ]; then
    continue
  fi

  # safety: don't touch the lead's tmux claude or anything under it
  if [ "$pid" = "$LEAD_PID" ] || is_descendant_of "$pid" "$LEAD_PID"; then
    printf "%-8s %-8s %-12s %-30s %-10s %s\n" "$pid" "?" "?" "-" "-" "SKIP (lead-owned)"
    continue
  fi

  ppid=$(awk '{print $4}' "/proc/$pid/stat" 2>/dev/null || echo "?")
  starttime=$(awk '{print $22}' "/proc/$pid/stat" 2>/dev/null || echo 0)

  # read /proc/<pid>/environ (null-delimited) for AGENT_ID and TOKEN
  agent_id=$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null \
    | awk -F= '$1=="CCT_AGENT_ID"{print $2; exit}')
  token=$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null \
    | awk -F= '$1=="CCT_BOT_TOKEN"{print $2; exit}')

  # CLASSIFY: must have a readable token to count as a poller.
  # Launcher-parents have no env on the parent (env lives on the child);
  # we must NOT lump them into an "<unknown>" group or we'd false-positive
  # kill them when the YOUNGEST stranger in the same false-group wins. The
  # only correct action for a no-token process is: ignore it.
  if [ -z "$token" ]; then
    printf "%-8s %-8s %-12s %-30s %-10s %s\n" \
      "$pid" "$ppid" "$starttime" "${agent_id:-<no-env>}" "-" \
      "SKIP (no BOT_TOKEN in environ — launcher-parent, not a poller)"
    continue
  fi

  token_hash=$(printf '%s' "$token" | sha256sum | awk '{print substr($1,1,8)}')
  [ -z "$agent_id" ] && agent_id="<unknown>"

  # Orphan = ppid==1 AND has a readable token. The token-readable guard
  # means we never label a launcher-parent as an orphan (its absence of
  # token is what made us SKIP above before getting here).
  if [ "$ppid" = "1" ]; then
    printf "%-8s %-8s %-12s %-30s %-10s %s\n" \
      "$pid" "$ppid" "$starttime" "$agent_id" "$token_hash" \
      "KILL (orphan: ppid==1, token readable)"
    KILL_PIDS+=("$pid")
    continue
  fi

  # Group strictly by token_hash (Telegram's 1-consumer-per-token rule
  # is the only thing that matters for duplicate detection).
  prev="${SEEN_GROUPS[$token_hash]:-}"
  if [ -z "$prev" ]; then
    SEEN_GROUPS[$token_hash]="$pid:$starttime"
    printf "%-8s %-8s %-12s %-30s %-10s %s\n" \
      "$pid" "$ppid" "$starttime" "$agent_id" "$token_hash" \
      "(candidate, first seen)"
    KEEP_PIDS+=("$pid")
    continue
  fi

  prev_pid="${prev%%:*}"
  prev_starttime="${prev##*:}"
  if [ "$starttime" -gt "$prev_starttime" ]; then
    # current is younger — keep current, kill previous (newest wins).
    printf "%-8s %-8s %-12s %-30s %-10s %s\n" \
      "$pid" "$ppid" "$starttime" "$agent_id" "$token_hash" \
      "(candidate, younger than prev winner $prev_pid)"
    SEEN_GROUPS[$token_hash]="$pid:$starttime"
    KILL_PIDS+=("$prev_pid")
    # remove prev_pid from KEEP_PIDS
    new_keep=()
    for k in "${KEEP_PIDS[@]}"; do
      [ "$k" = "$prev_pid" ] || new_keep+=("$k")
    done
    KEEP_PIDS=("${new_keep[@]}")
    KEEP_PIDS+=("$pid")
  else
    # current is older — kill it
    printf "%-8s %-8s %-12s %-30s %-10s %s\n" \
      "$pid" "$ppid" "$starttime" "$agent_id" "$token_hash" \
      "KILL (older sibling of token $token_hash; winner=$prev_pid)"
    KILL_PIDS+=("$pid")
  fi
done

echo "──────────────────────────────────────────────────────────────────────────────────────────"
echo "summary: would kill ${#KILL_PIDS[@]}, would keep ${#KEEP_PIDS[@]}"

if [ "$APPLY" != "--apply" ]; then
  echo
  echo "DRY-RUN — re-run with --apply to actually SIGTERM the kill list."
  exit 0
fi

echo
echo "applying: SIGTERM to ${#KILL_PIDS[@]} pids..."
for pid in "${KILL_PIDS[@]}"; do
  [ -z "$pid" ] && continue
  if kill -TERM "$pid" 2>/dev/null; then
    echo "  SIGTERM $pid"
  else
    echo "  SIGTERM $pid → failed (process gone?)"
  fi
done

echo "done. wait ~3s and re-run dry-run to verify cleanup."
