/**
 * One-time, startup-safe migration of the telegrammer state directory from the
 * OLD default location to the scitex-standard DEFAULT
 * (~/.scitex/claude-code-telegrammer/runtime/<agent-id>).
 *
 * WHY: an operator-declared incident — an agent's Telegram history GAPPED
 * because its DB path drifted across container restarts, so a fresh empty DB
 * opened at a new path and lost history. Making the default resolve
 * deterministically from the agent id eliminates the drift by construction
 * (see config.ts::resolveStateDir), but the switch MUST carry the existing
 * history forward — that is what this module does, once, at startup.
 *
 * DESIGN (data safety is paramount — this moves the operator's real history):
 *   - COPY, never move. The legacy dir is left intact as a backup.
 *   - Copy the SQLite trio together (db + -wal + -shm) so an un-checkpointed
 *     WAL is not lost, plus attachments/ and access.json when present.
 *   - Write a marker so it runs exactly once and a re-run is a no-op.
 *   - FAIL LOUD: if any copy step throws, do NOT write the marker and rethrow.
 *     A half-migration must be visible, never silently masked by a fresh DB.
 *   - CROSS-CONTAMINATION GUARD: a suffixed agent must NEVER read the bare
 *     ~/.claude-code-telegrammer dir (that is the lead/"telegram" bot's data).
 *     resolveOldDefaultDir mirrors the OLD default logic exactly, so only the
 *     "telegram"/default agent ever points at the bare dir.
 *
 * No-op when: the new DB already exists, OR the old DB is absent, OR an explicit
 * AGENT_STATE_DIR is set (that dir IS the state dir — nothing to migrate).
 */

import { homedir } from "os";
import { join } from "path";
import {
  existsSync,
  mkdirSync,
  copyFileSync,
  cpSync,
  writeFileSync,
  symlinkSync,
} from "fs";
import { getenv } from "./env.js";
import { resolveStateDir, sanitizeAgentSegment } from "./config.js";
import { log as defaultLog } from "./log.js";

const NEW_DB = "claude-code-telegrammer.db";
const OLD_DB = "messages.db";
const MARKER_NEW = ".migrated-from"; // written in the NEW dir (authoritative)
const MARKER_OLD = ".migrated-to"; // written in the OLD dir (best-effort)

// SQLite sidecars copied ALONGSIDE the main DB so an un-checkpointed WAL (and
// its shared-memory index) travel with the base file — copying the .db alone
// could drop the newest not-yet-checkpointed writes.
const DB_SIDECARS = ["-wal", "-shm"] as const;

type LogFn = (
  component: string,
  msg: string,
  data?: Record<string, unknown>,
) => void;

export interface MigrateOptions {
  /** Environment to read (defaults to process.env; injectable for tests). */
  env?: Record<string, string | undefined>;
  /** Home directory (defaults to os.homedir(); injectable for tests). */
  home?: string;
  /** NEW state dir override (defaults to resolveStateDir(env)); tests point at a temp dir. */
  newDir?: string;
  /** OLD default dir override (defaults to resolveOldDefaultDir(env, home)). */
  oldDir?: string | null;
  /** Timestamp stamped into the markers (defaults to now); injectable for tests. */
  now?: Date;
  /** Single-file copy primitive (defaults to fs.copyFileSync); injectable to test fail-loud. */
  copyFile?: (src: string, dst: string) => void;
  /** Recursive dir copy primitive (defaults to fs.cpSync). */
  copyDir?: (src: string, dst: string) => void;
  /** Log sink (defaults to lib/log.ts::log). */
  logFn?: LogFn;
}

export interface MigrateResult {
  migrated: boolean;
  /** Why migration ran or was skipped — for logs/tests. */
  reason:
    | "migrated"
    | "explicit-state-dir"
    | "new-db-exists"
    | "old-db-absent"
    | "already-migrated";
  newDir: string;
  oldDir: string | null;
}

/**
 * Compute THIS agent's OWN OLD DEFAULT dir — exactly what the OLD default
 * resolution returned before the scitex-standard switch. Returns null when an
 * explicit AGENT_STATE_DIR is set (there is no legacy default to migrate from).
 *
 * The bare ~/.claude-code-telegrammer is reserved for the "telegram"/default
 * agent; a suffixed agent resolves to ~/.claude-code-telegrammer-<id> and must
 * NEVER read the bare dir (that belongs to the lead bot). This mirror is the
 * cross-contamination guard.
 */
export function resolveOldDefaultDir(
  env: Record<string, string | undefined> = process.env,
  home: string = homedir(),
): string | null {
  if (getenv("AGENT_STATE_DIR", undefined, env)) return null;
  const base = join(home, ".claude-code-telegrammer");
  const agentId = getenv("AGENT_ID", undefined, env);
  if (agentId && agentId !== "telegram") {
    return `${base}-${sanitizeAgentSegment(agentId)}`;
  }
  return base;
}

