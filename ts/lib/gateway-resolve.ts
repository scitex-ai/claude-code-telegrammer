/**
 * Gateway token/slot self-resolution for the host-level supervisor
 * (ts/gateway-supervisor.ts).
 *
 * WHY THIS FILE EXISTS (plan cct-standalone-supervision, 2026-10-09): the
 * poller is today a child of agent boot — zero agents up means zero
 * pollers, by construction. The host-level supervisor must resolve the
 * gateway bot's token WITHOUT any agent lifecycle, mirroring the READ side
 * of SAC's `_cct_token_pool` precedence (slot `LEAD` → `CCT_BOT_TOKEN_LEAD`
 * from `SAC_SECRETS_ENVRC` files + environment). SAC stays the consumer;
 * this module never writes secrets anywhere, only reads.
 *
 * Precedence (first non-empty value wins):
 *   1. Direct token — `getenv("BOT_TOKEN")`, i.e. `CCT_BOT_TOKEN` ›
 *      `CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN` › legacy. Same rule as
 *      lib/config.ts `TOKEN`, so a directly-configured token behaves
 *      identically under the supervisor and under agent boot.
 *   2. Pool slot via environment — `CCT_BOT_TOKEN_<SLOT>` already exported
 *      (e.g. folded by an `.envrc`), where SLOT defaults to `LEAD` and is
 *      overridable via `CCT_BOT_TOKEN_SLOT`.
 *   3. Pool slot via secret files — the same `CCT_BOT_TOKEN_<SLOT>` key read
 *      out of the `SAC_SECRETS_ENVRC` colon-separated files, falling back to
 *      the canonical `$HOME/.bash.d/secrets/010_scitex/*.src` default (the
 *      2026-07-18 class fix in SAC `_envrc.resolve_secret_files`, mirrored
 *      here so a unit started without the var still finds the pool).
 *
 * LOGGING CONTRACT (same as SAC `_cct_token_resolution`): the resolution
 * carries slot NAMES and pool source PATHS only. The token VALUE never
 * appears in a log line; callers compare rotations by fingerprint.
 */

import { existsSync, readFileSync, readdirSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { getenv } from "./env.js";

/** Which precedence step produced the token. Operator-facing, safe to log. */
export type GatewayTokenSource = "direct" | "pool-env" | "pool-file";

/**
 * A resolved gateway token. `token` is the VALUE (never log it);
 * every other field is names/paths and safe to log.
 */
export interface GatewayTokenResolution {
  token: string;
  /** Pool slot that resolved (`LEAD` default); "" when source is direct. */
  slot: string;
  source: GatewayTokenSource;
  /** Secret-file paths consulted (may be empty when env sufficed). */
  poolPaths: string[];
  /**
   * False when NO secret file resolved, mirroring SAC `PoolRead.trusted`:
   * a miss against pure process env is INCONCLUSIVE (the pool file may
   * exist on this host, intact, and simply not be visible), never evidence
   * the slot is absent.
   */
  poolTrusted: boolean;
}

/** Slot override var, same spelling SAC specs declare. */
export const SLOT_VAR_SUFFIX = "BOT_TOKEN_SLOT";
/** Pool key prefix, same as SAC `_cct_token_pool._POOL_PREFIX`. */
export const POOL_PREFIX = "CCT_BOT_TOKEN_";
/** Name of the env var listing colon-separated secret files. */
export const SECRETS_ENVRC_VAR = "SAC_SECRETS_ENVRC";
/** Default gateway slot (the single human-facing bot). */
export const DEFAULT_SLOT = "LEAD";

/** File reader seam: tests inject a fake FS instead of touching disk. */
export type FileReader = (path: string) => string | null;

/** Directory lister seam for the canonical-default glob. */
export type DirLister = (dir: string) => string[];

function defaultReadFile(path: string): string | null {
  try {
    if (!existsSync(path)) return null;
    return readFileSync(path, "utf8");
  } catch {
    return null;
  }
}

function defaultListDir(dir: string): string[] {
  try {
    return readdirSync(dir);
  } catch {
    return [];
  }
}

/**
 * Resolve the secret files to consult, mirroring SAC
 * `_envrc.resolve_secret_files`:
 *   1. Explicit non-empty `SAC_SECRETS_ENVRC` wins verbatim (colon-separated,
 *      existing files only).
 *   2. Otherwise the canonical `$HOME/.bash.d/secrets/010_scitex/*.src`
 *      default (sorted, existing only).
 */
export function resolveSecretFiles(
  env: Record<string, string | undefined> = process.env,
  readFile: FileReader = defaultReadFile,
  listDir: DirLister = defaultListDir,
): string[] {
  const raw = (env[SECRETS_ENVRC_VAR] ?? "").trim();
  if (raw) {
    return raw
      .split(":")
      .map((p) => p.trim())
      .filter((p) => p.length > 0 && readFile(p) !== null);
  }
  const home = env["HOME"]?.trim() || homedir();
  const dir = join(home, ".bash.d", "secrets", "010_scitex");
  return listDir(dir)
    .filter((name) => name.endsWith(".src"))
    .sort()
    .map((name) => join(dir, name))
    .filter((p) => readFile(p) !== null);
}

/**
 * Parse a `KEY=VALUE`-per-line env file (the secrets-fold format): blank
 * lines and `#` comments tolerated, no shell semantics — same rule as SAC
 * `_secret_pool._read_env_file`.
 */
export function parseEnvFile(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of body.split("\n")) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    if (!key) continue;
    out[key] = line.slice(eq + 1).trim();
  }
  return out;
}

