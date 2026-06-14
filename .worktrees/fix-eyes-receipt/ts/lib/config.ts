/**
 * Configuration and constants for the Telegram MCP server.
 */

import { homedir, hostname } from "os";
import { join } from "path";

export const STATE_DIR =
  process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_STATE_DIR ??
  join(homedir(), ".claude-code-telegrammer");

export const ACCESS_FILE = join(STATE_DIR, "access.json");
export const LOCK_FILE = join(STATE_DIR, "claude-code-telegrammer-mcp.lock");
export const INBOX_DIR = join(STATE_DIR, "inbox");
export const ATTACHMENT_DIR =
  process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_ATTACHMENT_DIR ??
  join(STATE_DIR, "attachments");

export const TOKEN =
  process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_BOT_TOKEN ?? "";
export const API_BASE = `https://api.telegram.org/bot${TOKEN}`;
export const MAX_TEXT = 4096;

export const ENV_ALLOWED = (
  process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_ALLOWED_USERS ?? ""
)
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

// ── Read receipts ──────────────────────────────────────────────────────────
//
// Automatic four-stage read-receipt reactions on inbound operator messages.
// Single reaction per message that ADVANCES through stages (Telegram replaces
// the bot's reaction on each setMessageReaction call; non-premium bots are
// capped at 1 reaction/message per the Bot API):
//
//   Stage 1  ⚡  delivered — bridge received the Telegram message (and POSTed
//                            it to the agent's /v1/turn if configured)
//   Stage 2  👀 received   — /v1/turn POST returned 2xx in SDK-runner mode
//                            (the agent runner accepted the message). In
//                            interactive-CLI mode (no TURN_URL), set when
//                            the MCP <channel> notification ack returns.
//   Stage 3  ✅ done       — agent finished processing the turn / produced
//                            its reply. Under current scitex-agent-container
//                            this collapses to the same wakeTurn ok=true
//                            instant as stage 2 (sac /v1/turn is case B:
//                            HTTP 200 returns AFTER turn completes). The
//                            design fires 👀 then ✅ in sequence so it stays
//                            forward-compatible if sac later splits the
//                            signals (enqueue-ack vs completed-turn).
//   Stage 4  ❌ failed     — failure (agent down / 401 / connection refused /
//                            timeout / non-2xx). Final visible state until
//                            the operator retries.
//
// All four emojis are on Telegram's fixed reaction whitelist.
//
// Enabled by default. Set CLAUDE_CODE_TELEGRAMMER_TELEGRAM_READ_RECEIPTS to
// any of 0/false/no/off (case-insensitive) to disable without a code change.
export const READ_RECEIPTS_ENABLED: boolean = !["0", "false", "no", "off"].includes(
  (process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_READ_RECEIPTS ?? "").trim().toLowerCase(),
);

export const RECEIPT_DELIVERED_EMOJI = "⚡"; // stage 1
export const RECEIPT_READ_EMOJI = "👀"; // stage 2 (a.k.a. "received")
export const RECEIPT_DONE_EMOJI = "✅"; // stage 3 (turn completed)
export const RECEIPT_FAILED_EMOJI = "❌"; // stage 4 (failure)

// ── Wake-on-push (idle SDK-runner sessions) ─────────────────────────────────
//
// Inbound delivery via `notifications/claude/channel` renders a <channel> tag
// for an ACTIVE turn, but does NOT advance an IDLE session — the standard
// Claude Code CLI has a live event loop that picks it up, but an SDK-runner
// session (e.g. a scitex-agent-container apptainer agent) is parked on its
// inbox queue and never sees the notification.
//
// When TURN_URL is set, each qualifying inbound message is additionally
// POSTed to that endpoint (the agent's own /v1/turn) so the runner enqueues
// it onto the persistent SDK conversation and drives a turn at once — push
// behaves like the lead's interactive Telegram channel. Unset (the default)
// preserves the notification-only path for the interactive CLI.
//
// This mirrors scitex-agent-container's `sac mcp channel --turn-url` wake
// primitive (runtimes/_mcp/_channel_wake.py::_wake_turn).
export const TURN_URL =
  process.env.CLAUDE_CODE_TELEGRAMMER_TURN_URL ?? "";
// Optional bearer for the /v1/turn POST (sent as Authorization: Bearer ...).
export const TURN_BEARER =
  process.env.CLAUDE_CODE_TELEGRAMMER_TURN_BEARER ?? "";

// ── Agent identity ─────────────────────────────────────────────────────────

export const HOST_NAME =
  process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_HOST_NAME ?? hostname();
export const PROJECT =
  process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_PROJECT ?? process.cwd();
export const AGENT_ID =
  process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_AGENT_ID ?? "telegram";

export const BOT_TOKEN_HASH: string = TOKEN
  ? new Bun.CryptoHasher("sha256").update(TOKEN).digest("hex").slice(0, 8)
  : "";
