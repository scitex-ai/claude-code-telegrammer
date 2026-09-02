# Configuration

All configuration is via environment variables. Every telegrammer-owned var has
two accepted spellings — a short `CCT_<KEY>` (preferred) and a canonical
`CLAUDE_CODE_TELEGRAMMER_<KEY>`. They are aliases of one setting; if both are set
and disagree the server fails loud rather than silently pick one. An empty string
counts as unset.

## MCP server

| Variable (`CCT_…` / `CLAUDE_CODE_TELEGRAMMER_…`) | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | To enable | — | Telegram Bot API token. Empty/absent → telegram **disabled** (loud `[WARN]`, MCP still connects, no poller — not a crash). Present-but-invalid → **fail loud** (`getMe` 401/404). |
| `AGENT_STATE_DIR` | No | `~/.claude-code-telegrammer` (or `-<agent_id>`) | **Per-agent** state dir override (access.json, lock, downloaded attachments; messages live in PostgreSQL, not here). The old `…_STATE_DIR` name is renamed and rejected at startup — unset it. |
| `ALLOWED_USERS` | No | — | Comma-separated Telegram user IDs for the DM allowlist. |
| `AGENT_ID` | No | `telegram` | Per-agent identity; also derives the default state dir (see below). |
| `HOST_NAME` | No | `os.hostname()` | Hostname stored with each message. |
| `PROJECT` | No | `process.cwd()` | Project path stored with each message. |
| `READ_RECEIPTS` | No | `on` | Read-receipt reactions (⚡ received → 👀 surfaced → ✅ done → ❌ failed). Set `0`/`false`/`no`/`off` to disable. |
| `TURN_URL` | No | — | Wake endpoint for idle SDK-runner sessions (see below). |

## Launcher: locating the TS server

The `claude-code-telegrammer` Python command is a thin launcher that `execv`s
`bun` on `ts/telegram-server.ts`. Two variables steer it. Both are **launcher**
settings read by Python, so unlike the table above they have **no
`CLAUDE_CODE_TELEGRAMMER_…` alias** — the names below are the only spellings.

| Variable | Required | Default | Description |
|---|---|---|---|
| `CCT_SERVER_ENTRY` | No | — | Absolute path to `telegram-server.ts`. **Authoritative when set**: a path that does not exist is an error, never a silent fallback to a different server. |
| `BUN_BIN` | No | `bun` on `$PATH`, then `~/.bun/bin/bun` | Path to the `bun` executable. |

Without `CCT_SERVER_ENTRY` the launcher looks, in order, for the `ts/` directory
shipped **inside the installed package** (`importlib.resources`), then for
`<repo>/ts/telegram-server.ts` in a source checkout. If none resolves it exits
`2` and prints every path it tried — it does not start and then die later.

> **Installing from a wheel:** the wheel ships `telegram-server.ts`,
> `telegram-poller.ts` and all of `ts/lib/`, but **not** `node_modules` —
> third-party bun packages do not belong in a Python distribution. Run
> `bun install` once in the packaged `ts/` directory
> (`python -c "import claude_code_telegrammer, pathlib; print(pathlib.Path(claude_code_telegrammer.__file__).parent / 'ts')"`)
> or point `CCT_SERVER_ENTRY` at a checkout where you have already run it.

## Per-agent identity

Each agent runs its **own** Telegram bot (own `CCT_BOT_TOKEN`) and gets its own
isolated state so multiple agents on one host never collide on the poller
pidfile / `messages.db`:

- Set `CCT_AGENT_ID` per agent → the state dir derives to
  `~/.claude-code-telegrammer-<agent_id>` automatically. **This is the preferred
  path** — do not hand-set `CCT_AGENT_STATE_DIR` unless you need a non-standard
  location.
- Leave `CCT_AGENT_ID` unset (or `telegram`) → the shared base
  `~/.claude-code-telegrammer` (e.g. a single interactive bridge).

In the SciTeX fleet, tokens are injected per agent via each project's `.envrc`
(e.g. `export CCT_BOT_TOKEN="$CCT_BOT_TOKEN_<AGENT>"`), and the shared
`_shared/.mcp.json` references them with `${VAR}` brace expansion resolved at
MCP launch. An unexpanded `${…}` (launcher started without its `.env`) fails
loud at startup rather than running with a junk value.

## Registering the MCP server

`.mcp.json` (gitignored — copy `.mcp.json.example`):

```json
{
  "mcpServers": {
    "claude-code-telegrammer": {
      "type": "stdio",
      "command": "bun",
      "args": ["run", "/path/to/claude-code-telegrammer/ts/telegram-server.ts"],
      "env": {
        "CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN": "123456789:AAH...",
        "CLAUDE_CODE_TELEGRAMMER_ALLOWED_USERS": "YOUR_TELEGRAM_USER_ID",
        "CLAUDE_CODE_TELEGRAMMER_AGENT_STATE_DIR": "~/.claude-code-telegrammer"
      }
    }
  }
}
```

Find your Telegram user ID via [@userinfobot](https://t.me/userinfobot).

## Access control

Gating is allowlist-based. With `dmPolicy: allowlist` and an **empty** allow list
(no `access.json` and empty `CCT_ALLOWED_USERS`), every DM is **rejected** —
fail-closed, so the bot looks dead. The server warns loudly about this at
startup. Managed via `access.json` in the state dir:

```json
{
  "dmPolicy": "allowlist",
  "allowFrom": ["123456789"],
  "groups": {
    "-100123456": { "requireMention": true, "allowFrom": ["123456789"] }
  }
}
```

Merged with `CCT_ALLOWED_USERS` at runtime; mtime-based caching means edits take
effect without a restart.

## Wake-on-push (`TURN_URL`)

An interactive Claude Code CLI has a live event loop that picks up inbound
channel notifications. An **idle SDK-runner** session is parked on its inbox and
won't. When `CCT_TURN_URL` is set, each qualifying inbound is additionally
POSTed to that endpoint (the agent's own `/v1/turn`) so the runner drives a turn
at once. Optional `CCT_TURN_BEARER` sets the `Authorization: Bearer` header.
Unset (default) preserves the notification-only path.

## Watchdog

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_CODE_TELEGRAMMER_SESSION` | `claude-code-telegrammer` | GNU Screen session name |
| `CLAUDE_CODE_TELEGRAMMER_WATCHDOG_INTERVAL` | `1.5` | Poll interval (seconds) |
| `CLAUDE_CODE_TELEGRAMMER_RESP_Y_N` | `1` | Response for y/n prompts |
| `CLAUDE_CODE_TELEGRAMMER_RESP_Y_Y_N` | `2` | Response for y/y/n prompts |
| `CLAUDE_CODE_TELEGRAMMER_RESP_WAITING` | `/speak-and-call` | Response when idle/waiting |

See [architecture](architecture.md#tui-watchdog-state-detection) for the detection patterns.
