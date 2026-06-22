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

// Inbound-message channel source label. MUST equal the MCP server name
// registered in telegram-server.ts ("claude-code-telegrammer") so the agent's
// pane attributes every inbound stimulus to the EXACT channel that delivered
// it (``← claude-code-telegrammer · <user>: …``) and can reply through that
// same named MCP. The generic platform label "telegram" hid which integration
// the message arrived through — an attribution/provenance violation.
export const CHANNEL_SOURCE = "claude-code-telegrammer";
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

// ── Unexpanded-env guard ────────────────────────────────────────────────────
//
// Detect CLAUDE_CODE_TELEGRAMMER_* env vars whose value still contains a
// literal "${...}" — i.e. an unexpanded placeholder. The launchers declare the
// telegrammer env via "${SCITEX_LEAD_TELEGRAM_*}" (lead .mcp.json) and resolve
// it from the shell at MCP-launch. When the launcher starts without its backing
// .env sourced — e.g. a Claude resume that bypasses claude.sh — those shell
// vars are unset, so Claude Code passes the LITERAL "${SCITEX_LEAD_TELEGRAM_*}"
// string through. Unchecked, STATE_DIR becomes that literal (a relative path)
// and lib/lock.ts mkdir's a junk dir literally named "${...}" under the poller
// cwd, while TOKEN becomes a literal → every Telegram Bot API call 404s (a
// silent comms outage). This detector lets startup fail LOUD instead. Returns
// the offending "NAME=value" lines (empty array when all good). See the
// 2026-06-12 incident note for the full failure cascade.
export function findUnexpandedEnv(): string[] {
  return Object.entries(process.env)
    .filter(
      ([name, value]) =>
        name.startsWith("CLAUDE_CODE_TELEGRAMMER_") &&
        typeof value === "string" &&
        value.includes("${"),
    )
    .map(([name, value]) => `${name}=${value}`);
}

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
export const READ_RECEIPTS_ENABLED: boolean = ![
  "0",
  "false",
  "no",
  "off",
].includes(
  (process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_READ_RECEIPTS ?? "")
    .trim()
    .toLowerCase(),
);

export const RECEIPT_DELIVERED_EMOJI = "⚡"; // stage 1
export const RECEIPT_READ_EMOJI = "👀"; // stage 2 (a.k.a. "received")
export const RECEIPT_DONE_EMOJI = "✅"; // stage 3 (turn completed)
export const RECEIPT_FAILED_EMOJI = "❌"; // stage 4 (failure)

// ── Loud-fail outbound reply (#14, 2026-06-07) ──────────────────────────────
//
// When wakeTurn fails (agent down / 401 / quota-capped / timeout / 5xx),
// the bridge posts an outbound Telegram reply to the operator explaining
// the failure, so silence is impossible: every inbound either gets a
// reply from the agent (success) or a loud-fail reply from the bridge
// (failure). The reply text is:
//
//   "⚠️ <agent_id> unavailable: <reason> — retry <when>"
//
// (rendered by lib/loudfail.ts::buildLoudFailMessage with the matching
// WakeFailCategory). Posted via tgApi("sendMessage") with
// reply_parameters pointing back to the inbound, so the operator's
// thread stays coherent. Each inbound (chat_id, message_id) gets at
// most one loud-fail reply per process lifetime (sentLoudFailReplies
// dedup set).
//
// Enabled by default. Set CLAUDE_CODE_TELEGRAMMER_TELEGRAM_LOUD_FAIL
// to any of 0/false/no/off (case-insensitive) to suppress the outbound
// reply without a code change (the ❌ receipt still fires; only the
// text message is suppressed).
export function isLoudFailEnabled(): boolean {
  const v = (process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_LOUD_FAIL ?? "")
    .trim()
    .toLowerCase();
  return !["0", "false", "no", "off"].includes(v);
}

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
export const TURN_URL = process.env.CLAUDE_CODE_TELEGRAMMER_TURN_URL ?? "";
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

