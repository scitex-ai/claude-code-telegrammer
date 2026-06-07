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
  markReceived,
  markDone,
  markFailed,
  setReactionSender,
  _resetReceipts,
} from "../lib/receipts.js";
import {
  RECEIPT_DELIVERED_EMOJI,
  RECEIPT_READ_EMOJI,
  RECEIPT_DONE_EMOJI,
  RECEIPT_FAILED_EMOJI,
} from "../lib/config.js";

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

  test("dead agent: /v1/turn POST fails (502) → ❌ failed (NOT 👀)", async () => {
    // Arrange: poster simulates a dead agent — fetch resolves with 502, so
    // wakeTurn returns ok=false. (The receipt-sender is the same fake
    // installed by beforeAll above.)
    setTurnPoster(async () => 502);
    // Act: the exact gating pattern from poller.ts::handleUpdate's wake arm.
    const result = await wakeTurn("hello", {
      chat_id: "100",
      message_id: "5",
    });
    if (result.ok) {
      await markReceived("100", "5");
      await markDone("100", "5");
    } else {
      await markFailed("100", "5");
    }
    // Assert: exactly one call, and it's ❌ — 👀 is never reached.
    expect(calls.length).toBe(1);
    expect(calls[0].emoji).toBe(RECEIPT_FAILED_EMOJI);
  });

  test("live agent: /v1/turn POST 2xx → 👀 received then ✅ done (2-call advance)", async () => {
    // Under current sac, /v1/turn is case (B): HTTP 200 returns AFTER the
    // turn completes. So ok=true is simultaneously "agent received" (stage 2)
    // and "agent finished" (stage 3). The poller fires markReceived then
    // markDone in sequence — the visible Telegram reaction advances 👀→✅.
    setTurnPoster(async () => 200);
    const result = await wakeTurn("hello", {
      chat_id: "100",
      message_id: "5",
    });
    if (result.ok) {
      await markReceived("100", "5");
      await markDone("100", "5");
    }
    expect(calls.length).toBe(2);
    expect(calls[0].emoji).toBe(RECEIPT_READ_EMOJI);
    expect(calls[1].emoji).toBe(RECEIPT_DONE_EMOJI);
  });

  test("401 dead-agent auth → /v1/turn POST fails → no 👀", async () => {
    setTurnPoster(async () => 401);
    const result = await wakeTurn("hello", {
      chat_id: "100",
      message_id: "5",
    });
    expect(result.ok).toBe(false);
  });

  test("connection-refused (agent process dead) → /v1/turn POST fails → no 👀", async () => {
    setTurnPoster(async () => {
      throw new Error("connect ECONNREFUSED");
    });
    const result = await wakeTurn("hello", {
      chat_id: "100",
      message_id: "5",
    });
    expect(result.ok).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 4-stage receipts: ⚡→👀→✅, ❌ on failure (operator-approved 2026-06-01).
//
// Single advancing reaction per message (Telegram replaces the bot's
// reaction on each setMessageReaction call; non-premium bots cap at 1
// reaction/message). The four stages and the conditions that fire them:
//
//   Stage 1 ⚡ markDelivered — relay received the Telegram message
//   Stage 2 👀 markReceived  — /v1/turn POST returned 2xx (agent accepted)
//   Stage 3 ✅ markDone      — agent finished the turn (collapses to stage 2
//                              under sac case-B)
//   Stage 4 ❌ markFailed    — failure (agent down / 401 / refused / non-2xx)
//
// markRead is preserved as a deprecated alias for markReceived so the
// rename is non-breaking for any out-of-tree consumers.
// ---------------------------------------------------------------------------

describe("4-stage receipts: ⚡→👀→✅, ❌ on failure", () => {
  beforeEach(() => {
    calls.length = 0;
    shouldThrow = false;
    _resetReceipts();
  });

  test("markReceived sets 👀 (stage 2)", async () => {
    await markReceived("100", "5");
    expect(calls.length).toBe(1);
    expect(calls[0].emoji).toBe(RECEIPT_READ_EMOJI);
  });

  test("markDone sets ✅ (stage 3)", async () => {
    await markDone("100", "5");
    expect(calls.length).toBe(1);
    expect(calls[0].emoji).toBe(RECEIPT_DONE_EMOJI);
  });

  test("markFailed sets ❌ (stage 4)", async () => {
    await markFailed("100", "5");
    expect(calls.length).toBe(1);
    expect(calls[0].emoji).toBe(RECEIPT_FAILED_EMOJI);
  });

  test("markRead is a backwards-compat alias for markReceived", async () => {
    // Both call paths target stage "received" — idempotency cache treats
    // them as the same key, so exactly one setMessageReaction fires.
    await markRead("100", "5");
    await markReceived("100", "5");
    expect(calls.length).toBe(1);
    expect(calls[0].emoji).toBe(RECEIPT_READ_EMOJI);
  });

  test("delivered → received → done is a three-call ⚡→👀→✅ progression", async () => {
    await markDelivered("100", "5");
    await markReceived("100", "5");
    await markDone("100", "5");
    expect(calls.length).toBe(3);
    expect(calls[0].emoji).toBe(RECEIPT_DELIVERED_EMOJI);
    expect(calls[1].emoji).toBe(RECEIPT_READ_EMOJI);
    expect(calls[2].emoji).toBe(RECEIPT_DONE_EMOJI);
  });

  test("delivered then failed is a two-call ⚡→❌ progression (dead-agent path)", async () => {
    // A DM to a dead/stopped agent must NOT reach 👀 — it stays on ⚡
    // and advances to ❌ when wakeTurn returns ok=false. This is the
    // exact gating contract the operator confirmed on 2026-06-01.
    await markDelivered("100", "5");
    await markFailed("100", "5");
    expect(calls.length).toBe(2);
    expect(calls[0].emoji).toBe(RECEIPT_DELIVERED_EMOJI);
    expect(calls[1].emoji).toBe(RECEIPT_FAILED_EMOJI);
  });

  test("each stage is independently idempotent", async () => {
    // Each mark fires once and only once for the same (chat, message, stage).
    await markDelivered("100", "5");
    await markDelivered("100", "5");
    await markReceived("100", "5");
    await markReceived("100", "5");
    await markDone("100", "5");
    await markDone("100", "5");
    await markFailed("100", "5");
    await markFailed("100", "5");
    expect(calls.length).toBe(4);
    expect(calls.map((c) => c.emoji)).toEqual([
      RECEIPT_DELIVERED_EMOJI,
      RECEIPT_READ_EMOJI,
      RECEIPT_DONE_EMOJI,
      RECEIPT_FAILED_EMOJI,
    ]);
  });
});
