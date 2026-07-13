#!/usr/bin/env bun
/**
 * Fixture for ts/test/store-migration-race.test.ts (adversarial-review
 * finding #1). Races ONLY store.ts::ensureColumn itself against an
 * ALREADY-EXISTING (but not yet migrated) db file — deliberately isolated
 * from the rest of initStore()'s schema-creation statements, which
 * otherwise tend to serialize/desynchronize two racing processes well
 * before they ever reach the actual check-then-act window, making the
 * narrow race hard to trigger via realistic full-initStore() timing.
 *
 * Usage: bun run ensure-column-race-fixture.ts <workerId> <dbPath> <startAtEpochMs>
 */

import { Database } from "bun:sqlite";
import { ensureColumn } from "../../lib/store.js";

const [, , workerId, dbPath, startAtArg] = process.argv;
const startAt = Number(startAtArg);

const db = new Database(dbPath);
db.exec("PRAGMA busy_timeout = 5000;");

while (Date.now() < startAt) {
  // deliberate short-lived busy-wait — synchronizes sibling processes
}

try {
  ensureColumn(db, "messages", "forward_json", "TEXT");
  process.stdout.write(`worker ${workerId} ensureColumn ok\n`);
  process.exit(0);
} catch (err) {
  process.stderr.write(
    `worker ${workerId} FAILED: ${err instanceof Error ? err.message : String(err)}\n`,
  );
  process.exit(1);
} finally {
  db.close();
}
