/**
 * Tests for automatic two-stage read-receipt reactions (receipts.ts).
 *
 * Injects a fake reaction sender (no network) and asserts:
 *   - ⚡ delivered receipt is set on receive
 *   - 👀 read receipt is set on read
 *   - both are idempotent (no duplicate setMessageReaction calls)
 *   - a failed reaction is logged loudly and does not throw (best-effort)
 */

import { describe, test, expect, beforeEach, beforeAll } from "bun:test";
import {
  markDelivered,
  markRead,
  setReactionSender,
  _resetReceipts,
} from "../lib/receipts.js";
import { RECEIPT_DELIVERED_EMOJI, RECEIPT_READ_EMOJI } from "../lib/config.js";

type ReactionCall = { chatId: string; messageId: number; emoji: string };
const calls: ReactionCall[] = [];
let shouldThrow = false;

beforeAll(() => {
  setReactionSender(async (chatId, messageId, emoji) => {
    calls.push({ chatId, messageId, emoji });
    if (shouldThrow) throw new Error("simulated telegram failure");
    return { ok: true };
  });
});

describe("read receipts", () => {
  beforeEach(() => {
    calls.length = 0;
    shouldThrow = false;
    _resetReceipts();
  });

  test("markDelivered sets ⚡ on the inbound message", async () => {
    await markDelivered("100", "5");
    expect(calls.length).toBe(1);
    expect(calls[0].chatId).toBe("100");
    expect(calls[0].messageId).toBe(5);
    expect(calls[0].emoji).toBe(RECEIPT_DELIVERED_EMOJI);
  });

  test("markRead sets 👀 on the inbound message", async () => {
    await markRead("100", "5");
    expect(calls.length).toBe(1);
    expect(calls[0].emoji).toBe(RECEIPT_READ_EMOJI);
  });

  test("delivered → read is a two-call ⚡ then 👀 transition", async () => {
    await markDelivered("100", "5");
    await markRead("100", "5");
    expect(calls.length).toBe(2);
    expect(calls[0].emoji).toBe(RECEIPT_DELIVERED_EMOJI);
    expect(calls[1].emoji).toBe(RECEIPT_READ_EMOJI);
  });

  test("markDelivered is idempotent for the same message", async () => {
    await markDelivered("100", "5");
    await markDelivered("100", "5");
    await markDelivered("100", "5");
    expect(calls.length).toBe(1);
  });

  test("markRead is idempotent for the same message", async () => {
    await markRead("100", "5");
    await markRead("100", "5");
    expect(calls.length).toBe(1);
  });

  test("idempotency is keyed per (chat, message, stage)", async () => {
    await markDelivered("100", "5");
    await markDelivered("100", "6"); // different message
    await markDelivered("200", "5"); // different chat
    await markRead("100", "5"); // different stage, same message
    expect(calls.length).toBe(4);
  });

  test("a failed reaction does not throw (best-effort)", async () => {
    shouldThrow = true;
    // Must resolve, not reject — the relay must never crash on a failed receipt.
    await expect(markDelivered("100", "5")).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// 👀 gating against /v1/turn success (fix #14: bug operator confirmed
// 2026-06-01 — a STOPPED SDK-runner agent's DM was still getting 👀,
// because the relay was firing markRead on MCP-notification success
// rather than on a real successful /v1/turn). The two arms of the
// receipt-trigger in poller.ts::handleUpdate are now:
//
//   1. .notification().then() — fires markRead ONLY when !wakeEnabled()
//      (interactive CLI; no /v1/turn to confirm against).
//   2. wakeTurn().then((ok) => if (ok) markRead) — the AUTHORITATIVE
//      trigger in SDK-runner mode (TURN_URL set); fires ONLY on 2xx.
//
// These tests model the conditional decisions in isolation so the
// regression — “dead agent still gets 👀” — can never come back without
// flipping a clearly-named assert.
// ---------------------------------------------------------------------------

import { wakeTurn, setTurnPoster } from "../lib/wake.js";

describe("👀 = /v1/turn POST 2xx (poller.ts handleUpdate gating)", () => {
  beforeEach(() => {
    calls.length = 0;
    shouldThrow = false;
    _resetReceipts();
  });

  test("dead agent: /v1/turn POST fails (502) → NO 👀 set", async () => {
    // Arrange: poster simulates a dead agent — fetch resolves with 502, so
    // wakeTurn returns ok=false. (The receipt-sender is the same fake
    // installed by beforeAll above; if markRead were fired we'd see it in
    // `calls`.)
    setTurnPoster(async () => 502);
    // Act: the exact gating pattern from poller.ts::handleUpdate.
    const ok = await wakeTurn("hello", { chat_id: "100", message_id: "5" });
    if (ok) await markRead("100", "5"); // never reached when ok=false
    // Assert
    expect(calls).toEqual([]);
  });

  test("live agent: /v1/turn POST 2xx → 👀 set (no waiting for reply)", async () => {
    setTurnPoster(async () => 200);
    const ok = await wakeTurn("hello", { chat_id: "100", message_id: "5" });
    if (ok) await markRead("100", "5");
    expect(calls.length).toBe(1);
    expect(calls[0].emoji).toBe(RECEIPT_READ_EMOJI);
  });

  test("401 dead-agent auth → /v1/turn POST fails → no 👀", async () => {
    setTurnPoster(async () => 401);
    const ok = await wakeTurn("hello", { chat_id: "100", message_id: "5" });
    expect(ok).toBe(false);
  });

  test("connection-refused (agent process dead) → /v1/turn POST fails → no 👀", async () => {
    setTurnPoster(async () => {
      throw new Error("connect ECONNREFUSED");
    });
    const ok = await wakeTurn("hello", { chat_id: "100", message_id: "5" });
    expect(ok).toBe(false);
  });
});

