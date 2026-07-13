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
import { broadcastSystemAlert } from "./loudfail.js";
import type { WakeFailCategory } from "./wake.js";

export interface WakeFailureState {
  count: number;
  lastCategory: WakeFailCategory | null;
  lastReason: string | null;
  lastAtMs: number | null;
}

const META_KEY = "wake_failure_state";
// Round-2 adversarial review finding #3: sleepSync really does BLOCK this
// process's single JS thread (Atomics.wait — confirmed empirically), and
// each attempt previously opened a fresh connection with busy_timeout=5000
// — so 3 attempts could independently each block up to 5000ms, worst case
// ~15.1s total, in the exact process whose whole job is staying responsive
// to Telegram polling. Tightened: ONE retry (not two), and a MUCH shorter
// busy_timeout on that retry specifically — the first attempt's own 5000ms
// already gives lock contention a fair chance to clear; a second identical
// 5000ms wait 50ms later has narrow odds of a different outcome, and does
// nothing for non-lock failures (disk-full, permissions) this code cannot
// tell apart from contention anyway. wake-health's own data is a best-
// effort HEALTH SIGNAL, not user message data (which keeps the full
// 5000ms everywhere else in this codebase) — a shorter timeout here is a
// deliberate, reasoned deviation for that reason, not an oversight.
const PERSIST_MAX_ATTEMPTS = 2;
const PERSIST_RETRY_DELAY_MS = 50;
const FIRST_ATTEMPT_BUSY_TIMEOUT_MS = 2000;
const RETRY_ATTEMPT_BUSY_TIMEOUT_MS = 500;
// New worst case: 2000 + 50 + 500 = 2550ms — a small multiple of a
// second, not ~15.

let count = 0;
let lastCategory: WakeFailCategory | null = null;
let lastReason: string | null = null;
let lastAtMs: number | null = null;

/** Synchronous, bounded sleep (Atomics.wait — no busy-spin, no async so
 * callers stay synchronous). Mirrors lib/lock.ts's own sleepSync;
 * duplicated here (4 lines) rather than exported/shared, to avoid
 * coupling an unrelated module's internals for a trivial helper. */
function sleepSync(ms: number): void {
  const sab = new SharedArrayBuffer(4);
  const ia = new Int32Array(sab);
  Atomics.wait(ia, 0, 0, ms);
}

function realPersistAttempt(busyTimeoutMs: number): void {
  const db = new Database(DB_PATH);
  try {
    // busy_timeout is per-CONNECTION — an ad hoc handle like this one does
    // NOT inherit it from the file's WAL-mode schema (adversarial-review
    // finding #6). Deliberately SHORTER than the 5000ms used elsewhere in
    // this codebase for retry attempts — see the constants above.
    db.exec(`PRAGMA busy_timeout = ${busyTimeoutMs};`);
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
}

let persistAttempt: (busyTimeoutMs: number) => void = realPersistAttempt;

/** Test-only: override the single-attempt persist implementation, to
 * force failures deterministically without touching the real DB. Returns
 * the previous implementation. */
export function _setPersistAttempt(
  impl: (busyTimeoutMs: number) => void,
): (busyTimeoutMs: number) => void {
  const prev = persistAttempt;
  persistAttempt = impl;
  return prev;
}

/** Test-only: restore the real DB-backed persist attempt. */
export function _resetPersistAttempt(): void {
  persistAttempt = realPersistAttempt;
}

/**
 * Best-effort: write the current in-process state to the shared store,
 * retrying up to PERSIST_MAX_ATTEMPTS times (brief synchronous backoff
 * between attempts) before giving up LOUDLY (adversarial-review finding
 * #5: a silently-dropped write on this exact counter — meant to be the
 * trustworthy cross-process health signal the `health` tool reads — could
 * under-report or fail to clear a real failure streak with nothing to
 * notice). Synchronous by design (Atomics.wait, not setTimeout/await) so
 * callers (recordWakeFailure/recordWakeSuccess/_resetWakeFailureState)
 * keep their existing synchronous call contract.
 */
function persist(): void {
  for (let attempt = 1; attempt <= PERSIST_MAX_ATTEMPTS; attempt++) {
    const busyTimeoutMs =
      attempt === 1
        ? FIRST_ATTEMPT_BUSY_TIMEOUT_MS
        : RETRY_ATTEMPT_BUSY_TIMEOUT_MS;
    try {
      persistAttempt(busyTimeoutMs);
      return;
    } catch (err) {
      if (attempt < PERSIST_MAX_ATTEMPTS) {
        log(
          "wake-health",
          `persist attempt ${attempt}/${PERSIST_MAX_ATTEMPTS} failed — retrying`,
          { error: String(err) },
        );
        sleepSync(PERSIST_RETRY_DELAY_MS);
      } else {
        const msg =
          `FATAL: wake-failure state failed to persist after ` +
          `${PERSIST_MAX_ATTEMPTS} attempts — the cross-process wake-health ` +
          `signal (the health tool's wake_delivery_backlog) may now be ` +
          `stale/incorrect. Last error: ` +
          `${err instanceof Error ? err.message : String(err)}`;
        log("wake-health", msg);
        void broadcastSystemAlert(msg);
      }
    }
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
      db.exec("PRAGMA busy_timeout = 5000;"); // per-connection; see realPersistAttempt
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
