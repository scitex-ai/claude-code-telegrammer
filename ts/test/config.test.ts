/**
 * Tests for configuration module (config.ts).
 *
 * Because config.ts evaluates env vars at import time and preload.ts
 * sets them before any imports, we test the values that preload established.
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { tmpdir, hostname, homedir } from "os";
import { join } from "path";
import {
  resolveStateDir,
  STATE_DIR,
  ACCESS_FILE,
  LOCK_FILE,
  INBOX_DIR,
  ATTACHMENT_DIR,
  TOKEN,
  API_BASE,
  MAX_TEXT,
  ENV_ALLOWED,
  HOST_NAME,
  PROJECT,
  AGENT_ID,
  BOT_TOKEN_HASH,
  READ_RECEIPTS_ENABLED,
  RECEIPT_DELIVERED_EMOJI,
  RECEIPT_READ_EMOJI,
  findUnexpandedEnv,
  findRenamedEnv,
} from "../lib/config.js";

describe("config", () => {
  test("STATE_DIR reads from env var", () => {
    // preload.ts sets CLAUDE_CODE_TELEGRAMMER_AGENT_STATE_DIR to a tmp dir
    expect(STATE_DIR).toContain("cct-test-");
    expect(STATE_DIR.startsWith(tmpdir())).toBe(true);
  });

  test("ACCESS_FILE is under STATE_DIR", () => {
    expect(ACCESS_FILE).toBe(join(STATE_DIR, "access.json"));
  });

  test("LOCK_FILE is under STATE_DIR", () => {
    expect(LOCK_FILE).toBe(join(STATE_DIR, "claude-code-telegrammer-mcp.lock"));
  });

  test("INBOX_DIR is under STATE_DIR", () => {
    expect(INBOX_DIR).toBe(join(STATE_DIR, "inbox"));
  });

  test("ATTACHMENT_DIR defaults to STATE_DIR/attachments", () => {
    expect(ATTACHMENT_DIR).toBe(join(STATE_DIR, "attachments"));
  });

  test("TOKEN reads from env var", () => {
    // preload.ts sets CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN = "fake:token"
    expect(TOKEN).toBe("fake:token");
  });

  test("API_BASE includes token", () => {
    expect(API_BASE).toBe("https://api.telegram.org/botfake:token");
  });

  test("MAX_TEXT is 4096", () => {
    expect(MAX_TEXT).toBe(4096);
  });

  test("ENV_ALLOWED parses comma-separated users", () => {
    // preload.ts sets CLAUDE_CODE_TELEGRAMMER_ALLOWED_USERS = ""
    expect(ENV_ALLOWED).toEqual([]);
  });

  test("HOST_NAME defaults to os.hostname()", () => {
    // Not set in preload, so should fall back to hostname()
    expect(HOST_NAME).toBe(hostname());
  });

  test("PROJECT defaults to cwd", () => {
    // Not set in preload, so should fall back to process.cwd()
    expect(PROJECT).toBe(process.cwd());
  });

  test("AGENT_ID defaults to 'telegram'", () => {
    expect(AGENT_ID).toBe("telegram");
  });

  test("BOT_TOKEN_HASH is 8-char hex from token", () => {
    expect(BOT_TOKEN_HASH).toMatch(/^[0-9a-f]{8}$/);
  });

  test("READ_RECEIPTS_ENABLED defaults to true when env unset", () => {
    // preload.ts does not set CLAUDE_CODE_TELEGRAMMER_READ_RECEIPTS
    expect(READ_RECEIPTS_ENABLED).toBe(true);
  });

  test("receipt emojis are ⚡ and 👀", () => {
    expect(RECEIPT_DELIVERED_EMOJI).toBe("⚡");
    expect(RECEIPT_READ_EMOJI).toBe("👀");
  });
});

describe("resolveStateDir", () => {
  const base = join(homedir(), ".claude-code-telegrammer");

  test("explicit AGENT_STATE_DIR is honoured verbatim", () => {
    expect(resolveStateDir({ CCT_AGENT_STATE_DIR: "/tmp/explicit" })).toBe(
      "/tmp/explicit",
    );
  });

  test("explicit AGENT_STATE_DIR wins over AGENT_ID", () => {
    expect(
      resolveStateDir({
        CCT_AGENT_STATE_DIR: "/tmp/explicit",
        CCT_AGENT_ID: "neurovista",
      }),
    ).toBe("/tmp/explicit");
  });

  test("derives per-agent dir from AGENT_ID when AGENT_STATE_DIR unset", () => {
    expect(resolveStateDir({ CCT_AGENT_ID: "neurovista" })).toBe(
      `${base}-neurovista`,
    );
  });

  test("falls back to shared base when AGENT_ID unset", () => {
    expect(resolveStateDir({})).toBe(base);
  });

  test("treats the default AGENT_ID 'telegram' as the shared base", () => {
    expect(resolveStateDir({ CCT_AGENT_ID: "telegram" })).toBe(base);
  });

  test("sanitizes path separators out of an exotic AGENT_ID", () => {
    expect(resolveStateDir({ CCT_AGENT_ID: "../evil" })).toBe(
      `${base}-..-evil`,
    );
  });
});

describe("findUnexpandedEnv (neurovista unexpanded-${} regression)", () => {
  // Locks in the guard that caught the real neurovista outage: a materialized
  // .mcp.json carried `"CCT_STATE_DIR": "${CCT_STATE_DIR}"` for a var defined
  // nowhere, so Claude passed the LITERAL "${CCT_STATE_DIR}" through. The guard
  // must flag ANY telegrammer-prefixed var whose value still contains "${" and
  // name that exact var, so the startup abort is actionable (define it / drop
  // the placeholder). findUnexpandedEnv reads process.env live, so we mutate +
  // restore CCT_STATE_DIR around each case (preload.ts leaves a hermetic env).
  const KEY = "CCT_STATE_DIR";
  let saved: string | undefined;
  beforeEach(() => {
    saved = process.env[KEY];
  });
  afterEach(() => {
    if (saved === undefined) delete process.env[KEY];
    else process.env[KEY] = saved;
  });

  test("flags a var still holding a literal ${...}, as NAME=value naming the exact var", () => {
    process.env[KEY] = "${CCT_STATE_DIR}";
    const offenders = findUnexpandedEnv();
    const entry = offenders.find((line) => line.startsWith(`${KEY}=`));
    expect(entry).toBeDefined();
    // NAME=value form so the abort can name the exact var + its bad value.
    expect(entry).toContain("${");
  });

  test("does NOT flag a fully-expanded (clean) value", () => {
    process.env[KEY] = `${homedir()}/.claude-code-telegrammer-neurovista`;
    const offenders = findUnexpandedEnv();
    expect(offenders.some((line) => line.startsWith(`${KEY}=`))).toBe(false);
  });
});

describe("findRenamedEnv (CCT_STATE_DIR → CCT_AGENT_STATE_DIR rename guard)", () => {
  // The state-dir override was renamed to encode PER-AGENT scope. Either old
  // spelling still being set must fail loud, not be silently ignored. Injected
  // env keeps these pure (no process.env mutation).
  test("flags the old short spelling, pointing at the new name", () => {
    const out = findRenamedEnv({ CCT_STATE_DIR: "/tmp/x" });
    expect(out.length).toBe(1);
    expect(out[0]).toContain("CCT_STATE_DIR");
    expect(out[0]).toContain("CCT_AGENT_STATE_DIR");
  });

  test("flags the old canonical spelling, pointing at the new canonical name", () => {
    const out = findRenamedEnv({ CLAUDE_CODE_TELEGRAMMER_STATE_DIR: "/tmp/x" });
    expect(out.length).toBe(1);
    expect(out[0]).toContain("CLAUDE_CODE_TELEGRAMMER_AGENT_STATE_DIR");
  });

  test("flags the deprecated legacy spelling too", () => {
    const out = findRenamedEnv({
      CLAUDE_CODE_TELEGRAMMER_TELEGRAM_STATE_DIR: "/tmp/x",
    });
    expect(out.length).toBe(1);
    expect(out[0]).toContain("CLAUDE_CODE_TELEGRAMMER_TELEGRAM_STATE_DIR");
  });

  test("an EMPTY old var counts as ABSENT (no false trip on a folded secret)", () => {
    expect(findRenamedEnv({ CCT_STATE_DIR: "" })).toEqual([]);
  });

  test("the NEW name is not flagged", () => {
    expect(findRenamedEnv({ CCT_AGENT_STATE_DIR: "/tmp/x" })).toEqual([]);
  });

  test("clean env returns empty", () => {
    expect(findRenamedEnv({})).toEqual([]);
  });
});
