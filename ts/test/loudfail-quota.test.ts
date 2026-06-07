/**
 * Loud-fail quota-capped tests (#14 refinements, 2026-06-07).
 *
 * Covers:
 *   - quota_capped fallback wire when usage.json is unreadable
 *   - per-format parsing of reset_at_5h / reset_at_7d (epoch seconds,
 *     epoch ms, ISO-8601 string)
 *   - SOONER-of-two reset selection when both present
 *   - graceful degradation on malformed JSON / missing file / missing fields
 *
 * Uses a real temp directory + real fs writes — no mocks of the fs
 * layer. The CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH env
 * override (declared in config.ts usageJsonPath()) points at the
 * fixture file so tests don't touch the host's actual usage.json.
 */

import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

import { buildLoudFailMessage } from "../lib/loudfail.js";
import type { WakeResult } from "../lib/wake.js";

// Helper: build a Date at the operator's local-time today HH:MM, return
// matching epoch seconds + zero-padded "HH:MM" string. usage.ts renders
// reset times in LOCAL time (operator's host timezone — natural frame).
function todayAt(
  hh: number,
  mm: number,
): {
  epochSec: number;
  hhmm: string;
} {
  const d = new Date();
  d.setHours(hh, mm, 0, 0);
  return {
    epochSec: Math.floor(d.getTime() / 1000),
    hhmm: `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`,
  };
}

function quotaResult(): Extract<WakeResult, { ok: false }> {
  return {
    ok: false,
    status: 429,
    reason: "HTTP 429",
    category: "quota_capped",
  };
}

describe("quota_capped: fallback wire when usage.json unreadable", () => {
  beforeEach(() => {
    delete process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH;
  });

  afterEach(() => {
    delete process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH;
  });

  test("no override + preload sets no account → 'quota cap — after the quota resets'", () => {
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: quota cap — after the quota resets",
    );
  });

  test("override points at nonexistent path → silent fallback", () => {
    process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH =
      "/nonexistent/path/usage.json";
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: quota cap — after the quota resets",
    );
  });
});

describe("quota_capped: usage.json parsing (real on-disk fixtures)", () => {
  let usageDir: string;
  let usagePath: string;

  beforeEach(() => {
    usageDir = mkdtempSync(join(tmpdir(), "cct-usage-"));
    usagePath = join(usageDir, "usage.json");
    process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH = usagePath;
  });

  afterEach(() => {
    rmSync(usageDir, { recursive: true, force: true });
    delete process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH;
  });

  function writeUsage(payload: unknown): void {
    writeFileSync(usagePath, JSON.stringify(payload));
  }

  test("reset_at_5h only (epoch seconds) → '5h quota cap — retry after HH:MM'", () => {
    const { epochSec, hhmm } = todayAt(14, 30);
    writeUsage({ reset_at_5h: epochSec });
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      `⚠️ proj-foo unavailable: 5h quota cap — retry after ${hhmm}`,
    );
  });

  test("reset_at_7d only (epoch seconds) → '7d quota cap — retry after HH:MM'", () => {
    const { epochSec, hhmm } = todayAt(9, 5);
    writeUsage({ reset_at_7d: epochSec });
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      `⚠️ proj-foo unavailable: 7d quota cap — retry after ${hhmm}`,
    );
  });

  test("both present, 5h sooner → 5h wins", () => {
    const { epochSec: r5, hhmm: hhmm5 } = todayAt(11, 0);
    const { epochSec: r7 } = todayAt(23, 59);
    writeUsage({ reset_at_5h: r5, reset_at_7d: r7 });
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      `⚠️ proj-foo unavailable: 5h quota cap — retry after ${hhmm5}`,
    );
  });

  test("both present, 7d sooner → 7d wins (5h already past, 7d still ahead)", () => {
    const { epochSec: r7, hhmm: hhmm7 } = todayAt(7, 15);
    const { epochSec: r5 } = todayAt(22, 0);
    writeUsage({ reset_at_5h: r5, reset_at_7d: r7 });
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      `⚠️ proj-foo unavailable: 7d quota cap — retry after ${hhmm7}`,
    );
  });

  test("reset_at_5h as ISO-8601 string → still parses", () => {
    const d = new Date();
    d.setHours(16, 45, 0, 0);
    writeUsage({ reset_at_5h: d.toISOString() });
    const hhmm = `${String(d.getHours()).padStart(2, "0")}:${String(
      d.getMinutes(),
    ).padStart(2, "0")}`;
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      `⚠️ proj-foo unavailable: 5h quota cap — retry after ${hhmm}`,
    );
  });

  test("epoch ms (value > 1e12) → auto-detected and parsed", () => {
    const d = new Date();
    d.setHours(20, 0, 0, 0);
    writeUsage({ reset_at_5h: d.getTime() });
    const hhmm = `${String(d.getHours()).padStart(2, "0")}:${String(
      d.getMinutes(),
    ).padStart(2, "0")}`;
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      `⚠️ proj-foo unavailable: 5h quota cap — retry after ${hhmm}`,
    );
  });

  test("malformed JSON → silent fallback", () => {
    writeFileSync(usagePath, "{ broken: json");
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: quota cap — after the quota resets",
    );
  });

  test("neither reset_at_5h nor reset_at_7d present → silent fallback", () => {
    writeUsage({ unrelated: "key" });
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: quota cap — after the quota resets",
    );
  });

  test("reset_at_5h is a negative epoch (corrupt) → silent fallback", () => {
    writeUsage({ reset_at_5h: -1 });
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: quota cap — after the quota resets",
    );
  });

  test("reset_at_5h is an unparseable string → silent fallback (no throw)", () => {
    writeUsage({ reset_at_5h: "not a date" });
    expect(buildLoudFailMessage(quotaResult(), "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: quota cap — after the quota resets",
    );
  });
});
