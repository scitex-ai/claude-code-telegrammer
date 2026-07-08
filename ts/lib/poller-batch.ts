/**
 * Batch-processing + persistence-durability retry logic for the
 * getUpdates poller (durability fix PR-B, 2026-07).
 *
 * Owns the single durability invariant:
 *
 *   NEVER advance the persisted getUpdates offset past an inbound update
 *   whose DB persistence FAILED.
 *
 * Before this, the poller set `offset = update_id + 1` in-memory BEFORE
 * handleUpdate ran and persisted that advanced offset unconditionally
 * after the batch. A saveInbound throw was caught + swallowed, so the
 * offset still advanced → Telegram never redelivered → the message was
 * SILENTLY lost forever. processBatch closes that hole: it advances only
 * past updates the handler reports durable ("ok"/"duplicate") and STOPS
 * (loudly) on the first real "persistError", leaving the offset AT the
 * failed update_id so Telegram redelivers it (Telegram retains
 * undelivered updates ~24h).
 */

import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { log } from "./log.js";
import { CHANNEL_SOURCE } from "./config.js";
import { handleUpdate, type UpdateStatus } from "./handle-update.js";

/**
 * Consecutive persistError count on the SAME update_id we tolerate
 * before giving up and SKIPPING it (loudly). This bounds the wedge: a
 * permanently-unpersistable update (e.g. a genuinely corrupt row) can't
 * block the bridge forever, but the eventual loss is always announced,
 * never silent.
 */
export const MAX_PERSIST_RETRIES = 5;

// In-memory consecutive-failure tracker keyed on the failing update_id.
// Reset on ANY success (or once we skip past the poison update). Not
// persisted — a process restart re-reads the un-advanced offset and
// simply retries, which is exactly the desired behaviour.
let persistFail: { updateId: number; count: number } | null = null;

/** Test-only: reset the consecutive-failure tracker. */
export function _resetPersistFailures(): void {
  persistFail = null;
}

type UpdateHandler = (mcp: Server, update: any) => Promise<UpdateStatus>;

/**
 * Emit a LOUD failure notification. Same channel-notification mechanism
 * the poller's 409-fatal path uses (type: "error") so a persistence
 * failure is surfaced to the operator's channel and never silent. Also
 * logged. Best-effort — a failed notification is swallowed (we must not
 * throw out of the poll loop).
 */
function emitLoud(mcp: Server, content: string): void {
  log("poller", content);
  mcp
    .notification({
      method: "notifications/claude/channel",
      params: { content, meta: { source: CHANNEL_SOURCE, type: "error" } },
    })
    .catch(() => {});
}

/**
 * Process one getUpdates batch and return the offset that should be
 * persisted (via saveOffset) afterwards.
 *
 * For each update the handler returns an {@link UpdateStatus}:
 *
 *   - "ok" / "duplicate": the update is durable → advance the offset
 *     past it (update_id + 1) and reset the failure tracker.
 *
 *   - "persistError": saveInbound threw. On the 1st..(N-1)th consecutive
 *     failure for this update_id we do NOT advance past it — the returned
 *     offset is set to the failed update_id (so it AND the rest of the
 *     batch are refetched next poll), a LOUD notification is emitted, and
 *     the rest of the batch is DEFERRED (loop stops). On the Nth
 *     consecutive failure (MAX_PERSIST_RETRIES) we emit a FATAL loud
 *     notification and THEN advance past it (skip) so the bridge can't
 *     wedge forever — the loss is loud, never silent.
 *
 * The handler is injectable (defaults to handleUpdate) so the retry /
 * offset / loud-notification logic is unit-testable without any network.
 */
export async function processBatch(
  mcp: Server,
  updates: any[],
  startOffset: number,
  handle: UpdateHandler = handleUpdate,
): Promise<number> {
  let offset = startOffset;

  for (const update of updates) {
    let status: UpdateStatus;
    try {
      status = await handle(mcp, update);
    } catch (err) {
      // An UNEXPECTED throw — NOT the saveInbound-throw path, which
      // handleUpdate converts to "persistError". saveInbound failures
      // never reach here, so this is a post-persist / non-persist bug:
      // log and advance, exactly as the pre-PR loop did, so a handler
      // bug can't newly wedge the poller.
      log("poller", `error handling update ${update.update_id}`, {
        error: String(err),
      });
      offset = update.update_id + 1;
      persistFail = null;
      continue;
    }

    if (status === "persistError") {
      if (persistFail && persistFail.updateId === update.update_id) {
        persistFail.count += 1;
      } else {
        persistFail = { updateId: update.update_id, count: 1 };
      }

      if (persistFail.count >= MAX_PERSIST_RETRIES) {
        emitLoud(
          mcp,
          `FATAL: update ${update.update_id} failed to persist ` +
            `${persistFail.count}× consecutively — SKIPPING it to unwedge ` +
            `the poller. This message is PERMANENTLY LOST, but the loss is ` +
            `announced here, never silent. Investigate the SQLite store ` +
            `(disk full / corruption / locked DB).`,
        );
        offset = update.update_id + 1;
        persistFail = null;
        continue;
      }

      emitLoud(
        mcp,
        `persist FAILED for update ${update.update_id} ` +
          `(attempt ${persistFail.count}/${MAX_PERSIST_RETRIES}) — NOT ` +
          `advancing the getUpdates offset. Telegram will redeliver it on ` +
          `the next poll; the rest of this batch is deferred until it ` +
          `persists.`,
      );
      // Leave the offset AT the failed update_id — it (and everything
      // after it in this batch) is refetched next poll. Stop here.
      offset = update.update_id;
      break;
    }

    // "ok" or "duplicate": durable → advance past it and clear the
    // failure tracker (reset-on-any-success).
    offset = update.update_id + 1;
    persistFail = null;
  }

  return offset;
}
