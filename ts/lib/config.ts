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
// Automatic two-stage read-receipt reactions on inbound operator messages:
//   ⚡  ("delivered") — set the moment the relay receives + persists the message
//   👀 ("read")      — set when the message is surfaced into the Claude session
//
// Both emojis are on Telegram's fixed reaction whitelist. Telegram keeps only
// the latest bot reaction, so ⚡→👀 is a visible transition.
//
// Enabled by default. Set CLAUDE_CODE_TELEGRAMMER_TELEGRAM_READ_RECEIPTS to
// any of 0/false/no/off (case-insensitive) to disable without a code change.
export const READ_RECEIPTS_ENABLED: boolean = !["0", "false", "no", "off"].includes(
  (process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_READ_RECEIPTS ?? "").trim().toLowerCase(),
);

export const RECEIPT_DELIVERED_EMOJI = "⚡"; // ⚡
export const RECEIPT_READ_EMOJI = "👀"; // 👀

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
