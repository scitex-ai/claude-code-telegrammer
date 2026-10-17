/**
 * Cross-process relay for inbound messages that could not be live-pushed
 * at ingestion time (adversarial-review finding #3, follow-up to the
 * poller/MCP-server decoupling PR).
 *
 * Interactive-CLI (no TURN_URL / !wakeEnabled()) deployments used to
 * receive inbound Telegram messages as a live `mcp.notification()` push
 * straight from the poller's own lib/handle-update.ts, rendering into an
 * ACTIVE turn. Once the poller became a separate process
 * (ts/telegram-poller.ts) with no mcp/Server object at all, that direct
 * push became categorically impossible from there — a separate OS process
 * cannot call a method on another process's live MCP stdio connection.
 * The first cut of this decoupling PR left this as a documented gap
 * (message durably saved, but not live-pushed). This module closes it.
 *
 * The fix: the WRITER (the poller process, via
 * lib/handle-update.ts::savePendingNotification) persists the fully-built
 * notification payload onto the message's own row in the shared store. The
 * READER (THIS module, running in the MCP-server process, which still holds
 * the live `mcp` object throughout an interactive session) polls for pending
 * rows and calls mcp.notification() itself, then clears the payload once
 * delivered — restoring the ORIGINAL live-push behaviour via a short (default
 * 1s) delay instead of an immediate call, the necessary cost of the payload
 * having to cross a process boundary via the store instead of a function call.
 *
 * WHO WRITES HERE — TWO CASES, AND WAKE-ENABLED AGENTS ARE ONE OF THEM.
 *
 *   1. !wakeEnabled() (interactive CLI): every inbound message is written, and
 *      this relay is the normal delivery path.
 *   2. wakeEnabled() (sac TUI + SDK agents): a row is written ONLY WHEN THE
 *      WAKE POST FAILS. This relay is then the FALLBACK delivery path — it
 *      reaches an attached session without going through sac's a2a sidecar,
 *      and a row it cannot deliver yet stays pending until it can. A healthy
 *      wake writes nothing, so there is still exactly one delivery path and no
 *      double delivery.
 *
 * The relay is therefore started whenever Telegram is enabled
 * (ts/telegram-server.ts: `if (TELEGRAM_ENABLED) startNotifyRelay(...)`),
 * wake-enabled deployments included — since PR #77, 2026-07-14, which fixed
 * operator messages being dropped outright whenever the sidecar was down.
 *
 * THIS PARAGRAPH USED TO SAY THE OPPOSITE: "only ever populated for
 * !wakeEnabled() deployments ... wake-enabled agents ... never write here ...
 * started only when !wakeEnabled()". That was true before #77 and false for
 * the two months after it. It was not harmless: an agent read it on
 * 2026-08-23, concluded that a failed wake wrote to a queue with no reader,
 * and recommended REMOVING the fallback write — which would have reintroduced
 * the incident #77 fixed. The call site in telegram-server.ts is the source of
 * truth for whether this relay runs; if the two ever disagree again, believe
 * the call site and fix this comment.
 *
 * NOTE ON THE ENGINE MOVE: this module used to open its own independent
 * database handle, each one having to remember its own lock-timeout setting
 * (a footgun documented in four separate places in this codebase). It now
 * shares the one pooled connection like everything else, which retires that
 * whole class of mistake.
 */

import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  recordWakeFailure,
  recordWakeSuccess,
  getWakeFailureState,
  type WakeFailureState,
} from "./wake-health.js";
import { wakeTurn, type WakeResult, type WakeFailCategory } from "./wake.js";
import { getSql } from "./pg.js";
import { storeSchema } from "./store.js";
import { statements } from "./store-schema.js";
import { log } from "./log.js";
import {
  errorDetail,
  failingCheck,
  type ProtocolCheck,
} from "./protocol-status.js";

export interface PendingNotificationPayload {
  content: string;
  meta: Record<string, string>;
}

export type PendingNotificationWrite =
  | { ok: true }
  | { ok: false; check: ProtocolCheck };

export type PendingNotificationProbe =
  | { ok: true; pending: boolean }
  | { ok: false; check: ProtocolCheck };

/**
 * WRITER side — called from lib/handle-update.ts (standalone poller
 * process). Persists the fully-built notification payload VERBATIM on the
 * message's own row, so the reader delivers EXACTLY what the old direct
 * push would have (including the attachment descriptor appended to
 * `deliveredText`, which is not itself a separate stored column) — no
 * re-derivation needed on the reader side. Best-effort: a write failure is
 * logged, never thrown — must not crash inbound message handling over a
 * delivery-relay concern.
 */
