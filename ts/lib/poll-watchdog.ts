/**
 * Ingestion-stall watchdog for the getUpdates poller (PR-A, 2026-07).
 *
 * Closes the failure mode liveness checks MISS: the poller PROCESS is
 * alive (kill-0 passes, the per-token pidfile records a live PID) yet no
 * messages are being ingested because the getUpdates call itself is
 * WEDGED — a network black-hole, a hung socket, or a long-poll whose
 * await never resolves. kill-0 says "healthy"; the operator's channel
 * goes silent. That silence must become LOUD.
 *
 * Two decoupled pieces:
 *
 *   1. HEARTBEAT — {@link recordSuccessfulPoll} stamps an in-process
 *      epoch-ms timestamp every time getUpdates RETURNS (throws or not is
 *      the caller's concern; a return of zero updates still counts — a
 *      healthy 30s long-poll returns at least that often). It also
 *      persists the stamp to the DB (best-effort) so an out-of-band probe
 *      can read poll-freshness later, mirroring how the offset persists.
 *
 *   2. WATCHDOG — {@link createStallWatchdog} builds a stateful checker
 *      whose `tick()` compares `now - lastSuccessfulPoll` against the
 *      threshold and emits ONE loud channel notification per stall
 *      episode. It re-arms automatically once a fresh poll advances the
 *      heartbeat, and never fires while the poller is shutting down
 *      (isPolling() === false). `now`, the heartbeat getter, and the emit
 *      sink are all injectable so the whole thing is unit-testable with
 *      no timers and no network — the same seam poller-batch.ts uses for
 *      processBatch.
 *
 * PR-A is DETECTION/ALARM ONLY. It deliberately does NOT add an
 * HTTP-level timeout to tgApi, nor auto-restart the bridge — those are
 * noted follow-ups. The actionable alarm tells the operator to restart.
 */

import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { log } from "./log.js";
import { BOT_TOKEN_HASH, STATE_DIR, CHANNEL_SOURCE } from "./config.js";
import { saveLastPollTs } from "./store.js";
import { getenv } from "./env.js";

/** Default stall threshold (seconds) — well above the 30s long-poll cap
 * plus the 3s error backoff margin, so a healthy loop never trips it. */
export const DEFAULT_STALL_SECONDS = 180;

/** Watchdog check cadence ceiling (ms). Actual cadence is
 * min(this, threshold/4) so a short threshold still gets ~4 checks. */
export const MAX_CHECK_INTERVAL_MS = 30_000;

// ── In-process heartbeat ────────────────────────────────────────────────────
//
// Module-level so the poll loop and the watchdog share it without
// threading a value through every call. Read via getLastSuccessfulPoll().
let lastSuccessfulPollMs = 0;

/**
 * Stamp "getUpdates just returned successfully" — call from the poll loop
 * right where a successful getUpdates resets consecutive409. Updates the
 * in-process heartbeat AND persists it (best-effort; a store error is
 * logged, never thrown — the poll loop must not die because a heartbeat
 * write failed).
 *
 * @param now Injectable epoch-ms clock (defaults to Date.now()).
 */
export function recordSuccessfulPoll(now: number = Date.now()): void {
  lastSuccessfulPollMs = now;
  try {
    saveLastPollTs(now);
  } catch (err) {
    log("poller", "failed to persist last-poll heartbeat", {
      error: String(err),
    });
  }
}

/** Read the in-process heartbeat (epoch-ms of the last successful poll,
 * 0 if none yet). Exposed for the watchdog and for tests. */
export function getLastSuccessfulPoll(): number {
  return lastSuccessfulPollMs;
}

/** Test-only: reset the in-process heartbeat. */
export function _resetHeartbeat(): void {
  lastSuccessfulPollMs = 0;
}

/** Resolve the stall threshold (ms) from the env alias system.
 * `CCT_POLL_STALL_SECONDS` / `CLAUDE_CODE_TELEGRAMMER_POLL_STALL_SECONDS`;
 * empty/unset/invalid → {@link DEFAULT_STALL_SECONDS}. */
export function resolveStallThresholdMs(
  env: Record<string, string | undefined> = process.env,
): number {
  const raw = getenv("POLL_STALL_SECONDS", undefined, env);
  const secs = raw !== undefined ? Number(raw) : NaN;
  const eff = Number.isFinite(secs) && secs > 0 ? secs : DEFAULT_STALL_SECONDS;
  return eff * 1000;
}

// ── Watchdog ────────────────────────────────────────────────────────────────

