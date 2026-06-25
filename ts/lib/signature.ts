/**
 * Agent signature appended to every outbound Telegram message.
 *
 * Format — two shapes, chosen at SEND time depending on whether an
 * account+quota entry is available for this bridge:
 *
 *   ENRICHED (account known, quota-cache.json readable):
 *     — <agent> (<short> 5h:<int> percent 7d:<int> percent | <cwd>@<host>)
 *
 *   FALLBACK (no account or quota-cache unreadable — PR #18 original shape):
 *     — <agent> (<cwd>@<host>)
 *
 * Examples:
 *
 *   — lead (wyusuuke 5h:17 percent 7d:3 percent | /work@ywata-note-win)
 *   — proj-scitex-agent-container (/work@ywata-note-win)
 *
 * Single trailing line so the operator can tell which agent / which
 * account+quota / which host / which checkout each message came from when
 * multiple SDK-runner agents (or the lead's own bot) share one Telegram chat.
 *
 * Account + quota inputs (read on EVERY send so quota stays live —
 * the host cron refreshes quota-cache.json every 10 min):
 *   - accountDirname()  resolves to the account dir-name (e.g.
 *                       `wyusuuke-gmail-com`), via
 *                       CLAUDE_CODE_TELEGRAMMER_ACCOUNT then
 *                       CLAUDE_AGENT_ACCOUNT.
 *   - quotaCachePath()  default `/home/ywatanabe/.scitex/quota-cache.json`.
 *   - The lookup matches by the `short` field == first dash-segment of
 *     accountDirname() (i.e. the email local-part). This avoids fragile
 *     hyphen-to-dot heuristics on the domain side.
 *
 * Identity inputs (resolved at module-load time in config.ts):
 *   - AGENT_ID   = $CLAUDE_CODE_TELEGRAMMER_AGENT_ID   || "telegram"
 *   - PROJECT    = $CLAUDE_CODE_TELEGRAMMER_PROJECT    || process.cwd()
 *   - HOST_NAME  = $CLAUDE_CODE_TELEGRAMMER_HOST_NAME  || os.hostname()
 *
 * Opt-IN toggle (task #82): `appendSignature()` is a no-op UNLESS
 * isSignatureEnabled() returns true (env
 * CLAUDE_CODE_TELEGRAMMER_SIGNATURE = 1/true/yes/on). Default is
 * OFF — auto text-signature is abolished; /status replaces it and the
 * audio signature stays. The toggle is consulted at SEND time, not module
 * load, so a flip takes effect without restarting the bridge.
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

import { readFileSync } from "fs";
import {
  AGENT_ID,
  PROJECT,
  HOST_NAME,
  isSignatureEnabled,
  quotaCachePath,
  accountDirname,
} from "./config.js";

/** Leading marker for the signature line. */
const SIGNATURE_PREFIX = "— ";

/**
 * Wire shape of `quota-cache.json` — host cron writes:
 *
 *   {
 *     "written_at": <epoch float>,
 *     "accounts": {
 *       "<email>": { "short": "<name>", "h5": <pct>, "d7": <pct>, "ttl_h": <hours> }
 *     }
 *   }
 *
 * We only consume the per-account entry; `written_at` is informational and
 * does NOT gate use of the cache (stale-quota is better than no-quota; the
 * operator wants the line to ALWAYS show a number when one exists).
 */
export interface QuotaEntry {
  short: string;
  h5: number;
  d7: number;
  ttl_h: number;
}
interface QuotaCacheShape {
  written_at?: number;
  accounts?: Record<string, QuotaEntry>;
}

/**
 * Resolve the quota entry for THIS bridge's account from quota-cache.json,
 * or null if the file is missing, unreadable, malformed, or has no entry
 * whose `short` field matches the first dash-segment of accountDirname().
 *
 * NEVER throws — every failure mode (missing file, EACCES, JSON parse
 * error, shape mismatch, no matching account) collapses to `null` so the
 * caller can fall back to the PR #18 cwd@host signature. The operator's
 * explicit guidance: graceful degradation, no surprises.
 */
export function readQuotaEntry(): QuotaEntry | null {
  const dirname = accountDirname();
  if (!dirname) return null;

  const shortName = dirname.split("-")[0];
  if (!shortName) return null;

  let raw: string;
  try {
    raw = readFileSync(quotaCachePath(), "utf-8");
  } catch {
    return null;
  }

  let parsed: QuotaCacheShape;
  try {
    parsed = JSON.parse(raw) as QuotaCacheShape;
  } catch {
    return null;
  }

  const accts = parsed?.accounts;
  if (!accts || typeof accts !== "object") return null;

  for (const v of Object.values(accts)) {
    if (
      v &&
      typeof v === "object" &&
      typeof v.short === "string" &&
      v.short === shortName &&
      typeof v.h5 === "number" &&
      typeof v.d7 === "number" &&
      typeof v.ttl_h === "number"
    ) {
      return { short: v.short, h5: v.h5, d7: v.d7, ttl_h: v.ttl_h };
    }
  }
  return null;
}

/**
 * Build the signature line for this process. Pure function of the three
 * identity constants + an at-call-time read of quota-cache.json. No side
 * effects beyond a single best-effort file read (graceful fallback on any
 * failure).
 *
 * Returns the ENRICHED form when an account+quota entry is available, the
 * PR #18 fallback form otherwise. Percentages are rounded to integers
 * (operator's example used integer percent values, e.g. `5h:9`).
 */
export function buildSignature(): string {
  const quota = readQuotaEntry();
  if (quota) {
    const five = Math.round(quota.h5);
    const seven = Math.round(quota.d7);
    return `${SIGNATURE_PREFIX}${AGENT_ID} (${quota.short} 5h:${five} percent 7d:${seven} percent | ${PROJECT}@${HOST_NAME})`;
  }
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
 * from the body by a blank line.
 *
 * No-op when isSignatureEnabled() is false — the kill-switch returns `text`
 * verbatim so callers (e.g. sendMessage / sendDocument / editMessageText)
 * stay unchanged and a single env flip toggles ALL outbound signing.
 *
 * Idempotent when the signature IS enabled: already-signed text passes
 * through unchanged. Empty input is signed without a leading separator.
 */
export function appendSignature(text: string): string {
  if (!isSignatureEnabled()) return text;
  if (isSigned(text)) return text;
  const sig = buildSignature();
  if (text.length === 0) return sig;
  return `${text}\n\n${sig}`;
}
