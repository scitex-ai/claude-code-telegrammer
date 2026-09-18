/**
 * A store write that FAILS must hold the getUpdates offset, tested through the
 * REAL handleUpdate and a REAL store failure.
 *
 * handle-update.ts persists before acking Telegram: saveInbound throws →
 * return "persistError" → processBatch leaves the offset AT that update, so
 * Telegram redelivers it. Swallow that throw and the message is skipped for
 * good, with no retry able to recover it. scitex-agent-container made this a
 * hard constraint of the store migration: "Test that path explicitly with a
 * positive control — make the write fail once and prove the offset did not
 * move."
 *
 * poller-durability.test.ts covers processBatch's side, but through a
 * HAND-WRITTEN handler that "mirrors handleUpdate's persistence contract". The
 * real catch in handleUpdate was never run by any test, so replacing it with
 * `return "ok"` failed nothing.
 *
 * Here the handler is the real one and the failure is real: PostgreSQL rejects
 * a NUL byte in a text column, so saveInbound genuinely throws. No mocks.
 */

import {
  describe,
  test,
  expect,
  beforeAll,
  beforeEach,
  afterAll,
} from "bun:test";
import { writeFileSync, mkdirSync, rmSync } from "fs";
import { initStore, getHistory } from "../lib/store.js";
import { handleUpdate } from "../lib/handle-update.js";
import { processBatch, _resetPersistFailures } from "../lib/poller-batch.js";
import { setTurnPoster } from "../lib/wake.js";
import {
  setSystemAlertSender,
  _resetSystemAlertSender,
  setLoudFailSender,
  _resetLoudFail,
} from "../lib/loudfail.js";
import { _resetCache } from "../lib/access.js";
import { ACCESS_FILE, STATE_DIR } from "../lib/config.js";

// Unique per process: the store is shared with every other test file.
const USER_ID = `77${process.pid}`;
const CHAT_ID = USER_ID;
const alerts: string[] = [];
// PostgreSQL rejects a NUL byte in a text column: a REAL write failure.
// Built at runtime so this source file stays plain text.
const NUL = String.fromCharCode(0);

function textUpdate(updateId: number, messageId: number, text: string) {
  return {
    update_id: updateId,
    message: {
      message_id: messageId,
      from: { id: Number(USER_ID), is_bot: false, username: "op" },
      chat: { id: Number(CHAT_ID), type: "private" },
      date: 1726300000,
      text,
    },
  };
}

async function storedMessageIds(): Promise<Set<string>> {
  return new Set(
    (await getHistory(CHAT_ID, 100)).map((r) => String(r.message_id)),
  );
}

beforeAll(async () => {
  await initStore();
  mkdirSync(STATE_DIR, { recursive: true });
  writeFileSync(ACCESS_FILE, JSON.stringify({ allowFrom: [USER_ID] }));
  _resetCache();
  // Nothing in this file may reach Telegram or sac: record instead.
  setTurnPoster(async () => 200);
  setSystemAlertSender(async (_chatId, text) => {
    alerts.push(text);
    return { ok: true };
  });
  setLoudFailSender(async (_chatId, text) => {
    alerts.push(text);
  });
});

afterAll(() => {
  _resetSystemAlertSender();
  _resetLoudFail();
  rmSync(ACCESS_FILE, { force: true });
  _resetCache();
});

beforeEach(() => {
  _resetPersistFailures();
});

describe("a real store failure, through the real handleUpdate, holds the offset", () => {
  test("handleUpdate answers persistError when the write genuinely fails", async () => {
    const status = await handleUpdate(textUpdate(91001, 81001, `nul${NUL}byte`));
    expect(status).toBe("persistError");
    expect((await storedMessageIds()).has("81001")).toBe(false);
  });

  test("processBatch stops AT the failed update: the offset does not move past it", async () => {
    const ok = textUpdate(92001, 82001, "stored normally"); // positive control
    const bad = textUpdate(92010, 82002, `rejected${NUL}by the store`);
    const later = textUpdate(92020, 82003, "would store, but is deferred");

    const newOffset = await processBatch(
      [ok, bad, later],
      ok.update_id,
      handleUpdate,
    );

    // Left AT the failed update, so Telegram redelivers it and everything after.
    expect(newOffset).toBe(bad.update_id);

    const ids = await storedMessageIds();
    expect(ids.has("82001")).toBe(true); // the control really was stored
    expect(ids.has("82002")).toBe(false); // the failed write stored nothing
    expect(ids.has("82003")).toBe(false); // deferred, never handled
  });
});
