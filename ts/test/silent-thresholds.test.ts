/**
 * Thresholds whose WRONG value would be silent — pinned, and tied to each other.
 *
 * A test that builds its expectation FROM the constant under test passes at
 * every value of that constant. INBOUND_QUIET_WARN_MS survived at 7 days, a
 * threshold nothing real could ever cross, because its only test did exactly
 * that. A 2026-09-14 audit of every behaviour-gating constant in ts/lib found
 * four more like it, where a 100x error changes NOTHING anyone would see:
 *
 *   DEFAULT_STALL_SECONDS      a wedged poller is not restarted for 5 hours
 *   SUPERVISION_INTERVAL_MS    a dead adopted poller goes unnoticed for 50 min
 *   DEFAULT_POLL_STALENESS_MS  message reads say "covered" for 5 hours after
 *                              polling stopped
 *   ERROR_BACKOFF_MS           each transient error outlasts the stall
 *                              threshold: a silent inbound gap plus a respawn
 *
 * Each is pinned to its value, and — more usefully — bound to the relationship
 * the code's own comments state, using the REAL imported constants. A relationship
 * breaks when one side moves without the other, which is how these go wrong.
 */

import { describe, test, expect } from "bun:test";
import { DEFAULT_STALL_SECONDS } from "../lib/poll-watchdog.js";
import { SUPERVISION_INTERVAL_MS } from "../lib/poller-supervisor.js";
import {
  DEFAULT_POLL_STALENESS_MS,
  buildCoverage,
} from "../lib/ingestion-coverage.js";
import { ERROR_BACKOFF_MS } from "../lib/poller.js";
import { INGESTION_STALE_MS } from "../lib/health-checks-ingestion.js";

const STALL_MS = DEFAULT_STALL_SECONDS * 1000;
// Telegram's long-poll cap. Independently pinned where the wire is observed:
// api-base-seam.test.ts asserts the real poller sends `timeout: 30`.
const LONG_POLL_MS = 30_000;

describe("the values, pinned (change one only on purpose, and re-check the rest)", () => {
  test("stall threshold 180 s", () => expect(DEFAULT_STALL_SECONDS).toBe(180));
  test("supervision tick 30 s", () =>
    expect(SUPERVISION_INTERVAL_MS).toBe(30_000));
  test("poll staleness 180 s", () =>
    expect(DEFAULT_POLL_STALENESS_MS).toBe(180_000));
  test("error backoff 3 s", () => expect(ERROR_BACKOFF_MS).toBe(3000));
});

describe("the relationships their own comments promise", () => {
  test("a healthy loop never trips the stall watchdog: stall > long-poll + backoff", () => {
    // poll-watchdog.ts: "well above the 30s long-poll cap plus the 3s error
    // backoff margin, so a healthy loop never trips it".
    expect(STALL_MS).toBeGreaterThan(LONG_POLL_MS + ERROR_BACKOFF_MS);
  });

  test("coverage and the watchdog agree on what 'recently alive' means", () => {
    // ingestion-coverage.ts: "180s matches the stall watchdog's own threshold
    // ... so the two agree". Disagreeing, reads could vouch for a window the
    // watchdog already considers dead (or the reverse).
    expect(DEFAULT_POLL_STALENESS_MS).toBe(STALL_MS);
  });

  test("the doctor calls ingestion stale only after self-healing had its chance", () => {
    // health-checks-ingestion.ts: stale means "the self-healing path had its
    // chance and inbound is STILL not moving".
    expect(INGESTION_STALE_MS).toBeGreaterThan(STALL_MS);
  });

  test("supervision re-checks at least as often as a stall would be noticed", () => {
    // A dead adopted poller has no exit watcher; this tick is all that sees it.
    expect(SUPERVISION_INTERVAL_MS).toBeLessThanOrEqual(STALL_MS);
  });
});

describe("the coverage verdict at the PRODUCTION default threshold", () => {
  // Production calls buildCoverage WITHOUT stalenessThresholdMs, so the default
  // decides. Existing tests pass a threshold of their own, or only check that a
  // verdict is some string — neither can see the default drift.
  const now = 1_800_000_000_000;
  const at = (lastPollTs: number) =>
    buildCoverage({
      now,
      lastPollTs,
      lastGapAt: null,
      lastGapMissedUpdates: null,
    }).verdict;

  test("a poll 1 s ago is covered", () => {
    expect(at(now - 1000)).toBe("covered");
  });

  test("a poll 200 s ago is NOT covered — polling has visibly stopped", () => {
    expect(at(now - 200_000)).toBe("unverifiable");
  });
});
