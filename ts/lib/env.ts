/**
 * Single source of truth for reading claude-code-telegrammer env vars.
 *
 * Mirrors SAC's `SAC_` / `SCITEX_AGENT_CONTAINER_` helper
 * (scitex_agent_container/_env.py): every telegrammer-owned var has more than
 * one accepted spelling, and reads go through `getenv()` instead of bare
 * `process.env` so whichever spelling the operator used is honoured.
 *
 *   CCT_<SUFFIX>                              short alias  (preferred — cleanest)
 *   CLAUDE_CODE_TELEGRAMMER_<SUFFIX>          canonical / long form
 *   CLAUDE_CODE_TELEGRAMMER_TELEGRAM_<SUFFIX> legacy (deprecated, back-compat —
 *                                             the old redundant "…_TELEGRAM_…"
 *                                             spelling; "telegrammer" already
 *                                             implies telegram)
 *
 * Reading via a legacy CLAUDE_CODE_TELEGRAMMER_TELEGRAM_* name still works but
 * logs a one-time deprecation warning nudging migration to CCT_<KEY>.
 *
 * Precedence: CCT_ (short) › CLAUDE_CODE_TELEGRAMMER_ (canonical) › legacy.
 * The two CURRENT spellings (short ↔ canonical) are aliases of one setting, so
 * if both are set and DISAGREE `getenv()` throws — that drift is a templating
 * bug and silently preferring one is worse than failing fast. The legacy form
 * is always OVERRIDABLE by a current one (warn, never throw): the per-project
 * `.envrc` model deliberately sets CCT_<KEY> to override an ambient legacy
 * base value, so a current↔legacy mismatch is expected, not an error.
 *
 * Foreign vars (CLAUDE_AGENT_ACCOUNT, etc.) keep using `process.env` directly.
 */

import { log } from "./log.js";

export const LONG_PREFIX = "CLAUDE_CODE_TELEGRAMMER_";
export const SHORT_PREFIX = "CCT_";
export const LEGACY_PREFIX = "CLAUDE_CODE_TELEGRAMMER_TELEGRAM_";

// Prefixes that introduce a telegrammer-owned variable, for callers that scan
// the whole environment (e.g. the unexpanded-${...} guard in config.ts).
// LONG_PREFIX also covers LEGACY_PREFIX, which begins with it.
export const READ_PREFIXES = [SHORT_PREFIX, LONG_PREFIX] as const;

/** Raised when two alias spellings of the same var are set to different values. */
export class TelegrammerEnvConflict extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TelegrammerEnvConflict";
  }
}

// Legacy var names already warned about — dedup so the deprecation nudge fires
// once per distinct var in a process, not on every getenv() read.
const _warnedLegacy = new Set<string>();

/**
 * Read a telegrammer-owned env var by SUFFIX; any accepted spelling resolves.
 *
 * Behaves like `process.env[name] ?? default` but reads `CCT_<suffix>`,
 * `CLAUDE_CODE_TELEGRAMMER_<suffix>` and the legacy
 * `CLAUDE_CODE_TELEGRAMMER_TELEGRAM_<suffix>`, returning whichever is set.
 * Throws `TelegrammerEnvConflict` if two forms are set with different values.
 * Using the legacy spelling logs a one-time deprecation warning.
 *
 * An EMPTY-string value (`""`) for ANY spelling is treated as ABSENT (same as
 * unset) — a per-agent `.envrc` that folds an unresolved secret may export
 * `CCT_BOT_TOKEN=""`, and an empty short form must never SHADOW a real value in
 * the canonical or legacy spelling (root cause of a fleet-wide dead-poller
 * outage). Empty short + real long is therefore NOT a conflict, and an empty
 * legacy var fires no deprecation warning.
 *
 * @param suffix  Variable name WITHOUT prefix, e.g. `"BOT_TOKEN"`.
 * @param fallback Returned when no form is set (default `undefined`).
 * @param env     Environment to read (defaults to `process.env`; injectable
 *                for tests).
 * @param warn    Optional sink for the deprecation warning (injectable for
 *                tests); when omitted the warning is logged once per var.
 */
export function getenv(
  suffix: string,
  fallback?: string,
  env: Record<string, string | undefined> = process.env,
  warn?: (message: string) => void,
): string | undefined {
  const shortName = SHORT_PREFIX + suffix;
  const longName = LONG_PREFIX + suffix;
  const legacyName = LEGACY_PREFIX + suffix;
  // An empty string is treated as ABSENT for every spelling: a folded but
  // unresolved per-agent secret can export `CCT_<KEY>=""`, and that empty value
  // must never shadow a real value in another spelling, nor count as a conflict.
  const absent = (v: string | undefined): string | undefined =>
    v === "" ? undefined : v;
  const shortVal = absent(env[shortName]);
  const longVal = absent(env[longName]);
  const legacyVal = absent(env[legacyName]);

  // The two CURRENT spellings (CCT_ short ↔ CLAUDE_CODE_TELEGRAMMER_ canonical)
  // are aliases of one setting; if both are set and DISAGREE that is a
  // templating bug → fail loud (no silent pick).
  if (shortVal !== undefined && longVal !== undefined && shortVal !== longVal) {
    throw new TelegrammerEnvConflict(
      `Conflicting telegrammer env vars: ${shortName}=${JSON.stringify(shortVal)} vs ` +
        `${longName}=${JSON.stringify(longVal)}. These are aliases of the same setting ` +
        `and must agree (or set only one). Check ~/.bashrc, the agent's spec.env, and ` +
        `.mcp.json.`,
    );
  }
  const current = shortVal !== undefined ? shortVal : longVal; // short wins

  // The legacy spelling is DEPRECATED but still honoured, and is always
  // OVERRIDABLE by a current form (no throw) — the per-project .envrc override
  // sets CCT_<KEY> to beat an ambient legacy base value. Nudge migration; say
  // it is ignored when a current form wins.
  if (legacyVal !== undefined) {
    const overridden = current !== undefined && current !== legacyVal;
    const message = overridden
      ? `${legacyName} is deprecated and IGNORED — ${shortName} overrides it; ` +
        `remove the legacy var.`
      : `${legacyName} is deprecated — rename it to ${shortName} ` +
        `(or ${longName}); the legacy spelling still works for now.`;
    if (warn) {
      warn(message);
    } else if (!_warnedLegacy.has(legacyName)) {
      _warnedLegacy.add(legacyName);
      log("env", message, { var: legacyName });
    }
  }

  if (current !== undefined) return current;
  if (legacyVal !== undefined) return legacyVal;
  return fallback;
}

/**
 * Return the two forward-going spellings for a suffix (short, canonical).
 * Useful for error messages and tests. The legacy form is intentionally not
 * advertised here — it is accepted by `getenv()` but deprecated.
 */
export function aliases(suffix: string): [string, string] {
  return [SHORT_PREFIX + suffix, LONG_PREFIX + suffix];
}
