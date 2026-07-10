/**
 * Tests for the env-var alias resolver (lib/env.ts).
 *
 * getenv() accepts an injected `env` object (3rd arg), so these tests pass
 * fake environments directly — no process.env mutation / monkeypatching.
 */

import { describe, test, expect } from "bun:test";
import {
  getenv,
  aliases,
  TelegrammerEnvConflict,
  SHORT_PREFIX,
  LONG_PREFIX,
  LEGACY_PREFIX,
} from "../lib/env.js";

describe("getenv alias resolution", () => {
  test("reads the canonical CLAUDE_CODE_TELEGRAMMER_<KEY> form", () => {
    const env = { CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "canon" };
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("canon");
  });

  test("reads the short CCT_<KEY> alias", () => {
    const env = { CCT_BOT_TOKEN: "short" };
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("short");
  });

  test("reads the legacy CLAUDE_CODE_TELEGRAMMER_TELEGRAM_<KEY> form", () => {
    const env = { CLAUDE_CODE_TELEGRAMMER_TELEGRAM_BOT_TOKEN: "legacy" };
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("legacy");
  });

  test("returns the fallback when no form is set", () => {
    expect(getenv("BOT_TOKEN", "fallback", {})).toBe("fallback");
  });

  test("returns undefined when unset and no fallback given", () => {
    expect(getenv("BOT_TOKEN", undefined, {})).toBeUndefined();
  });

  test("accepts multiple forms that AGREE (no conflict)", () => {
    const env = {
      CCT_BOT_TOKEN: "same",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "same",
      CLAUDE_CODE_TELEGRAMMER_TELEGRAM_BOT_TOKEN: "same",
    };
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("same");
  });

  test("throws TelegrammerEnvConflict when the two CURRENT forms DIFFER", () => {
    const env = {
      CCT_BOT_TOKEN: "short",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "canon",
    };
    expect(() => getenv("BOT_TOKEN", undefined, env)).toThrow(
      TelegrammerEnvConflict,
    );
  });

  test("a current form overrides legacy without throwing", () => {
    const env = {
      CCT_BOT_TOKEN: "current",
      CLAUDE_CODE_TELEGRAMMER_TELEGRAM_BOT_TOKEN: "old",
    };
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("current");
  });

  test("conflict message names both offending vars", () => {
    const env = {
      CCT_BOT_TOKEN: "a",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "b",
    };
    expect(() => getenv("BOT_TOKEN", undefined, env)).toThrow(
      /CCT_BOT_TOKEN.*CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN/s,
    );
  });
});

describe("empty-string env vars are treated as ABSENT", () => {
  // Root cause of the dead-poller fleet outage: a folded but unresolved
  // per-agent secret exports CCT_BOT_TOKEN="" while the real value lives in the
  // legacy/canonical spelling. An empty short form must never shadow it.
  test("empty short + real legacy → returns the legacy value", () => {
    const env = {
      CCT_BOT_TOKEN: "",
      CLAUDE_CODE_TELEGRAMMER_TELEGRAM_BOT_TOKEN: "legacy",
    };
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("legacy");
  });

  test("empty short + real long → returns long, does NOT throw a conflict", () => {
    const env = {
      CCT_BOT_TOKEN: "",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "canon",
    };
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("canon");
  });

  test("empty short + empty long + real legacy → returns the legacy value", () => {
    const env = {
      CCT_BOT_TOKEN: "",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "",
      CLAUDE_CODE_TELEGRAMMER_TELEGRAM_BOT_TOKEN: "legacy",
    };
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("legacy");
  });

  test("all empty → returns the fallback", () => {
    const env = {
      CCT_BOT_TOKEN: "",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "",
      CLAUDE_CODE_TELEGRAMMER_TELEGRAM_BOT_TOKEN: "",
    };
    expect(getenv("BOT_TOKEN", "fallback", env)).toBe("fallback");
  });

  test("a real conflict (non-empty short ≠ non-empty long) STILL throws", () => {
    const env = {
      CCT_BOT_TOKEN: "short",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "canon",
    };
    expect(() => getenv("BOT_TOKEN", undefined, env)).toThrow(
      TelegrammerEnvConflict,
    );
  });

  test("equal non-empty short and long → returns it (no conflict)", () => {
    const env = {
      CCT_BOT_TOKEN: "same",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "same",
    };
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("same");
  });

  test("empty short + non-empty long → returns long, no throw", () => {
    const env = {
      CCT_BOT_TOKEN: "",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "canon",
    };
    expect(() => getenv("BOT_TOKEN", undefined, env)).not.toThrow();
    expect(getenv("BOT_TOKEN", undefined, env)).toBe("canon");
  });

  test("does NOT warn for an EMPTY legacy var", () => {
    const warnings: string[] = [];
    const env = { CLAUDE_CODE_TELEGRAMMER_TELEGRAM_DEP_EMPTY: "" };
    getenv("DEP_EMPTY", undefined, env, (m) => warnings.push(m));
    expect(warnings).toHaveLength(0);
  });
});

describe("prefixes and aliases()", () => {
  test("prefix constants have the expected values", () => {
    expect(SHORT_PREFIX).toBe("CCT_");
    expect(LONG_PREFIX).toBe("CLAUDE_CODE_TELEGRAMMER_");
    expect(LEGACY_PREFIX).toBe("CLAUDE_CODE_TELEGRAMMER_TELEGRAM_");
  });

  test("aliases() returns the [short, canonical] pair", () => {
    expect(aliases("BOT_TOKEN")).toEqual([
      "CCT_BOT_TOKEN",
      "CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN",
    ]);
  });
});

describe("legacy deprecation warning", () => {
  test("warns when a legacy CLAUDE_CODE_TELEGRAMMER_TELEGRAM_ var is read", () => {
    const warnings: string[] = [];
    const env = { CLAUDE_CODE_TELEGRAMMER_TELEGRAM_DEP_A: "v" };
    getenv("DEP_A", undefined, env, (m) => warnings.push(m));
    expect(warnings).toHaveLength(1);
  });

  test("the warning names the legacy var being deprecated", () => {
    const warnings: string[] = [];
    const env = { CLAUDE_CODE_TELEGRAMMER_TELEGRAM_DEP_B: "v" };
    getenv("DEP_B", undefined, env, (m) => warnings.push(m));
    expect(warnings[0]).toContain("CLAUDE_CODE_TELEGRAMMER_TELEGRAM_DEP_B");
  });

  test("does NOT warn when only the CCT_ short alias is set", () => {
    const warnings: string[] = [];
    const env = { CCT_DEP_C: "v" };
    getenv("DEP_C", undefined, env, (m) => warnings.push(m));
    expect(warnings).toHaveLength(0);
  });
});
