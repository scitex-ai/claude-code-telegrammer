/**
 * broadcastSystemAlert — direct-Telegram system-level alarm broadcast
 * (architecture fix, incident-cct-inbound-dies-silently-with-mcp-server-
 * 20260711 follow-up, 2026-07).
 *
 * Unlike sendLoudFailReply (which replies to ONE specific inbound message),
 * broadcastSystemAlert has no anchoring (chat_id, message_id) — it fans out
 * to every recipient in the CURRENT allowlist. These tests pin:
 *   - fan-out to every passed recipient
 *   - the default recipients resolve from loadAccess().allowFrom when not
 *     passed explicitly
 *   - one recipient's send failure does not block delivery to the others
 *     (best-effort, per-recipient)
 *   - never throws/rejects even when every send fails
 *   - the LOUD_FAIL env kill-switch suppresses the broadcast entirely
 *   - an empty recipient list is a logged no-op, not a throw
 */

import { afterEach, beforeEach, describe, expect, test } from "bun:test";

import {
  broadcastSystemAlert,
  setSystemAlertSender,
  _resetSystemAlertSender,
} from "../lib/loudfail.js";

type Sent = { chatId: string; text: string };
const sent: Sent[] = [];
let throwFor: Set<string> = new Set();

beforeEach(() => {
  sent.length = 0;
  throwFor = new Set();
  setSystemAlertSender(async (chatId, text) => {
    if (throwFor.has(chatId))
      throw new Error(`simulated failure for ${chatId}`);
    sent.push({ chatId, text });
    return { ok: true };
  });
  delete process.env.CLAUDE_CODE_TELEGRAMMER_LOUD_FAIL;
});

afterEach(() => {
  _resetSystemAlertSender();
  delete process.env.CLAUDE_CODE_TELEGRAMMER_LOUD_FAIL;
});

describe("broadcastSystemAlert: fan-out", () => {
  test("sends the same text to every explicit recipient", async () => {
    await broadcastSystemAlert("FATAL: something broke", ["100", "200", "300"]);
    expect(sent.length).toBe(3);
    expect(new Set(sent.map((s) => s.chatId))).toEqual(
      new Set(["100", "200", "300"]),
    );
    for (const s of sent) {
      expect(s.text).toBe("FATAL: something broke");
    }
  });

  test("empty recipient list is a no-op (never throws)", async () => {
    await expect(
      broadcastSystemAlert("nobody will see this", []),
    ).resolves.toBeUndefined();
    expect(sent.length).toBe(0);
  });
});

describe("broadcastSystemAlert: best-effort per recipient", () => {
  test("one recipient's send failure does not block the others", async () => {
    throwFor = new Set(["200"]);
    await broadcastSystemAlert("INGESTION STALL", ["100", "200", "300"]);
    expect(sent.map((s) => s.chatId).sort()).toEqual(["100", "300"]);
  });

  test("every recipient failing never throws/rejects", async () => {
    throwFor = new Set(["100", "200"]);
    await expect(
      broadcastSystemAlert("all fail", ["100", "200"]),
    ).resolves.toBeUndefined();
    expect(sent.length).toBe(0);
  });
});

describe("broadcastSystemAlert: env kill-switch", () => {
  test("LOUD_FAIL=0 suppresses the broadcast entirely", async () => {
    process.env.CLAUDE_CODE_TELEGRAMMER_LOUD_FAIL = "0";
    await broadcastSystemAlert("should not send", ["100", "200"]);
    expect(sent.length).toBe(0);
  });

  test("unset (default) sends normally", async () => {
    await broadcastSystemAlert("should send", ["100"]);
    expect(sent.length).toBe(1);
  });
});

describe("broadcastSystemAlert: default recipients from the allowlist", () => {
  test("with no explicit recipients, resolves from loadAccess().allowFrom", async () => {
    const { _resetCache } = await import("../lib/access.js");
    const { ACCESS_FILE, STATE_DIR } = await import("../lib/config.js");
    const { writeFileSync, mkdirSync, rmSync } = await import("fs");

    mkdirSync(STATE_DIR, { recursive: true });
    writeFileSync(ACCESS_FILE, JSON.stringify({ allowFrom: ["555666777"] }));
    _resetCache();
    try {
      await broadcastSystemAlert("default-recipients test");
      expect(sent.length).toBe(1);
      expect(sent[0].chatId).toBe("555666777");
    } finally {
      rmSync(ACCESS_FILE, { force: true });
      _resetCache();
    }
  });
});
