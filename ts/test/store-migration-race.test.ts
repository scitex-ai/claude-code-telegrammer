/**
 * Regression test: store.ts::ensureColumn's migration TOCTOU
 * (adversarial-review finding #1, follow-up to the poller/MCP-server
 * decoupling PR).
 *
 * ensureColumn (the ALTER TABLE ADD COLUMN forward_json migration, run
 * unconditionally by every initStore() call since the column is
 * deliberately kept OUT of CREATE TABLE — see store.ts) reads
 * PRAGMA table_info then conditionally ALTERs: a classic check-then-act
 * race. Two processes racing it on a genuinely FRESH (not yet migrated)
 * DB — the realistic case is an MCP server and its freshly-spawned
 * standalone poller both calling initStore() around the same moment on a
 * brand-new state dir — the loser hits `SQLiteError: duplicate column
 * name`, a LOGICAL error, not a lock error, so busy_timeout does nothing
 * for it. Because this throw happens SYNCHRONOUSLY inside initStore() at
 * the poller's top level (no try/catch there), and JS cannot resume
 * top-level execution after an uncaught exception, startPolling() would
 * never run — the poller goes silently inert (not even a crash — the
 * global uncaughtException handler only logs) before ever polling, and
 * nothing notices (ensurePollerRunning's fire-and-forget spawn never
 * checks back).
 *
 * REPRODUCTION NOTE: racing two processes through the FULL initStore()
 * sequence (WAL-mode switch, several CREATE TABLE/INDEX statements, the
 * schema_version INSERT OR IGNORE, THEN ensureColumn) empirically almost
 * never collides — those preceding statements' own lock contention +
 * busy_timeout retries tend to desynchronize the two processes well
 * before either reaches the actual 2-statement race window, verified
 * empirically at 0/20 reproductions. Isolating the race to JUST the
 * ensureColumn call against an already-existing (but not yet migrated)
 * db file — removing that preceding noise — reproduces the exact
 * `duplicate column name` error reliably (~45% per single attempt,
 * verified empirically). This test races ensureColumn directly (via
 * fixtures/ensure-column-race-fixture.ts) in a loop of independent
 * attempts against fresh DBs, so the overall test has a near-certain
 * (>99.9%, 1-0.55^10) chance of exercising the race at least once even
 * though any SINGLE attempt is probabilistic.
 */

import { describe, test, expect } from "bun:test";
import { mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { Database } from "bun:sqlite";

const FIXTURE = join(
  import.meta.dir,
  "fixtures",
  "ensure-column-race-fixture.ts",
);
const ATTEMPTS = 10;

interface AttemptResult {
  exit1: number;
  exit2: number;
  stderr1: string;
  stderr2: string;
}

async function raceOnce(): Promise<AttemptResult> {
  const dir = mkdtempSync(join(tmpdir(), "cct-ensurecol-"));
  try {
    const dbPath = join(dir, "race-test.db");
    // Minimal pre-existing "messages" table WITHOUT forward_json — the
    // exact precondition ensureColumn's migration exists to handle. Only
    // the column presence matters to ensureColumn; the rest of the real
    // schema is irrelevant to this specific race.
    const setupDb = new Database(dbPath, { create: true });
    setupDb.exec(
      "PRAGMA journal_mode = WAL; CREATE TABLE messages (id INTEGER PRIMARY KEY);",
    );
    setupDb.close();

    const startAt = Date.now() + 100;
    const spawnWorker = (workerId: string) =>
      Bun.spawn(
        [process.execPath, "run", FIXTURE, workerId, dbPath, String(startAt)],
        { stdout: "pipe", stderr: "pipe" },
      );

    const w1 = spawnWorker("1");
    const w2 = spawnWorker("2");

    const [exit1, exit2, stderr1, stderr2] = await Promise.all([
      w1.exited,
      w2.exited,
      new Response(w1.stderr as ReadableStream).text(),
      new Response(w2.stderr as ReadableStream).text(),
    ]);
    return { exit1, exit2, stderr1, stderr2 };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

describe("store.ts::ensureColumn — multi-process migration race", () => {
  test(`${ATTEMPTS} independent two-process race attempts against fresh DBs never surface duplicate-column-name`, async () => {
    const results: AttemptResult[] = [];
    for (let i = 0; i < ATTEMPTS; i++) {
      results.push(await raceOnce());
    }

    const failures = results
      .map((r, i) => ({ i, ...r }))
      .filter((r) => r.exit1 !== 0 || r.exit2 !== 0);

    expect(
      failures,
      `${failures.length}/${ATTEMPTS} attempts failed:\n` +
        failures
          .map(
            (f) =>
              `  attempt ${f.i}: exit1=${f.exit1} exit2=${f.exit2}\n    stderr1=${f.stderr1.trim()}\n    stderr2=${f.stderr2.trim()}`,
          )
          .join("\n"),
    ).toEqual([]);
  }, 30_000);
});
