/**
 * Wake-delivery failure tracker for the health doctor (incident
 * incident-cct-inbound-dies-silently-with-mcp-server-20260711).
 *
 * poller_alive proves the getUpdates FETCH loop lives; it says nothing
 * about whether the WAKE POST to the agent's own /v1/turn actually lands.
 * A dead turn-bridge (nothing listening on the configured TURN_URL) makes
 * every wake fail while poller_alive stays green — the exact gap that let
 * an outage go undetected while the doctor reported every check ok.
 *
 * This module is the durable-enough signal a LATER health check can read:
 * a running count of consecutive wake failures since the last success.
 * Reset to zero on any success, so it answers "is the wake path stuck
 * failing RIGHT NOW", not "did it ever fail".
 *
 * CROSS-PROCESS (architecture fix, incident-cct-inbound-dies-silently-with-
 * mcp-server-20260711 follow-up, 2026-07): the getUpdates poller now runs in
 * its own standalone process (ts/telegram-poller.ts), decoupled from the MCP
 * server (ts/telegram-server.ts) so an MCP-child restart can no longer kill
 * inbound delivery. recordWakeFailure/recordWakeSuccess are called from the
 * POLLER process (lib/handle-update.ts); the `health` MCP tool that reads
 * getWakeFailureState() runs in the SEPARATE MCP-server process. In-process
 * module state alone can no longer bridge that gap, so every write is ALSO
 * persisted to the shared SQLite store (same meta-table kv pattern
 * lib/poll-watchdog.ts uses for its own last-poll heartbeat via
 * saveLastPollTs/loadLastPollTs) and every read prefers the persisted value,
 * falling back to the in-process one only when the DB is unavailable (e.g.
 * a unit test that never called initStore(), or the CLI `health` doctor mode
 * which deliberately never starts the store). Uses its OWN independent DB
 * handle against the exported store.ts::DB_PATH — the same "many independent
 * handles against one WAL-mode file" pattern lib/attachments.ts::getDb() and
 * lib/health-adapters.ts::probeDb() already rely on — rather than growing
 * store.ts itself (already at this repo's per-file line cap).
 */

import { Database } from "bun:sqlite";
import { DB_PATH } from "./store.js";
import { log } from "./log.js";
import type { WakeFailCategory } from "./wake.js";

export interface WakeFailureState {
  count: number;
  lastCategory: WakeFailCategory | null;
  lastReason: string | null;
  lastAtMs: number | null;
}

const META_KEY = "wake_failure_state";

let count = 0;
let lastCategory: WakeFailCategory | null = null;
let lastReason: string | null = null;
let lastAtMs: number | null = null;

/** Best-effort: write the current in-process state to the shared store.
 * Never throws — a persistence failure is logged, not propagated, exactly
 * like poll-watchdog.ts::recordSuccessfulPoll's saveLastPollTs call. */
function persist(): void {
  try {
    const db = new Database(DB_PATH);
    try {
      db.prepare(
        `INSERT INTO meta (key, value) VALUES (?, ?)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
      ).run(
        META_KEY,
        JSON.stringify({ count, lastCategory, lastReason, lastAtMs }),
      );
    } finally {
      db.close();
    }
  } catch (err) {
    log("wake-health", "failed to persist wake-failure state", {
      error: String(err),
    });
  }
}

/** Best-effort READONLY read of the persisted state (never mutates — safe
 * against the live poller's WAL). Returns null when the store isn't
 * reachable yet (no DB file, no meta row, or a genuinely unrelated process
 * that never called initStore()) so the caller can fall back cleanly. */
function readPersisted(): WakeFailureState | null {
  try {
    const db = new Database(DB_PATH, { readonly: true });
    try {
      const row = db
        .prepare(`SELECT value FROM meta WHERE key = ?`)
        .get(META_KEY) as { value: string } | undefined;
      if (!row) return null;
      return JSON.parse(row.value) as WakeFailureState;
    } finally {
      db.close();
    }
  } catch (err) {
    log(
      "wake-health",
      "failed to read persisted wake-failure state — falling back to in-process value",
      { error: String(err) },
    );
    return null;
  }
}

/** Call on every wakeTurn failure. Increments the running backlog counter. */
export function recordWakeFailure(
  category: WakeFailCategory,
  reason: string,
  now: number = Date.now(),
): void {
  count += 1;
  lastCategory = category;
  lastReason = reason;
  lastAtMs = now;
  persist();
}

/** Call on every wakeTurn success. Clears the backlog — the path is proven live again. */
export function recordWakeSuccess(): void {
  count = 0;
  lastCategory = null;
  lastReason = null;
  lastAtMs = null;
  persist();
}

/**
 * Read the current state for the health doctor. Prefers the persisted
 * (possibly cross-process) value — the poller process is the one actually
 * calling record{Failure,Success}, so a health-tool call running in the
 * separate MCP-server process must read THAT, not its own (permanently
 * unwritten) in-process copy. Falls back to the in-process value when the
 * store isn't reachable (unit tests that skip initStore(), or the CLI
 * `health` doctor mode, which never starts the store at all).
 */
export function getWakeFailureState(): WakeFailureState {
  const persisted = readPersisted();
  if (persisted !== null) return persisted;
  return { count, lastCategory, lastReason, lastAtMs };
}

/** Test-only: reset all state, in-process AND persisted. */
export function _resetWakeFailureState(): void {
  count = 0;
  lastCategory = null;
  lastReason = null;
  lastAtMs = null;
  persist();
}
