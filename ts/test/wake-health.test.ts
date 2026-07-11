/**
 * Tests for lib/wake-health.ts — the consecutive-wake-failure tracker
 * (incident incident-cct-inbound-dies-silently-with-mcp-server-20260711).
 */

import { describe, test, expect, beforeEach } from "bun:test";
import {
  recordWakeFailure,
  recordWakeSuccess,
  getWakeFailureState,
  _resetWakeFailureState,
} from "../lib/wake-health.js";

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
