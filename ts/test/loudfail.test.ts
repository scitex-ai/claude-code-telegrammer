/**
 * Tests for loud-fail outbound reply (#14, 2026-06-07).
 *
 * The contract:
 *   - retrySuggestion()   returns a plain-English retry hint per WakeFailCategory.
 *   - buildLoudFailMessage() renders the "⚠️ <agent> unavailable: <reason> — retry <when>" wire format.
 *   - sendLoudFailReply() calls the injected sender with (chat_id, text, replyToMessageId).
 *   - dedup: each (chat_id, message_id) gets at most one loud-fail reply per process lifetime.
 *   - env kill-switch: CLAUDE_CODE_TELEGRAMMER_TELEGRAM_LOUD_FAIL=0 suppresses the send.
 *   - best-effort: a sender that throws does NOT throw out of sendLoudFailReply.
 *
 * Real Telegram update-JSON fixtures drive the integration test (a single
 * inbound message.json from a Telegram update is the input; we assert
 * the loud-fail sender is called with the correct (chat_id, text,
 * replyToMessageId) derived from it).
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
  buildLoudFailMessage,
  retrySuggestion,
  sendLoudFailReply,
  setLoudFailSender,
} from "../lib/loudfail.js";
import type { WakeResult } from "../lib/wake.js";

// ── Capture the sender so we can assert on the wire payload ────────────────

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
  delete process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_LOUD_FAIL;
});

afterEach(() => {
  delete process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_LOUD_FAIL;
});

// ── retrySuggestion ────────────────────────────────────────────────────────

describe("retrySuggestion: actionable hint per category", () => {
  test("auth", () =>
    expect(retrySuggestion("auth")).toBe("after fixing the bot token"));
  test("client_error", () =>
    expect(retrySuggestion("client_error")).toBe(
      "after fixing the request shape",
    ));
  test("server_error", () =>
    expect(retrySuggestion("server_error")).toBe("in a few minutes"));
  test("connection_refused", () =>
    expect(retrySuggestion("connection_refused")).toBe(
      "after the agent restarts",
    ));
  test("timeout", () => expect(retrySuggestion("timeout")).toBe("shortly"));
  test("unknown", () => expect(retrySuggestion("unknown")).toBe("shortly"));
});

// ── buildLoudFailMessage ───────────────────────────────────────────────────

describe("buildLoudFailMessage: wire-format pinned", () => {
  test("server_error 502", () => {
    const result: WakeResult = {
      ok: false,
      status: 502,
      reason: "HTTP 502",
      category: "server_error",
    };
    expect(buildLoudFailMessage(result, "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: HTTP 502 — retry in a few minutes",
    );
  });

  test("auth 401", () => {
    const result: WakeResult = {
      ok: false,
      status: 401,
      reason: "HTTP 401",
      category: "auth",
    };
    expect(buildLoudFailMessage(result, "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: HTTP 401 — retry after fixing the bot token",
    );
  });

  test("connection_refused: reason text is preserved verbatim", () => {
    const result: WakeResult = {
      ok: false,
      reason: "connect ECONNREFUSED 127.0.0.1:9876",
      category: "connection_refused",
    };
    expect(buildLoudFailMessage(result, "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: connect ECONNREFUSED 127.0.0.1:9876 — retry after the agent restarts",
    );
  });

  test("timeout", () => {
    const result: WakeResult = {
      ok: false,
      reason: "network timeout",
      category: "timeout",
    };
    expect(buildLoudFailMessage(result, "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: network timeout — retry shortly",
    );
  });

  test("uses the AGENT_ID default when no agentId is passed", () => {
    // preload.ts does not set CLAUDE_CODE_TELEGRAMMER_TELEGRAM_AGENT_ID,
    // so AGENT_ID falls back to "telegram" (config.ts default).
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 503",
      category: "server_error",
    };
    expect(buildLoudFailMessage(result)).toBe(
      "⚠️ telegram unavailable: HTTP 503 — retry in a few minutes",
    );
  });
});

// ── sendLoudFailReply: wiring ──────────────────────────────────────────────

describe("sendLoudFailReply: posts to the injected sender", () => {
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
      text: "⚠️ proj-foo unavailable: HTTP 502 — retry in a few minutes",
      replyToMessageId: 5,
    });
  });

  test("dedup: a second call for the same (chat, msg) is a no-op", async () => {
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

  test("dedup is keyed per (chat, msg) — different chats / msgs are independent", async () => {
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

  test("env kill-switch CLAUDE_CODE_TELEGRAMMER_TELEGRAM_LOUD_FAIL=0 suppresses the send", async () => {
    process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_LOUD_FAIL = "0";
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 502",
      category: "server_error",
    };
    await sendLoudFailReply("100", 5, result, "proj-foo");
    expect(sent.length).toBe(0);
  });

  test("env kill-switch is case-insensitive (false/no/off/FALSE/NO/OFF all suppress)", async () => {
    const variants = ["false", "no", "off", "FALSE", "NO", "OFF", "0"];
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 502",
      category: "server_error",
    };
    for (let i = 0; i < variants.length; i++) {
      _resetLoudFail();
      sent.length = 0;
      process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_LOUD_FAIL = variants[i];
      await sendLoudFailReply(`${i}`, 5, result, "proj-foo");
      expect(sent.length).toBe(0);
    }
  });

  test("env kill-switch off (unset or any truthy value) → send fires", async () => {
    const truthy = ["", "1", "on", "yes", "true", "anything-else"];
    const result: WakeResult = {
      ok: false,
      reason: "HTTP 502",
      category: "server_error",
    };
    for (let i = 0; i < truthy.length; i++) {
      _resetLoudFail();
      sent.length = 0;
      process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_LOUD_FAIL = truthy[i];
      await sendLoudFailReply(`${i}`, 5, result, "proj-foo");
      expect(sent.length).toBe(1);
    }
  });

  test("sender throw is swallowed (best-effort — must never crash the relay)", async () => {
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

// ── Real-fixture integration: chat_id / message_id derived from update ─────

describe("integration with a real Telegram update-JSON fixture", () => {
  // A real Telegram update.message envelope as observed in production (PII
  // anonymised). The poller extracts chat_id + message_id from msg.chat.id +
  // msg.message_id; we assert the loud-fail reply lands on the right thread.
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

  test("dead-agent wake (502) → loud-fail reply uses real chat_id + message_id", async () => {
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
    expect(sent[0].text).toMatch(/^⚠️ proj-foo unavailable: HTTP 502/);
  });

  test("ECONNREFUSED wake → loud-fail reply explains agent process is down", async () => {
    const chatId = String(update.message.chat.id);
    const messageId = Number(update.message.message_id);
    const result: WakeResult = {
      ok: false,
      reason: "connect ECONNREFUSED 127.0.0.1:9876",
      category: "connection_refused",
    };
    await sendLoudFailReply(chatId, messageId, result, "proj-foo");
    expect(sent[0].text).toBe(
      "⚠️ proj-foo unavailable: connect ECONNREFUSED 127.0.0.1:9876 — retry after the agent restarts",
    );
  });
});