export interface StallWatchdogDeps {
  /** Epoch-ms clock (injectable for tests; defaults to Date.now). */
  now?: () => number;
  /** Heartbeat getter (defaults to the module in-process stamp). */
  getLastPoll?: () => number;
  /** Loud-notification sink (defaults to an mcp channel notification). */
  emit?: (content: string) => void;
  /** True while the poller is actively polling; when false the watchdog
   * stays silent (clean shutdown / preemption must not alarm). */
  isPolling: () => boolean;
  /** Stall threshold in ms. */
  thresholdMs: number;
}

export interface StallWatchdog {
  /** Run one stall check. Idempotent per episode: fires the alarm at most
   * once until a fresh poll re-arms it. */
  tick(): void;
}

/**
 * Build the loud, actionable stall message. Names the stall duration, the
 * "alive but not polling" nature, the likely causes, and the fix.
 */
function stallMessage(stallMs: number, thresholdMs: number): string {
  const stallSec = Math.round(stallMs / 1000);
  const thresholdSec = Math.round(thresholdMs / 1000);
  return (
    `INGESTION STALL: getUpdates has not returned successfully for ` +
    `~${stallSec}s (threshold ${thresholdSec}s). The bridge process is ` +
    `ALIVE but NOT polling — no Telegram messages are being ingested. ` +
    `A liveness/kill-0 check would still pass, so this is invisible ` +
    `WITHOUT this alarm. Likely cause: a network black-hole, a hung ` +
    `socket, or a wedged long-poll (the getUpdates await never resolved). ` +
    `ACTION: restart the bridge to recover. ` +
    `(token=${BOT_TOKEN_HASH} state_dir=${STATE_DIR})`
  );
}

/** Default emit: same channel-notification mechanism the poller's
 * 409-fatal path and poller-batch's emitLoud use (meta.type "error"). */
function defaultEmit(mcp: Server, content: string): void {
  log("poller", content);
  mcp
    .notification({
      method: "notifications/claude/channel",
      params: { content, meta: { source: CHANNEL_SOURCE, type: "error" } },
    })
    .catch(() => {});
}

/**
 * Create a stateful stall watchdog. Re-arm semantics live entirely in the
 * heartbeat value: each tick remembers the last heartbeat it saw; when a
 * newer heartbeat appears (a poll resumed) the "already alarmed" latch is
 * cleared, so a later stall alarms again. No coupling to the heartbeat
 * writer is needed.
 */
export function createStallWatchdog(deps: StallWatchdogDeps): StallWatchdog {
  const now = deps.now ?? Date.now;
  const getLastPoll = deps.getLastPoll ?? getLastSuccessfulPoll;
  const { emit, isPolling, thresholdMs } = deps;

  let alreadyAlarmed = false;
  let lastSeenPoll = getLastPoll();

  return {
    tick(): void {
      const lastPoll = getLastPoll();
      // A fresh poll advanced the heartbeat → the stall (if any) is over;
      // re-arm so a FUTURE stall alarms again.
      if (lastPoll > lastSeenPoll) {
        alreadyAlarmed = false;
      }
      lastSeenPoll = lastPoll;

      // Clean shutdown / preemption: never alarm once polling stops.
      if (!isPolling()) return;

      const stallMs = now() - lastPoll;
      if (stallMs > thresholdMs && !alreadyAlarmed) {
        emit(stallMessage(stallMs, thresholdMs));
        alreadyAlarmed = true;
      }
    },
  };
}

export interface WatchdogHandle {
  /** Stop the interval so it can't leak or alarm after shutdown. */
  stop(): void;
}

/**
 * Production entry point: seed the heartbeat to "now" (so the first
 * threshold window starts at poll start, not epoch 0), start the
 * setInterval watchdog, and return a handle whose stop() clears it.
 * Called by startPolling; its stop() runs on every poll-loop exit path.
 */
export function startStallWatchdog(
  mcp: Server,
  isPolling: () => boolean,
): WatchdogHandle {
  const thresholdMs = resolveStallThresholdMs();
  const checkIntervalMs = Math.min(MAX_CHECK_INTERVAL_MS, thresholdMs / 4);

  // Seed so the watchdog does not fire before the first getUpdates has had
  // a chance to return (heartbeat starts at 0 = "1970", which would look
  // like an infinite stall on the very first tick).
  recordSuccessfulPoll();

  const watchdog = createStallWatchdog({
    isPolling,
    thresholdMs,
    emit: (content) => defaultEmit(mcp, content),
  });

  log(
    "poller",
    `ingestion-stall watchdog armed (threshold ${Math.round(
      thresholdMs / 1000,
    )}s, checking every ${Math.round(checkIntervalMs / 1000)}s)`,
  );

  const handle = setInterval(() => watchdog.tick(), checkIntervalMs);
  // Do not keep the process alive solely for this timer.
  if (typeof handle === "object" && handle && "unref" in handle) {
    (handle as { unref: () => void }).unref();
  }

  return {
    stop(): void {
      clearInterval(handle);
    },
  };
}
