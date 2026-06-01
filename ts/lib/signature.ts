/**
 * Agent signature appended to every outbound Telegram message.
 *
 * Format (operator-confirmed 2026-06-01):
 *
 *   — <label> (<full-workdir-path>@<hostname>)
 *
 * Example:
 *
 *   — proj-scitex-agent-container (/home/ywatanabe/proj/scitex-agent-container@ywata-note-win)
 *
 * Single trailing line so the operator can tell which agent / which host /
 * which checkout each message came from when multiple SDK-runner agents (or
 * the lead's own bot) share one Telegram chat. Applies to ALL bots — no
 * exemption for the lead's interactive CLI; uniform signing keeps the
 * surface predictable.
 *
 * Inputs are resolved at module-load time in config.ts:
 *   - AGENT_ID   = $CLAUDE_CODE_TELEGRAMMER_TELEGRAM_AGENT_ID   || "telegram"
 *   - PROJECT    = $CLAUDE_CODE_TELEGRAMMER_TELEGRAM_PROJECT    || process.cwd()
 *   - HOST_NAME  = $CLAUDE_CODE_TELEGRAMMER_TELEGRAM_HOST_NAME  || os.hostname()
 *
 * `process.cwd()` resolves to the bridge's working directory, which is the
 * same as the spawning process's cwd. The MCP server is spawned by the
 * agent / CLI it serves, so it inherits the agent's full workdir path. The
 * operator's required "<full-workdir-path>" is therefore directly available
 * — no extra resolution path is needed.
 *
 * Signing is idempotent: text that already ends with the EXACT current
 * signature is returned unchanged. This protects against:
 *   - long messages split into multiple sendMessage chunks (we sign once
 *     BEFORE splitting; the splitter naturally keeps the signature on the
 *     tail chunk).
 *   - editMessageText callsites where the existing message text already
 *     carried the signature and the agent re-edits.
 *   - accidental re-signing in tests / by upstream callers.
 */

import { AGENT_ID, PROJECT, HOST_NAME } from "./config.js";

/** Leading marker for the signature line. */
const SIGNATURE_PREFIX = "— ";

/**
 * Build the signature line for this process. Pure function of the three
 * config constants — no side effects, no I/O.
 */
export function buildSignature(): string {
  return `${SIGNATURE_PREFIX}${AGENT_ID} (${PROJECT}@${HOST_NAME})`;
}

/**
 * True iff `text` already ends with the EXACT current signature (trailing
 * whitespace / newlines tolerated). Strict match — only our exact format
 * counts. Manual / hand-written signatures with a different shape do NOT
 * suppress auto-signing; the operator will see both, which is the safer
 * failure mode (visible duplication vs. silent mis-attribution).
 */
export function isSigned(text: string): boolean {
  return text.trimEnd().endsWith(buildSignature());
}

/**
 * Append the agent signature to `text` as a single trailing line, separated
 * from the body by a blank line. Idempotent — returns `text` unchanged if
 * it already ends with the exact current signature. Empty input is signed
 * without a leading separator.
 */
export function appendSignature(text: string): string {
  if (isSigned(text)) return text;
  const sig = buildSignature();
  if (text.length === 0) return sig;
  return `${text}\n\n${sig}`;
}
