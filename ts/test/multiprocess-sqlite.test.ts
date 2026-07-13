/**
 * Genuine multi-process SQLite concurrency test.
 *
 * Explicitly called out in the architecture-fix task (incident-cct-inbound-
 * dies-silently-with-mcp-server-20260711 follow-up, 2026-07): once the
 * poller and the MCP server are two independent OS processes sharing one
 * SQLite file (lib/store.ts, WAL + busy_timeout=5000 — see SCHEMA_SQL), the
 * "many independent handles against one WAL-mode file" pattern this
 * codebase already relies on (lib/attachments.ts::getDb(),
 * lib/health-adapters.ts::probeDb(), lib/wake-health.ts) needed to be
 * verified for REAL, genuinely concurrent writers across PROCESS
 * boundaries — not just concurrent async calls within one process, which
 * is all any existing test exercised. This spawns two REAL separate `bun`
 * processes (ts/test/fixtures/concurrent-writer-fixture.ts) that both call
 * initStore() and write to the SAME db file concurrently, then asserts no
 * corruption / lock errors and every row from both workers survived.
 */

import { describe, test, expect } from "bun:test";
import { mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { Database } from "bun:sqlite";

const FIXTURE = join(
  import.meta.dir,
  "fixtures",
  "concurrent-writer-fixture.ts",
);
const ROWS_PER_WORKER = 50;

describe("multi-process concurrent writers against the shared WAL-mode store", () => {
  test("two real bun processes writing concurrently produce zero corruption / lock errors and every row lands", async () => {
    const stateDir = mkdtempSync(join(tmpdir(), "cct-mp-sqlite-"));
    try {
      const spawnWorker = (workerId: string) =>
        Bun.spawn(
          [process.execPath, "run", FIXTURE, workerId, String(ROWS_PER_WORKER)],
          {
            env: {
              ...process.env,
              CLAUDE_CODE_TELEGRAMMER_AGENT_STATE_DIR: stateDir,
            },
            stdout: "pipe",
            stderr: "pipe",
          },
        );

      // Spawn BOTH before awaiting either — this is the whole point:
      // genuinely overlapping, concurrent writers, not sequential ones.
      const w1 = spawnWorker("1");
      const w2 = spawnWorker("2");

      const [exit1, exit2, stdout1, stdout2, stderr1, stderr2] =
        await Promise.all([
          w1.exited,
          w2.exited,
          new Response(w1.stdout as ReadableStream).text(),
          new Response(w2.stdout as ReadableStream).text(),
          new Response(w1.stderr as ReadableStream).text(),
          new Response(w2.stderr as ReadableStream).text(),
        ]);

      // Both workers must exit 0. stderr is NOT expected to be empty — the
      // fixture's own initStore() call logs a normal, benign
      // `{"component":"store","msg":"initialized at ..."}` line there (see
      // lib/log.ts: "Structured JSON logging to stderr" is this codebase's
      // deliberate convention, stdout stays reserved for MCP stdio /
      // CLI-probe JSON). Any SQLITE_BUSY / "database is locked" /
      // corruption error would instead surface as an UNCAUGHT exception
      // (the fixture does not catch saveInbound errors) — a non-zero exit
      // code AND a stack trace on stderr, neither of which is present here.
      const errorIndicators =
        /SQLITE_BUSY|database is locked|Uncaught|unhandled|corrupt/i;
      expect(exit1).toBe(0);
      expect(stderr1).not.toMatch(errorIndicators);
      expect(exit2).toBe(0);
      expect(stderr2).not.toMatch(errorIndicators);
      expect(stdout1).toContain(`worker 1 wrote ${ROWS_PER_WORKER} rows`);
      expect(stdout2).toContain(`worker 2 wrote ${ROWS_PER_WORKER} rows`);

      // Open the SAME db file with a THIRD, independent handle — the
      // exact "many independent handles against one WAL-mode file" shape
      // the real MCP-server + poller processes use — and verify
      // integrity plus full row survival from BOTH workers.
      const dbPath = join(stateDir, "claude-code-telegrammer.db");
      const db = new Database(dbPath, { readonly: true });
      try {
        const integrity = db.prepare("PRAGMA integrity_check").get() as {
          integrity_check: string;
        };
        expect(integrity.integrity_check).toBe("ok");

        const total = db
          .prepare(
            "SELECT COUNT(*) as n FROM messages WHERE chat_id = 'concurrency-test'",
          )
          .get() as { n: number };
        expect(total.n).toBe(ROWS_PER_WORKER * 2);

        const perWorker = db
          .prepare(
            `SELECT user_id, COUNT(*) as n FROM messages
               WHERE chat_id = 'concurrency-test'
               GROUP BY user_id ORDER BY user_id`,
          )
          .all() as Array<{ user_id: string; n: number }>;
        expect(perWorker).toEqual([
          { user_id: "1", n: ROWS_PER_WORKER },
          { user_id: "2", n: ROWS_PER_WORKER },
        ]);

        // No duplicate/collided message_ids — every row from both
        // workers is distinct and present.
        const distinctMessageIds = db
          .prepare(
            "SELECT COUNT(DISTINCT message_id) as n FROM messages WHERE chat_id = 'concurrency-test'",
          )
          .get() as { n: number };
        expect(distinctMessageIds.n).toBe(ROWS_PER_WORKER * 2);
      } finally {
        db.close();
      }
    } finally {
      rmSync(stateDir, { recursive: true, force: true });
    }
  }, 30_000); // generous timeout: two real bun process spawns + 100 real SQLite writes
});
