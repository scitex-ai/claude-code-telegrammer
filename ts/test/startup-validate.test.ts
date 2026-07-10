/**
 * Tests for the pure startup-validation surface (lib/startup-validate.ts).
 *
 * These functions gate NORMAL startup: validateBotToken() classifies a getMe
 * response into ok / definitive-bad-token / transient, and describeAccessGating()
 * derives the effective DM-gating posture. Both are pure (injectable inputs, no
 * network/fs/process.exit) so we cover every branch without mocking the DB —
 * the raw getMe is a plain stubbed function here.
 *
 * The incident-class regression (an invalid token that silently 404s the whole
 * poller) is asserted explicitly: the invalid_token message must carry BOTH
 * Telegram's own description AND the exact env var CCT_BOT_TOKEN so the operator
 * gets a loud, actionable cause instead of a wall of "✘ failed".
 */

import { describe, test, expect } from "bun:test";
import {
  validateBotToken,
  describeAccessGating,
  buildDisabledWarning,
  type RawTgResponse,
} from "../lib/startup-validate.js";

describe("validateBotToken", () => {
  test("ok:true → { ok:true, username, id }", async () => {
    const check = await validateBotToken(async () => ({
      ok: true,
      result: { id: 4242, username: "my_bot" },
    }));
    expect(check.ok).toBe(true);
    if (check.ok) {
      expect(check.username).toBe("my_bot");
      expect(check.id).toBe(4242);
    }
  });

  test("error_code 401 → invalid_token (definitive, FATAL)", async () => {
    const check = await validateBotToken(async () => ({
      ok: false,
      error_code: 401,
      description: "Unauthorized",
    }));
    expect(check.ok).toBe(false);
    if (!check.ok) {
      expect(check.kind).toBe("invalid_token");
    }
  });

  test("error_code 404 → invalid_token (definitive, FATAL)", async () => {
    const check = await validateBotToken(async () => ({
      ok: false,
      error_code: 404,
      description: "Not Found",
    }));
    expect(check.ok).toBe(false);
    if (!check.ok) {
      expect(check.kind).toBe("invalid_token");
    }
  });

  test("rawGetMe throws (network/DNS) → transient (non-fatal)", async () => {
    const check = await validateBotToken(async () => {
      throw new Error("getaddrinfo ENOTFOUND api.telegram.org");
    });
    expect(check.ok).toBe(false);
    if (!check.ok) {
      expect(check.kind).toBe("transient");
      expect(check.message).toContain("ENOTFOUND");
    }
  });

  test("error_code 429 → transient (flood-wait, non-fatal)", async () => {
    const check = await validateBotToken(async () => ({
      ok: false,
      error_code: 429,
      description: "Too Many Requests: retry after 5",
    }));
    expect(check.ok).toBe(false);
    if (!check.ok) {
      expect(check.kind).toBe("transient");
    }
  });

  test("5xx-style error_code → transient (Telegram outage, non-fatal)", async () => {
    const check = await validateBotToken(async () => ({
      ok: false,
      error_code: 502,
      description: "Bad Gateway",
    }));
    expect(check.ok).toBe(false);
    if (!check.ok) {
      expect(check.kind).toBe("transient");
    }
  });

  test("incident-class regression: invalid_token message contains BOTH the Telegram description AND CCT_BOT_TOKEN", async () => {
    const description = "Unauthorized: bot token revoked";
    const raw: RawTgResponse = { ok: false, error_code: 401, description };
    const check = await validateBotToken(async () => raw);
    expect(check.ok).toBe(false);
    if (!check.ok) {
      expect(check.kind).toBe("invalid_token");
      // The actionable cause must be self-contained in the message the caller
      // prints — both Telegram's reason and the var to fix.
      expect(check.message).toContain(description);
      expect(check.message).toContain("CCT_BOT_TOKEN");
    }
  });
});

describe("describeAccessGating", () => {
  test("no access.json + envAllowedCount 0 + allowlist → warn, names CCT_ALLOWED_USERS + fail-closed/rejected", () => {
    const res = describeAccessGating({
      accessFileExists: false,
      envAllowedCount: 0,
      dmPolicy: "allowlist",
    });
    expect(res.level).toBe("warn");
    expect(res.message).toContain("CCT_ALLOWED_USERS");
    expect(res.message).toContain("FAIL-CLOSED");
    expect(res.message).toContain("REJECTED");
  });

  test("with env allow entries → non-warn (info)", () => {
    const res = describeAccessGating({
      accessFileExists: false,
      envAllowedCount: 2,
      dmPolicy: "allowlist",
    });
    expect(res.level).toBe("info");
  });

  test("with access.json present → non-warn (info) even when env list empty", () => {
    const res = describeAccessGating({
      accessFileExists: true,
      envAllowedCount: 0,
      dmPolicy: "allowlist",
    });
    expect(res.level).toBe("info");
  });

  test("non-allowlist policy → non-warn (info)", () => {
    const res = describeAccessGating({
      accessFileExists: false,
      envAllowedCount: 0,
      dmPolicy: "disabled",
    });
    expect(res.level).toBe("info");
  });
});

describe("buildDisabledWarning (tokenless = warn + disable, not fail)", () => {
  // Empty CCT_BOT_TOKEN is an intentional "no bot yet" state for the universal
  // channel, not a misconfig — it must produce a LOUD, actionable, VISIBLE warn
  // (no silent fallback), naming the agent + the exact var + secrets file + fix.
  test("is a loud [WARN] that names the agent, the var, and the fix", () => {
    const msg = buildDisabledWarning("neurovista");
    expect(msg).toContain("[WARN]");
    expect(msg).toContain("neurovista");
    expect(msg).toContain("CCT_BOT_TOKEN");
    expect(msg).toContain("CCT_BOT_TOKEN_<NAME>");
    expect(msg).toContain("restart");
  });
});
