/**
 * Tests for lib/usage.ts (#14 copy refinement, 2026-06-07).
 *
 * Pins the parseResetAt / readQuotaReset / formatResetTime helpers
 * directly. The wire-format-end-to-end tests live in
 * loudfail-quota.test.ts; this file covers the unit-level contract so
 * a regression in the parser is caught at its source.
 */

import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

import { formatResetTime, parseResetAt, readQuotaReset } from "../lib/usage.js";

describe("parseResetAt: accepts the documented formats", () => {
  test("epoch seconds (number ≤ 1e12)", () => {
    // 1717000000 is somewhere in 2024 — well-formed epoch seconds.
    const d = parseResetAt(1717000000);
    expect(d).not.toBeNull();
    expect(d!.getFullYear()).toBeGreaterThan(2020);
  });

  test("epoch ms (number > 1e12)", () => {
    // 1717000000000 ms = same wall-clock as 1717000000 sec.
    const a = parseResetAt(1717000000000);
    const b = parseResetAt(1717000000);
    expect(a).not.toBeNull();
    expect(b).not.toBeNull();
    expect(a!.getTime()).toBe(b!.getTime());
  });

  test("ISO-8601 string", () => {
    const d = parseResetAt("2026-06-07T14:30:00Z");
    expect(d).not.toBeNull();
    expect(d!.toISOString()).toBe("2026-06-07T14:30:00.000Z");
  });

  test("ISO-8601 without seconds → parses", () => {
    const d = parseResetAt("2026-06-07T14:30");
    expect(d).not.toBeNull();
  });

  // Garbage-input cases are written as separate tests rather than
  // test.each — bun-test's done-callback inference can mis-fire on a
  // 2-arity callback (timing out the test after 5s waiting for `done`).
  test("returns null on null", () => expect(parseResetAt(null)).toBeNull());
  test("returns null on undefined", () =>
    expect(parseResetAt(undefined)).toBeNull());
  test("returns null on 0", () => expect(parseResetAt(0)).toBeNull());
  test("returns null on negative epoch", () =>
    expect(parseResetAt(-1)).toBeNull());
  test("returns null on NaN", () => expect(parseResetAt(NaN)).toBeNull());
  test("returns null on unparseable string", () =>
    expect(parseResetAt("not a date")).toBeNull());
  test("returns null on empty string", () =>
    expect(parseResetAt("")).toBeNull());
  test("returns null on object", () => expect(parseResetAt({})).toBeNull());
  test("returns null on array", () => expect(parseResetAt([])).toBeNull());
  test("returns null on boolean", () => expect(parseResetAt(true)).toBeNull());
});

describe("formatResetTime: 'HH:MM' zero-padded local time", () => {
  test("14:30 → '14:30'", () => {
    const d = new Date();
    d.setHours(14, 30, 0, 0);
    expect(formatResetTime(d)).toBe("14:30");
  });

  test("09:05 → '09:05' (zero-pad both fields)", () => {
    const d = new Date();
    d.setHours(9, 5, 0, 0);
    expect(formatResetTime(d)).toBe("09:05");
  });

  test("00:00 → '00:00' (midnight edge)", () => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    expect(formatResetTime(d)).toBe("00:00");
  });

  test("23:59 → '23:59' (end-of-day edge)", () => {
    const d = new Date();
    d.setHours(23, 59, 0, 0);
    expect(formatResetTime(d)).toBe("23:59");
  });
});

describe("readQuotaReset: integration via fixture file", () => {
  let usageDir: string;
  let usagePath: string;

  beforeEach(() => {
    usageDir = mkdtempSync(join(tmpdir(), "cct-usage-unit-"));
    usagePath = join(usageDir, "usage.json");
    process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH = usagePath;
  });

  afterEach(() => {
    rmSync(usageDir, { recursive: true, force: true });
    delete process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH;
  });

  test("returns null when path is empty (no env + no account)", () => {
    delete process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH;
    // preload sets no account → usageJsonPath() returns "" → null.
    expect(readQuotaReset()).toBeNull();
  });

  test("returns null when file missing", () => {
    process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH =
      "/nope/usage.json";
    expect(readQuotaReset()).toBeNull();
  });

  test("returns null on malformed JSON", () => {
    writeFileSync(usagePath, "{not valid");
    expect(readQuotaReset()).toBeNull();
  });

  test("returns null when both fields absent", () => {
    writeFileSync(usagePath, JSON.stringify({ other: "key" }));
    expect(readQuotaReset()).toBeNull();
  });

  test("returns 5h variant when only reset_at_5h present", () => {
    const epoch = Math.floor(Date.now() / 1000) + 3600;
    writeFileSync(usagePath, JSON.stringify({ reset_at_5h: epoch }));
    const result = readQuotaReset();
    expect(result).not.toBeNull();
    expect(result!.variant).toBe("5h");
  });

  test("returns 7d variant when only reset_at_7d present", () => {
    const epoch = Math.floor(Date.now() / 1000) + 86400 * 3;
    writeFileSync(usagePath, JSON.stringify({ reset_at_7d: epoch }));
    const result = readQuotaReset();
    expect(result).not.toBeNull();
    expect(result!.variant).toBe("7d");
  });

  test("returns SOONER variant when both present", () => {
    const sooner = Math.floor(Date.now() / 1000) + 60;
    const later = Math.floor(Date.now() / 1000) + 86400;
    writeFileSync(
      usagePath,
      JSON.stringify({ reset_at_5h: later, reset_at_7d: sooner }),
    );
    const result = readQuotaReset();
    expect(result).not.toBeNull();
    expect(result!.variant).toBe("7d");
  });
});
