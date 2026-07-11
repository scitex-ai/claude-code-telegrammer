/**
 * Tests for the two wake-delivery health checks (incident
 * incident-cct-inbound-dies-silently-with-mcp-server-20260711):
 * wake_target_reachable and wake_delivery_backlog. Same fixture/pattern as
 * health-checks.test.ts.
 */

import { describe, test, expect } from "bun:test";
import { buildHealthReport } from "../lib/health.js";
import { healthyInputs, byName } from "./health-fixtures.js";

describe("wake_target_reachable", () => {
  test("wake disabled (no TURN_URL) → skipped ok", () => {
    const c = byName(
      buildHealthReport(healthyInputs({ wakeReachability: { kind: "disabled" } })),
      "wake_target_reachable",
    );
    expect(c.ok).toBe(true);
    expect(c.detail).toContain("skipped");
  });

  test("reachable → ok, names host:port", () => {
    const c = byName(
      buildHealthReport(
        healthyInputs({
          wakeReachability: { kind: "reachable", host: "127.0.0.1", port: 19015 },
        }),
      ),
      "wake_target_reachable",
    );
    expect(c.ok).toBe(true);
    expect(c.detail).toContain("127.0.0.1:19015");
  });

  test("unreachable (connection refused) → fail, hint names the restart action", () => {
    const c = byName(
      buildHealthReport(
        healthyInputs({
          wakeReachability: {
            kind: "unreachable",
            host: "127.0.0.1",
            port: 19015,
            detail: "connect ECONNREFUSED 127.0.0.1:19015",
          },
        }),
      ),
      "wake_target_reachable",
    );
    expect(c.ok).toBe(false);
    expect(c.detail).toContain("127.0.0.1:19015");
    expect(c.detail).toContain("ECONNREFUSED");
    expect(c.hint).toContain("restart");
    expect(c.hint).toContain("wake_delivery_backlog");
  });

  test("invalid URL → fail, hint names CCT_TURN_URL", () => {
    const c = byName(
      buildHealthReport(
        healthyInputs({
          wakeReachability: {
            kind: "invalid_url",
            url: "not a url",
            detail: "Invalid URL",
          },
        }),
      ),
      "wake_target_reachable",
    );
    expect(c.ok).toBe(false);
    expect(c.hint).toContain("CCT_TURN_URL");
  });
});

describe("wake_delivery_backlog", () => {
  test("wake disabled (null state) → skipped ok", () => {
    const c = byName(
      buildHealthReport(healthyInputs({ wakeBacklog: null })),
      "wake_delivery_backlog",
    );
    expect(c.ok).toBe(true);
    expect(c.detail).toContain("skipped");
  });

  test("count=0 (last wake succeeded) → ok", () => {
    const c = byName(
      buildHealthReport(
        healthyInputs({
          wakeBacklog: {
            count: 0,
            lastCategory: null,
            lastReason: null,
            lastAtMs: null,
          },
        }),
      ),
      "wake_delivery_backlog",
    );
    expect(c.ok).toBe(true);
    expect(c.detail).toContain("no undelivered messages");
  });

  test("count>0 → fail, detail names the count + category + reason; never silent", () => {
    const c = byName(
      buildHealthReport(
        healthyInputs({
          wakeBacklog: {
            count: 3,
            lastCategory: "connection_refused",
            lastReason: "connect ECONNREFUSED 127.0.0.1:19015",
            lastAtMs: Date.UTC(2026, 6, 11, 14, 0, 0),
          },
        }),
      ),
      "wake_delivery_backlog",
    );
    expect(c.ok).toBe(false);
    expect(c.detail).toContain("3 consecutive wake failure");
    expect(c.detail).toContain("connection_refused");
    expect(c.detail).toContain("ECONNREFUSED");
    expect(c.hint).toContain("wake_target_reachable");
  });

  test("this check alone flips the top-level report ok to false", () => {
    const report = buildHealthReport(
      healthyInputs({
        wakeBacklog: {
          count: 1,
          lastCategory: "timeout",
          lastReason: "network timeout",
          lastAtMs: Date.now(),
        },
      }),
    );
    expect(report.ok).toBe(false);
    expect(report.summary).toContain("wake_delivery_backlog");
  });
});
