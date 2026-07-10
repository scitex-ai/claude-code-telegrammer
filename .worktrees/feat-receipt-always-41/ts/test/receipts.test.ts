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
// #41 (2026-06-07) — receipt reaction ALWAYS fires.
//
// The new contract REPLACES the 2026-06-01 "dead-agent → no 👀" gating:
//
//   ⚡ markDelivered  fires unconditionally as soon as the relay
//                     persists the inbound message.
//   👀 markReceived   fires unconditionally IMMEDIATELY AFTER ⚡,
//                     before the wakeTurn POST and independent of its
//                     outcome. Operator-revised semantic: "👀 means
//                     THE BRIDGE has the message" — not "👀 means the
//                     AGENT has the message".
//   ✅ markDone       fires only if wakeTurn returns ok=true (sac
//                     case-B: ok=true is the agent-finished signal).
//   ❌ markFailed     fires only if wakeTurn returns ok=false.
//
// Why the change: under the old contract, a dead agent left the
// operator's message stuck on ⚡ with no advance, which was
// indistinguishable from a poller crash / 409 silent-loss (operator's
// #1 pain 2026-06-07). The new contract guarantees a 👀 advance for
// every inbound the bridge accepts, so silence past ⚡ now exclusively
// indicates a bridge-level failure — a clean infra signal.
// ---------------------------------------------------------------------------

import { wakeTurn, setTurnPoster } from "../lib/wake.js";

describe("👀 fires unconditionally (#41, post-2026-06-07 contract)", () => {
  beforeEach(() => {
    calls.length = 0;
    shouldThrow = false;
    _resetReceipts();
  });

  // The exact gating pattern poller.ts::handleUpdate now follows:
  //
  //   void markDelivered(...);
  //   void markReceived(...);          // <-- unconditional, the #41 change
  //   if (wakeEnabled()) {
  //     void wakeTurn(text, meta).then((ok) => {
  //       if (ok)  void markDone(...);
  //       else     void markFailed(...);
  //     });
  //   }
  //
  // Each test below models a different wakeTurn outcome and asserts
  // the reaction sequence the operator sees on the message.

  async function runHandleUpdateGating(): Promise<boolean> {
    await markDelivered("100", "5");
    await markReceived("100", "5"); // unconditional now
    const ok = await wakeTurn("hello", { chat_id: "100", message_id: "5" });
    if (ok) {
      await markDone("100", "5");
    } else {
      await markFailed("100", "5");
    }
    return ok;
  }

  test("dead agent (502): ⚡ → 👀 → ❌ — 👀 IS now reached (the #41 change)", async () => {
    setTurnPoster(async () => 502);
    const ok = await runHandleUpdateGating();
    expect(ok).toBe(false);
    expect(calls.length).toBe(3);
    expect(calls.map((c) => c.emoji)).toEqual([
      RECEIPT_DELIVERED_EMOJI,
      RECEIPT_READ_EMOJI,
      RECEIPT_FAILED_EMOJI,
    ]);
  });

  test("live agent (200): ⚡ → 👀 → ✅ — 👀 fires BEFORE wake, ✅ after ok=true", async () => {
    setTurnPoster(async () => 200);
    const ok = await runHandleUpdateGating();
    expect(ok).toBe(true);
    expect(calls.length).toBe(3);
    expect(calls.map((c) => c.emoji)).toEqual([
      RECEIPT_DELIVERED_EMOJI,
      RECEIPT_READ_EMOJI,
      RECEIPT_DONE_EMOJI,
    ]);
  });

  test("401 auth failure: ⚡ → 👀 → ❌ — bridge is up, agent rejected POST", async () => {
    setTurnPoster(async () => 401);
    const ok = await runHandleUpdateGating();
    expect(ok).toBe(false);
    expect(calls.length).toBe(3);
    expect(calls[1].emoji).toBe(RECEIPT_READ_EMOJI); // 👀 still fires
    expect(calls[2].emoji).toBe(RECEIPT_FAILED_EMOJI);
  });

  test("connection-refused (agent process dead): ⚡ → 👀 → ❌", async () => {
    setTurnPoster(async () => {
      throw new Error("connect ECONNREFUSED");
    });
    const ok = await runHandleUpdateGating();
    expect(ok).toBe(false);
    expect(calls.length).toBe(3);
    expect(calls[1].emoji).toBe(RECEIPT_READ_EMOJI);
    expect(calls[2].emoji).toBe(RECEIPT_FAILED_EMOJI);
  });

  test("timeout: ⚡ → 👀 → ❌ — the visible progression for any wake failure", async () => {
    setTurnPoster(async () => {
      throw new Error("network timeout");
    });
    const ok = await runHandleUpdateGating();
    expect(ok).toBe(false);
    expect(calls[1].emoji).toBe(RECEIPT_READ_EMOJI);
    expect(calls[2].emoji).toBe(RECEIPT_FAILED_EMOJI);
  });

  test("👀 visible BEFORE wakeTurn resolves — operator sees 👀 even if wake hangs", async () => {
    // The critical operator-pain case: wakeTurn never resolves (network
    // partition / agent stuck mid-turn). 👀 must still appear because
    // the poller fires it BEFORE awaiting wakeTurn. We model "wakeTurn
    // hangs" by intentionally not awaiting it.
    await markDelivered("100", "5");
    await markReceived("100", "5");
    expect(calls.length).toBe(2);
    expect(calls[0].emoji).toBe(RECEIPT_DELIVERED_EMOJI);
    expect(calls[1].emoji).toBe(RECEIPT_READ_EMOJI);
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

  test("delivered → received → failed is a three-call ⚡→👀→❌ (dead-agent path, #41)", async () => {
    // Under the #41 (2026-06-07) contract, EVERY received message
    // advances to 👀 before any further outcome — including failure.
    // A DM to a dead/stopped agent now produces ⚡ → 👀 → ❌. The
    // operator can still tell agent-down from agent-live by the FINAL
    // state (❌ vs ✅); the intermediate 👀 proves the bridge itself
    // is alive (silence past ⚡ now exclusively means bridge crash).
    //
    // This REPLACES the older 2026-06-01 contract where 👀 was gated
    // on /v1/turn 2xx and a dead agent went ⚡ → ❌ skipping 👀.
    await markDelivered("100", "5");
    await markReceived("100", "5");
    await markFailed("100", "5");
    expect(calls.length).toBe(3);
    expect(calls[0].emoji).toBe(RECEIPT_DELIVERED_EMOJI);
    expect(calls[1].emoji).toBe(RECEIPT_READ_EMOJI);
    expect(calls[2].emoji).toBe(RECEIPT_FAILED_EMOJI);
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