// ── Outbound signature toggle + account-quota enrichment ───────────────────
//
// The outbound-agent-signature feature (PR #18) unconditionally appends a
// trailing line `— <agent> (<cwd>@<hostname>)` to every Telegram message so a
// human (and downstream parsers) can attribute a message to a specific
// agent/host/checkout. Two follow-ups operator-requested 2026-06-02:
//
//   1. Kill-switch — sometimes the operator wants a clean message body (for
//      example when another layer is also signing, to avoid double-signing).
//      A single env flag toggles the entire append off. Mirrors the
//      READ_RECEIPTS_ENABLED pattern.
//
//   2. Account + remaining quota — the human-facing line should also show
//      WHICH Claude account is talking and HOW MUCH 5h / 7d quota that
//      account has left. Operator's wire example:
//          — lead (wyusuuke 5h:9 percent 7d:2 percent | /work@ywata-note-win)
//      Data lives in <quotaCachePath()>/quota-cache.json — a host cron
//      refreshes the file every 10 min, so we re-read on every send. The
//      cwd@host suffix from PR #18 is preserved as a `|`-separated tail so
//      we keep BOTH signals on one line (single append, no double-signing).
//
// Both behaviours are runtime-toggleable via env — buildSignature() /
// appendSignature() consult these getters on every call, not module load,
// so the operator can flip a flag without restarting the bridge. This is
// also why the existing module-load constants (AGENT_ID/PROJECT/HOST_NAME)
// stay as-is: identity is fixed for the lifetime of a bun process, but
// signature ON/OFF + the quota numbers genuinely change at runtime.

/**
 * Returns true iff the outbound text signature should be appended. Opt-IN
 * (task #82): default OFF. Enable by setting
 * CLAUDE_CODE_TELEGRAMMER_TELEGRAM_SIGNATURE to one of `1|true|yes|on`
 * (case-insensitive, trimmed). Any other value (including unset, empty
 * string, `0`, `off`) leaves the signature OFF. The auto text-signature is
 * abolished in favour of the /status command; the audio signature stays.
 */
export function isSignatureEnabled(): boolean {
  const v = (process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_SIGNATURE ?? "")
    .trim()
    .toLowerCase();
  return ["1", "true", "yes", "on"].includes(v);
}

/**
 * Path to the host-maintained quota-cache.json. Defaults to the operator-
 * specified canonical location `/home/ywatanabe/.scitex/quota-cache.json`
 * (host cron writes there every 10 min). Override with
 * CLAUDE_CODE_TELEGRAMMER_TELEGRAM_QUOTA_CACHE_PATH — primarily for tests
 * that point at a fixture file.
 */
export function quotaCachePath(): string {
  return (
    process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_QUOTA_CACHE_PATH ??
    "/home/ywatanabe/.scitex/quota-cache.json"
  );
}

/**
 * Path to the per-account usage.json the host writes after each turn
 * completes. Operator-specified canonical location (2026-06-07):
 *   ~/.scitex/agent-container/accounts/<acct>/usage.json
 *
 * Distinct from quota-cache.json (which is a single host-wide file with
 * percentages): usage.json carries ABSOLUTE reset timestamps (epoch
 * seconds OR ISO-8601 strings) under the keys `reset_at_5h` and
 * `reset_at_7d` — used by lib/loudfail.ts to render
 * "⚠️ <agent> unavailable: 5h quota cap — retry after HH:MM" so the
 * operator sees when the quota wall actually lifts.
 *
 * Override with CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH —
 * primarily for tests pointing at a fixture file. When the override is
 * unset, accountDirname() supplies the <acct> segment; an empty
 * accountDirname yields an empty path → the reader returns null
 * (loud-fail falls back to "after the quota resets").
 */
export function usageJsonPath(): string {
  const override = process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_USAGE_JSON_PATH;
  if (override) return override;
  const acct = accountDirname();
  if (!acct) return "";
  return `${homedir()}/.scitex/agent-container/accounts/${acct}/usage.json`;
}

/**
 * Account directory-name for THIS bridge (e.g. `wyusuuke-gmail-com`,
 * `ywatanabe-scitex-ai`). Used to look up the matching entry in
 * quota-cache.json — we match by the `short` field, which is the email
 * local-part (first dash-segment of the dirname).
 *
 * Resolution order:
 *   1. CLAUDE_CODE_TELEGRAMMER_TELEGRAM_ACCOUNT — telegrammer-scoped
 *      override (lead-host use, or tests).
 *   2. CLAUDE_AGENT_ACCOUNT — injected by SAC into every agent container
 *      (see scitex-agent-container `config/_loaders.py`).
 *   3. "" — empty means "no account known"; the signature gracefully
 *      omits the enriched parenthetical and falls back to the
 *      `(cwd@host)` form that PR #18 shipped.
 */
export function accountDirname(): string {
  return (
    process.env.CLAUDE_CODE_TELEGRAMMER_TELEGRAM_ACCOUNT ??
    process.env.CLAUDE_AGENT_ACCOUNT ??
    ""
  );
}
