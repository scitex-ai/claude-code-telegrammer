/**
 * Automatic four-stage read-receipt reactions on inbound operator messages.
 *
 * Driven by the relay daemon itself (not by the agent reacting manually).
 * Single reaction per message that ADVANCES through stages — Telegram
 * replaces the bot's reaction on each setMessageReaction call (non-premium
 * bots cap at 1 reaction/message per the Bot API):
 *
 *   Stage 1  ⚡  delivered — relay received the Telegram message and
 *                            persisted it. Fires UNCONDITIONALLY on every
 *                            inbound the bridge accepts.
 *   Stage 2  👀 received   — BRIDGE has accepted ownership and is now
 *                            driving delivery (MCP notification + wake
 *                            POST). Fires UNCONDITIONALLY immediately
 *                            after ⚡, regardless of agent state.
 *                            Operator-revised semantic (#41, 2026-06-07):
 *                            "👀 means the bridge has it" not "👀 means
 *                            the agent has it". This guarantees the
 *                            operator NEVER sees a stuck-on-⚡ message;
 *                            silence past ⚡ would mean a bridge crash.
 *   Stage 3  ✅ done       — agent finished processing the turn. Under
 *                            sac case-B semantics (/v1/turn returns 2xx
 *                            AFTER the turn completes), this is the
 *                            wakeTurn ok=true instant — advance straight
 *                            to ✅ from 👀.
 *   Stage 4  ❌ failed     — failure (agent down / 401 / connection refused /
 *                            timeout / non-2xx). Final visible state until
 *                            the operator retries. Progression is
 *                            ⚡ → 👀 → ❌; the operator can still tell
 *                            "agent down" from "agent live" by the FINAL
 *                            state, but the intermediate 👀 proves the
 *                            bridge itself is alive (the original #14
 *                            "👀 only on agent-live" contract is REPLACED
 *                            by this revision — the agent-live signal
 *                            moved up to ✅, freeing 👀 to mean
 *                            "bridge has it").
 *
 * All four emojis are on Telegram's fixed reaction whitelist.
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
  RECEIPT_DONE_EMOJI,
  RECEIPT_FAILED_EMOJI,
} from "./config.js";
import { log } from "./log.js";

type Stage = "delivered" | "received" | "done" | "failed";

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
export function markDelivered(
  chatId: string,
  messageId: string,
): Promise<void> {
  return setReceipt(chatId, messageId, "delivered", RECEIPT_DELIVERED_EMOJI);
}

/**
 * Stage 2 — 👀 the BRIDGE accepted ownership of the message.
 *
 * Operator-revised semantic (#41, 2026-06-07): 👀 means the relay has
 * accepted ownership and is now driving delivery (MCP notification +
 * wake POST), independent of whether the agent itself is reachable.
 * Fires UNCONDITIONALLY in poller.ts handleUpdate immediately after
 * markDelivered. The previous "👀 means agent received" contract from
 * #14 (2026-06-01) is replaced — that signal now lives at stage 3
 * (markDone). The motivation: under the old contract, a dead agent
 * left the operator's message stuck on ⚡ with no advance, which was
 * indistinguishable from a poller crash / 409 silent-loss. Decoupling
 * 👀 from agent state means the absence of 👀 now exclusively means
 * the bridge itself is down — a clean infra signal.
 */
export function markReceived(chatId: string, messageId: string): Promise<void> {
  return setReceipt(chatId, messageId, "received", RECEIPT_READ_EMOJI);
}

/**
 * Stage 3 — ✅ the agent finished processing the turn / produced its reply.
 *
 * Under current scitex-agent-container, sac /v1/turn is case (B): the POST
 * returns 2xx only AFTER the turn completes. So in SDK-runner mode, the
 * wakeTurn ok=true instant IS "agent finished" — the poller advances
 * straight from 👀 (already set unconditionally) to ✅. If sac ever
 * splits enqueue-ack from completed-turn, an explicit "agent received"
 * stage can be reintroduced between 👀 and ✅ without re-architecting.
 */
export function markDone(chatId: string, messageId: string): Promise<void> {
  return setReceipt(chatId, messageId, "done", RECEIPT_DONE_EMOJI);
}

/**
 * Stage 4 — ❌ failure (agent down / 401 / connection refused / timeout /
 * non-2xx response from /v1/turn). The final visible state until the
 * operator retries; replaces the ⚡ from stage 1.
 */
export function markFailed(chatId: string, messageId: string): Promise<void> {
  return setReceipt(chatId, messageId, "failed", RECEIPT_FAILED_EMOJI);
}

/**
 * @deprecated Backwards-compat alias for {@link markReceived}. The old
 * two-stage spec called this "read"; the four-stage spec calls it "received"
 * to disambiguate from stage 3 ("done", a.k.a. reply produced). Internal
 * callers should use markReceived; this alias is kept so external tests and
 * any out-of-tree consumers don't break across the rename.
 */
export function markRead(chatId: string, messageId: string): Promise<void> {
  return markReceived(chatId, messageId);
}
