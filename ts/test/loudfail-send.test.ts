/**
 * Loud-fail SEND-PATH tests (#14, 2026-06-07).
 *
 * Pins:
 *   - sendLoudFailReply calls the injected sender with (chatId, body,
 *     replyToMessageId)
 *   - dedup is keyed strictly per (chat_id, message_id) per process
 *     lifetime — different chats / msgs are independent
 *   - the CLAUDE_CODE_TELEGRAMMER_LOUD_FAIL env kill-switch
 *     suppresses the send on the documented vocab (0/false/no/off,
 *     case-insensitive)
 *   - any other env value (including "", "1", "on", "yes", "true",
 *     arbitrary strings) keeps the send ON
 *   - the sender throwing does NOT crash the relay (best-effort)
 *
 * Plus an integration test that drives the path with a real Telegram
 * update.message envelope (no mocks of the JSON shape).
 */

import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  test,
} from "bun:test";

import {
  _resetLoudFail,
  sendLoudFailReply,
  setLoudFailSender,
} from "../lib/loudfail.js";
import type { WakeResult } from "../lib/wake.js";

type Sent = { chatId: string; text: string; replyToMessageId: number };
const sent: Sent[] = [];
let throwOnSend = false;

beforeAll(() => {
  setLoudFailSender(async (chatId, text, replyToMessageId) => {
    sent.push({ chatId, text, replyToMessageId });
    if (throwOnSend) throw new Error("simulated telegram failure");
    return { ok: true, message_id: 999 };
  });
});

beforeEach(() => {
  sent.length = 0;
  throwOnSend = false;
  _resetLoudFail();
  delete process.env.CLAUDE_CODE_TELEGRAMMER_LOUD_FAIL;
});

afterEach(() => {
  delete process.env.CLAUDE_CODE_TELEGRAMMER_LOUD_FAIL;
});

describe("sendLoudFailReply: wiring", () => {
  test("calls sender with (chat_id, body, replyToMessageId)", async () => {
    const result: WakeResult = {
      ok: false,
      status: 502,
      reason: "HTTP 502",
      category: "server_error",
    };
    await sendLoudFailReply("100", 5, result, "proj-foo");
    expect(sent.length).toBe(1);
    expect(sent[0]).toEqual({
      chatId: "100",
      text: "⚠️ proj-foo unavailable: agent busy — retry shortly",
      replyToMessageId: 5,
    });
  });

  test("dedup: second call for same (chat, msg) is no-op", async () => {
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 502",
      category: "server_error",
    };
    await sendLoudFailReply("100", 5, result, "proj-foo");
    await sendLoudFailReply("100", 5, result, "proj-foo");
    await sendLoudFailReply("100", 5, result, "proj-foo");
    expect(sent.length).toBe(1);
  });

  test("dedup keyed per (chat, msg) — different chats / msgs independent", async () => {
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 502",
      category: "server_error",
    };
    await sendLoudFailReply("100", 5, result, "proj-foo");
    await sendLoudFailReply("100", 6, result, "proj-foo");
    await sendLoudFailReply("200", 5, result, "proj-foo");
    expect(sent.length).toBe(3);
  });
});

describe("sendLoudFailReply: env kill-switch", () => {
  test("LOUD_FAIL=0 suppresses the send", async () => {
    process.env.CLAUDE_CODE_TELEGRAMMER_LOUD_FAIL = "0";
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 502",
      category: "server_error",
    };
    await sendLoudFailReply("100", 5, result, "proj-foo");
    expect(sent.length).toBe(0);
  });

  test("case-insensitive vocab: false/no/off/FALSE/NO/OFF/0 → suppressed", async () => {
    const variants = ["false", "no", "off", "FALSE", "NO", "OFF", "0"];
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 502",
      category: "server_error",
    };
    for (let i = 0; i < variants.length; i++) {
      _resetLoudFail();
      sent.length = 0;
      process.env.CLAUDE_CODE_TELEGRAMMER_LOUD_FAIL = variants[i];
      await sendLoudFailReply(`${i}`, 5, result, "proj-foo");
      expect(sent.length).toBe(0);
    }
  });

  test("unset OR any other value → send fires", async () => {
    const truthy = ["", "1", "on", "yes", "true", "anything-else"];
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 502",
      category: "server_error",
    };
    for (let i = 0; i < truthy.length; i++) {
      _resetLoudFail();
      sent.length = 0;
      process.env.CLAUDE_CODE_TELEGRAMMER_LOUD_FAIL = truthy[i];
      await sendLoudFailReply(`${i}`, 5, result, "proj-foo");
      expect(sent.length).toBe(1);
    }
  });
});

describe("sendLoudFailReply: best-effort", () => {
  test("sender throw is swallowed (must never crash the relay)", async () => {
    throwOnSend = true;
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 502",
      category: "server_error",
    };
    await expect(
      sendLoudFailReply("100", 5, result, "proj-foo"),
    ).resolves.toBeUndefined();
    expect(sent.length).toBe(1); // attempted exactly once
  });
});

describe("integration with a real Telegram update.message fixture", () => {
  // Real Telegram update.message shape (PII anonymised). The poller
  // extracts chat_id from msg.chat.id and message_id from
  // msg.message_id; we assert the loud-fail reply lands on the right
  // thread with the right body for each category.
  const update = {
    update_id: 700000001,
    message: {
      message_id: 42,
      from: {
        id: 8675309,
        is_bot: false,
        first_name: "operator",
        username: "alice",
      },
      chat: { id: 8675309, first_name: "operator", type: "private" },
      date: 1717000000,
      text: "any update?",
    },
  };

  test("server_error (502) → 'agent busy — retry shortly' on right thread", async () => {
    const chatId = String(update.message.chat.id);
    const messageId = Number(update.message.message_id);
    const result: WakeResult = {
      ok: false,
      status: 502,
      reason: "HTTP 502",
      category: "server_error",
    };
    await sendLoudFailReply(chatId, messageId, result, "proj-foo");
    expect(sent.length).toBe(1);
    expect(sent[0].chatId).toBe("8675309");
    expect(sent[0].replyToMessageId).toBe(42);
    expect(sent[0].text).toBe(
      "⚠️ proj-foo unavailable: agent busy — retry shortly",
    );
  });

  test("connection_refused → 'connection refused — retry in ~30s'", async () => {
    const chatId = String(update.message.chat.id);
    const messageId = Number(update.message.message_id);
    const result: WakeResult = {
      ok: false,
      reason: "connect ECONNREFUSED 127.0.0.1:9876",
      category: "connection_refused",
    };
    await sendLoudFailReply(chatId, messageId, result, "proj-foo");
    expect(sent[0].text).toBe(
      "⚠️ proj-foo unavailable: connection refused — retry in ~30s",
    );
  });

  test("auth (401) → 'auth refresh needed — escalating to lead'", async () => {
    const chatId = String(update.message.chat.id);
    const messageId = Number(update.message.message_id);
    const result: WakeResult = {
      ok: false,
      status: 401,
      reason: "HTTP 401",
      category: "auth",
    };
    await sendLoudFailReply(chatId, messageId, result, "proj-foo");
    expect(sent[0].text).toBe(
      "⚠️ proj-foo unavailable: auth refresh needed — escalating to lead",
    );
  });
});
