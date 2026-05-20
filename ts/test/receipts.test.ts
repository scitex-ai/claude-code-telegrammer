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
