/**
 * parseSendArgs — the MCP-independent outbound send path.
 *
 * Card cct-cli-send-outbound-path-independent-of-mcp. `grant` had a
 * time-critical finding for the operator, the cct MCP server was down, and it
 * could not deliver. This mode is the path that would have worked.
 *
 * The parse FAILURES are the important cases: an agent reaching for this is
 * already in a degraded state, so a malformed invocation must fail loudly
 * rather than quietly send the wrong thing (or the wrong text) and let the
 * agent believe the operator was reached.
 */

import { describe, test, expect } from "bun:test";
import {
  parseSendArgs,
  emptyTokenError,
  executeDurableSend,
  TelegramAcceptedPersistenceError,
  type DurableSendDeps,
} from "../lib/send-cli.js";

describe("parseSendArgs", () => {
  test("parses the minimal invocation", () => {
    const r = parseSendArgs(["--chat-id", "8379369979", "--text", "hello"]);
    expect(r).toEqual({
      ok: true,
      args: { chatId: "8379369979", text: "hello" },
    });
  });

  test("parses an optional --reply-to", () => {
    const r = parseSendArgs([
      "--chat-id",
      "1",
      "--text",
      "hi",
      "--reply-to",
      "4242",
    ]);
    expect(r).toEqual({
      ok: true,
      args: { chatId: "1", text: "hi", replyTo: 4242 },
    });
  });

  test("rejects a missing --chat-id", () => {
    const r = parseSendArgs(["--text", "hello"]);
    expect(r.ok).toBe(false);
  });

  test("rejects a missing --text", () => {
    const r = parseSendArgs(["--chat-id", "1"]);
    expect(r.ok).toBe(false);
  });

  // `--text --chat-id 5` must NOT quietly send the literal string "--chat-id".
  // A message the agent never wrote reaching the operator is worse than an
  // error it can see and retry.
  test("rejects a flag whose value is the next flag, not a value", () => {
    const r = parseSendArgs(["--text", "--chat-id", "5"]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain("--text");
  });

  test("rejects a trailing flag with no value at all", () => {
    const r = parseSendArgs(["--chat-id", "1", "--text"]);
    expect(r.ok).toBe(false);
  });

  // A garbled --reply-to must not silently degrade into an unthreaded send:
  // the caller asked for a thread, so failing to thread is a failure.
  test("rejects a non-numeric --reply-to instead of dropping it", () => {
    const r = parseSendArgs([
      "--chat-id",
      "1",
      "--text",
      "hi",
      "--reply-to",
      "not-a-number",
    ]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain("--reply-to");
  });

  test("rejects a non-positive --reply-to", () => {
    const r = parseSendArgs([
      "--chat-id",
      "1",
      "--text",
      "hi",
      "--reply-to",
      "0",
    ]);
    expect(r.ok).toBe(false);
  });

  test("accepts text that itself looks like prose with dashes", () => {
    const r = parseSendArgs(["--chat-id", "1", "--text", "done - all green"]);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.args.text).toBe("done - all green");
  });
});

/**
 * #81 regression: the `send` branch runs BEFORE the TELEGRAM_ENABLED token
 * guard, so an EMPTY token used to build https://api.telegram.org/bot/sendMessage
 * and Telegram 404'd it as "Not Found" — an absent token disguised as a missing
 * request, which sent `grant` chasing a token rotation that never happened.
 * emptyTokenError is the pre-send guard that names the real cause instead.
 */
describe("emptyTokenError", () => {
  test("returns null for a present token (send proceeds)", () => {
    expect(emptyTokenError("123456:AA-real-looking-token")).toBeNull();
    // A single non-empty char is enough to be 'present' — validity is Telegram's
    // job, not this guard's; this guard only distinguishes absent from present.
    expect(emptyTokenError("x")).toBeNull();
  });

  test("returns a loud, actionable message for an empty token", () => {
    const msg = emptyTokenError("");
    expect(msg).not.toBeNull();
    // Names the real cause, not a Telegram error.
    expect(msg).toContain("CCT_BOT_TOKEN is EMPTY");
    // Explicitly disowns the misleading Telegram framing.
    expect(msg).toContain("NOT a Telegram problem");
    // Gives the safe, leak-free confirmation command (literal, for the user's
    // shell — not the token value).
    expect(msg).toContain('echo "len=${#CCT_BOT_TOKEN}"');
    // Points at the actual upstream owner (sac's pool fold / a blocked direnv).
    expect(msg).toContain("SAC_SECRETS_ENVRC");
    // Never leaks a token value (there is none, but assert the contract).
    expect(msg).not.toContain("123456:AA");
  });
});

function fakeDeps(events: string[]): DurableSendDeps {
  return {
    async initStore() {
      events.push("store:init");
    },
    async resolveInboundReplyTarget(chatId, messageId) {
      events.push(`store:resolve:${chatId}:${messageId}`);
      return {
        rowId: 71,
        chatId,
        messageId,
        readAt: null,
        repliedAt: null,
      };
    },
    async sendMessage(chatId, text, replyTo) {
      events.push(`telegram:${chatId}:${text}:${replyTo ?? "none"}`);
      return 9001;
    },
    async saveExplicitReply(target, _text, messageId) {
      events.push(`store:reply:${target.rowId}:${messageId}`);
      return 72;
    },
    async saveOutbound(_chatId, _text, messageId) {
      events.push(`store:outbound:${messageId}`);
      return 73;
    },
  };
}

const context = {
  host: "test-host",
  project: "/test",
  agent_id: "test-agent",
  bot_token_hash: "hash",
};

describe("executeDurableSend", () => {
  test("resolves the inbound before Telegram and commits linked semantics after", async () => {
    const events: string[] = [];
    const result = await executeDurableSend(
      { chatId: "42", text: "answer", replyTo: 123 },
      context,
      fakeDeps(events),
    );
    expect({ events, result }).toEqual({
      events: [
        "store:init",
        "store:resolve:42:123",
        "telegram:42:answer:123",
        "store:reply:71:9001",
      ],
      result: {
        messageId: 9001,
        rowId: 72,
        replyToRowId: 71,
        semanticState: "read_and_replied",
      },
    });
  });

  test("missing correlation fails before Telegram is called", async () => {
    const events: string[] = [];
    const deps = fakeDeps(events);
    deps.resolveInboundReplyTarget = async () => {
      events.push("store:resolve:missing");
      throw new Error("no inbound row matches");
    };
    await expect(
      executeDurableSend(
        { chatId: "42", text: "answer", replyTo: 123 },
        context,
        deps,
      ),
    ).rejects.toThrow("no inbound row matches");
    expect(events).toEqual(["store:init", "store:resolve:missing"]);
  });

  test("Telegram failure leaves persistence untouched", async () => {
    const events: string[] = [];
    const deps = fakeDeps(events);
    deps.sendMessage = async () => {
      events.push("telegram:failed");
      throw new Error("network down");
    };
    await expect(
      executeDurableSend(
        { chatId: "42", text: "answer", replyTo: 123 },
        context,
        deps,
      ),
    ).rejects.toThrow("network down");
    expect(events).toEqual([
      "store:init",
      "store:resolve:42:123",
      "telegram:failed",
    ]);
  });

  test("post-delivery persistence failure reports accepted message id", async () => {
    const events: string[] = [];
    const deps = fakeDeps(events);
    deps.saveExplicitReply = async () => {
      throw new Error("database unavailable");
    };
    const promise = executeDurableSend(
      { chatId: "42", text: "answer", replyTo: 123 },
      context,
      deps,
    );
    await expect(promise).rejects.toBeInstanceOf(
      TelegramAcceptedPersistenceError,
    );
    await expect(promise).rejects.toThrow("Telegram accepted message 9001");
  });

  test("unthreaded sends also persist an outbound receipt", async () => {
    const events: string[] = [];
    const result = await executeDurableSend(
      { chatId: "42", text: "update" },
      context,
      fakeDeps(events),
    );
    expect({ events, result }).toEqual({
      events: [
        "store:init",
        "telegram:42:update:none",
        "store:outbound:9001",
      ],
      result: {
        messageId: 9001,
        rowId: 73,
        semanticState: "outbound_recorded",
      },
    });
  });
});
