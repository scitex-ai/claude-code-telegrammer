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
 * In-process only — same durability model as poll-watchdog.ts's heartbeat.
 * A process restart starts the counter at zero, but the very next inbound
 * message re-probes the wake path immediately, so a restart can't hide a
 * still-broken target for more than one message.
 */

import type { WakeFailCategory } from "./wake.js";

export interface WakeFailureState {
  count: number;
  lastCategory: WakeFailCategory | null;
  lastReason: string | null;
  lastAtMs: number | null;
}

let count = 0;
let lastCategory: WakeFailCategory | null = null;
let lastReason: string | null = null;
let lastAtMs: number | null = null;

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
}

/** Call on every wakeTurn success. Clears the backlog — the path is proven live again. */
export function recordWakeSuccess(): void {
  count = 0;
  lastCategory = null;
  lastReason = null;
  lastAtMs = null;
}

/** Read the current state for the health doctor. */
export function getWakeFailureState(): WakeFailureState {
  return { count, lastCategory, lastReason, lastAtMs };
}

/** Test-only: reset all state. */
export function _resetWakeFailureState(): void {
  count = 0;
  lastCategory = null;
  lastReason = null;
  lastAtMs = null;
}