export async function savePendingNotification(
  rowId: number,
  payload: PendingNotificationPayload,
): Promise<PendingNotificationWrite> {
  try {
    await getSql().unsafe(statements(storeSchema()).setPendingNotification, [
      JSON.stringify(payload),
      rowId,
    ]);
    return { ok: true };
  } catch (err) {
    log("notify-relay", "failed to persist pending notification", {
      row_id: rowId,
      error: String(err),
    });
    return {
      ok: false,
      check: failingCheck(
        "wake_fallback_persisted",
        `wake fallback for message row ${rowId} was not persisted: ${errorDetail(err)}`,
        "Restore writable message-store capacity, then redeliver this inbound message; it has no durable fallback notification.",
        err,
      ),
    };
  }
}

/**
 * Check whether a notification saved via savePendingNotification() is still
 * pending (i.e. the notify-relay reader has not yet delivered and NULLed
 * the column). Returns true when the row exists AND its
 * pending_notification is not null. On a thrown error the compatibility
 * boolean returns true: unknown must not be collapsed into "delivered".
 *
 * @param rowId - The messages row to check.
 * @param schema - The namespace to read. Defaults to the initialized store's.
 *   Injected so tests can target a namespace that does not exist without
 *   touching the one the rest of the suite shares.
 */
export async function isNotificationPending(
  rowId: number,
  schema?: string,
): Promise<boolean> {
  const result = await probePendingNotification(rowId, schema);
  // Compatibility wrapper, deliberately conservative: inability to inspect
  // the durable fallback must never be read as "relay delivered it".
  return result.ok ? result.pending : true;
}

export async function probePendingNotification(
  rowId: number,
  schema?: string,
): Promise<PendingNotificationProbe> {
  try {
    const rows = await getSql().unsafe(
      statements(schema ?? storeSchema()).readPendingNotification,
      [rowId],
    );
    const row = rows[0] as { pending_notification: string | null } | undefined;
    return { ok: true, pending: !!row && row.pending_notification !== null };
  } catch (err) {
    return {
      ok: false,
      check: failingCheck(
        "wake_fallback_receipt_observed",
        `could not verify the durable wake fallback for message row ${rowId}: ${errorDetail(err)}`,
        "Restore message-store access, then inspect and redeliver this message; do not assume the fallback relay completed.",
        err,
      ),
    };
  }
}

interface PendingRow {
  id: number;
  pending_notification: string;
}

/** Currently-pending rows, oldest first. */
async function readPendingRows(): Promise<PendingRow[]> {
  const rows = (await getSql().unsafe(
    statements(storeSchema()).pendingNotifications,
    [],
  )) as Array<{ id: string | number; pending_notification: string }>;
  return rows.map((r) => ({
    id: Number(r.id),
    pending_notification: r.pending_notification,
  }));
}

async function clearPendingRow(id: number): Promise<void> {
  await getSql().unsafe(statements(storeSchema()).clearPendingNotification, [
    id,
  ]);
}

export interface NotifyRelayDeps {
  mcp: Server;
  /** Harnesses without Claude channel-notification admission (Codex, Hermes)
   * cannot see an mcp.notification push. In that harness retry the durable
   * payload through /v1/turn and clear it only on the bridge's positive
   * admission response. */
  deliveryMode?: "mcp" | "wake";
  wake?: (content: string, meta: Record<string, string>) => Promise<WakeResult>;
  /** Injectable for tests; defaults to a real readPendingRows() call. */
  getPending?: () => PendingRow[] | Promise<PendingRow[]>;
  /** Injectable for tests; defaults to a real clearPendingRow() call. */
  clearPending?: (id: number) => void | Promise<void>;
  logFn?: typeof log;
}

/**
 * Wake-failure categories that will not clear on a 1s-retry timescale
 * (card cct-wake-backlog-20261017): a quota wall lifts in hours, auth /
 * client-shape / disk-quota failures need an operator, not another POST.
 * Retrying these every relay tick (default 1s) turned one capped account
 * into hundreds of 429s and re-pinned atMs on every attempt, defeating
 * any staleness signal. Transient categories (timeout, server_error,
 * connection_refused, unknown) keep the every-tick retry — same split
 * lib/handle-update.ts uses for its inline wake retry.
 */
