/**
 * Tests for the outbound agent-signature module (signature.ts) and its
 * integration in the outbound send path (sendMessage chunking + sendDocument
 * caption + editMessageText).
 *
 * Coverage areas:
 *   - PR #18 baseline format `— <agent> (<cwd>@<host>)` still emitted when
 *     no quota entry is resolvable (operator's stated fallback).
 *   - Idempotency of signing across all formats (PR #18 contract).
 *   - Chunked-send contract: signature appears on the LAST chunk exactly once.
 *   - NEW (#16): the env-flag kill-switch makes appendSignature a no-op.
 *   - NEW (#16): the enriched form `— <agent> (<short> 5h:<int> percent
 *     7d:<int> percent | <cwd>@<host>)` is emitted when accountDirname()
 *     resolves to an account present in quota-cache.json.
 */

import {
  describe,
  test,
  expect,
  beforeEach,
  afterEach,
} from "bun:test";
import { writeFileSync, mkdtempSync, rmSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";
import {
  buildSignature,
  isSigned,
  appendSignature,
  readQuotaEntry,
} from "../lib/signature.js";
import { AGENT_ID, PROJECT, HOST_NAME } from "../lib/config.js";

// Envs the new code reads at call time. We snapshot + restore so test order
// is independent and the default dev environment (where the operator's
// /home/ywatanabe/.scitex/quota-cache.json may genuinely exist) doesn't
// leak into the fallback-shape assertions below.
const SIG_ENV = "CLAUDE_CODE_TELEGRAMMER_TELEGRAM_SIGNATURE";
const QUOTA_PATH_ENV = "CLAUDE_CODE_TELEGRAMMER_TELEGRAM_QUOTA_CACHE_PATH";
const ACCOUNT_ENV = "CLAUDE_CODE_TELEGRAMMER_TELEGRAM_ACCOUNT";
const ACCOUNT_FALLBACK_ENV = "CLAUDE_AGENT_ACCOUNT";

let snapshot: Record<string, string | undefined>;
let tmpDir: string;

function clearEnv(): void {
  delete process.env[SIG_ENV];
  delete process.env[QUOTA_PATH_ENV];
  delete process.env[ACCOUNT_ENV];
  delete process.env[ACCOUNT_FALLBACK_ENV];
}

function restoreEnv(): void {
  for (const k of [SIG_ENV, QUOTA_PATH_ENV, ACCOUNT_ENV, ACCOUNT_FALLBACK_ENV]) {
    if (snapshot[k] === undefined) delete process.env[k];
    else process.env[k] = snapshot[k] as string;
  }
}

beforeEach(() => {
  snapshot = {
    [SIG_ENV]: process.env[SIG_ENV],
    [QUOTA_PATH_ENV]: process.env[QUOTA_PATH_ENV],
    [ACCOUNT_ENV]: process.env[ACCOUNT_ENV],
    [ACCOUNT_FALLBACK_ENV]: process.env[ACCOUNT_FALLBACK_ENV],
  };
  clearEnv();
  tmpDir = mkdtempSync(join(tmpdir(), "sig-test-"));
  // By default point at a path that does NOT exist so readQuotaEntry()
  // falls back to null — every "fallback shape" test gets a clean slate
  // regardless of whether the operator's real cache file is on disk.
  process.env[QUOTA_PATH_ENV] = join(tmpDir, "no-such-quota-cache.json");
});

afterEach(() => {
  rmSync(tmpDir, { recursive: true, force: true });
  restoreEnv();
});

// ---------------------------------------------------------------------------
// PR #18 baseline (fallback shape — preserved)
// ---------------------------------------------------------------------------

describe("signature.buildSignature — fallback (no quota entry)", () => {
  test("matches PR #18 em-dash + label + cwd@host format", () => {
    const sig = buildSignature();
    expect(sig).toBe(`— ${AGENT_ID} (${PROJECT}@${HOST_NAME})`);
  });

  test("starts with the em-dash marker (visual separator from body)", () => {
    expect(buildSignature().startsWith("— ")).toBe(true);
  });

  test("contains the full workdir path (not the basename)", () => {
    // Operator was explicit: full path, not basename. PROJECT in config.ts
    // defaults to process.cwd() which is the bridge's full cwd.
    expect(buildSignature()).toContain(PROJECT);
    expect(PROJECT.startsWith("/")).toBe(true);
  });
});

describe("signature.isSigned", () => {
  test("true for text ending in the exact current signature", () => {
    expect(isSigned(`hello\n\n${buildSignature()}`)).toBe(true);
  });

  test("true with trailing whitespace / newlines (trimEnd-tolerant)", () => {
    expect(isSigned(`hello\n\n${buildSignature()}\n\n`)).toBe(true);
    expect(isSigned(`hello\n\n${buildSignature()}   `)).toBe(true);
  });

  test("false for plain unsigned text", () => {
    expect(isSigned("just a normal message")).toBe(false);
  });

  test("false for a different-shape manual signature (strict match)", () => {
    expect(isSigned("hi\n\n-- somebody else (elsewhere)")).toBe(false);
  });
});

describe("signature.appendSignature — fallback (no quota entry)", () => {
  test("appends signature on a fresh body with a blank-line separator", () => {
    const out = appendSignature("hello world");
    expect(out).toBe(`hello world\n\n${buildSignature()}`);
  });

  test("is idempotent — already-signed text passes through unchanged", () => {
    const once = appendSignature("hello");
    const twice = appendSignature(once);
    expect(twice).toBe(once);
  });

  test("idempotency tolerates trailing whitespace after the signature", () => {
    const once = appendSignature("hello") + "\n\n";
    const twice = appendSignature(once);
    expect(twice).toBe(once);
  });

  test("empty input → bare signature, no leading newlines", () => {
    expect(appendSignature("")).toBe(buildSignature());
  });

  test("preserves the body verbatim above the signature", () => {
    const body = "line1\nline2\n  indented\n```code```";
    const out = appendSignature(body);
    expect(out.startsWith(body)).toBe(true);
    expect(out.endsWith(buildSignature())).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Chunked-send contract
// ---------------------------------------------------------------------------

describe("signature integration — chunked sendMessage", () => {
  // The integration contract: sendMessage in telegram-api.ts calls
  // appendSignature BEFORE splitText. This mirrors that ordering and
  // asserts the visible outcome: LAST chunk carries the signature, exactly
  // once across the chunks.
  test("when sign+split produces multiple chunks, only the LAST chunk carries the signature", async () => {
    const { splitText } = await import("../lib/telegram-api.js");
    const body = "x".repeat(5000);
    const signed = appendSignature(body);
    const chunks = splitText(signed);
    expect(chunks.length).toBeGreaterThanOrEqual(2);
    const signatureCount = chunks.filter((c) =>
      c.includes(buildSignature()),
    ).length;
    expect(signatureCount).toBe(1);
    expect(chunks[chunks.length - 1].endsWith(buildSignature())).toBe(true);
  });

  test("a short body produces a single chunk that ends with the signature", async () => {
    const { splitText } = await import("../lib/telegram-api.js");
    const signed = appendSignature("hi");
    const chunks = splitText(signed);
    expect(chunks.length).toBe(1);
    expect(chunks[0].endsWith(buildSignature())).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// #16 PART 1 — kill-switch toggle
// ---------------------------------------------------------------------------

describe("signature.appendSignature — kill-switch (env CLAUDE_CODE_TELEGRAMMER_TELEGRAM_SIGNATURE)", () => {
  test.each([
    ["0"],
    ["false"],
    ["no"],
    ["off"],
    ["FALSE"],
    ["Off"],
    ["  off  "],
  ])("disabled by env value %p → appendSignature is a no-op", (value) => {
    process.env[SIG_ENV] = value;
    const body = "hello";
    expect(appendSignature(body)).toBe(body);
    // Empty-input contract: still verbatim (i.e. empty string, NOT bare sig).
    expect(appendSignature("")).toBe("");
    // Already-enriched body: NOT re-signed, NOT stripped — just passthrough.
    const enriched = `hi\n\n— foo (bar)`;
    expect(appendSignature(enriched)).toBe(enriched);
  });

  test.each([["1"], ["true"], ["yes"], ["on"], [""], ["anything-else"]])(
    "env value %p keeps the signature ON",
    (value) => {
      process.env[SIG_ENV] = value;
      expect(appendSignature("hello")).toBe(`hello\n\n${buildSignature()}`);
    },
  );

  test("env unset = signature ON (default)", () => {
    delete process.env[SIG_ENV];
    expect(appendSignature("hello")).toBe(`hello\n\n${buildSignature()}`);
  });
});

// ---------------------------------------------------------------------------
// #16 PART 2 — enriched signature with account + quota
// ---------------------------------------------------------------------------

/**
 * Drop a fixture quota-cache.json at the path the new code reads.
 * Mirrors the lead's confirmed schema:
 *   { "written_at": <epoch>, "accounts": { "<email>": { short, h5, d7, ttl_h } } }
 */
function writeFixtureCache(
  payload: object,
  filename = "quota-cache.json",
): string {
  const p = join(tmpDir, filename);
  writeFileSync(p, JSON.stringify(payload), "utf-8");
  return p;
}

const SAMPLE_CACHE = {
  written_at: 1780352404.82,
  accounts: {
    "wyusuuke@gmail.com": {
      short: "wyusuuke",
      h5: 17.0,
      d7: 3.0,
      ttl_h: 7.74,
    },
    "ywata1989@gmail.com": {
      short: "ywata1989",
      h5: 11.0,
      d7: 2.0,
      ttl_h: 6.52,
    },
    "ywatanabe@scitex.ai": {
      short: "ywatanabe",
      h5: 19.0,
      d7: 3.0,
      ttl_h: 7.74,
    },
  },
};

describe("signature.readQuotaEntry — quota-cache.json lookup", () => {
  test("returns the matching entry by short field (lookup by dash-segment)", () => {
    process.env[QUOTA_PATH_ENV] = writeFixtureCache(SAMPLE_CACHE);
    process.env[ACCOUNT_ENV] = "ywata1989-gmail-com";
    const entry = readQuotaEntry();
    expect(entry).not.toBeNull();
    expect(entry!.short).toBe("ywata1989");
    expect(entry!.h5).toBe(11);
    expect(entry!.d7).toBe(2);
    expect(entry!.ttl_h).toBeCloseTo(6.52, 2);
  });

  test("returns null when CLAUDE_AGENT_ACCOUNT is the resolution source", () => {
    process.env[QUOTA_PATH_ENV] = writeFixtureCache(SAMPLE_CACHE);
    delete process.env[ACCOUNT_ENV];
    process.env[ACCOUNT_FALLBACK_ENV] = "wyusuuke-gmail-com";
    const entry = readQuotaEntry();
    expect(entry).not.toBeNull();
    expect(entry!.short).toBe("wyusuuke");
  });

  test("CLAUDE_CODE_TELEGRAMMER_TELEGRAM_ACCOUNT wins over CLAUDE_AGENT_ACCOUNT", () => {
    process.env[QUOTA_PATH_ENV] = writeFixtureCache(SAMPLE_CACHE);
    process.env[ACCOUNT_ENV] = "ywatanabe-scitex-ai";
    process.env[ACCOUNT_FALLBACK_ENV] = "wyusuuke-gmail-com";
    expect(readQuotaEntry()!.short).toBe("ywatanabe");
  });

  test("returns null when neither account env is set", () => {
    process.env[QUOTA_PATH_ENV] = writeFixtureCache(SAMPLE_CACHE);
    expect(readQuotaEntry()).toBeNull();
  });

  test("returns null when file is missing (path points nowhere)", () => {
    process.env[ACCOUNT_ENV] = "wyusuuke-gmail-com";
    process.env[QUOTA_PATH_ENV] = join(tmpDir, "does-not-exist.json");
    expect(readQuotaEntry()).toBeNull();
  });

  test("returns null on malformed JSON", () => {
    process.env[ACCOUNT_ENV] = "wyusuuke-gmail-com";
    const p = join(tmpDir, "bad.json");
    writeFileSync(p, "this is not json {", "utf-8");
    process.env[QUOTA_PATH_ENV] = p;
    expect(readQuotaEntry()).toBeNull();
  });

  test("returns null when the resolved short does not appear in the cache", () => {
    process.env[QUOTA_PATH_ENV] = writeFixtureCache(SAMPLE_CACHE);
    process.env[ACCOUNT_ENV] = "no-such-acct-here";
    expect(readQuotaEntry()).toBeNull();
  });

  test("returns null when the matched entry has wrong-typed fields", () => {
    process.env[QUOTA_PATH_ENV] = writeFixtureCache({
      accounts: {
        "x@y.z": { short: "wyusuuke", h5: "lots", d7: 3, ttl_h: 1 },
      },
    });
    process.env[ACCOUNT_ENV] = "wyusuuke-gmail-com";
    expect(readQuotaEntry()).toBeNull();
  });
});

describe("signature.buildSignature — enriched (account+quota present)", () => {
  beforeEach(() => {
    process.env[QUOTA_PATH_ENV] = writeFixtureCache(SAMPLE_CACHE);
  });

  test("emits the operator-confirmed enriched format with integer percents", () => {
    process.env[ACCOUNT_ENV] = "wyusuuke-gmail-com";
    // SAMPLE_CACHE has wyusuuke at h5=17, d7=3 — both already integers.
    expect(buildSignature()).toBe(
      `— ${AGENT_ID} (wyusuuke 5h:17 percent 7d:3 percent | ${PROJECT}@${HOST_NAME})`,
    );
  });

  test("rounds non-integer percentages to nearest int", () => {
    process.env[QUOTA_PATH_ENV] = writeFixtureCache({
      accounts: {
        "x@y.z": { short: "wyusuuke", h5: 8.6, d7: 2.4, ttl_h: 7.1 },
      },
    });
    process.env[ACCOUNT_ENV] = "wyusuuke-gmail-com";
    // 8.6 → 9, 2.4 → 2
    expect(buildSignature()).toContain("5h:9 percent");
    expect(buildSignature()).toContain("7d:2 percent");
  });

  test("falls back to cwd@host form when account+quota cannot be resolved", () => {
    // Cache present, but account unset → fallback.
    expect(buildSignature()).toBe(`— ${AGENT_ID} (${PROJECT}@${HOST_NAME})`);
  });

  test("appendSignature wires the enriched buildSignature output", () => {
    process.env[ACCOUNT_ENV] = "ywatanabe-scitex-ai";
    const out = appendSignature("body");
    // 19 percent, 3 percent for ywatanabe entry.
    expect(out).toContain("ywatanabe 5h:19 percent 7d:3 percent");
    expect(out.startsWith("body\n\n— ")).toBe(true);
  });

  test("isSigned recognises the enriched form (idempotency holds)", () => {
    process.env[ACCOUNT_ENV] = "ywata1989-gmail-com";
    const once = appendSignature("hi");
    expect(isSigned(once)).toBe(true);
    expect(appendSignature(once)).toBe(once);
  });
});
