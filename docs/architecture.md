# Architecture

How claude-code-telegrammer wires an autonomous Claude Code agent to a Telegram
bot. For the top-level diagram see the [README](../README.md#architecture); this
document covers the internals.

## Components

The MCP server (`ts/telegram-server.ts`, Bun + `@modelcontextprotocol/sdk`) is a
single stdio process with these internal modules (`ts/lib/`):

| Module | Responsibility |
|--------|----------------|
| `poller` | Telegram `getUpdates` long-poll; delivers inbound messages as MCP channel notifications |
| `store` | SQLite (WAL) message persistence + dedup + read/replied tracking |
| `tools` | The 10 MCP tools (see [interfaces](interfaces.md)) |
| `attachments` | Background download queue for inbound files |
| `access` | Allowlist gating (`access.json` + `CCT_ALLOWED_USERS`), mtime-cached |
| `config` / `env` | Env-var resolution (see [configuration](configuration.md)) |
| `lock` / `takeover` | Single-instance PID lock + newest-wins per-token takeover |

An optional **TUI Watchdog** (`lib/`, shell) keeps an interactive CLI session
alive; SDK-runner agents use the [wake path](configuration.md#wake-on-push-turn_url)
instead. Lifecycle orchestration is handled by
[scitex-agent-container](https://github.com/ywatanabe1989/scitex-agent-container).

## Data flow

**Inbound:** Telegram `getUpdates` → poller → allowlist gate → (if allowed) MCP
channel notification → Claude Code. **Outbound:** Claude Code calls the `reply` /
`react` / `send_document` tools → `sendMessage` → Telegram → operator.

Each agent is a self-contained unit: its own bot token, its own state directory,
its own poller. See [per-agent identity](configuration.md#per-agent-identity).

## Startup fail-loud guards

The server refuses to start (loud, actionable stderr) rather than run degraded —
every failure names the exact env var and the fix:

1. **Unexpanded `${…}` placeholder** in any telegrammer env var — the launcher
   started without its `.env` sourced, so a literal `${VAR}` came through. Abort
   before touching state.
2. **Missing bot token** (`CCT_BOT_TOKEN` unset/empty).
3. **Invalid/revoked token** — a `getMe` call at startup classifies `401`/`404`
   as fatal (re-issue via @BotFather) vs. a transient network/`429`/`5xx` error
   (warn + continue; a Telegram outage must not permanently kill a valid poller).
4. **Renamed env var still set** — the old `CCT_STATE_DIR` /
   `CLAUDE_CODE_TELEGRAMMER_STATE_DIR` name is rejected; use
   `CCT_AGENT_STATE_DIR` (see [configuration](configuration.md)).

The `config` identity probe (`bun run ts/telegram-server.ts config [--check]`)
resolves and prints the config as JSON without starting the server — used to
preflight per-agent bot identity and detect two agents on the same token.

## Bot token exclusivity

The server **must be the sole consumer** of its bot token: the Telegram Bot API
allows only one `getUpdates` long-poll per token.

| Scenario | Symptom | Detection |
|----------|---------|-----------|
| Two pollers start simultaneously | One gets 409, the other wins | Loser logs `409 Conflict` |
| Two pollers start sequentially | Only one receives messages | **No error** — the other gets empty responses forever |
| Webhook active + poller | Poller gets nothing | **No error** — Telegram ignores `getUpdates` when a webhook is set |

**Why 409 detection alone is insufficient:** Telegram does not reliably 409 for
sequential (non-overlapping) polls — both connections succeed, one just gets no
messages. A `timeout=3` startup preflight catches overlapping polls, not the
sequential case. Two same-token pollers of OURS resolve via the **newest-wins
takeover**: a fresh poller records its PID in the per-token pidfile and preempts
the predecessor, instead of both 409-looping forever.

**If messages aren't arriving:**
1. Another poller on the token? `ps aux | grep telegram-server`
2. A webhook set? `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
3. Give each component/agent its own bot token (see
   [per-agent identity](configuration.md#per-agent-identity)).

**Webhook alternative:** [scitex-orochi](https://github.com/ywatanabe1989/scitex-orochi)
supports Telegram webhook mode (`POST /webhook/telegram/`), eliminating polling
conflicts (`SCITEX_OROCHI_TELEGRAM_WEBHOOK_URL`).

## TUI watchdog state detection

The watchdog polls the GNU Screen buffer and sends keystrokes to keep an
interactive session moving:

| State | Pattern | Response |
|-------|---------|----------|
| `running` | `(esc to interrupt)`, `tokens ·`, `ing...` | No action |
| `y_n` | `1. Yes` + `3. No` | Send `1` (accept) |
| `y_y_n` | `2. Yes, and…` / `2. Yes, allow…` / `2. Yes, don't ask…` | Send `2` (accept all) |
| `waiting` | idle hints, empty `>` prompt | Send configurable command |

Throttled: minimum inter-response interval, burst limit (10 in 3s), same-state delay.

## SQLite schema (v2)

All messages persist in `$CLAUDE_CODE_TELEGRAMMER_AGENT_STATE_DIR/messages.db` (WAL mode).

- **messages** — direction, chat_id, message_id, user_id, username, text,
  timestamps (telegram_ts, received_at, read_at, replied_at), threading
  (reply_to_message_id, reply_to_row_id), identity (host, project, agent_id,
  bot_token_hash), raw_json.
- **attachments** — message_row_id (FK), kind, file_id, file_name, mime_type,
  file_size, local_path, downloaded_at.
- **meta** — key-value store for schema_version, update_offset.

## Part of the SciTeX agent stack

```
scitex-orochi          — agent definitions, dashboard
        ↓
scitex-agent-container — lifecycle, health, restart, per-agent .envrc + .mcp.json
        ↓
claude-code-telegrammer — MCP server (Telegram API, message DB, 10 tools) + watchdog
```
