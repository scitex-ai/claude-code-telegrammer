/**
 * Schema-migration helpers for lib/store.ts. Extracted to its own module to
 * keep store.ts under this repo's per-file line cap (the same "extract for
 * the line cap" pattern already used for lib/handle-update.ts /
 * lib/poller-batch.ts / lib/tools-messages.ts).
 */

import type { Database } from "bun:sqlite";
import { log } from "./log.js";

/**
 * Idempotent ALTER TABLE ADD COLUMN.
 *
 * SQLite's CREATE TABLE IF NOT EXISTS does NOT update existing tables when
 * columns are added to the schema, so store.ts::initStore() calls this on
 * every startup to bring older databases forward without dropping data.
 *
 * Also tolerates the multi-process TOCTOU race between the table_info read
 * and the ALTER below (adversarial-review finding #1, follow-up to the
 * poller/MCP-server decoupling PR): two fresh processes migrating the SAME
 * brand-new db concurrently (the realistic case — an MCP server and its
 * freshly-spawned standalone poller both calling initStore() around the
 * same moment) can both observe the column absent, then both attempt the
 * ALTER; the loser hits `SQLiteError: duplicate column name` — a LOGICAL
 * error, not a lock error, so store.ts's busy_timeout fix does nothing for
 * it. That throw used to propagate out of initStore() synchronously; since
 * JS cannot resume top-level execution after an uncaught exception, a
 * poller process hitting this would go silently inert before ever calling
 * startPolling() (see ts/telegram-poller.ts) — nothing would notice.
 * "duplicate column name" is therefore treated as a benign, expected
 * outcome of LOSING this race (the column exists either way — the other
 * process's migration already did the job), not a fatal error. Reproduced
 * empirically and regression-guarded by
 * ts/test/store-migration-race.test.ts.
 */
export function ensureColumn(
  database: Database,
  table: string,
  column: string,
  decl: string,
): void {
  const cols = database.prepare(`PRAGMA table_info(${table})`).all() as Array<{
    name: string;
  }>;
  if (cols.some((c) => c.name === column)) return;
  try {
    database.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${decl}`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (!msg.includes("duplicate column")) throw err;
    log(
      "store",
      `ensureColumn: lost the race adding ${table}.${column} — another ` +
        `process already added it concurrently; treating as success`,
    );
  }
}
