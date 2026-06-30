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
  resolveStateDir,
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
  test("(a) explicit CCT_STATE_DIR wins, used verbatim", () => {
    // Even with an agent id set, the explicit override takes precedence.
    expect(
      resolveStateDir({
        CCT_STATE_DIR: "/srv/explicit-state",
        CCT_AGENT_ID: "agent-7",
      }),
    ).toBe("/srv/explicit-state");
  });

  test("(a') explicit long-form CLAUDE_CODE_TELEGRAMMER_STATE_DIR wins", () => {
    expect(
      resolveStateDir({
        CLAUDE_CODE_TELEGRAMMER_STATE_DIR: "/srv/long-state",
        CCT_AGENT_ID: "agent-7",
      }),
    ).toBe("/srv/long-state");
  });

  test("(b) CCT_AGENT_ID + no state dir → per-agent default dir", () => {
    expect(resolveStateDir({ CCT_AGENT_ID: "agent-7" })).toBe(
      join(homedir(), ".claude-code-telegrammer-agent-7"),
    );
  });

  test("(c) neither set → legacy ~/.claude-code-telegrammer", () => {
    expect(resolveStateDir({})).toBe(
      join(homedir(), ".claude-code-telegrammer"),
    );
  });

  test("(d) agent id with unsafe chars is sanitized", () => {
    // path separators / traversal chars collapse to "_"
    expect(resolveStateDir({ CCT_AGENT_ID: "a/b" })).toBe(
      join(homedir(), ".claude-code-telegrammer-a_b"),
    );
    // The path separator "/" is the security-critical char to neutralize;
    // "." is allowed (harmless in a dir-name leaf), so only the slashes
    // collapse to "_" — the result can no longer escape into another dir.
    expect(resolveStateDir({ CCT_AGENT_ID: "../../etc" })).toBe(
      join(homedir(), ".claude-code-telegrammer-.._.._etc"),
    );
    // a value made entirely of separators leaves no traversal:
    expect(resolveStateDir({ CCT_AGENT_ID: "a b\tc" })).toBe(
      join(homedir(), ".claude-code-telegrammer-a_b_c"),
    );
  });

  test("(e) internal 'telegram' default does NOT leak when AGENT_ID env unset", () => {
    // The module's AGENT_ID constant defaults to "telegram", but resolveStateDir
    // reads RAW getenv("AGENT_ID"); with no agent id env set it must fall back to
    // the legacy dir, NOT "-telegram" (which would collide across un-ID'd agents).
    const resolved = resolveStateDir({});
    expect(resolved).toBe(join(homedir(), ".claude-code-telegrammer"));
    // Guard against the "telegram" default leaking as a per-agent suffix:
    // the dir must be the plain legacy name, not "...-telegram".
    expect(resolved.endsWith("-telegram")).toBe(false);
    expect(resolved).toBe(join(homedir(), ".claude-code-telegrammer"));
  });

  test("empty-string agent id is treated as unset (falls back to legacy)", () => {
    expect(resolveStateDir({ CCT_AGENT_ID: "" })).toBe(
      join(homedir(), ".claude-code-telegrammer"),
    );
  });
});
