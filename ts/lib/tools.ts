/**
 * MCP tool definitions and handlers for the Telegram MCP server.
 */

import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { assertAllowedChat } from "./access.js";
import {
  tgApi,
  sendMessage,
  sendDocument,
  editMessageText,
} from "./telegram-api.js";
import {
  saveOutbound,
  getHistory,
  getUnread,
  markRead,
  markAllRead,
  searchMessages,
  getConversationContext,
} from "./store.js";
import { HOST_NAME, PROJECT, AGENT_ID, BOT_TOKEN_HASH } from "./config.js";
import { log } from "./log.js";
import { downloadNow } from "./attachments.js";
import { runHealth, serializeHealthReport } from "./health-adapters.js";
import { TOOL_DEFINITIONS } from "./tool-definitions.js";

export function registerTools(mcp: Server): void {
  mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOL_DEFINITIONS,
  }));

  mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
    const args = (req.params.arguments ?? {}) as Record<string, unknown>;
    try {
      switch (req.params.name) {
        case "reply": {
          const chatId = args.chat_id as string;
          const text = args.text as string;
          // Hard length cap (operator 2026-06-04, raised to 512 on
          // 2026-06-06 per operator request): the operator reads on a
          // phone and cannot scan walls of text. REJECT over-limit messages
          // here at the send boundary instead of letting the API layer auto-
          // chunk them — this forces the caller (lead or any agent) to be
          // brief and split. Counts Unicode code points (CJK == Latin).
          // Read PER CALL (not at module load) so a running process picks
          // up CCT_TG_MAX_CHARS if it's set in its environment at spawn.
          const TG_LIMIT = Number(process.env.CCT_TG_MAX_CHARS ?? "512");
          if (
            typeof text === "string" &&
            [...text].length > TG_LIMIT &&
            process.env.CCT_TG_ALLOW_LONG !== "1"
          ) {
            return {
              content: [
                {
                  type: "text",
                  text:
                    `BLOCKED: message is ${[...text].length} chars > ${TG_LIMIT}-char limit. ` +
                    `Keep every Telegram message short (<=${TG_LIMIT} chars). ` +
                    `1) SPLIT a long update into MULTIPLE short messages, one point each. ` +
                    `2) Write ONLY what the operator must act on — no filler, no trivia, ` +
                    `no process-narration, no markdown bold. ` +
                    `If it is not worth ${TG_LIMIT} chars to the operator, do not send it. ` +
                    `Override (rare): set env CCT_TG_ALLOW_LONG=1.`,
                },
              ],
              isError: true,
            };
          }
          const replyTo =
            args.reply_to != null ? Number(args.reply_to) : undefined;
          const rowId = args.row_id != null ? Number(args.row_id) : undefined;
          const shouldMarkRead = args.mark_read !== false;
          assertAllowedChat(chatId);
          const msgId = await sendMessage(chatId, text, replyTo);
          try {
            saveOutbound(chatId, text, String(msgId), rowId, {
              host: HOST_NAME,
              project: PROJECT,
              agent_id: AGENT_ID,
              bot_token_hash: BOT_TOKEN_HASH,
            });
            // Mark the inbound as read if requested
            if (shouldMarkRead && rowId) {
              markRead(rowId);
            }
          } catch (err) {
            const errMsg = err instanceof Error ? err.message : String(err);
            log("tools", "failed to save outbound to store", {
              error: errMsg,
            });
          }
          return { content: [{ type: "text", text: `sent (id: ${msgId})` }] };
        }
        case "react": {
          const chatId = args.chat_id as string;
          assertAllowedChat(chatId);
          await tgApi("setMessageReaction", {
            chat_id: chatId,
            message_id: Number(args.message_id),
            reaction: [{ type: "emoji", emoji: args.emoji as string }],
          });
          return { content: [{ type: "text", text: "reacted" }] };
        }
        case "edit_message": {
          const chatId = args.chat_id as string;
          assertAllowedChat(chatId);
          // editMessageText() applies the agent signature (idempotent).
          const result = await editMessageText(
            chatId,
            Number(args.message_id),
            args.text as string,
          );
          const id =
            typeof result === "object" ? result.message_id : args.message_id;
          return { content: [{ type: "text", text: `edited (id: ${id})` }] };
        }
        case "get_history": {
          const chatId = args.chat_id as string;
          const limit = (args.limit as number) ?? 20;
          const offset = (args.offset as number) ?? 0;
          assertAllowedChat(chatId);
          const rows = getHistory(chatId, limit, offset);
          return {
            content: [{ type: "text", text: JSON.stringify(rows, null, 2) }],
          };
        }
        case "get_unread": {
          const chatId = args.chat_id as string | undefined;
          if (chatId) assertAllowedChat(chatId);
          const rows = getUnread(chatId);
          return {
            content: [{ type: "text", text: JSON.stringify(rows, null, 2) }],
          };
        }
        case "mark_read": {
          const chatId = args.chat_id as string | undefined;
          const messageIds = args.message_ids as number[] | undefined;
          if (chatId) {
            assertAllowedChat(chatId);
            markAllRead(chatId);
            return {
              content: [
                {
                  type: "text",
                  text: `marked all unread in ${chatId} as read`,
                },
              ],
            };
          }
          if (messageIds && messageIds.length > 0) {
            for (const id of messageIds) {
              markRead(id);
            }
            return {
              content: [
                {
                  type: "text",
                  text: `marked ${messageIds.length} message(s) as read`,
                },
              ],
            };
          }
          return {
            content: [
              {
                type: "text",
                text: "provide chat_id or message_ids to mark as read",
              },
            ],
            isError: true,
          };
        }
        case "download_attachment": {
          const fileId = args.file_id as string;
          const chatId = (args.chat_id as string) ?? "unknown";
          const localPath = await downloadNow(fileId, chatId);
          return {
            content: [{ type: "text", text: `downloaded to: ${localPath}` }],
          };
        }
        case "send_document": {
          const chatId = args.chat_id as string;
          const filePath = args.file_path as string;
          const caption = args.caption as string | undefined;
          assertAllowedChat(chatId);
          const msgId = await sendDocument(chatId, filePath, caption);
          return {
            content: [{ type: "text", text: `document sent (id: ${msgId})` }],
          };
        }
        case "search_messages": {
          const query = args.query as string;
          const chatId = args.chat_id as string | undefined;
          const limit = (args.limit as number) ?? 20;
          if (chatId) assertAllowedChat(chatId);
          const rows = searchMessages(query, chatId, limit);
          return {
            content: [{ type: "text", text: JSON.stringify(rows, null, 2) }],
          };
        }
        case "health": {
          // MCP-tool variant: this server process IS the poller, so the
          // poller_alive check reports our own pid ("self") instead of the
          // lockfile/pidfile round-trip the CLI probe does. The serialized
          // report has the raw token redacted (belt-and-braces — the checks
          // never include it in the first place).
          const report = await runHealth({ poller: "self" });
          return {
            content: [{ type: "text", text: serializeHealthReport(report) }],
          };
        }
        case "get_context": {
          const chatId = args.chat_id as string;
          const maxMessages = (args.max_messages as number) ?? 10;
          assertAllowedChat(chatId);
          const context = getConversationContext(chatId, maxMessages);
          return {
            content: [{ type: "text", text: context }],
          };
        }
        default:
          return {
            content: [
              { type: "text", text: `unknown tool: ${req.params.name}` },
            ],
            isError: true,
          };
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `${req.params.name} failed: ${msg}` }],
        isError: true,
      };
    }
  });
}
