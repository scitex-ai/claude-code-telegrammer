/**
 * Tests for configuration module (config.ts).
 *
 * Because config.ts evaluates env vars at import time and preload.ts
 * sets them before any imports, we test the values that preload established.
 */

import { describe, test, expect } from "bun:test";
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
} from "../lib/config.js";

describe("config", () => {
  test("STATE_DIR reads from env var", () => {
    // preload.ts sets CLAUDE_CODE_TELEGRAMMER_STATE_DIR to a tmp dir
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

  test("explicit STATE_DIR is honoured verbatim", () => {
    expect(resolveStateDir({ CCT_STATE_DIR: "/tmp/explicit" })).toBe(
      "/tmp/explicit",
    );
  });

  test("explicit STATE_DIR wins over AGENT_ID", () => {
    expect(
      resolveStateDir({
        CCT_STATE_DIR: "/tmp/explicit",
        CCT_AGENT_ID: "neurovista",
      }),
    ).toBe("/tmp/explicit");
  });

  test("derives per-agent dir from AGENT_ID when STATE_DIR unset", () => {
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
    expect(resolveStateDir({ CCT_AGENT_ID: "../evil" })).toBe(`${base}-..-evil`);
  });
});
