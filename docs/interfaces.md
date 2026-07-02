# Interfaces

## MCP server (for AI agents)

Start command:

```bash
bun run ts/telegram-server.ts
```

Exposes 10 tools over the MCP stdio protocol. The server's MCP instructions embed
a **responsiveness policy**: acknowledge inbound messages immediately and
delegate heavy work to background subagents, so the relay never blocks.

| Tool | Description |
|------|-------------|
| `reply` | Reply on Telegram. Supports threading (`reply_to`), auto-marks the inbound as read; inbound reply-to references are tracked and forwarded. |
| `react` | Add an emoji reaction. Inbound reactions (`message_reaction`) are also delivered as channel notifications. |
| `edit_message` | Edit a message the bot previously sent. |
| `get_history` | Retrieve message history for a chat from local SQLite. |
| `get_unread` | List unread inbound messages, optionally filtered by `chat_id`. |
| `mark_read` | Mark messages read by `chat_id` or `message_ids`. |
| `download_attachment` | Download a Telegram file by `file_id`; returns a local path. |
| `send_document` | Upload a local file to a Telegram chat. |
| `search_messages` | Text search across stored messages. |
| `get_context` | Recent conversation formatted as compact text for LLM context. |

Inbound messages arrive as `<channel source="claude-code-telegrammer" …>`
notifications carrying `chat_id` / `message_id` / `row_id` / `user` — pass
`chat_id` and `row_id` back to `reply`.

## Skills (for AI agent discovery)

A bundled skill lives at
`src/claude_code_telegrammer/_skills/claude-code-telegrammer/SKILL.md`.

## config probe (for orchestrators)

```bash
bun run ts/telegram-server.ts config [--check]
```

Resolves and prints the effective config as JSON (agent_id, bot_token_hash,
state_dir, channel_source, turn_url) **without** starting the server or poller.
`--check` adds a single `getMe` to confirm the token → `@username` mapping. Used
to preflight per-agent bot identity and detect two agents resolving to the same
bot. The raw token is never printed.
