/**
 * Health check ("doctor") — THIN adapters over the real fs / network / sqlite.
 *
 * All classification lives in the pure lib/health.ts + lib/health-checks.ts;
 * this module only GATHERS the raw inputs and hands them over:
 *
 *   runHealth({ poller: "self" | "external" }) → Promise<HealthReport>
 *
 *   - "self"     : the MCP-tool variant, running INSIDE the server process —
 *                  that process IS the poller, so poller_alive reports its own
 *                  pid instead of the lockfile/pidfile round-trip.
 *   - "external" : the CLI variant (`bun run ts/telegram-server.ts health`) —
 *                  a fresh probe process that reads the lock file and the
 *                  per-token pidfile and kill-0s the recorded PID.
 *
 * Token hygiene: the raw bot token must NEVER appear in health output. The
 * probes themselves only pass URLs/PIDs/counters, but transport-level fetch
 * errors can embed the request URL (which contains the token) — so every
 * probe string is passed through redactToken(), and serializeHealthReport()
 * applies it once more to the final JSON as a belt-and-braces guarantee.
 */

import {
  existsSync,
  accessSync,
  writeFileSync,
  unlinkSync,
  readFileSync,
  constants,
} from "fs";
import { join, dirname } from "path";
import { Database } from "bun:sqlite";
import {
  STATE_DIR,
  ACCESS_FILE,
  LOCK_FILE,
  ENV_ALLOWED,
  AGENT_ID,
  TOKEN,
  API_BASE,
  BOT_TOKEN_HASH,
  findUnexpandedEnv,
  findRenamedEnv,
} from "./config.js";
import { LEGACY_PREFIX } from "./env.js";
import { validateBotToken } from "./startup-validate.js";
import { getMeRaw } from "./telegram-api.js";
import { loadAccess } from "./access.js";
import { pollerPidfilePath, readPidfile, isPidAlive } from "./takeover.js";
import { DB_PATH } from "./store.js";
import {
  buildHealthReport,
  type HealthReport,
  type HealthInputs,
  type WebhookProbe,
  type PollerProbe,
  type StateDirProbe,
  type DbProbe,
} from "./health.js";

/**
 * Replace every occurrence of the raw bot token with the literal placeholder
 * `<TOKEN>`. No-op when no token is set. Applied to every probe string that
 * could carry a URL (fetch error messages embed the request URL, which
 * contains the token) AND to the final serialized report.
 */
export function redactToken(s: string, token: string = TOKEN): string {
  if (!token) return s;
  return s.split(token).join("<TOKEN>");
}

/** Serialize a report to pretty JSON with the token redaction belt applied. */
export function serializeHealthReport(report: HealthReport): string {
  return redactToken(JSON.stringify(report, null, 2));
}

// ── Individual probes ───────────────────────────────────────────────────────

/**
 * Raw getWebhookInfo — same raw-fetch style as getMeRaw() (lib/telegram-api):
 * returns the parsed Telegram envelope on ANY HTTP response so the pure check
 * can classify ok/transient itself; a transport-level fetch reject folds into
 * a transport_error probe (with the token redacted out of the message).
 */
export async function probeWebhook(): Promise<WebhookProbe> {
  try {
    const res = await fetch(`${API_BASE}/getWebhookInfo`, { method: "POST" });
    const json = (await res.json()) as {
      ok: boolean;
      result?: { url?: string };
      error_code?: number;
      description?: string;
    };
    if (json.ok) {
      return { kind: "response", ok: true, url: json.result?.url ?? "" };
    }
    return {
      kind: "response",
      ok: false,
      url: "",
      error_code: json.error_code,
      description: redactToken(json.description ?? ""),
    };
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return { kind: "transport_error", detail: redactToken(detail) };
  }
}

/**
 * Poller-liveness inputs. "self" short-circuits to our own pid (the MCP-tool
 * variant runs inside the server process, which IS the poller). "external"
 * reads the single-instance lock file + the per-token pidfile
 * (poller-<hash>.pid, lib/takeover.ts format) and kill-0s the recorded PIDs —
 * kill-0, not `ps -p`, because it survives PID-namespace boundaries.
 */
export function probePoller(mode: "self" | "external"): PollerProbe {
  if (mode === "self") return { kind: "self", pid: process.pid };

  let lockPid: number | null = null;
  try {
    const raw = parseInt(readFileSync(LOCK_FILE, "utf8").trim(), 10);
    if (Number.isFinite(raw) && raw > 0) lockPid = raw;
  } catch {
    lockPid = null; // missing/unreadable lock file — reported as "not recorded"
  }

  const pidfilePath = pollerPidfilePath(STATE_DIR, BOT_TOKEN_HASH);
  const snap = readPidfile(pidfilePath);
  const pidfilePid = snap?.pid ?? null;

  return {
    kind: "external",
    lockPid,
    lockAlive: lockPid !== null && isPidAlive(lockPid),
    pidfilePid,
    pidfileAlive: pidfilePid !== null && isPidAlive(pidfilePid),
    pidfilePath,
  };
}