const WAKE_DEFERRABLE: ReadonlySet<WakeFailCategory> = new Set([
  "quota_capped",
  "auth",
  "client_error",
  "resource_exhausted",
]);

/** Base 60s, doubling per recorded attempt, capped at 30min. Exported for tests. */
export const WAKE_DEFER_BASE_MS = 60_000;
export const WAKE_DEFER_CAP_MS = 30 * 60_000;

export function wakeDeferMs(attempts: number): number {
  const n = Number.isFinite(attempts) ? Math.max(1, Math.floor(attempts)) : 1;
  return Math.min(WAKE_DEFER_BASE_MS * 2 ** (n - 1), WAKE_DEFER_CAP_MS);
}

/**
 * Per-row wake-attempt budget, ms (card cct-wake-backlog-20261017, burst
 * tolerance): how long one relay tick waits for one row's wake POST before
 * moving on to the next row.
 *
 * WHY. The tick awaits rows SEQUENTIALLY and the next tick only starts
 * after the current one settles (see startNotifyRelay below) — and wakeTurn
 * deliberately has NO client-side timeout (lib/wake.ts: aborting a
 * legitimately long turn client-side would orphan server-side execution).
 * So one hung attempt (wedged sidecar: connection accepted, 504 never
 * comes) stalls every row behind it and every future tick — the relay
 * freezes with zero progress while a 4-burst waits. The budget bounds the
 * stall: on expiry the tick moves on WITHOUT aborting the attempt (no
 * duplicate-turn hazard — the late settlement still does the record/clear
 * bookkeeping, and the in-flight guard below forbids a second attempt for
 * the same message while the first is outstanding).
 *
 * Worst case per tick is rows × budget (order-preserving sequential
 * attempts); the fast-502 busy case the card data shows stays ms-scale.
 * Default 120s — above the ~2min legit-turn horizon handle-update.ts
 * assumes, so only truly wedged attempts detach. CCT_WAKE_RELAY_ROW_BUDGET_MS
 * overrides; 0 disables (fully sequential, the old behaviour).
 */
export const WAKE_ROW_BUDGET_MS_DEFAULT = 120_000;

export function wakeRowBudgetMs(
  env: Record<string, string | undefined> = process.env,
): number {
  const raw = env.CCT_WAKE_RELAY_ROW_BUDGET_MS;
  if (raw === undefined || raw === "") return WAKE_ROW_BUDGET_MS_DEFAULT;
  const ms = parseInt(raw, 10);
  if (!Number.isFinite(ms) || ms < 0) return WAKE_ROW_BUDGET_MS_DEFAULT;
  return ms;
}

/**
 * Wake attempts detached from tick flow after their row budget expired,
 * by messageKey. While a key is present, no further attempt for that
 * message starts — at most one wake POST is ever in flight per message
 * (the relay otherwise runs one tick at a time in a single process, so a
 * module-level set is sufficient; the poller process never runs this
 * function, only its own phased retry chains).
 */
const wakeInFlight = new Set<string>();

