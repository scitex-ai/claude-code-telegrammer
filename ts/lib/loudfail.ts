/**
 * Auto-error-reply / loud-fail outbound message (#14, 2026-06-07).
 *
 * When wakeTurn cannot deliver to /v1/turn (agent down / 401 / 5xx /
 * connection refused / timeout / quota-capped / etc.), the bridge sends a
 * Telegram reply to the operator on that bot explaining the failure.
 * Silence becomes impossible: every inbound either gets a reply from
 * the agent (success) or a loud-fail reply from the bridge (failure).
 *
 * Pre-#14 behaviour: a dead-agent inbound got ❌ as its FINAL reaction
 * state and no text message — the operator was left to guess WHY the
 * agent didn't answer. The operator's 2026-06-07 mandate: encode the
 * failure-explanation IN CODE so they don't have to remember "if you
 * see ❌, ssh and check the agent's logs". The reply tells them.
 *
 * Wire shape: "⚠️ <agent_id> unavailable: <reason> — retry <when>"
 *
 *   examples:
 *     ⚠️ proj-foo unavailable: HTTP 502 — retry in a few minutes
 *     ⚠️ proj-foo unavailable: HTTP 401 — retry after fixing the bot token
 *     ⚠️ proj-foo unavailable: connect ECONNREFUSED — retry after the agent restarts
 *     ⚠️ proj-foo unavailable: network timeout — retry shortly
 *
 * The outbound message-poster is injectable (setLoudFailSender) so tests
 * exercise the wiring without real network calls — same pattern as
 * receipts.ts::setReactionSender and wake.ts::setTurnPoster.
 *
 * Dedup: each (chat_id, message_id) gets at most one loud-fail reply per
 * process lifetime. The poller guarantees handleUpdate runs once per
 * message (saveInbound returns null on dedup), but a transient
 * within-process retry path could otherwise produce double-replies.
 *
 * Best-effort: a failed send is logged loudly and never thrown — must
 * not crash the relay or block subsequent deliveries.
 */

import { sendMessage } from "./telegram-api.js";
import { AGENT_ID, isLoudFailEnabled } from "./config.js";
import { log } from "./log.js";
import type { WakeFailCategory, WakeResult } from "./wake.js";

/**
 * Operator-facing retry-suggestion per failure category. Plain English,
 * actionable. No emoji, no jargon — these get rendered into Telegram
 * messages and read by humans.
 */
export function retrySuggestion(category: WakeFailCategory): string {
  switch (category) {
    case "auth":
      return "after fixing the bot token";
    case "client_error":
      return "after fixing the request shape";
    case "server_error":
      return "in a few minutes";
    case "connection_refused":
      return "after the agent restarts";
    case "timeout":
      return "shortly";
    case "unknown":
      return "shortly";
  }
}

/**
 * Render the loud-fail message body. Pure function — no I/O, no env reads
 * beyond the agent identity. Exported so tests can pin the wire-format
 * directly without going through the network seam.
 */
export function buildLoudFailMessage(
  result: Extract<WakeResult, { ok: false }>,
  agentId: string = AGENT_ID,
): string {
  return `⚠️ ${agentId} unavailable: ${result.reason} — retry ${retrySuggestion(
    result.category,
  )}`;
}

/**
 * Low-level sender for the loud-fail message. Overridable in tests via
 * setLoudFailSender so the path can be exercised without real Telegram
 * calls. The contract: send (chat_id, text) reply-attached to
 * replyToMessageId. Returns whatever the underlying sender returns
 * (typically the outbound message id from the Bot API).
 */
type LoudFailSender = (
  chatId: string,
  text: string,
  replyToMessageId: number,
) => Promise<unknown>;

let loudFailSender: LoudFailSender = (chatId, text, replyToMessageId) =>
  sendMessage(chatId, text, replyToMessageId);

/** Test-only: override the loud-fail sender. Returns the previous sender. */
export function setLoudFailSender(sender: LoudFailSender): LoudFailSender {
  const prev = loudFailSender;
  loudFailSender = sender;
  return prev;
}

// Tracks which (chat_id, message_id) have already received a loud-fail
// reply this process lifetime, so a retry path can't double-send.
const sentLoudFailReplies = new Set<string>();

function loudFailKey(chatId: string, messageId: number): string {
  return `${chatId}:${messageId}`;
}

/** Test-only: clear the dedup cache. */
export function _resetLoudFail(): void {
  sentLoudFailReplies.clear();
}

/**
 * Post the loud-fail reply for a wakeTurn failure. No-op when:
 *   - isLoudFailEnabled() returns false (operator kill-switch), OR
 *   - we have already sent a loud-fail reply for this (chat_id, msg_id).
 *
 * Best-effort: any send failure is logged at warning, never thrown. The
 * caller (poller.ts handleUpdate) `void`s the returned promise.
 */
export async function sendLoudFailReply(
  chatId: string,
  replyToMessageId: number,
  result: Extract<WakeResult, { ok: false }>,
  agentId: string = AGENT_ID,
): Promise<void> {
  if (!isLoudFailEnabled()) return;

  const key = loudFailKey(chatId, replyToMessageId);
  if (sentLoudFailReplies.has(key)) return;
  // Mark before awaiting so concurrent calls for the same message don't
  // double-fire.
  sentLoudFailReplies.add(key);

  const text = buildLoudFailMessage(result, agentId);
  try {
    await loudFailSender(chatId, text, replyToMessageId);
    log("loudfail", "sent loud-fail reply", {
      chat_id: chatId,
      message_id: String(replyToMessageId),
      category: result.category,
      reason: result.reason,
    });
  } catch (err) {
    log("loudfail", "WARNING: failed to send loud-fail reply", {
      level: "warning",
      chat_id: chatId,
      message_id: String(replyToMessageId),
      category: result.category,
      reason: result.reason,
      error: String(err),
    });
  }
}
