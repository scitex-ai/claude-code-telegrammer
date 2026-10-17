/**
 * lib/notify-relay.ts — cross-process inbound-notification relay
 * (adversarial-review finding #3, follow-up to the poller/MCP-server
 * decoupling PR). Restores live-push delivery for interactive-CLI
 * (!wakeEnabled()) deployments after the poller became a separate process
 * with no mcp/Server object: the poller persists the notification payload
 * on the message's own row; the MCP-server process (this module) polls
 * for pending rows and delivers them.
 *
 * The relay DECISION logic (relayPendingNotificationsOnce) is thoroughly
 * covered below with injected dependencies. startNotifyRelay() (the
 * production timer wrapper) gets ONE direct test too — unlike
 * lib/poll-watchdog.ts::startStallWatchdog (untested directly; only its
 * pure createStallWatchdog is), this wrapper owns real scheduling
 * behaviour worth pinning: the reentrancy guard (round-2 adversarial-
 * review finding #1) that stops a slow/backlogged tick from overlapping
 * with the next scheduled one and double-relaying the same rows.
 */

import { describe, test, expect, beforeAll } from "bun:test";
import { initStore, saveInbound } from "../lib/store.js";
import {
  savePendingNotification,
  relayPendingNotificationsOnce,
  startNotifyRelay,
  wakeDeferMs,
  WAKE_DEFER_BASE_MS,
  WAKE_DEFER_CAP_MS,
  wakeRowBudgetMs,
  WAKE_ROW_BUDGET_MS_DEFAULT,
  _resetWakeInFlight,
  type PendingNotificationPayload,
} from "../lib/notify-relay.js";
import {
  recordWakeFailure,
  getWakeFailureState,
  _resetWakeFailureState,
} from "../lib/wake-health.js";

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

beforeAll(async () => {
  await initStore();
});

