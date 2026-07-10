/**
 * Health check ("doctor") — report shape, injected-probe types, and assembly.
 *
 * Contract (SHARED across sac / scitex-todo / claude-code-telegrammer — the
 * operator's standard health-checker per infra package; do not deviate):
 *
 *   { "package": "claude-code-telegrammer",
 *     "ok": bool,                      // AND of all non-warn checks
 *     "checks": [ { "name", "ok", "detail", "hint" } ],
 *     "summary": str }
 *
 *   - Every FAILING check carries an actionable `hint` naming the exact env
 *     var / file / fix. Passing checks have hint null (except explicit
 *     warn-style nudges like env_legacy, whose spec mandates a hint).
 *   - No silent pass: every check appears in the array with a real `detail`.
 *   - "Status as hints, fail-loud, no silent fallback" (operator directive,
 *     card cct-health-doctor-mcp-tool-20260702).
 *
 * Everything in this module (and lib/health-checks.ts, which holds the ten
 * individual check builders) is PURE — no network, no filesystem, no process
 * inspection. All probes are injected as plain data (`HealthInputs`), gathered
 * by the thin adapters in lib/health-adapters.ts. That keeps every branch unit
 * -testable under `bun test` without mocking fetch/fs (same split as
 * lib/startup-validate.ts).
 *
 * WARN-style checks (excluded from the top-level `ok` AND):
 *   - bot_token_present when the token is ABSENT: telegram is DISABLED by
 *     design (universal channel in every agent spec) — the entry reports
 *     ok:false with the buildDisabledWarning() hint, but a deliberately
 *     tokenless agent must not read as unhealthy.
 *   - env_legacy: deprecated spellings still work; nudge, don't fail.
 * When the token is absent, the telegram-dependent checks (bot_token_valid,
 * webhook_absent, poller_alive, allowlist_nonempty) are emitted as
 * skipped-with-ok:true — the disabled state is already flagged loudly by
 * bot_token_present, and double-failing would make the honest disabled state
 * look broken.
 */

import type { TokenCheck, AccessGatingInput } from "./startup-validate.js";
import {
  checkEnvUnexpanded,
  checkEnvRenamed,
  checkBotTokenPresent,
  checkBotTokenValid,
  checkWebhookAbsent,
  checkPollerAlive,
  checkAllowlistNonempty,
  checkStateDirWritable,
  checkDbSchemaCurrent,
  checkEnvLegacy,
  type CheckOutcome,
} from "./health-checks.js";

// Re-export the builders + skip marker so callers/tests have one import surface.
export * from "./health-checks.js";

// ── Report shape (shared contract) ──────────────────────────────────────────

export interface HealthCheckEntry {
  name: string;
  ok: boolean;
  detail: string;
  hint: string | null;
}

export interface HealthReport {
  package: "claude-code-telegrammer";
  ok: boolean;
  checks: HealthCheckEntry[];
  summary: string;
}

// ── Injected probe inputs ────────────────────────────────────────────────────

/** Raw getWebhookInfo outcome, gathered by the adapter (never the raw token). */
export type WebhookProbe =
  | {
      kind: "response";
      ok: boolean;
      /** result.url — empty string means "no webhook set". */
      url: string;
      error_code?: number;
      description?: string;
    }
  | { kind: "transport_error"; detail: string };

/**
 * Poller-liveness probe. "self" is the MCP-tool variant: the health tool runs
 * INSIDE the server process, and that process IS the poller — no pidfile
 * round-trip needed. "external" is the CLI variant: a fresh probe process
 * reads the state dir's lock file + per-token pidfile (lib/takeover.ts format)
 * and checks the recorded PID via process.kill(pid, 0) — NOT `ps -p`, because
 * PID-namespace boundaries (apptainer vs host) make `ps -p` lie while kill-0
 * survives them.
 */
