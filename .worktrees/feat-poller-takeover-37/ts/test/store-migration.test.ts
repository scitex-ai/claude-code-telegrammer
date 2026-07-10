/**
 * Migration safety: confirm the forward_json column can be added to
 * a pre-existing (legacy-schema) messages table WITHOUT losing data,
 * and that the migration is idempotent across re-runs.
 *
 * Exercises the same ensureColumn helper initStore() uses on every
 * startup. No mocks — real bun:sqlite, real ALTER TABLE.
 */

import { describe, test, expect } from "bun:test";
import { Database } from "bun:sqlite";
import { join } from "path";
import { tmpdir } from "os";
import { mkdirSync } from "fs";
import { ensureColumn } from "../lib/store.js";

describe("ensureColumn migration helper", () => {
  test("adds forward_json TEXT to a legacy messages table and preserves data", () => {
    const dir = join(tmpdir(), `cct-mig-${process.pid}-${Date.now()}`);
    mkdirSync(dir, { recursive: true });
    const dbPath = join(dir, "messages.db");

    // 1) Build legacy schema (no forward_json) + insert a real row.
    const db = new Database(dbPath, { create: true });
    db.exec(`
      CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        direction TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        message_id TEXT,
        text TEXT
      );
    `);
    db.prepare(
      `INSERT INTO messages (direction, chat_id, message_id, text) VALUES ('inbound', 'legacy-chat', 'legacy-1', 'pre-migration body')`,
    ).run();

    const colsBefore = db
      .prepare("PRAGMA table_info(messages)")
      .all() as Array<{ name: string }>;
    expect(colsBefore.some((c) => c.name === "forward_json")).toBe(false);

    // 2) Run the migration — adds forward_json column.
    ensureColumn(db, "messages", "forward_json", "TEXT");

    const colsAfter = db.prepare("PRAGMA table_info(messages)").all() as Array<{
      name: string;
    }>;
    expect(colsAfter.some((c) => c.name === "forward_json")).toBe(true);

    // 3) Legacy row survives + forward_json is NULL on it (SQLite
    //    default for ALTER TABLE ADD COLUMN without DEFAULT).
    const row = db
      .prepare("SELECT * FROM messages WHERE chat_id = 'legacy-chat'")
      .get() as Record<string, unknown>;
    expect(row.text).toBe("pre-migration body");
    expect(row.forward_json).toBeNull();

    // 4) Re-run is idempotent — must NOT throw "duplicate column".
    expect(() =>
      ensureColumn(db, "messages", "forward_json", "TEXT"),
    ).not.toThrow();

    // 5) New rows can persist non-null forward_json after migration.
    db.prepare(
      `INSERT INTO messages (direction, chat_id, message_id, text, forward_json) VALUES ('inbound', 'legacy-chat', 'post-1', 'after migration', ?)`,
    ).run(JSON.stringify({ kind: "user", from_name: "X" }));
    const postRow = db
      .prepare("SELECT * FROM messages WHERE message_id = 'post-1'")
      .get() as Record<string, unknown>;
    expect(typeof postRow.forward_json).toBe("string");

    db.close();
  });
});
