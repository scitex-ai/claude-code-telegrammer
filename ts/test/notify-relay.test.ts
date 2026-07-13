/**
 * lib/notify-relay.ts — cross-process inbound-notification relay
 * (adversarial-review finding #3, follow-up to the poller/MCP-server
 * decoupling PR). Restores live-push delivery for interactive-CLI
 * (!wakeEnabled()) deployments after the poller became a separate process
 * with no mcp/Server object: the poller persists the notification payload
 * on the message's own row; the MCP-server process (this module) polls
 * for pending rows and delivers them.
 *
 * startNotifyRelay() itself (the real-setInterval production wrapper) has
 * no direct test here, matching this repo's own established convention
 * (lib/poll-watchdog.ts::startStallWatchdog is likewise untested directly
 * — only its pure decision function, createStallWatchdog, is). All the
 * actual relay DECISION logic lives in relayPendingNotificationsOnce,
 * which is thoroughly covered below with injected dependencies.
 */

import { describe, test, expect, beforeAll } from "bun:test";
import { initStore, saveInbound } from "../lib/store.js";
import {
  savePendingNotification,
  relayPendingNotificationsOnce,
  type PendingNotificationPayload,
} from "../lib/notify-relay.js";

const CHAT = "notify-relay-test-chat";

function fakeMcp() {
  const calls: Array<{ method: string; params: PendingNotificationPayload }> =
    [];
  return {
    mcp: {
      notification: async (n: {
        method: string;
        params: PendingNotificationPayload;
      }) => {
        calls.push(n);
      },
    } as any,
    calls,
  };
}

beforeAll(() => {
  initStore();
});

describe("savePendingNotification + relayPendingNotificationsOnce: real store round trip", () => {
  test("a saved pending row is relayed via mcp.notification, then cleared so it is not delivered twice", async () => {
    const rowId = saveInbound({
      chat_id: CHAT,
      message_id: `msg-${Date.now()}`,
      user_id: "1",
      username: "op",
      text: "hello from the relay round-trip test",
      telegram_ts: new Date().toISOString(),
      host: "h",
      project: "p",
      agent_id: "a",
      bot_token_hash: "b",
      raw_json: "{}",
    });
    expect(rowId).not.toBeNull();

    const payload: PendingNotificationPayload = {
      content: "hello from the relay round-trip test",
      meta: { chat_id: CHAT, source: "cct" },
    };
    savePendingNotification(rowId!, payload);

    const { mcp, calls } = fakeMcp();
    const delivered = await relayPendingNotificationsOnce({ mcp });
    expect(delivered).toBeGreaterThanOrEqual(1);
    expect(
      calls.some(
        (c) =>
          c.method === "notifications/claude/channel" &&
          c.params.content === "hello from the relay round-trip test" &&
          c.params.meta.chat_id === CHAT,
      ),
    ).toBe(true);

    // Second tick: this row's payload was cleared — must NOT be delivered
    // again (no double-delivery once relayed).
    const { mcp: mcp2, calls: calls2 } = fakeMcp();
    await relayPendingNotificationsOnce({ mcp: mcp2 });
    expect(calls2.some((c) => c.params.meta.chat_id === CHAT)).toBe(false);
  });
});

describe("relayPendingNotificationsOnce: injected deps (no real store)", () => {
  test("delivers each pending row in order and clears it", async () => {
    const rows = [
      {
        id: 1,
        pending_notification: JSON.stringify({ content: "a", meta: {} }),
      },
      {
        id: 2,
        pending_notification: JSON.stringify({ content: "b", meta: {} }),
      },
    ];
    const cleared: number[] = [];
    const { mcp, calls } = fakeMcp();

    const delivered = await relayPendingNotificationsOnce({
      mcp,
      getPending: () => rows,
      clearPending: (id) => cleared.push(id),
    });

    expect(delivered).toBe(2);
    expect(cleared).toEqual([1, 2]);
    expect(calls.map((c) => c.params.content)).toEqual(["a", "b"]);
  });

  test("a malformed pending_notification JSON is logged and left pending — never thrown", async () => {
    const rows = [{ id: 42, pending_notification: "not-json{{{" }];
    const cleared: number[] = [];
    const logs: Array<{ component: string; msg: string; data?: unknown }> = [];
    const { mcp, calls } = fakeMcp();

    const delivered = await relayPendingNotificationsOnce({
      mcp,
      getPending: () => rows,
      clearPending: (id) => cleared.push(id),
      logFn: (component, msg, data) => logs.push({ component, msg, data }),
    });

    expect(delivered).toBe(0);
    expect(cleared).toEqual([]);
    expect(calls.length).toBe(0);
    expect(
      logs.some((l) => (l.data as { row_id?: number })?.row_id === 42),
    ).toBe(true);
  });

  test("an mcp.notification rejection leaves the row pending for retry — never thrown", async () => {
    const rows = [
      {
        id: 7,
        pending_notification: JSON.stringify({ content: "x", meta: {} }),
      },
    ];
    const cleared: number[] = [];
    const mcp = {
      notification: async () => {
        throw new Error("simulated stdio write failure");
      },
    } as any;

    const delivered = await relayPendingNotificationsOnce({
      mcp,
      getPending: () => rows,
      clearPending: (id) => cleared.push(id),
    });

    expect(delivered).toBe(0);
    expect(cleared).toEqual([]);
  });

  test("one failing row does not block delivery of the others", async () => {
    const rows = [
      { id: 1, pending_notification: "bad-json" },
      {
        id: 2,
        pending_notification: JSON.stringify({ content: "good", meta: {} }),
      },
    ];
    const cleared: number[] = [];
    const { mcp, calls } = fakeMcp();

    const delivered = await relayPendingNotificationsOnce({
      mcp,
      getPending: () => rows,
      clearPending: (id) => cleared.push(id),
    });

    expect(delivered).toBe(1);
    expect(cleared).toEqual([2]);
    expect(calls.length).toBe(1);
  });

  test("no pending rows -> zero delivered, no calls at all", async () => {
    const { mcp, calls } = fakeMcp();
    const delivered = await relayPendingNotificationsOnce({
      mcp,
      getPending: () => [],
      clearPending: () => {
        throw new Error("must not be called when there is nothing pending");
      },
    });
    expect(delivered).toBe(0);
    expect(calls.length).toBe(0);
  });
});
