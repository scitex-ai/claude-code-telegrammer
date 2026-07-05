/**
 * MCP tool list definitions (schema + annotations) for the Telegram MCP
 * server. Split out of tools.ts (which holds the request handlers) purely
 * to keep tools.ts under the repo's line-count limit — no behavior here,
 * just the static `tools/list` response consumed by registerTools().
 *
 * Annotation rationale (readOnlyHint / destructiveHint / idempotentHint /
 * openWorldHint, per the MCP tool-annotations spec):
 *   - readOnlyHint: true only for tools that don't mutate any state
 *     (get_history, get_unread, search_messages, health, get_context).
 *   - destructiveHint: false for every tool here — none of them delete or
 *     irrecoverably overwrite data. edit_message overwrites message text
 *     but nothing is "lost" in the destructive-update sense the spec means
 *     (e.g. an irreversible delete); mark_read/react are simple state
 *     flips.
 *   - idempotentHint: true where repeating the same call has no additional
 *     effect (react, edit_message, mark_read, download_attachment, and the
 *     read-only tools). false for reply/send_document, which each create a
 *     new message on every call.
 *   - openWorldHint: true only for tools that actually call out to the
 *     Telegram Bot API (reply, react, edit_message, download_attachment,
 *     send_document, health). get_history/get_unread/search_messages/
 *     get_context only read the local SQLite store, so openWorldHint is
 *     false for those.
 */

import type { Tool } from "@modelcontextprotocol/sdk/types.js";

export const TOOL_DEFINITIONS: Tool[] = [
  {
    name: "reply",
    description:
      "Reply on Telegram. Pass chat_id from the inbound message. " +
      "Optionally pass reply_to (message_id) for threading. " +
      "Set mark_read=false to keep the inbound message unread.",
    inputSchema: {
      type: "object" as const,
      properties: {
        chat_id: { type: "string" },
        text: { type: "string" },
        reply_to: {
          type: "string",
          description:
            "Message ID to thread under. Use message_id from the inbound <channel> block.",
        },
        row_id: {
          type: "number",
          description:
            "DB row ID of the inbound message being replied to (from row_id in meta). " +
            "Sets replied_at on that message and links the outbound row.",
        },
        mark_read: {
          type: "boolean",
          description:
            "Mark the inbound message (row_id) as read. Default: true.",
        },
      },
      required: ["chat_id", "text"],
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true,
    },
  },
  {
    name: "react",
    description:
      "Add an emoji reaction to a Telegram message. " +
      "Telegram only accepts a fixed whitelist.",
    inputSchema: {
      type: "object" as const,
      properties: {
        chat_id: { type: "string" },
        message_id: { type: "string" },
        emoji: { type: "string" },
      },
      required: ["chat_id", "message_id", "emoji"],
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
  },
  {
    name: "edit_message",
    description:
      "Edit a message the bot previously sent. " +
      "Edits don't trigger push notifications.",
    inputSchema: {
      type: "object" as const,
      properties: {
        chat_id: { type: "string" },
        message_id: { type: "string" },
        text: { type: "string" },
      },
      required: ["chat_id", "message_id", "text"],
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
  },
  {
    name: "get_history",
    description:
      "Get message history for a chat from the local DB. " +
      "Returns both inbound and outbound messages in chronological order.",
    inputSchema: {
      type: "object" as const,
      properties: {
        chat_id: { type: "string" },
        limit: {
          type: "number",
          description: "Max messages to return. Default: 20.",
        },
        offset: {
          type: "number",
          description: "Number of messages to skip. Default: 0.",
        },
      },
      required: ["chat_id"],
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: "get_unread",
    description: "Get unread inbound messages, optionally filtered by chat_id.",
    inputSchema: {
      type: "object" as const,
      properties: {
        chat_id: {
          type: "string",
          description: "Filter by chat. Omit to get all unread.",
        },
      },
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: "mark_read",
    description:
      "Mark messages as read. Pass either chat_id (marks all unread in that chat) " +
      "or message_ids (array of DB row IDs to mark individually).",
    inputSchema: {
      type: "object" as const,
      properties: {
        chat_id: {
          type: "string",
          description: "Mark all unread in this chat as read.",
        },
        message_ids: {
          type: "array",
          items: { type: "number" },
          description: "Array of DB row IDs to mark as read.",
        },
      },
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: "download_attachment",
    description:
      "Download a Telegram file attachment immediately. Returns the local file path.",
    inputSchema: {
      type: "object" as const,
      properties: {
        file_id: {
          type: "string",
          description: "Telegram file_id from the attachment.",
        },
        chat_id: {
          type: "string",
          description:
            "Chat ID for organizing downloads. Defaults to 'unknown'.",
        },
      },
      required: ["file_id"],
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
  },
  {
    name: "send_document",
    description: "Upload a file to a Telegram chat via sendDocument API.",
    inputSchema: {
      type: "object" as const,
      properties: {
        chat_id: {
          type: "string",
          description: "Target chat ID.",
        },
        file_path: {
          type: "string",
          description: "Absolute path to the local file to upload.",
        },
        caption: {
          type: "string",
          description: "Optional caption for the document.",
        },
      },
      required: ["chat_id", "file_path"],
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true,
    },
  },
  {
    name: "search_messages",
    description:
      "Text search across stored messages using LIKE matching. " +
      "Returns matching messages in reverse chronological order.",
    inputSchema: {
      type: "object" as const,
      properties: {
        query: {
          type: "string",
          description: "Search text (matched with LIKE %query%).",
        },
        chat_id: {
          type: "string",
          description: "Filter by chat. Omit to search all chats.",
        },
        limit: {
          type: "number",
          description: "Max results. Default: 20.",
        },
      },
      required: ["query"],
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: "health",
    description:
      "Run the claude-code-telegrammer health check (doctor). Returns a JSON report " +
      "{package, ok, checks[], summary} — env hygiene, bot token presence/validity, " +
      "webhook absence, poller liveness, allowlist, state dir, and DB schema/offset. " +
      "Every failing check carries an actionable hint. Takes no parameters.",
    inputSchema: {
      type: "object" as const,
      properties: {},
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
  },
  {
    name: "get_context",
    description:
      "Get recent conversation context for a chat, formatted as compact text for LLM consumption. " +
      "Returns messages in chronological order with timestamps and sender info.",
    inputSchema: {
      type: "object" as const,
      properties: {
        chat_id: {
          type: "string",
          description: "Chat to get context for.",
        },
        max_messages: {
          type: "number",
          description: "Max messages to include. Default: 10.",
        },
      },
      required: ["chat_id"],
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
];
