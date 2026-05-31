/**
 * Automatic two-stage read-receipt reactions on inbound operator messages.
 *
 * Driven by the relay daemon itself (not by the agent reacting manually):
 *   ⚡  delivered — set the moment the relay receives the Telegram message
 *                  (and POSTs it to the agent's /v1/turn, if configured)
 *   👀 received  — set when the agent's /v1/turn POST returns 2xx in
 *                  SDK-runner mode (the agent runner accepted the
 *                  message). In interactive-CLI mode (no TURN_URL),
 *                  set when the MCP <channel> notification ack returns.
 *                  We do NOT wait for a reply / turn completion — 👀
 *                  is the 'agent got it' signal, nothing more.
 *
 * Telegram keeps only the latest bot reaction, so the ⚡→👀 transition is
 * visible to the operator. Both emojis are on Telegram's fixed whitelist.
 *
 * Reactions are:
 *   - configurable: gated by READ_RECEIPTS_ENABLED (env var, default ON)
 *   - idempotent:   each (chat_id, message_id, stage) reacts at most once
 *   - best-effort:  a failed reaction is logged loudly at warning, never
 *                   thrown — it must not crash the relay or block delivery
 */

import { tgApi } from "./telegram-api.js";
import {
  READ_RECEIPTS_ENABLED,
  RECEIPT_DELIVERED_EMOJI,
  RECEIPT_READ_EMOJI,
} from "./config.js";
import { log } from "./log.js";

type Stage = "delivered" | "read";

/**
 * Low-level reaction sender. Reuses the same setMessageReaction code path as
 * the `react` MCP tool. Overridable in tests via setReactionSender() to avoid
 * real network calls without globally mocking the telegram-api module.
 */
type ReactionSender = (
  chatId: string,
  messageId: number,
  emoji: string,
) => Promise<unknown>;

let reactionSender: ReactionSender = (chatId, messageId, emoji) =>
  tgApi("setMessageReaction", {
    chat_id: chatId,
    message_id: messageId,
    reaction: [{ type: "emoji", emoji }],
  });

/** Test-only: override the reaction sender. Returns the previous sender. */
export function setReactionSender(sender: ReactionSender): ReactionSender {
  const prev = reactionSender;
  reactionSender = sender;
  return prev;
}

// Tracks which (chat_id, message_id, stage) reactions have already been sent
// this process lifetime, so replays / duplicate updates don't re-react.
const sentReceipts = new Set<string>();

function receiptKey(chatId: string, messageId: string, stage: Stage): string {
  return `${chatId}:${messageId}:${stage}`;
}

/** Test-only: clear the idempotency cache. */
export function _resetReceipts(): void {
  sentReceipts.clear();
}

async function setReceipt(
  chatId: string,
  messageId: string,
  stage: Stage,
  emoji: string,
): Promise<void> {
  if (!READ_RECEIPTS_ENABLED) return;

  const key = receiptKey(chatId, messageId, stage);
  if (sentReceipts.has(key)) return;
  // Mark before awaiting so concurrent calls for the same message don't double-fire.
  sentReceipts.add(key);

  try {
    await reactionSender(chatId, Number(messageId), emoji);
  } catch (err) {
    // Best-effort: log loudly at warning, never throw — must not crash the relay.
    log("receipts", `WARNING: failed to set ${stage} receipt (${emoji})`, {
      level: "warning",
      chat_id: chatId,
      message_id: messageId,
      stage,
      error: String(err),
    });
  }
}

/** Stage 1 — ⚡ the moment the relay receives + persists the message. */
export function markDelivered(chatId: string, messageId: string): Promise<void> {
  return setReceipt(chatId, messageId, "delivered", RECEIPT_DELIVERED_EMOJI);
}

/** Stage 2 — 👀 when the message is surfaced into the Claude session. */
export function markRead(chatId: string, messageId: string): Promise<void> {
  return setReceipt(chatId, messageId, "read", RECEIPT_READ_EMOJI);
}
