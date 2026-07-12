#!/usr/bin/env bun
/**
 * Fixture process for ts/test/multiprocess-sqlite.test.ts.
 *
 * NOT a test file itself (no `.test.` in the name — bun test's default file
 * discovery skips it) and not run directly by `bun test`; it is spawned as
 * a REAL, separate OS process by that test to exercise genuine multi-process
 * SQLite concurrency against lib/store.ts's schema (WAL + busy_timeout=5000).
 *
 * Usage: bun run concurrent-writer-fixture.ts <workerId> <count>
 * Env: CLAUDE_CODE_TELEGRAMMER_AGENT_STATE_DIR must already point at the
 * shared state dir when this process starts (set by the parent test via
 * Bun.spawn's `env` option) — STATE_DIR/DB_PATH are module-load-time
 * constants in lib/config.ts/lib/store.ts, resolved from that env var.
 *
 * Calls initStore() — the exact schema-init path every real poller / MCP-
 * server process uses — then performs `count` real saveInbound() calls
 * tagged with this workerId, each on its own message_id so no two workers'
 * rows collide on the (chat_id, message_id, direction) dedup unique index;
 * this test is about concurrent-write SAFETY, not dedup behaviour (already
 * covered elsewhere — ts/test/store.test.ts).
 */

import { initStore, saveInbound } from "../../lib/store.js";

const [, , workerIdArg, countArg] = process.argv;
const workerId = workerIdArg ?? "0";
const count = Number(countArg ?? "50");

initStore();

for (let i = 0; i < count; i++) {
  saveInbound({
    chat_id: "concurrency-test",
    message_id: `w${workerId}-${i}`,
    user_id: workerId,
    username: `worker${workerId}`,
    text: `message ${i} from worker ${workerId}`,
    telegram_ts: new Date().toISOString(),
    host: "test-host",
    project: "test-project",
    agent_id: `worker-${workerId}`,
    bot_token_hash: "testhash",
    raw_json: JSON.stringify({ worker: workerId, i }),
  });
}

process.stdout.write(`worker ${workerId} wrote ${count} rows\n`);
process.exit(0);
