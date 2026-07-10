/**
 * Telegram getUpdates long-polling loop with inbound message delivery.
 */

import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { tgApi } from "./telegram-api.js";
import { isAllowed, loadAccess } from "./access.js";
import { log } from "./log.js";
import { HOST_NAME, PROJECT, AGENT_ID, BOT_TOKEN_HASH } from "./config.js";
import {
  saveInbound,
  saveOffset,
  loadOffset,
  insertAttachment,
} from "./store.js";
import { queueDownload } from "./attachments.js";
import {
  markDelivered,
  markReceived,
  markDone,
  markFailed,
  markRead,
} from "./receipts.js";
import { wakeTurn, wakeEnabled } from "./wake.js";
import { parseForward, buildInboundText } from "./forward.js";

let updateOffset = 0;
let polling = true;

export function stopPolling(): void {
  polling = false;
}

export async function startPolling(mcp: Server): Promise<void> {
  log("poller", "starting getUpdates polling...");

  // Restore persisted offset from DB
  try {
    updateOffset = loadOffset();
    if (updateOffset > 0) {
      log("poller", `resumed from persisted offset ${updateOffset}`);
    }
  } catch (err) {
    log("poller", "failed to load offset from DB, starting from 0", {
      error: String(err),
    });
  }

  // Check allowlist at startup — fail loud if empty
  const access = loadAccess();
  if (
    access.allowFrom.length === 0 &&
    Object.keys(access.groups).length === 0
  ) {
    log(
      "poller",
      "ERROR: allowlist is empty — all messages will be rejected. Set CLAUDE_CODE_TELEGRAMMER_TELEGRAM_ALLOWED_USERS or create access.json in CLAUDE_CODE_TELEGRAMMER_TELEGRAM_STATE_DIR",
    );
  }

  try {
    const me = await tgApi("getMe");
    log("poller", `polling as @${me.username}`);
  } catch (err) {
    log("poller", `getMe failed: ${err}`);
  }

  // Preflight: try a short long-poll to detect competing consumers.
  // timeout=0 is instant and won't collide — we need timeout>0 to trigger
  // the 409 if another consumer is already in a long-poll.
  log("poller", "preflight: testing for competing consumers (3s)...");
  try {
    await tgApi("getUpdates", { offset: updateOffset, timeout: 3, limit: 1 });
    log("poller", "preflight OK — no competing consumers detected");
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    if (errMsg.includes("409")) {
      const fatalMsg =
        "FATAL: 409 Conflict on startup — another process is already polling this bot token. " +
        "Only one getUpdates consumer is allowed per token. " +
        "Stop the other consumer first, or use a different bot token. " +
        "Refusing to start.";
      log("poller", fatalMsg);
      // Notify the agent so it knows Telegram is NOT connected
      mcp
        .notification({
          method: "notifications/claude/channel",
          params: {
            content: fatalMsg,
            meta: { source: "telegram", type: "error" },
          },
        })
        .catch(() => {});
      polling = false;
      return;
    }
    // Non-409 errors are OK to proceed (e.g., network hiccup)
    log("poller", `preflight warning: ${errMsg} (proceeding anyway)`);
  }

  while (polling) {
    try {
      const updates = await tgApi("getUpdates", {
        offset: updateOffset,
        timeout: 30,
        allowed_updates: ["message", "message_reaction"],
      });
      if (!Array.isArray(updates)) continue;
      for (const update of updates) {
        updateOffset = update.update_id + 1;
        try {
          await handleUpdate(mcp, update);
        } catch (err) {
          log("poller", `error handling update ${update.update_id}`, {
            error: String(err),
          });
        }
      }
      // Persist offset after each batch
      if (updates.length > 0) {
        try {
          saveOffset(updateOffset);
        } catch (err) {
          log("poller", "failed to persist offset", { error: String(err) });
        }
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      if (errMsg.includes("409")) {
        const conflictMsg =
          "409 Conflict — another process is polling this bot token. " +
          "Only one getUpdates consumer is allowed per token. " +
          "Telegram connection is DOWN. Stop the other consumer or use a different bot token.";
        log("poller", conflictMsg);
        mcp
          .notification({
            method: "notifications/claude/channel",
            params: {
              content: conflictMsg,
              meta: { source: "telegram", type: "error" },
            },
          })
          .catch(() => {});
        // Stop polling — don't retry, the agent needs to fix this
        polling = false;
        return;
      } else {
        log("poller", `getUpdates error: ${errMsg}. Retrying in 3s...`);
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
  }
}

async function handleReaction(mcp: Server, update: any): Promise<void> {
  const reaction = update.message_reaction;
  if (!reaction?.user || !reaction?.new_reaction) return;

  const userId = String(reaction.user.id);
  const chatId = String(reaction.chat.id);
  const chatType = reaction.chat.type;

  if (!isAllowed(userId, chatId, chatType)) {
    log(
      "poller",
      `REJECTED: reaction from user ${userId} in chat ${chatId} — not in allowlist`,
    );
    return;
  }

  const emojis = reaction.new_reaction
    .filter((r: any) => r.type === "emoji" && r.emoji)
    .map((r: any) => r.emoji)
    .join("");

  if (!emojis) return;

  const ts = new Date((reaction.date ?? 0) * 1000).toISOString();
  const meta: Record<string, string> = {
    chat_id: chatId,
    message_id: String(reaction.message_id),
    user_id: userId,
    user: reaction.user.username ?? userId,
    ts,
    source: "telegram",
    type: "reaction",
  };

  const text = `(reaction: ${emojis} on message ${reaction.message_id})`;
  log("poller", `delivering reaction from ${userId} in ${chatId}`, { emojis });
  mcp
    .notification({
      method: "notifications/claude/channel",
      params: { content: text, meta },
    })
    .catch((err) => {
      log("poller", "failed to deliver reaction to Claude", {
        error: String(err),
      });
    });
}

async function handleUpdate(mcp: Server, update: any): Promise<void> {
  if (update.message_reaction) {
    await handleReaction(mcp, update);
    return;
  }

  const msg = update.message;
  if (!msg?.from) return;

  const userId = String(msg.from.id);
  const chatId = String(msg.chat.id);
  const chatType = msg.chat.type;

  if (!isAllowed(userId, chatId, chatType)) {
    log(
      "poller",
      `REJECTED: message from user ${userId} in chat ${chatId} (type=${chatType}) — not in allowlist. Set CLAUDE_CODE_TELEGRAMMER_TELEGRAM_ALLOWED_USERS or create access.json`,
      { userId, chatId, chatType },
    );
    return;
  }

  // Build the text the agent sees. buildInboundText handles:
  //   - text vs caption (for media messages with a caption)
  //   - placeholder strings for media without a caption ("(photo)" etc.)
  //   - prepending "[forwarded from <whom>, <when>]" when forwarded
  // Caption + attachment file_id survive together; forward banner sits
  // on top of any caption/placeholder so provenance is always visible.
  const text = buildInboundText(msg);
  if (!text) return;

  // Capture forward metadata (Bot API >=7.0 forward_origin OR legacy
  // forward_from / forward_from_chat / forward_sender_name). null when
  // the message is not a forward.
  const forwardInfo = parseForward(msg);
  const forwardJson = forwardInfo ? JSON.stringify(forwardInfo) : undefined;

  const ts = new Date((msg.date ?? 0) * 1000).toISOString();
  const replyToMessageId = msg.reply_to_message
    ? String(msg.reply_to_message.message_id)
    : undefined;

  // Persist to SQLite before acking
  let rowId: number | null = null;
  try {
    rowId = saveInbound({
      chat_id: chatId,
      message_id: String(msg.message_id),
      user_id: userId,
      username: msg.from.username ?? userId,
      text,
      telegram_ts: ts,
      reply_to_message_id: replyToMessageId,
      forward_json: forwardJson,
      host: HOST_NAME,
      project: PROJECT,
      agent_id: AGENT_ID,
      bot_token_hash: BOT_TOKEN_HASH,
      raw_json: JSON.stringify(update),
    });
  } catch (err) {
    log("poller", "failed to save inbound message to store", {
      error: String(err),
    });
  }

  // If saveInbound returned null, it's a duplicate — skip reaction + notification
  if (rowId === null) return;

  // Extract and persist attachments
  const attachments: Array<{ kind: string; obj: any }> = [
    { kind: "photo", obj: msg.photo?.[msg.photo.length - 1] },
    { kind: "document", obj: msg.document },
    { kind: "voice", obj: msg.voice },
    { kind: "audio", obj: msg.audio },
    { kind: "video", obj: msg.video },
  ];
  for (const { kind, obj } of attachments) {
    if (obj) {
      try {
        insertAttachment(rowId, {
          kind,
          file_id: obj.file_id,
          file_unique_id: obj.file_unique_id,
          file_name: obj.file_name,
          mime_type: obj.mime_type,
          file_size: obj.file_size,
        });
        queueDownload(rowId, obj.file_id, kind, chatId);
      } catch (err) {
        log("poller", "failed to insert attachment", {
          error: String(err),
          kind,
        });
      }
    }
  }

  // Stage 1 + Stage 2 receipts fire UNCONDITIONALLY here (#41,
  // operator 2026-06-07):
  //
  //   \u26A1 markDelivered \u2014 relay received + persisted the message.
  //   \uD83D\uDC40 markReceived  \u2014 relay accepted ownership and is now driving
  //                      delivery (MCP notification + wake POST).
  //
  // Previous behaviour gated \uD83D\uDC40 on either MCP-notification ack OR
  // wakeTurn 2xx. That meant a dead/down agent never reached \uD83D\uDC40 \u2014 the
  // operator confirmed in 2026-06-07 they prefer "\uD83D\uDC40 means the BRIDGE
  // has the message" over "\uD83D\uDC40 means the AGENT has the message",
  // because the absence of \uD83D\uDC40 in the old contract was indistinguishable
  // from a poller crash / 409 loss / silent drop (the operator's
  // single most painful failure mode this week).
  //
  // The advancing reaction sequence is now:
  //
  //     \u26A1 \u2192 \uD83D\uDC40 \u2192 \u2705  (live agent, /v1/turn ok)
  //     \u26A1 \u2192 \uD83D\uDC40 \u2192 \u274C  (down agent, /v1/turn non-2xx or unreachable)
  //     \u26A1 \u2192 \uD83D\uDC40       (interactive CLI, no TURN_URL \u2014 no further stages)
  //
  // The operator can still tell "agent down" from "agent live": the
  // FINAL state is \u274C vs \u2705. The intermediate \uD83D\uDC40 reassures them the
  // bridge itself is alive. The "no reaction" state can now only mean
  // the poller is dead (no PID claim on the token, can't issue a
  // setMessageReaction) \u2014 which together with the #37 newest-wins
  // takeover protocol means "silence == infra problem", never a logic
  // problem in the bridge.
  //
  // Both calls are idempotent (per-(chat, msg, stage) dedupe in
  // receipts.ts) and best-effort (errors logged at warning, never
  // thrown). Safe to fire eagerly.
  void markDelivered(chatId, String(msg.message_id));
  void markReceived(chatId, String(msg.message_id));

  // Fire-and-forget typing indicator
  tgApi("sendChatAction", { chat_id: chatId, action: "typing" }).catch(
    () => {},
  );

  // Build meta for channel notification
  const meta: Record<string, string> = {
    chat_id: chatId,
    message_id: String(msg.message_id),
    row_id: String(rowId),
    user: msg.from.username ?? userId,
    user_id: userId,
    ts,
    source: "telegram",
  };
  if (replyToMessageId) {
    meta.reply_to_message_id = replyToMessageId;
  }

  // Forward provenance — exposed on meta so downstream consumers
  // (audit, signature, /v1/turn payload) can distinguish a forwarded
  // message from one the user typed themselves. The banner is already
  // prepended to text; these fields make the structured metadata
  // available without re-parsing.
  if (forwardInfo) {
    meta.forward_kind = forwardInfo.kind;
    meta.forward_from = forwardInfo.from_name;
    meta.forward_date = forwardInfo.date_iso;
    if (forwardInfo.from_id) meta.forward_from_id = forwardInfo.from_id;
    if (forwardInfo.from_username)
      meta.forward_from_username = forwardInfo.from_username;
    if (forwardInfo.original_message_id)
      meta.forward_original_message_id = forwardInfo.original_message_id;
    if (forwardInfo.signature) meta.forward_signature = forwardInfo.signature;
  }

  // Add attachment metadata to channel notification
  for (const { kind, obj } of attachments) {
    if (obj) {
      meta.attachment_kind = kind;
      meta.attachment_file_id = obj.file_id;
      if (obj.file_name) meta.attachment_name = obj.file_name;
      if (obj.mime_type) meta.attachment_mime = obj.mime_type;
      break;
    }
  }

  log("poller", `delivering message from ${userId} in ${chatId}`, {
    text: text.slice(0, 50),
    row_id: rowId,
  });

  // Notification path — renders <channel> in an ACTIVE turn (interactive
  // Claude Code CLI). Does NOT advance an IDLE SDK-runner session. The
  // 👀 receipt has already fired above; the notification ack is no
  // longer the trigger (it never was a reliable signal in SDK-runner
  // mode anyway, since a dead agent's MCP server can still ack).
  mcp
    .notification({
      method: "notifications/claude/channel",
      params: { content: text, meta },
    })
    .catch((err) => {
      log("poller", "failed to deliver inbound to Claude", {
        error: String(err),
      });
    });

  // Wake-on-push — when CLAUDE_CODE_TELEGRAMMER_TURN_URL is set
  // (SDK-runner agents), POST the message to the agent's own /v1/turn.
  // The outcome advances the reaction past 👀 to the FINAL stage:
  //
  //   wakeTurn ok=true  → ✅ done   (stage 3)
  //   wakeTurn ok=false → ❌ failed (stage 4)
  //
  // Under current scitex-agent-container, sac /v1/turn is case (B):
  // the POST returns 2xx only AFTER the turn completes. So ok=true is
  // simultaneously "agent received" and "agent finished" — we advance
  // straight to ✅. This sequence is forward-compatible if sac ever
  // splits the signals (enqueue-ack vs completed-turn): the two
  // callsites can then be wired independently.
  //
  // A dead / stopped agent (connection refused, timeout, 401, any non-
  // 2xx) yields ok=false and ❌ is set; the operator sees ⚡ → 👀 → ❌
  // and can tell the agent is down by the FINAL state. (Pre-#41 the
  // operator saw ⚡ → ❌ and never 👀 — now they get 👀 first so the
  // bridge's aliveness is visible regardless of agent state.)
  if (wakeEnabled()) {
    void wakeTurn(text, meta).then((ok) => {
      if (ok) {
        void markDone(chatId, String(msg.message_id));
      } else {
        void markFailed(chatId, String(msg.message_id));
      }
    });
  }
}