describe("savePendingNotification + relayPendingNotificationsOnce: real store round trip", () => {
  test("a saved pending row is relayed via mcp.notification, then cleared so it is not delivered twice", async () => {
    const rowId = await saveInbound({
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
    await savePendingNotification(rowId!, payload);

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

  test("Codex wake mode clears only after semantic turn admission", async () => {
    const rows = [{
      id: 1665,
      pending_notification: JSON.stringify({
        content: "operator request",
        meta: { row_id: "1665", message_id: "19824" },
      }),
    }];
    const cleared: number[] = [];
    const { mcp, calls } = fakeMcp();
    const failed = await relayPendingNotificationsOnce({
      mcp,
      deliveryMode: "wake",
      getPending: () => rows,
      clearPending: (id) => cleared.push(id),
      wake: async () => ({ ok: false, category: "server_error", reason: "HTTP 502" }),
    });
    expect(failed).toBe(0);
    expect(cleared).toEqual([]);
    expect(calls).toEqual([]);

    const admitted = await relayPendingNotificationsOnce({
      mcp,
      deliveryMode: "wake",
      getPending: () => rows,
      clearPending: (id) => cleared.push(id),
      wake: async () => ({ ok: true, status: 200 }),
    });
    expect(admitted).toBe(1);
    expect(cleared).toEqual([1665]);
    expect(calls).toEqual([]);
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

describe("wake-health reconcile-on-clear (cct-wake-live-session-20260930 residual)", () => {
  test("an MCP-relay drain clears the key a wake failure recorded — backlog does not freeze", async () => {
    await _resetWakeFailureState();
    await recordWakeFailure("server_error", "HTTP 502", Date.now(), "9101");
    expect((await getWakeFailureState()).count).toBe(1);

    const rows = [{
      id: 9101,
      pending_notification: JSON.stringify({
        content: "storm message, now drained via mcp",
        meta: { row_id: "9101" },
      }),
    }];
    const cleared: number[] = [];
    const { mcp, calls } = fakeMcp();
    const delivered = await relayPendingNotificationsOnce({
      mcp,
      getPending: () => rows,
      clearPending: (id) => cleared.push(id),
    });

    expect(delivered).toBe(1);
    expect(cleared).toEqual([9101]);
    expect(calls.length).toBe(1);
    expect((await getWakeFailureState()).count).toBe(0);
    await _resetWakeFailureState();
  });

  test("an MCP-relay drain of a never-failed row leaves the backlog at zero", async () => {
    await _resetWakeFailureState();
    const rows = [{
      id: 9102,
      pending_notification: JSON.stringify({
        content: "ordinary message",
        meta: { row_id: "9102" },
      }),
    }];
    const { mcp } = fakeMcp();
    const delivered = await relayPendingNotificationsOnce({
      mcp,
      getPending: () => rows,
      clearPending: async () => {},
    });

    expect(delivered).toBe(1);
    expect((await getWakeFailureState()).count).toBe(0);
  });
});

describe("wake retry deferral for non-transient failures (cct-wake-backlog-20261017)", () => {
  test("wakeDeferMs: 60s base, doubling per attempt, capped at 30min", () => {
    expect(WAKE_DEFER_BASE_MS).toBe(60_000);
    expect(WAKE_DEFER_CAP_MS).toBe(30 * 60_000);
    expect(wakeDeferMs(1)).toBe(60_000);
    expect(wakeDeferMs(2)).toBe(120_000);
    expect(wakeDeferMs(3)).toBe(240_000);
    expect(wakeDeferMs(100)).toBe(WAKE_DEFER_CAP_MS);
    expect(wakeDeferMs(NaN)).toBe(60_000);
    expect(wakeDeferMs(0)).toBe(60_000);
  });

  test("a quota_capped wake failure defers the next tick — no per-second 429 hammering", async () => {
    await _resetWakeFailureState();
    const rows = [{
      id: 1667,
      pending_notification: JSON.stringify({
        content: "operator request during quota wall",
        meta: { row_id: "1667" },
      }),
    }];
    let wakes = 0;
    const { mcp } = fakeMcp();
    const deps = {
      mcp,
      deliveryMode: "wake" as const,
      getPending: () => rows,
      clearPending: async () => {},
      wake: async () => {
        wakes += 1;
        return { ok: false, category: "quota_capped", reason: "HTTP 429" };
      },
    };
    expect(await relayPendingNotificationsOnce(deps)).toBe(0);
    expect(wakes).toBe(1);
    expect((await getWakeFailureState()).count).toBe(1);

    // Immediate second tick: deferred — wake NOT called again, row pending.
    expect(await relayPendingNotificationsOnce(deps)).toBe(0);
    expect(wakes).toBe(1);
    expect((await getWakeFailureState()).count).toBe(1);
    await _resetWakeFailureState();
  });

  test("backoff expiry resumes the wake retry and a success clears the key", async () => {
    await _resetWakeFailureState();
    await recordWakeFailure(
      "quota_capped",
      "HTTP 429",
      Date.now() - wakeDeferMs(1) - 1000,
      "1668",
    );
    const rows = [{
      id: 1668,
      pending_notification: JSON.stringify({
        content: "quota wall just lifted",
        meta: { row_id: "1668" },
      }),
    }];
    let wakes = 0;
    const cleared: number[] = [];
    const { mcp } = fakeMcp();
    const delivered = await relayPendingNotificationsOnce({
      mcp,
      deliveryMode: "wake",
      getPending: () => rows,
      clearPending: (id: number) => cleared.push(id),
      wake: async () => {
        wakes += 1;
        return { ok: true, status: 200 };
      },
    });
    expect(wakes).toBe(1);
    expect(delivered).toBe(1);
    expect(cleared).toEqual([1668]);
    expect((await getWakeFailureState()).count).toBe(0);
    await _resetWakeFailureState();
  });

  test("transient server_error keeps the every-tick retry (no deferral)", async () => {
    await _resetWakeFailureState();
    const rows = [{
      id: 1669,
      pending_notification: JSON.stringify({
        content: "transient 502",
        meta: { row_id: "1669" },
      }),
    }];
    let wakes = 0;
    const { mcp } = fakeMcp();
    const deps = {
      mcp,
      deliveryMode: "wake" as const,
      getPending: () => rows,
      clearPending: async () => {},
      wake: async () => {
        wakes += 1;
        return { ok: false, category: "server_error", reason: "HTTP 502" };
      },
    };
    expect(await relayPendingNotificationsOnce(deps)).toBe(0);
    expect(await relayPendingNotificationsOnce(deps)).toBe(0);
    expect(wakes).toBe(2);
    await _resetWakeFailureState();
  });
});

describe("burst tolerance: 4-message busy-502 bursts (cct-wake-backlog-20261017)", () => {
  test("wakeRowBudgetMs defaults to 120s; env override parses, garbage falls back", () => {
    expect(WAKE_ROW_BUDGET_MS_DEFAULT).toBe(120_000);
    expect(wakeRowBudgetMs({})).toBe(WAKE_ROW_BUDGET_MS_DEFAULT);
    expect(wakeRowBudgetMs({ CCT_WAKE_RELAY_ROW_BUDGET_MS: "5000" })).toBe(5000);
    expect(wakeRowBudgetMs({ CCT_WAKE_RELAY_ROW_BUDGET_MS: "0" })).toBe(0);
    expect(wakeRowBudgetMs({ CCT_WAKE_RELAY_ROW_BUDGET_MS: "" })).toBe(
      WAKE_ROW_BUDGET_MS_DEFAULT,
    );
    expect(wakeRowBudgetMs({ CCT_WAKE_RELAY_ROW_BUDGET_MS: "banana" })).toBe(
      WAKE_ROW_BUDGET_MS_DEFAULT,
    );
    expect(wakeRowBudgetMs({ CCT_WAKE_RELAY_ROW_BUDGET_MS: "-3" })).toBe(
      WAKE_ROW_BUDGET_MS_DEFAULT,
    );
  });

  function burstRows(ids: number[]) {
    return ids.map((id) => ({
      id,
      pending_notification: JSON.stringify({
        content: `burst message ${id}`,
        meta: { row_id: String(id) },
      }),
    }));
  }

  test("a 4-burst of fast 502s is fully attempted in one tick — nothing stalls, backlog records all four", async () => {
    await _resetWakeFailureState();
    const rows = burstRows([1671, 1672, 1673, 1674]);
    const attempted: number[] = [];
    const { mcp } = fakeMcp();
    const delivered = await relayPendingNotificationsOnce({
      mcp,
      deliveryMode: "wake",
      getPending: () => rows,
      clearPending: async () => {},
      wake: async (_content, meta) => {
        attempted.push(Number(meta.row_id));
        return { ok: false, category: "server_error", reason: "HTTP 502" };
      },
    });
    expect(delivered).toBe(0);
    expect(attempted.sort()).toEqual([1671, 1672, 1673, 1674]);
    expect((await getWakeFailureState()).count).toBe(4);
    await _resetWakeFailureState();
  });

  test("one hung 502 attempt does not freeze the tick: the other three still attempt, the hung row detaches without a second POST", async () => {
    await _resetWakeFailureState();
    _resetWakeInFlight();
    const prev = process.env.CCT_WAKE_RELAY_ROW_BUDGET_MS;
    process.env.CCT_WAKE_RELAY_ROW_BUDGET_MS = "50";
    try {
      const rows = burstRows([1681, 1682, 1683, 1684]);
      const attempted: number[] = [];
      const { mcp } = fakeMcp();
      const deps = {
        mcp,
        deliveryMode: "wake" as const,
        getPending: () => rows,
        clearPending: async () => {},
        wake: (_content: string, meta: Record<string, string>) => {
          attempted.push(Number(meta.row_id));
          if (meta.row_id === "1681") return new Promise<any>(() => {}); // wedged sidecar: never settles
          return Promise.resolve({ ok: false, category: "server_error", reason: "HTTP 502" });
        },
      };
      const started = Date.now();
      // Would hang forever pre-fix (sequential await + settle-gated reschedule).
      expect(await relayPendingNotificationsOnce(deps)).toBe(0);
      expect(Date.now() - started).toBeLessThan(4000);
      expect(attempted.sort()).toEqual([1681, 1682, 1683, 1684]);

      // Immediate second tick: the hung row is guarded (no second POST),
      // the 502 rows retry as designed.
      const hungAttempts = attempted.filter((id) => id === 1681).length;
      expect(await relayPendingNotificationsOnce(deps)).toBe(0);
      expect(attempted.filter((id) => id === 1681).length).toBe(hungAttempts);
      expect(attempted.filter((id) => id !== 1681).length).toBeGreaterThan(3);
    } finally {
      if (prev === undefined) delete process.env.CCT_WAKE_RELAY_ROW_BUDGET_MS;
      else process.env.CCT_WAKE_RELAY_ROW_BUDGET_MS = prev;
      _resetWakeInFlight();
      await _resetWakeFailureState();
    }
  });

  test("a detached attempt that succeeds late still clears its row and its backlog key", async () => {
    await _resetWakeFailureState();
    _resetWakeInFlight();
    const prev = process.env.CCT_WAKE_RELAY_ROW_BUDGET_MS;
    process.env.CCT_WAKE_RELAY_ROW_BUDGET_MS = "25";
    try {
      const rows = burstRows([1691]);
      const cleared: number[] = [];
      let wakes = 0;
      const { mcp } = fakeMcp();
      const delivered = await relayPendingNotificationsOnce({
        mcp,
        deliveryMode: "wake",
        getPending: () => rows,
        clearPending: (id: number) => cleared.push(id),
        wake: async () => {
          wakes += 1;
          await new Promise((r) => setTimeout(r, 100)); // settles after the 25ms budget
          return { ok: true, status: 200 };
        },
      });
      // Tick moved on without waiting: nothing counted delivered yet.
      expect(wakes).toBe(1);
      expect(delivered).toBe(0);
      expect(cleared).toEqual([]);
      // Late settlement finishes the bookkeeping: row cleared, key resolved.
      await new Promise((r) => setTimeout(r, 300));
      expect(cleared).toEqual([1691]);
      expect((await getWakeFailureState()).count).toBe(0);
    } finally {
      if (prev === undefined) delete process.env.CCT_WAKE_RELAY_ROW_BUDGET_MS;
      else process.env.CCT_WAKE_RELAY_ROW_BUDGET_MS = prev;
      _resetWakeInFlight();
      await _resetWakeFailureState();
    }
  });
});

describe("startNotifyRelay: reentrancy guard (round-2 adversarial-review finding #1)", () => {
  test("a tick slower than intervalMs never overlaps with the next scheduled tick — no row is relayed twice", async () => {
    // Realistic trigger: a long-lived detached poller accumulates a
    // backlog while no MCP-server session is running, then it drains in a
    // burst the moment a session connects — several rows in one tick,
    // comfortably over the poll interval. Simulated here with a SHORT
    // intervalMs (20ms) and a notification call slower than that (60ms
    // per row), so a bare `setInterval` (no reentrancy guard) would fire
    // several more times WHILE the first tick is still mid-flight,
    // re-relaying the still-uncleared rows.
    const rows = [
      {
        id: 1,
        pending_notification: JSON.stringify({ content: "row-1", meta: {} }),
      },
      {
        id: 2,
        pending_notification: JSON.stringify({ content: "row-2", meta: {} }),
      },
    ];
    const cleared = new Set<number>();
    const deliveryCounts: Record<string, number> = {};

    const getPending = () => rows.filter((r) => !cleared.has(r.id));
    const clearPending = (id: number) => cleared.add(id);
    const mcp = {
      notification: async (n: { params: PendingNotificationPayload }) => {
        deliveryCounts[n.params.content] =
          (deliveryCounts[n.params.content] ?? 0) + 1;
        await new Promise((r) => setTimeout(r, 60)); // slower than intervalMs
      },
    } as any;

    const handle = startNotifyRelay({ mcp, getPending, clearPending }, 20);
    try {
      // Let several 20ms intervals elapse while the (2 rows x 60ms =
      // ~120ms) first tick is still mid-flight, plus margin for a second
      // tick to run once the first one legitimately finishes.
      await new Promise((r) => setTimeout(r, 400));
    } finally {
      handle.stop();
    }

    expect(cleared.size).toBe(2);
    expect(deliveryCounts["row-1"]).toBe(1);
    expect(deliveryCounts["row-2"]).toBe(1);
  });

  test("stop() prevents any further ticks, including one already scheduled", async () => {
    let getPendingCalls = 0;
    const { mcp } = fakeMcp();
    const handle = startNotifyRelay(
      {
        mcp,
        getPending: () => {
          getPendingCalls += 1;
          return [];
        },
      },
      15,
    );
    await new Promise((r) => setTimeout(r, 40));
    handle.stop();
    const countAtStop = getPendingCalls;
    await new Promise((r) => setTimeout(r, 80));
    expect(getPendingCalls).toBe(countAtStop);
  });
});
