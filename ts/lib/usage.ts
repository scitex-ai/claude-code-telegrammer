/**
 * Per-account quota-reset reader (#14 copy refinement, 2026-06-07).
 *
 * Reads ~/.scitex/agent-container/accounts/<acct>/usage.json (path
 * resolved through usageJsonPath() in config.ts) and returns the
 * earliest pending reset between the 5h and 7d quota walls. Loud-fail
 * (lib/loudfail.ts) uses this to render
 *
 *     "⚠️ <agent> unavailable: <5h|7d> quota cap — retry after HH:MM"
 *
 * Format flexibility: reset_at_5h / reset_at_7d accept ANY of:
 *   - Epoch seconds (number, e.g. 1717000000)
 *   - Epoch ms     (number, e.g. 1717000000000) — auto-detected by
 *                  magnitude (any value > 1e12 is treated as ms)
 *   - ISO-8601 string (e.g. "2026-06-07T14:30:00Z" / "2026-06-07T14:30")
 *
 * Returns null on any failure (missing file, EACCES, malformed JSON,
 * neither field present, both fields un-parseable) — graceful
 * degradation; loud-fail falls back to "after the quota resets".
 */

import { readFileSync } from "fs";
import { usageJsonPath } from "./config.js";

/** Discriminates which quota wall is firing. */
export type QuotaVariant = "5h" | "7d";

export interface QuotaReset {
  variant: QuotaVariant;
  resetAt: Date;
}

/**
 * Parse a single `reset_at_*` value into a Date. Accepts:
 *   - number   → epoch seconds (or ms if > 1e12)
 *   - string   → ISO-8601 (Date.parse)
 * Returns null on any failure (NaN, unparseable string, negative/zero).
 */
export function parseResetAt(raw: unknown): Date | null {
  if (raw == null) return null;
  if (typeof raw === "number") {
    if (!Number.isFinite(raw) || raw <= 0) return null;
    // Heuristic: values above 1e12 are ms-since-epoch (≈ year 2001 in
    // ms vs year 33658 in seconds — safe separator). Values below are
    // seconds. Either way we end up with ms for the Date constructor.
    const ms = raw > 1e12 ? raw : raw * 1000;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  if (typeof raw === "string") {
    const t = Date.parse(raw);
    if (Number.isNaN(t)) return null;
    return new Date(t);
  }
  return null;
}

/**
 * Read the per-account usage.json and return the SOONER of the two
 * reset times (whichever wall hits first is the one the operator
 * will see lift first). null on any failure.
 */
export function readQuotaReset(): QuotaReset | null {
  const path = usageJsonPath();
  if (!path) return null;

  let raw: string;
  try {
    raw = readFileSync(path, "utf-8");
  } catch {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }

  if (!parsed || typeof parsed !== "object") return null;
  const obj = parsed as Record<string, unknown>;

  const r5 = parseResetAt(obj.reset_at_5h);
  const r7 = parseResetAt(obj.reset_at_7d);

  if (r5 === null && r7 === null) return null;
  if (r5 !== null && r7 === null) return { variant: "5h", resetAt: r5 };
  if (r5 === null && r7 !== null) return { variant: "7d", resetAt: r7 };
  // Both present — pick the SOONER. Equal-time edge case picks 5h.
  return r5!.getTime() <= r7!.getTime()
    ? { variant: "5h", resetAt: r5! }
    : { variant: "7d", resetAt: r7! };
}

/**
 * Render a Date as "HH:MM" in local time (the operator's host time
 * zone — usage.json is host-written so local time is the natural
 * frame). Zero-padded; 24h clock; no seconds.
 *
 * Lead's example: "retry after 14:30" — so "HH:MM" is the wire format.
 */
export function formatResetTime(d: Date): string {
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}