/**
 * Run the one-time legacy → scitex-standard state-dir migration. Idempotent and
 * safe to call unconditionally at startup BEFORE the store opens. See the module
 * header for the full contract. Returns a structured result; throws (fail loud)
 * only if a copy step fails mid-migration.
 */
export function migrateLegacyStateDir(
  opts: MigrateOptions = {},
): MigrateResult {
  const env = opts.env ?? process.env;
  const home = opts.home ?? homedir();
  const log = opts.logFn ?? defaultLog;
  const copyFile = opts.copyFile ?? copyFileSync;
  const copyDir =
    opts.copyDir ??
    ((s: string, d: string) => cpSync(s, d, { recursive: true }));

  const newDir = opts.newDir ?? resolveStateDir(env);
  const oldDir =
    opts.oldDir !== undefined ? opts.oldDir : resolveOldDefaultDir(env, home);

  // Explicit AGENT_STATE_DIR → that dir IS the state dir; nothing to migrate.
  if (oldDir === null || getenv("AGENT_STATE_DIR", undefined, env)) {
    return { migrated: false, reason: "explicit-state-dir", newDir, oldDir };
  }

  const newDb = join(newDir, NEW_DB);
  const oldDb = join(oldDir, OLD_DB);

  // Already on the new path (or a previous migration completed) → no-op.
  if (existsSync(newDb)) {
    return { migrated: false, reason: "new-db-exists", newDir, oldDir };
  }
  if (existsSync(join(newDir, MARKER_NEW))) {
    return { migrated: false, reason: "already-migrated", newDir, oldDir };
  }
  // Nothing to carry forward.
  if (!existsSync(oldDb)) {
    return { migrated: false, reason: "old-db-absent", newDir, oldDir };
  }

  log("migrate-state", "migrating legacy telegrammer state forward", {
    from: oldDir,
    to: newDir,
  });

  mkdirSync(newDir, { recursive: true });

  // Copy phase — any failure here rethrows WITHOUT writing a marker, so a
  // half-migration is visible and the operator never sees a silent fresh DB.
  try {
    copyFile(oldDb, newDb);
    for (const suffix of DB_SIDECARS) {
      const src = oldDb + suffix;
      if (existsSync(src)) copyFile(src, newDb + suffix);
    }
    const oldAttachments = join(oldDir, "attachments");
    if (existsSync(oldAttachments)) {
      copyDir(oldAttachments, join(newDir, "attachments"));
    }
    const oldAccess = join(oldDir, "access.json");
    if (existsSync(oldAccess)) {
      copyFile(oldAccess, join(newDir, "access.json"));
    }
  } catch (err) {
    log("migrate-state", "MIGRATION FAILED — leaving legacy state untouched", {
      from: oldDir,
      to: newDir,
      error: String(err),
    });
    throw err;
  }

  // Markers — the new-dir marker is authoritative (idempotency also holds via
  // the newDb-exists check above); the old-dir marker is best-effort.
  const at = (opts.now ?? new Date()).toISOString();
  writeFileSync(
    join(newDir, MARKER_NEW),
    JSON.stringify({ from: oldDir, at }) + "\n",
  );
  try {
    writeFileSync(
      join(oldDir, MARKER_OLD),
      JSON.stringify({ to: newDir, at }) + "\n",
    );
  } catch (err) {
    // The legacy dir may be read-only; the new-dir marker already records the
    // completed migration, so this is non-fatal.
    log("migrate-state", "could not stamp legacy-dir marker (non-fatal)", {
      dir: oldDir,
      error: String(err),
    });
  }

  log("migrate-state", "migration complete — history carried forward", {
    from: oldDir,
    to: newDir,
  });

  return { migrated: true, reason: "migrated", newDir, oldDir };
}

/**
 * PART 3 (best-effort convenience): ensure ~/.scitex/cct → claude-code-telegrammer
 * so the runtime tree has a short alias. NEVER throws — wrapped in try/catch and
 * logged on failure. A no-op when the alias already exists.
 */
export function ensureCctAlias(
  home: string = homedir(),
  logFn: LogFn = defaultLog,
): void {
  try {
    const scitex = join(home, ".scitex");
    const alias = join(scitex, "cct");
    if (!existsSync(scitex)) return; // don't create ~/.scitex just for the alias
    if (existsSync(alias)) return;
    // Relative target so the symlink stays valid if ~/.scitex moves.
    symlinkSync("claude-code-telegrammer", alias);
    logFn("migrate-state", "created convenience alias ~/.scitex/cct", {
      alias,
    });
  } catch (err) {
    logFn("migrate-state", "could not create ~/.scitex/cct alias (non-fatal)", {
      error: String(err),
    });
  }
}
