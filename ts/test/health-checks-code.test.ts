/**
 * code_current — the DETECTION gap.
 *
 * Raised by `grant` (2026-07-14) after three agents hit the same class of bug
 * independently inside 24 hours: each of us inferred an artifact's contents from
 * its HISTORY (PyPI, GitHub, `git merge-base`, a symptom) instead of
 * interrogating the artifact. That is how v0.5.6 was released, merged,
 * published, reported "live" — and never once executed.
 *
 * PR #78 fixed the DEPLOY gap. This check exists so the drift is VISIBLE before
 * it becomes an incident, and so the answer never comes from a version string.
 */

import { describe, test, expect } from "bun:test";
import { checkCodeCurrent } from "../lib/health-checks-code.js";

const T = 1_700_000_000_000; // an arbitrary fixed "now"

describe("checkCodeCurrent", () => {
  test("ok when both processes postdate the source", () => {
    const r = checkCodeCurrent({
      serverStartMs: T,
      pollerStartMs: T,
      codeMtimeMs: T - 60_000, // code written BEFORE they started
    });
    expect(r.entry.ok).toBe(true);
  });

  // The exact shape of the 2026-07-14 incident: a git pull landed, the poller
  // kept running the pre-pull code, and nothing anywhere said so.
  test("FAILS when the poller predates the source (the stale-poller incident)", () => {
    const r = checkCodeCurrent({
      serverStartMs: T + 120_000, // server restarted after the pull
      pollerStartMs: T, // poller did NOT — it survives restarts by design
      codeMtimeMs: T + 60_000, // the pull
    });
    expect(r.entry.ok).toBe(false);
    expect(r.entry.detail).toContain("poller");
    expect(r.entry.detail).toContain("STALE CODE");
    expect(r.entry.hint).toBeTruthy();
  });

  test("FAILS when the MCP server itself predates the source", () => {
    const r = checkCodeCurrent({
      serverStartMs: T,
      pollerStartMs: T + 120_000,
      codeMtimeMs: T + 60_000,
    });
    expect(r.entry.ok).toBe(false);
    expect(r.entry.detail).toContain("MCP server");
  });

  test("reports BOTH when both are stale", () => {
    const r = checkCodeCurrent({
      serverStartMs: T,
      pollerStartMs: T,
      codeMtimeMs: T + 60_000,
    });
    expect(r.entry.ok).toBe(false);
    expect(r.entry.detail).toContain("MCP server");
    expect(r.entry.detail).toContain("poller");
  });

  test("no live poller (null) is not itself drift", () => {
    const r = checkCodeCurrent({
      serverStartMs: T,
      pollerStartMs: null,
      codeMtimeMs: T - 60_000,
    });
    expect(r.entry.ok).toBe(true);
  });

  // FAIL-SAFE. A check whose whole job is to be believed must not cry wolf on a
  // bad read — a false alarm here trains people to ignore exactly the signal
  // that would have caught this incident.
  test("FAIL-SAFE: unreadable source mtime (0) reports ok, not stale", () => {
    const r = checkCodeCurrent({
      serverStartMs: T,
      pollerStartMs: T,
      codeMtimeMs: 0,
    });
    expect(r.entry.ok).toBe(true);
    expect(r.entry.detail).toContain("skipped");
  });

  // The hint must steer away from the instrument that lied to us.
  test("the hint warns off version strings", () => {
    const r = checkCodeCurrent({
      serverStartMs: T,
      pollerStartMs: T,
      codeMtimeMs: T + 60_000,
    });
    expect(r.entry.hint).toContain("version string");
  });
});