/** Test-only: drop all in-flight markers (a wedged stub would pin them). */
export function _resetWakeInFlight(): void {
  wakeInFlight.clear();
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Await a wake attempt up to budgetMs. Settles normally when the attempt
 * finishes first; on budget expiry returns the still-running flight so the
 * caller can detach (tick moves on) while settlement bookkeeping happens
 * exactly once, late. A REJECTED attempt rethrows (the real wakeTurn never
 * rejects — documented never-throw — so this only fires for a misbehaving
 * injected stub, preserving the old leave-pending semantics via the row's
 * catch). budgetMs <= 0 disables the budget (plain await).
 */
async function attemptWakeBounded(
  flight: Promise<WakeResult>,
  budgetMs: number,
): Promise<
  | { settled: true; result: WakeResult }
  | { settled: false; flight: Promise<WakeResult | undefined> }
> {
  if (budgetMs <= 0) return { settled: true, result: await flight };
  let result: WakeResult | undefined;
  let failure: unknown;
  let failed = false;
  const tracked = flight.then(
    (r) => {
      result = r;
    },
    (err) => {
      failed = true;
      failure = err;
    },
  );
  const inTime = await Promise.race([
    tracked.then(() => true),
    sleep(budgetMs).then(() => false),
  ]);
  if (inTime) {
    if (failed) throw failure;
    return { settled: true, result: result as WakeResult };
  }
  return {
    settled: false,
    flight: tracked.then(() => (failed ? undefined : result)),
  };
}

/**
 * READER side — called from ts/telegram-server.ts, which holds the live
 * mcp object throughout the process lifetime. One poll tick: relay every
 * currently-pending notification, oldest first, then clear it. Exported
 * separately from startNotifyRelay() so the relay DECISION is unit-
 * testable without a real timer (same injectable-seam pattern
 * poller-batch.ts / poll-watchdog.ts already use).
 */
export async function relayPendingNotificationsOnce(
  deps: NotifyRelayDeps,
): Promise<number> {
  const getPending = deps.getPending ?? readPendingRows;
  const clearPending = deps.clearPending ?? clearPendingRow;
  const logFn = deps.logFn ?? log;

  let delivered = 0;
  let pending: PendingRow[];
  try {
    pending = await getPending();
  } catch (err) {
    // The snapshot itself failed (store unreachable). Nothing to relay this
    // tick; the next one retries. Logged, never thrown — same contract the
    // per-row branch below already honoured.
    logFn("notify-relay", "failed to read pending notifications", {
      error: String(err),
    });
    return 0;
  }
  // ONE backlog snapshot per tick (not per row): the deferral/backoff clock
  // below only needs tick-start state, and a burst of N rows must not pay N
  // sequential store reads before its first wake attempt. In-tick records
  // become visible on the next tick — a 1s delay on an hours-scale backoff.
  const rowBudgetMs = wakeRowBudgetMs();
  const backlog = await getWakeFailureState().then(
    (s) => s.unresolved ?? {},
    () => ({}) as NonNullable<WakeFailureState["unresolved"]>,
  );
  for (const row of pending) {
    try {
      const payload = JSON.parse(
        row.pending_notification,
      ) as PendingNotificationPayload;
      // Reconcile key for the wake-health backlog (cct-wake-live-session-20260930
      // residual): the counter is per-message-keyed, so EVERY path that drains a
      // row must clear that row's key — otherwise the health signal freezes at
      // the storm count while deliveries work again.
      const messageKey = payload.meta.row_id ?? String(row.id);
      if (deps.deliveryMode === "wake") {
        // In-flight guard (burst tolerance): an earlier tick detached this
        // message's attempt after its row budget expired and it still hasn't
        // settled. Starting a second POST now would put two turns for one
        // message in flight — skip until the first settles (its settlement
        // still records success/failure and clears the row, late).
        if (wakeInFlight.has(messageKey)) {
          logFn("notify-relay", "wake attempt already in flight; leaving message pending", {
            row_id: row.id,
          });
          continue;
        }
        // Deferral (card cct-wake-backlog-20261017): a row whose last wake
        // attempt failed in a non-transient category (quota wall, auth,
        // client-shape, disk-quota) is NOT re-POSTed until its backoff
        // elapses — the row stays pending, the wake endpoint stops getting
        // hammered, and atMs stops being re-pinned every tick (which is
        // what kept stale 429 entries looking fresh). The backoff clock is
        // the wake-health unresolved entry the failed attempt already
        // recorded — no new state, and visible cross-process via the store.
        // A missing entry (store down, never attempted) degrades to the
        // old behaviour: attempt now.
        const backoff = backlog[messageKey];
        if (
          backoff &&
          WAKE_DEFERRABLE.has(backoff.category) &&
          Date.now() - backoff.atMs < wakeDeferMs(backoff.attempts)
        ) {
          logFn("notify-relay", "wake retry deferred (backoff); leaving message pending", {
            row_id: row.id,
            category: backoff.category,
            attempts: backoff.attempts,
          });
          continue;
        }
        let flight: Promise<WakeResult>;
        try {
          flight = (deps.wake ?? wakeTurn)(payload.content, payload.meta);
        } catch (err) {
          // A synchronously-throwing wake stub: same as the old path —
          // leave the row pending, never thrown.
          logFn("notify-relay", "failed to relay a pending notification", {
            row_id: row.id,
            error: String(err),
          });
          continue;
        }
        wakeInFlight.add(messageKey);
        const outcome = await attemptWakeBounded(flight, rowBudgetMs);
        if (!outcome.settled) {
          // Row budget expired: the tick moves on so one hung POST can no
          // longer freeze the rows behind it or any future tick. The attempt
          // itself is NOT aborted (aborting client-side would orphan a
          // server-side turn and risk a duplicate on retry); its late
          // settlement finishes the bookkeeping exactly once.
          void outcome.flight.then(async (late) => {
            try {
              if (late === undefined) return; // stub rejected; row stays pending
              if (late.ok) {
                await recordWakeSuccess(messageKey);
                await clearPending(row.id);
              } else {
                await recordWakeFailure(
                  late.category,
                  late.reason,
                  Date.now(),
                  messageKey,
                );
              }
              logFn("notify-relay", "detached wake attempt settled after tick moved on", {
                row_id: row.id,
                ok: late.ok,
              });
            } catch (err) {
              logFn("notify-relay", "failed to settle a detached wake attempt", {
                row_id: row.id,
                error: String(err),
              });
            } finally {
              wakeInFlight.delete(messageKey);
            }
          });
          logFn("notify-relay", "wake attempt exceeded row budget; tick moving on, attempt stays in flight", {
            row_id: row.id,
          });
          continue;
        }
        wakeInFlight.delete(messageKey);
        const result = outcome.result;
        if (!result.ok) {
          await recordWakeFailure(result.category, result.reason, Date.now(), messageKey);
          logFn("notify-relay", "wake retry not admitted; leaving message pending", {
            row_id: row.id,
            check: result.check,
            reason: result.reason,
          });
          continue;
        }
        await recordWakeSuccess(messageKey);
      } else {
        await deps.mcp.notification({
          method: "notifications/claude/channel",
          params: payload,
        });
        // An MCP-relay drain proves this message got out: clear the key the
        // wake-failure path recorded, or it stays in the unresolved map forever.
        await recordWakeSuccess(messageKey);
      }
      await clearPending(row.id);
      delivered += 1;
    } catch (err) {
      // Leave the row pending — retried on the next tick. Logged, never
      // thrown (must not crash the relay loop or the MCP server).
      logFn("notify-relay", "failed to relay a pending notification", {
        row_id: row.id,
        error: String(err),
      });
    }
  }
  return delivered;
}

export interface NotifyRelayHandle {
  stop(): void;
}

/**
 * Production entry point: poll every intervalMs (default 1000ms), unref'd
 * so it never keeps the MCP server process alive on its own. Called from
 * ts/telegram-server.ts only when !wakeEnabled().
 *
 * SELF-RESCHEDULING, not a bare setInterval (round-2 adversarial-review
 * finding #1 — real duplicate delivery, confirmed via
 * ts/test/notify-relay.test.ts): relayPendingNotificationsOnce takes a
 * snapshot then sequentially awaits mcp.notification()+clearPending() per
 * row, uncapped. A bare setInterval fires on a fixed wall-clock schedule
 * REGARDLESS of whether the previous tick finished — so a tick slower than
 * intervalMs (one slow notification round-trip, or a modest backlog; the
 * realistic trigger is a long-lived detached poller draining an
 * accumulated backlog in a burst the moment an MCP-server session
 * connects) lets the NEXT tick start while the SAME rows are still
 * uncleared, re-relaying them — the operator sees the same message twice.
 * Scheduling the next tick only AFTER the current one's promise settles
 * makes that structurally impossible: at most one tick is ever in flight.
 * (In wake deliveryMode each row's attempt additionally carries a row
 * budget — see WAKE_ROW_BUDGET_MS_DEFAULT — so one hung POST bounds the
 * tick's stall instead of freezing it: the tick moves on, the attempt
 * stays in flight exactly once, and its late settlement still records.)
 */
export function startNotifyRelay(
  deps: NotifyRelayDeps,
  intervalMs = 1000,
): NotifyRelayHandle {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const logFn = deps.logFn ?? log;

  const unrefTimer = (h: ReturnType<typeof setTimeout>) => {
    if (typeof h === "object" && h && "unref" in h) {
      (h as { unref: () => void }).unref();
    }
  };

  const scheduleNext = () => {
    if (stopped) return;
    timer = setTimeout(tick, intervalMs);
    unrefTimer(timer);
  };

  const tick = () => {
    void relayPendingNotificationsOnce(deps)
      .catch((err) => {
        // relayPendingNotificationsOnce already catches per-row errors
        // internally and never rejects in practice, but guard here too —
        // a throw must not silently kill the reschedule loop.
        logFn("notify-relay", "unexpected error in relay tick", {
          error: String(err),
        });
      })
      .finally(() => {
        scheduleNext();
      });
  };

  scheduleNext();

  return {
    stop: () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    },
  };
}