/**
 * STATE_DIR existence/writability. When the dir exists: accessSync(W_OK) plus
 * a real create+unlink probe file (only inside an EXISTING dir — the probe
 * never mkdirs). When it does not exist: walk up to the nearest existing
 * ancestor and check that it is writable ("creatable").
 */
export function probeStateDir(dir: string = STATE_DIR): StateDirProbe {
  if (existsSync(dir)) {
    try {
      accessSync(dir, constants.W_OK);
      const probeFile = join(dir, `.health-probe-${process.pid}`);
      writeFileSync(probeFile, "ok");
      unlinkSync(probeFile);
      return { path: dir, exists: true, writable: true };
    } catch (err) {
      return {
        path: dir,
        exists: true,
        writable: false,
        detail: err instanceof Error ? err.message : String(err),
      };
    }
  }
  // Not created yet (first run) — find the nearest existing ancestor.
  let ancestor = dirname(dir);
  while (!existsSync(ancestor)) {
    const parent = dirname(ancestor);
    if (parent === ancestor) break;
    ancestor = parent;
  }
  try {
    accessSync(ancestor, constants.W_OK);
    return { path: dir, exists: false, writable: true };
  } catch (err) {
    return {
      path: dir,
      exists: false,
      writable: false,
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

/**
 * messages.db probe — READONLY open (never mutates; safe against the live
 * poller's WAL). Missing DB is a normal first-run state, reported as such.
 * The max stored update_id is extracted from inbound raw_json (the poller
 * persists the whole Telegram update, update_id included) so the pure check
 * can flag a poisoned meta.update_offset.
 */
export function probeDb(dbPath: string = DB_PATH): DbProbe {
  if (!existsSync(dbPath)) return { exists: false };
  let db: Database;
  try {
    db = new Database(dbPath, { readonly: true });
  } catch (err) {
    return {
      exists: true,
      error: err instanceof Error ? err.message : String(err),
    };
  }
  try {
    const ver = db
      .prepare("SELECT value FROM meta WHERE key = 'schema_version'")
      .get() as { value: string } | undefined;
    const off = db
      .prepare("SELECT value FROM meta WHERE key = 'update_offset'")
      .get() as { value: string } | undefined;
    const agg = db
      .prepare(
        "SELECT MAX(CAST(json_extract(raw_json, '$.update_id') AS INTEGER)) AS max_id, " +
          "COUNT(*) AS n FROM messages WHERE direction = 'inbound' AND raw_json IS NOT NULL",
      )
      .get() as { max_id: number | null; n: number };
    const parsedOffset = off ? parseInt(off.value, 10) : NaN;
    return {
      exists: true,
      schemaVersion: ver?.value ?? null,
      updateOffset: Number.isFinite(parsedOffset) ? parsedOffset : null,
      maxUpdateId: agg.max_id ?? null,
      inboundCount: agg.n,
    };
  } catch (err) {
    return {
      exists: true,
      error: err instanceof Error ? err.message : String(err),
    };
  } finally {
    db.close();
  }
}

/** Names of deprecated CLAUDE_CODE_TELEGRAMMER_TELEGRAM_* vars set (non-empty). */
export function probeLegacyEnv(
  env: Record<string, string | undefined> = process.env,
): string[] {
  return Object.keys(env)
    .filter((name) => name.startsWith(LEGACY_PREFIX) && env[name] !== "")
    .sort();
}

// ── Entry point ─────────────────────────────────────────────────────────────

/**
 * Gather every probe and build the report. Telegram-dependent probes
 * (getMe, getWebhookInfo, poller, access gating) are skipped (null inputs →
 * skipped-ok entries) when no token is set — the disabled state is already
 * flagged by bot_token_present, and without a token there is no bot, no
 * poller, and no DMs to gate.
 */
export async function runHealth(opts: {
  poller: "self" | "external";
}): Promise<HealthReport> {
  const tokenPresent = TOKEN.length > 0;

  let tokenCheck: HealthInputs["tokenCheck"] = null;
  let webhook: WebhookProbe | null = null;
  let poller: PollerProbe | null = null;
  let access: HealthInputs["access"] = null;
  if (tokenPresent) {
    [tokenCheck, webhook] = await Promise.all([
      validateBotToken(getMeRaw),
      probeWebhook(),
    ]);
    if (!tokenCheck.ok) {
      tokenCheck = { ...tokenCheck, message: redactToken(tokenCheck.message) };
    }
    poller = probePoller(opts.poller);
    access = {
      accessFileExists: existsSync(ACCESS_FILE),
      envAllowedCount: ENV_ALLOWED.length,
      dmPolicy: loadAccess().dmPolicy,
      accessFilePath: ACCESS_FILE,
    };
  }

  return buildHealthReport({
    agentId: AGENT_ID,
    stateDir: STATE_DIR,
    tokenPresent,
    unexpandedEnvLines: findUnexpandedEnv(),
    renamedEnvLines: findRenamedEnv(),
    legacyEnvNames: probeLegacyEnv(),
    tokenCheck,
    webhook,
    poller,
    access,
    stateDirProbe: probeStateDir(),
    db: probeDb(),
  });
}
