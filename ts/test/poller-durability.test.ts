/**
 * Durability fix PR-B: the getUpdates offset must NEVER advance past an
 * inbound update whose DB persistence FAILED, so Telegram redelivers it
 * on the next poll instead of the message being silently lost forever.
 *
 * These tests drive poller-batch.ts::processBatch directly — the module
 * that owns the "advance vs stop" decision. The injected handler mirrors
 * handleUpdate's exact persistence contract:
 *
 *     try { rowId = saveInbound(...) } catch { return "persistError" }
 *     return rowId === null ? "duplicate" : "ok";
 *
 * so a designated update literally simulates saveInbound THROWING while
 * its neighbours persist real rows against a real SQLite store. No
 * network is touched (the wake/receipt paths of the real handleUpdate
 * are deliberately not exercised — this is a pure test of the offset /
 * retry / loud-notification logic).
 */

import { describe, test, expect, beforeAll, beforeEach } from "bun:test";
import { initStore, saveInbound, getUnread } from "../lib/store.js";
import {
  processBatch,
  _resetPersistFailures,
  MAX_PERSIST_RETRIES,
} from "../lib/poller-batch.js";
import type { UpdateStatus } from "../lib/handle-update.js";

const CHAT = "7700";

/** A recording stand-in for the MCP Server's notification seam. */
function fakeMcp() {
  const notifications: any[] = [];
  const mcp = {
    notification: (n: any) => {
      notifications.push(n);
      return Promise.resolve();
    },
  } as any;
  return { mcp, notifications };
}

function textUpdate(updateId: number, messageId: number) {
  return {
    update_id: updateId,
    message: {
      message_id: messageId,
      from: { id: 42, is_bot: false, first_name: "Op", username: "op" },
      chat: { id: Number(CHAT), type: "private" },
      date: 1720400000,
      text: `msg ${messageId}`,
    },
  };
}

/**
 * Handler that mirrors handleUpdate's persistence contract. Updates whose
 * update_id is in `throwIds` simulate saveInbound THROWING (→
 * "persistError"); every other update persists a real row and returns
 * "ok" (or "duplicate" if saveInbound reported an existing row).
 */
function persistingHandler(throwIds: Set<number>) {
  return async (_mcp: any, update: any): Promise<UpdateStatus> => {
    try {
      if (throwIds.has(update.update_id)) {
        throw new Error("simulated DB failure");
      }
      const msg = update.message;
      const rowId = saveInbound({
        chat_id: CHAT,
        message_id: String(msg.message_id),
        user_id: "42",
        username: "op",
        text: msg.text,
        telegram_ts: new Date(msg.date * 1000).toISOString(),
        host: "h",
        project: "p",
        agent_id: "a",
        bot_token_hash: "b",
        raw_json: JSON.stringify(update),
      });
      return rowId === null ? "duplicate" : "ok";
    } catch {
      return "persistError";
    }
  };
}

/** Always-fail handler for the retry-then-skip test. */
async function alwaysPersistError(): Promise<UpdateStatus> {
  return "persistError";
}

function storedMessageIds(): Set<string> {
  return new Set(getUnread(CHAT).map((r) => String(r.message_id)));
}

beforeAll(() => {
  initStore();
});

beforeEach(() => {
  // The consecutive-failure tracker is module-global — isolate each test.
  _resetPersistFailures();
});

