/**
 * Auto-error-reply / loud-fail outbound message (#14, 2026-06-07).
 *
 * When wakeTurn cannot deliver to /v1/turn (agent down / 401 /
 * quota-capped / connection refused / timeout / 5xx / etc.), the bridge
 * sends a Telegram reply to the operator on that bot explaining the
 * failure. Silence becomes impossible: every inbound either gets a
 * reply from the agent (success) or a loud-fail reply from the bridge
 * (failure).
 *
 * Wire shape (operator's revised spec 2026-06-07):
 *
 *     "⚠️ <agent_id> unavailable: <reason_phrase> — <retry_phrase>"
 *
 * The reason_phrase and retry_phrase are CATEGORY-DERIVED — they are
 * NOT a verbatim echo of the underlying wakeTurn error string. Per
 * lead's review (msg ab8d86e4 2026-06-07), the operator wants a fixed
 * actionable vocabulary so they can read failure-classes at a glance
 * without parsing stack-trace fragments. The raw error message lives
 * in the WARN log line for diagnostics; the Telegram reply stays
 * human-tier.
 *
 *   category            reason_phrase           retry_phrase
 *   ───────────────────────────────────────────────────────────────
 *   quota_capped        "<variant> quota cap"   "retry after <HH:MM>"  (when usage.json readable)
 *                       "quota cap"             "after the quota resets" (fallback)
 *   auth                "auth refresh needed"   "escalating to lead"
 *   connection_refused  "connection refused"    "retry in ~30s"
 *   timeout             "agent busy"            "retry shortly"
 *   server_error        "agent busy"            "retry shortly"
 *   client_error        "HTTP <status>"         "retry shortly"
 *   unknown             "<reason from result>"  "retry shortly"
 *
 * The outbound message-poster is injectable (setLoudFailSender) so
 * tests exercise the wiring without real network calls — same pattern
 * as receipts.ts::setReactionSender and wake.ts::setTurnPoster.
 *
 * Dedup: each (chat_id, message_id) gets at most one loud-fail reply
 * per process lifetime. The poller guarantees handleUpdate runs once
 * per message (saveInbound returns null on dedup), but a transient
 * within-process retry path could otherwise produce double-replies.
 *
 * Best-effort: a failed send is logged loudly and never thrown — must
 * not crash the relay or block subsequent deliveries.
 */

import { sendMessage } from "./telegram-api.js";
import { AGENT_ID, isLoudFailEnabled } from "./config.js";
import { log } from "./log.js";
import { formatResetTime, readQuotaReset } from "./usage.js";
import type { WakeFailCategory, WakeResult } from "./wake.js";

/**
 * Pair of strings that compose the loud-fail message body for one
 * category, before agent-id prefixing. Pure data — buildLoudFailMessage
 * concatenates them with " — " in the wire format.
 */
export interface FailPhrases {
  reason: string;
  retry: string;
}

/**
 * Resolve the (reason, retry) pair for a wakeTurn failure. Reads
 * usage.json for quota_capped (best-effort; falls back to a static
 * "after the quota resets" string when the file is missing/unreadable).
 *
 * Pure-ish: the only side effect is one best-effort fs read for the
 * quota_capped branch; every other branch is a pure mapping.
 */
export function resolveFailPhrases(
  result: Extract<WakeResult, { ok: false }>,
): FailPhrases {
  switch (result.category) {
    case "quota_capped": {
      const reset = readQuotaReset();
      if (reset) {
        return {
          reason: `${reset.variant} quota cap`,
          retry: `retry after ${formatResetTime(reset.resetAt)}`,
        };
      }
      return {
        reason: "quota cap",
        retry: "after the quota resets",
      };
    }
    case "auth":
      return {
        reason: "auth refresh needed",
        retry: "escalating to lead",
      };
    case "connection_refused":
      return {
        reason: "connection refused",
        retry: "retry in ~30s",
      };
    case "timeout":
      return {
        reason: "agent busy",
        retry: "retry shortly",
      };
    case "server_error":
      return {
        reason: "agent busy",
        retry: "retry shortly",
      };
    case "client_error":
      return {
        reason:
          result.status != null ? `HTTP ${result.status}` : "client error",
        retry: "retry shortly",
      };
    case "unknown":
      return {
        reason: result.reason || "unknown error",
        retry: "retry shortly",
      };
  }
}

/** Back-compat alias (older code may import retrySuggestion directly). */
export function retrySuggestion(category: WakeFailCategory): string {
  return resolveFailPhrases({
    ok: false,
    reason: "",
    category,
  }).retry;
}

/**
 * Render the loud-fail message body. Pure function — no I/O beyond the
 * one best-effort fs read in resolveFailPhrases() for the quota_capped
 * branch (the read still returns null on any failure, so even there the
 * function never throws). Exported so tests can pin the wire-format
 * directly without going through the network seam.
 *
 *     "⚠️ <agentId> unavailable: <reason> — <retry>"
 */
export function buildLoudFailMessage(
  result: Extract<WakeResult, { ok: false }>,
  agentId: string = AGENT_ID,
): string {
  const { reason, retry } = resolveFailPhrases(result);
  return `⚠️ ${agentId} unavailable: ${reason} — ${retry}`;
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