export type PollerProbe =
  | { kind: "self"; pid: number }
  | {
      kind: "external";
      lockPid: number | null;
      lockAlive: boolean;
      pidfilePid: number | null;
      pidfileAlive: boolean;
      pidfilePath: string;
    };

export interface StateDirProbe {
  path: string;
  exists: boolean;
  /** exists=true → dir itself is writable; exists=false → dir is CREATABLE
   *  (nearest existing ancestor is writable). */
  writable: boolean;
  /** fs error detail on failure. */
  detail?: string;
}

export type DbProbe =
  | { exists: false }
  | { exists: true; error: string }
  | {
      exists: true;
      error?: undefined;
      schemaVersion: string | null;
      updateOffset: number | null;
      /** MAX(update_id) extracted from stored inbound raw_json; null when no
       *  inbound rows carry one. */
      maxUpdateId: number | null;
      inboundCount: number;
    };

/** Everything buildHealthReport needs, as plain injected data. */
export interface HealthInputs {
  agentId: string;
  stateDir: string;
  tokenPresent: boolean;
  /** findUnexpandedEnv() lines ("NAME=value" with a literal ${...}). */
  unexpandedEnvLines: string[];
  /** findRenamedEnv() lines (already actionable "OLD was renamed to NEW…"). */
  renamedEnvLines: string[];
  /** Names of deprecated CLAUDE_CODE_TELEGRAMMER_TELEGRAM_* vars still set. */
  legacyEnvNames: string[];
  /** validateBotToken(getMeRaw) result; null ⇔ skipped (no token). */
  tokenCheck: TokenCheck | null;
  /** getWebhookInfo probe; null ⇔ skipped (no token). */
  webhook: WebhookProbe | null;
  /** Poller-liveness probe; null ⇔ skipped (no token → poller never starts). */
  poller: PollerProbe | null;
  /** describeAccessGating() inputs; null ⇔ skipped (no token). */
  access: AccessGatingInput | null;
  stateDirProbe: StateDirProbe;
  db: DbProbe;
}

// ── Report assembly ─────────────────────────────────────────────────────────

/**
 * Assemble the full HealthReport from injected inputs. Pure and synchronous —
 * every network/fs probe already happened in the adapter layer.
 */
export function buildHealthReport(inputs: HealthInputs): HealthReport {
  const outcomes: CheckOutcome[] = [
    checkEnvUnexpanded(inputs.unexpandedEnvLines),
    checkEnvRenamed(inputs.renamedEnvLines),
    checkBotTokenPresent(inputs.tokenPresent, inputs.agentId),
    checkBotTokenValid(inputs.tokenCheck),
    checkWebhookAbsent(inputs.webhook),
    checkPollerAlive(inputs.poller),
    checkAllowlistNonempty(inputs.access),
    checkStateDirWritable(inputs.stateDirProbe),
    checkDbSchemaCurrent(inputs.db),
    checkEnvLegacy(inputs.legacyEnvNames),
  ];

  const checks = outcomes.map((o) => o.entry);
  // Top-level ok = AND of all NON-warn checks (shared contract). Warn-style
  // entries (tokenless bot_token_present, env_legacy nudge) are visible in
  // `checks` but never flip the aggregate.
  const failing = outcomes
    .filter((o) => !o.warn && !o.entry.ok)
    .map((o) => o.entry.name);
  const warned = outcomes
    .filter((o) => o.warn && (o.entry.hint !== null || !o.entry.ok))
    .map((o) => o.entry.name);
  const ok = failing.length === 0;

  const passed = checks.filter((c) => c.ok).length;
  const parts = [`${passed}/${checks.length} checks ok`];
  if (failing.length > 0) parts.push(`FAILING: ${failing.join(", ")}`);
  if (warned.length > 0) parts.push(`warnings: ${warned.join(", ")}`);

  return {
    package: "claude-code-telegrammer",
    ok,
    checks,
    summary: parts.join("; "),
  };
}