describe("processBatch never advances past an un-persisted update", () => {
  test("stops at the failed update; preceding successes persist, rest deferred", async () => {
    const { mcp, notifications } = fakeMcp();
    // u1 persists, u2 THROWS (persist error), u3 would persist but is
    // deferred because we stop at u2.
    const u1 = textUpdate(5001, 7001);
    const u2 = textUpdate(5010, 7002);
    const u3 = textUpdate(5020, 7003);
    const handle = persistingHandler(new Set([u2.update_id]));

    const newOffset = await processBatch(
      mcp,
      [u1, u2, u3],
      u1.update_id,
      handle,
    );

    // Offset left AT the failed update_id — NOT advanced past it, so
    // Telegram redelivers u2 (and u3) on the next poll.
    expect(newOffset).toBe(u2.update_id);
    expect(newOffset).toBeLessThan(u2.update_id + 1);

    // The preceding success is durably stored; the failed + deferred
    // updates are NOT.
    const ids = storedMessageIds();
    expect(ids.has("7001")).toBe(true); // u1 persisted
    expect(ids.has("7002")).toBe(false); // u2 threw
    expect(ids.has("7003")).toBe(false); // u3 deferred (never handled)

    // A LOUD channel notification fired for the persist failure.
    expect(notifications.length).toBeGreaterThanOrEqual(1);
    const loud = notifications[notifications.length - 1];
    expect(loud.method).toBe("notifications/claude/channel");
    expect(loud.params.meta.type).toBe("error");
    expect(loud.params.content).toContain("NOT");
    expect(loud.params.content).toContain(String(u2.update_id));
  });

  test("an all-success batch advances past every update", async () => {
    const { mcp } = fakeMcp();
    const u1 = textUpdate(5101, 7101);
    const u2 = textUpdate(5102, 7102);
    const handle = persistingHandler(new Set());

    const newOffset = await processBatch(mcp, [u1, u2], u1.update_id, handle);
    expect(newOffset).toBe(u2.update_id + 1);
  });

  test("a duplicate (saveInbound → null) is durable → advances", async () => {
    const { mcp } = fakeMcp();
    const u = textUpdate(5201, 7201);
    const handle = persistingHandler(new Set());
    // Pre-store the row so the second attempt returns null (duplicate).
    await processBatch(mcp, [u], u.update_id, handle);

    const newOffset = await processBatch(mcp, [u], u.update_id, handle);
    // duplicate is NOT a persistError — safe to advance past it.
    expect(newOffset).toBe(u.update_id + 1);
  });
});

describe("retry-then-loud-skip after N consecutive failures", () => {
  test(`holds the offset for ${MAX_PERSIST_RETRIES - 1} tries, then SKIPS loudly on the Nth`, async () => {
    const { mcp, notifications } = fakeMcp();
    const u = textUpdate(5301, 7301);

    // Attempts 1..(N-1): offset stays AT the failed update_id.
    for (let attempt = 1; attempt < MAX_PERSIST_RETRIES; attempt++) {
      const off = await processBatch(mcp, [u], u.update_id, alwaysPersistError);
      expect(off).toBe(u.update_id);
    }

    const before = notifications.length;

    // Attempt N: FATAL loud + advance PAST the poison update (skip).
    const off = await processBatch(mcp, [u], u.update_id, alwaysPersistError);
    expect(off).toBe(u.update_id + 1);

    const fatal = notifications[notifications.length - 1];
    expect(notifications.length).toBeGreaterThan(before);
    expect(fatal.params.meta.type).toBe("error");
    expect(fatal.params.content).toContain("FATAL");
    expect(fatal.params.content).toContain("SKIPPING");
  });

  test("a success resets the counter (fresh update starts at attempt 1)", async () => {
    const { mcp } = fakeMcp();
    const u = textUpdate(5401, 7401);

    // Rack up (N-1) failures, then a success resets the tracker.
    for (let attempt = 1; attempt < MAX_PERSIST_RETRIES; attempt++) {
      await processBatch(mcp, [u], u.update_id, alwaysPersistError);
    }
    await processBatch(
      mcp,
      [textUpdate(5402, 7402)],
      5402,
      persistingHandler(new Set()),
    );

    // The next failure for u must be treated as attempt 1 again — i.e.
    // the offset is HELD (not skipped), proving the counter reset.
    const off = await processBatch(mcp, [u], u.update_id, alwaysPersistError);
    expect(off).toBe(u.update_id);
  });
});
