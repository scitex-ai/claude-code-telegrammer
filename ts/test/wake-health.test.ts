/**
 * Tests for lib/wake-health.ts — the consecutive-wake-failure tracker
 * (incident incident-cct-inbound-dies-silently-with-mcp-server-20260711).
 *
 * Cross-process persistence (architecture-fix follow-up, 2026-07): the
 * getUpdates poller now runs in its own standalone process
 * (ts/telegram-poller.ts), so recordWakeFailure/recordWakeSuccess (called
 * from lib/handle-update.ts, which only runs in the poller process) and
 * getWakeFailureState (called from the `health` MCP tool, which runs in the
 * SEPARATE MCP-server process) can no longer share in-process module state.
 * The describe block below pins the DB-persistence half of that fix,
 * mirroring how ts/test/poll-watchdog.test.ts pins saveLastPollTs/
 * loadLastPollTs for the poll heartbeat.
 */

import { describe, test, expect, beforeEach, beforeAll } from "bun:test";
import { Database } from "bun:sqlite";
import {
  recordWakeFailure,
  recordWakeSuccess,
  getWakeFailureState,
  _resetWakeFailureState,
} from "../lib/wake-health.js";
import { initStore, DB_PATH } from "../lib/store.js";

describe("wake failure tracker", () => {
  beforeEach(() => {
    _resetWakeFailureState();
  });

  test("starts at count 0, everything else null", () => {
    const s = getWakeFailureState();
    expect(s.count).toBe(0);
    expect(s.lastCategory).toBeNull();
    expect(s.lastReason).toBeNull();
    expect(s.lastAtMs).toBeNull();
  });

  test("one failure → count 1, records category/reason/timestamp", () => {
    recordWakeFailure("connection_refused", "connect ECONNREFUSED", 1000);
    const s = getWakeFailureState();
    expect(s.count).toBe(1);
    expect(s.lastCategory).toBe("connection_refused");
    expect(s.lastReason).toBe("connect ECONNREFUSED");
    expect(s.lastAtMs).toBe(1000);
  });

  test("consecutive failures increment the count and overwrite last-seen fields", () => {
    recordWakeFailure("connection_refused", "connect ECONNREFUSED", 1000);
    recordWakeFailure("timeout", "network timeout", 2000);
    recordWakeFailure("server_error", "HTTP 500", 3000);
    const s = getWakeFailureState();
    expect(s.count).toBe(3);
    expect(s.lastCategory).toBe("server_error");
    expect(s.lastReason).toBe("HTTP 500");
    expect(s.lastAtMs).toBe(3000);
  });

  test("a success resets the counter to zero and clears last-seen fields", () => {
    recordWakeFailure("connection_refused", "connect ECONNREFUSED", 1000);
    recordWakeFailure("connection_refused", "connect ECONNREFUSED", 2000);
    recordWakeSuccess();
    const s = getWakeFailureState();
    expect(s.count).toBe(0);
    expect(s.lastCategory).toBeNull();
    expect(s.lastReason).toBeNull();
    expect(s.lastAtMs).toBeNull();
  });

  test("failure after a success starts a fresh count of 1, not a continuation", () => {
    recordWakeFailure("connection_refused", "a", 1000);
    recordWakeSuccess();
    recordWakeFailure("timeout", "b", 2000);
    const s = getWakeFailureState();
    expect(s.count).toBe(1);
    expect(s.lastCategory).toBe("timeout");
  });

  test("defaults `now` to Date.now() when not injected", () => {
    const before = Date.now();
    recordWakeFailure("unknown", "x");
    const after = Date.now();
    const s = getWakeFailureState();
    expect(s.lastAtMs).not.toBeNull();
    expect(s.lastAtMs!).toBeGreaterThanOrEqual(before);
    expect(s.lastAtMs!).toBeLessThanOrEqual(after);
  });
});

describe("wake failure tracker: cross-process DB persistence", () => {
  beforeAll(() => {
    initStore();
  });
  beforeEach(() => {
    _resetWakeFailureState();
  });

  test("recordWakeFailure persists the state to the shared DB", () => {
    recordWakeFailure("connection_refused", "connect ECONNREFUSED", 1000);

    // Read back via a totally independent DB handle — the same "many
    // independent handles against one WAL-mode file" shape a SEPARATE
    // process (the MCP server, post-split) would use.
    const db = new Database(DB_PATH, { readonly: true });
    const row = db
      .prepare(`SELECT value FROM meta WHERE key = 'wake_failure_state'`)
      .get() as { value: string } | undefined;
    db.close();

    expect(row).toBeDefined();
    const parsed = JSON.parse(row!.value);
    expect(parsed).toEqual({
      count: 1,
      lastCategory: "connection_refused",
      lastReason: "connect ECONNREFUSED",
      lastAtMs: 1000,
    });
  });

  test("recordWakeSuccess persists the cleared state", () => {
    recordWakeFailure("timeout", "t", 1);
    recordWakeSuccess();

    const db = new Database(DB_PATH, { readonly: true });
    const row = db
      .prepare(`SELECT value FROM meta WHERE key = 'wake_failure_state'`)
      .get() as { value: string } | undefined;
    db.close();

    expect(row).toBeDefined();
    expect(JSON.parse(row!.value)).toEqual({
      count: 0,
      lastCategory: null,
      lastReason: null,
      lastAtMs: null,
    });
  });

  test("getWakeFailureState prefers the persisted value over stale in-process vars — the cross-process case", () => {
    // In THIS process's own view: one failure recorded.
    recordWakeFailure("timeout", "in-process view", 1000);

    // Simulate a DIFFERENT process (the real poller, post-split) having
    // written a DIFFERENT value directly to the shared DB — exactly the
    // situation the MCP-server process is in: its own in-process vars only
    // reflect what IT called record*() with (normally nothing, since only
    // the poller process ever does), but the shared DB reflects what the
    // poller process actually saw.
    const db = new Database(DB_PATH);
    db.prepare(
      `INSERT INTO meta (key, value) VALUES ('wake_failure_state', ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
    ).run(
      JSON.stringify({
        count: 7,
        lastCategory: "server_error",
        lastReason: "cross-process write",
        lastAtMs: 9999,
      }),
    );
    db.close();

    const state = getWakeFailureState();
    expect(state).toEqual({
      count: 7,
      lastCategory: "server_error",
      lastReason: "cross-process write",
      lastAtMs: 9999,
    });
  });

  test("_resetWakeFailureState clears the persisted value too (no stale leak into the next test)", () => {
    recordWakeFailure("auth", "x", 1);
    _resetWakeFailureState();

    const db = new Database(DB_PATH, { readonly: true });
    const row = db
      .prepare(`SELECT value FROM meta WHERE key = 'wake_failure_state'`)
      .get() as { value: string } | undefined;
    db.close();

    expect(row).toBeDefined();
    expect(JSON.parse(row!.value)).toEqual({
      count: 0,
      lastCategory: null,
      lastReason: null,
      lastAtMs: null,
    });
  });
});