/**
 * Resolve the gateway token. Returns null when nothing resolves (caller
 * fails loud: log slot names + pool paths, back off, never run degraded).
 *
 * `getenv("BOT_TOKEN")` may throw `TelegrammerEnvConflict` when the short
 * and canonical spellings disagree — that propagates: a templating bug must
 * fail fast, not pick silently (lib/env.ts contract).
 */
export function resolveGatewayToken(
  env: Record<string, string | undefined> = process.env,
  readFile: FileReader = defaultReadFile,
  listDir: DirLister = defaultListDir,
): GatewayTokenResolution | null {
  // 1. Direct token — identical precedence to lib/config.ts TOKEN.
  const direct = getenv("BOT_TOKEN", undefined, env);
  if (direct) {
    return {
      token: direct,
      slot: "",
      source: "direct",
      poolPaths: [],
      poolTrusted: true,
    };
  }

  // 2./3. Pool slot. The SLOT override itself honours the alias spellings
  // (CCT_BOT_TOKEN_SLOT › CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN_SLOT).
  const slot = (
    getenv(SLOT_VAR_SUFFIX, undefined, env) ??
    env["CCT_BOT_TOKEN_SLOT"] ??
    DEFAULT_SLOT
  )
    .trim()
    .toUpperCase();
  const poolKey = `${POOL_PREFIX}${slot || DEFAULT_SLOT}`;
  const resolvedSlot = slot || DEFAULT_SLOT;

  const fromEnv = (env[poolKey] ?? "").trim();
  if (fromEnv) {
    return {
      token: fromEnv,
      slot: resolvedSlot,
      source: "pool-env",
      poolPaths: [],
      poolTrusted: true,
    };
  }

  const poolPaths = resolveSecretFiles(env, readFile, listDir);
  for (const path of poolPaths) {
    const body = readFile(path);
    if (body === null) continue;
    const value = (parseEnvFile(body)[poolKey] ?? "").trim();
    if (value) {
      return {
        token: value,
        slot: resolvedSlot,
        source: "pool-file",
        poolPaths,
        poolTrusted: true,
      };
    }
  }

  // Nothing resolved (null: no token to carry, so no fingerprint, no
  // source). The caller re-runs resolveSecretFiles() for the fail-loud log
  // (slot names + pool paths, never values).
  return null;
}

/**
 * Opaque fingerprint of a token for logs/status/comparison — the same
 * sha256-first-8-hex as lib/config.ts `BOT_TOKEN_HASH`, so a supervisor
 * fingerprint and a poller hash for the SAME bot compare equal. Carries no
 * recoverable token material.
 */
export function tokenFingerprint(token: string): string {
  if (!token) return "";
  return new Bun.CryptoHasher("sha256").update(token).digest("hex").slice(0, 8);
}

/**
 * Crash-restart backoff (ms) for respawn attempt n (1-based): 2s doubling,
 * capped at 60s. Pure so the schedule is unit-testable; the supervisor loop
 * is the only caller.
 */
export function backoffForAttempt(attempt: number): number {
  const n = Math.max(1, Math.floor(attempt));
  return Math.min(2000 * 2 ** (n - 1), 60_000);
}
