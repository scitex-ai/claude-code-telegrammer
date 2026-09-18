/**
 * Handler bodies for the message-query MCP tools: get_history,
 * get_unread, search_messages, mark_read, download_attachment.
 *
 * Extracted from tools.ts (incident cct-inbound-images-20260707) for two
 * reasons: (1) tools.ts sits near the repo's 512-line .ts cap and these
 * handlers grew (attachments join, row_id download path); (2) exporting
 * the bodies makes them unit-testable without standing up an MCP server
 * — the download dependency is injectable so tests can prove the
 * local_path short-circuit never touches the network. Registration
 * (schemas + dispatch) stays in tools.ts.
 */

import { existsSync } from "fs";
import { assertAllowedChat } from "./access.js";
import {
  getHistory,
  countHistory,
  getUnread,
  searchMessages,
  countSearchMatches,
  markAllRead,
  markReadRows,
  chatsForRows,
  attachmentsForRows,
  findAttachmentByFileId,
  markAttachmentDownloaded,
  loadLastPollTs,
  loadCoverageGap,
  type AttachmentRow,
} from "./store.js";
import {
  buildCoverage,
  assertValidCoverage,
  type IngestionCoverage,
} from "./ingestion-coverage.js";
import { downloadNow } from "./attachments.js";
import { log } from "./log.js";

/** Shape of an MCP CallTool result (the subset these handlers produce). */
export interface ToolResult {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
}

function textResult(text: string, isError = false): ToolResult {
  return isError
    ? { content: [{ type: "text", text }], isError: true }
    : { content: [{ type: "text", text }] };
}

function jsonResult(value: unknown): ToolResult {
  return textResult(JSON.stringify(value, null, 2));
}

/**
 * Join stored attachments onto message rows: each row that has any gets
 * an `attachments` array ({message_row_id, kind, file_id, file_name,
 * mime_type, local_path, downloaded_at, chat_id}); rows without stay
 * untouched (no empty-array noise). This is how an agent maps an
 * inbound "(photo) [attachment …]" line back to a file_id / local_path
 * from the DB instead of digging through raw_json.
 */
export async function withAttachments(
  rows: Array<Record<string, unknown>>,
): Promise<Array<Record<string, unknown>>> {
  const ids = rows
    .map((r) => Number(r.id))
    .filter((n) => Number.isFinite(n) && n > 0);
  if (ids.length === 0) return rows;
  const byRow = new Map<number, AttachmentRow[]>();
  for (const att of await attachmentsForRows(ids)) {
    const list = byRow.get(att.message_row_id) ?? [];
    list.push(att);
    byRow.set(att.message_row_id, list);
  }
  if (byRow.size === 0) return rows;
  return rows.map((r) => {
    const list = byRow.get(Number(r.id));
    return list ? { ...r, attachments: list } : r;
  });
}

/**
 * Read the store's own statement about whether it can vouch for what it just
 * returned. Best-effort: if the coverage probe itself fails, the caller still
 * gets its messages, with the failure stated (never a silent "covered").
 */
export async function currentCoverage(): Promise<IngestionCoverage> {
  try {
    const gap = await loadCoverageGap();
    const coverage = buildCoverage({
      lastPollTs: await loadLastPollTs(),
      lastGapAt: gap?.at ?? null,
      lastGapMissedUpdates: gap?.missedUpdates ?? null,
    });
    assertValidCoverage(coverage);
    return coverage;
  } catch (err) {
    log("tools", "coverage probe failed", { error: String(err) });
    return {
      verdict: "unverifiable",
      lastPollTs: null,
      pollStaleMs: null,
      stalenessThresholdMs: 0,
      lastGapAt: null,
      lastGapMissedUpdates: null,
      reason:
        `The coverage probe itself failed (${String(err)}), so this store` +
        " cannot say whether the result below is complete. Treat an empty" +
        " result as UNKNOWN, not as 'nothing was sent'.",
    };
  }
}

/**
 * Every message read answers in ONE shape: `{coverage, count, total, messages}`.
 *
 * It used to answer with a bare array, which made `[]` mean both "the
 * operator said nothing" and "this store recorded nothing for that window" —
 * the exact ambiguity that let 8h35m of scitex-dev's conversation read as a
 * quiet inbox on 2026-08-10. The fleet restart protocol tells every agent to
 * check this tool and NOT to assume a quiet inbox means nothing was sent; the
 * tool now carries the evidence needed to honour that instruction.
 *
 * `total` is every row the query matches, ignoring limit and offset. `count`
 * alone cannot tell "that is everything" from "that is one page": a page of 20
 * reads the same whether the chat holds 20 messages or 2,000.
 */
async function messagesResult(
  rows: Array<Record<string, unknown>>,
  total: number,
): Promise<ToolResult> {
  return jsonResult({
    coverage: await currentCoverage(),
    count: rows.length,
    total,
    messages: await withAttachments(rows),
  });
}

export async function handleGetHistory(
  args: Record<string, unknown>,
): Promise<ToolResult> {
  const chatId = args.chat_id as string;
  const limit = (args.limit as number) ?? 20;
  const offset = (args.offset as number) ?? 0;
  assertAllowedChat(chatId);
  const [rows, total] = await Promise.all([
    getHistory(chatId, limit, offset),
    countHistory(chatId),
  ]);
  return messagesResult(rows, total);
}

export async function handleGetUnread(
  args: Record<string, unknown>,
): Promise<ToolResult> {
  const chatId = args.chat_id as string | undefined;
  if (chatId) assertAllowedChat(chatId);
  const rows = await getUnread(chatId);
  // No limit: everything get_unread matched is on this page.
  return messagesResult(rows, rows.length);
}

/**
 * search_messages — the third message read, and now in the same shape.
 *
 * It was the one read left out when get_history and get_unread moved to
 * `{coverage, count, messages}` on 2026-08-15. For nine days after #132 it
 * returned a bare `{}` for every query (an un-awaited Promise, fixed in #140),
 * and three separate agents read that `{}` as "the store is empty" — one told
 * its user so. #140 turned it into a bare `[]`, which is honest about the rows
 * and still silent about whether the store can vouch for the window. That is
 * the ambiguity messagesResult exists to remove, so search goes through it too.
 */
/**
 * mark_read answers with what it ACTUALLY marked.
 *
 * It used to reply "marked N message(s) as read" with N = the ids it was GIVEN.
 * The update only touches rows that exist, are inbound and are still unread, so
 * any other id changed nothing and was reported as marked anyway. The likeliest
 * wrong input is a Telegram message_id passed where the DB row id belongs, and
 * both sit in every channel message. That path also never consulted the
 * allowlist, so rows of any chat could be marked.
 *
 * Every row's chat is now checked BEFORE anything is written, so one disallowed
 * row refuses the whole call with no partial write. The answer counts the rows
 * the database reports it changed and names the ids it could not mark.
 */
export async function handleMarkRead(
  args: Record<string, unknown>,
): Promise<ToolResult> {
  const chatId = args.chat_id as string | undefined;
  if (chatId) {
    assertAllowedChat(chatId);
    const marked = await markAllRead(chatId);
    return textResult(`marked ${marked} unread message(s) in ${chatId} as read`);
  }
  const requested = args.message_ids;
  if (!Array.isArray(requested) || requested.length === 0) {
    return textResult("provide chat_id or message_ids to mark as read", true);
  }
  // Digits only: the ids travel to the database as one comma-joined string.
  const notRowIds = requested.filter(
    (v) =>
      !(typeof v === "number" || (typeof v === "string" && /^\d+$/.test(v))) ||
      !Number.isSafeInteger(Number(v)) ||
      Number(v) <= 0,
  );
  if (notRowIds.length > 0) {
    throw new Error(
      "message_ids must be DB row ids (positive integers: the row_id in the " +
        `<channel> meta, not Telegram's message_id); got: ${notRowIds.join(", ")}`,
    );
  }
  const ids = [...new Set(requested.map(Number))];
  const found = await chatsForRows(ids);
  for (const chat of new Set(found.map((r) => r.chat_id))) {
    assertAllowedChat(chat);
  }
  const marked = new Set(await markReadRows(found.map((r) => r.id)));
  const foundIds = new Set(found.map((r) => r.id));
  const notFound = ids.filter((id) => !foundIds.has(id));
  const notMarkable = [...foundIds].filter((id) => !marked.has(id));
  let text = `marked ${marked.size} of ${ids.length} message(s) as read`;
  if (notFound.length > 0) text += `; not found: ${notFound.join(", ")}`;
  if (notMarkable.length > 0) {
    text += `; already read or not inbound: ${notMarkable.join(", ")}`;
  }
  return textResult(text);
}

export async function handleSearchMessages(
  args: Record<string, unknown>,
): Promise<ToolResult> {
  const query = args.query as string;
  const chatId = args.chat_id as string | undefined;
  const limit = (args.limit as number) ?? 20;
  if (chatId) assertAllowedChat(chatId);
  const [rows, total] = await Promise.all([
    searchMessages(query, chatId, limit),
    countSearchMatches(query, chatId),
  ]);
  return messagesResult(rows, total);
}

/**
 * download_attachment: accepts EITHER file_id OR row_id (the row_id from
 * the inbound <channel> meta / get_history — no raw_json digging).
 *
 * Resolution order:
 *   1. row_id → the message row's attachment record (clear error when
 *      the row has none — e.g. a plain-text message).
 *   2. file_id → the newest matching attachment record when one exists
 *      (an unknown file_id still downloads; it just can't short-circuit).
 * If the resolved record already has a local_path AND the file is still
 * on disk (auto-download completed, nothing pruned it), return that path
 * immediately — no network. Otherwise download and record the path so
 * the next call short-circuits.
 *
 * ALLOWLIST. A stored attachment's chat — and any chat_id passed — is checked
 * BEFORE that short-circuit. This tool used to check nothing, so the cached
 * return handed back any stored chat's file. (Rows exist only for chats that
 * were allowlisted when the message arrived, so the reach was a chat removed
 * from the allowlist since.) An unknown file_id with no chat_id still cannot be
 * attributed to any chat, and is downloaded as before.
 *
 * `download` is injectable for tests (defaults to the real downloadNow).
 */
export async function handleDownloadAttachment(
  args: Record<string, unknown>,
  download: (fileId: string, chatId: string) => Promise<string> = downloadNow,
): Promise<ToolResult> {
  if (args.chat_id) assertAllowedChat(args.chat_id as string);
  const fileIdArg = args.file_id as string | undefined;
  const rowIdArg = args.row_id != null ? Number(args.row_id) : undefined;
  if (!fileIdArg && rowIdArg == null) {
    return textResult(
      "provide file_id or row_id (row_id comes from the inbound message's meta / get_history)",
      true,
    );
  }

  let att: AttachmentRow | null = null;
  if (rowIdArg != null) {
    att = (await attachmentsForRows([rowIdArg]))[0] ?? null;
    if (!att) {
      return textResult(
        `no attachment recorded for row_id ${rowIdArg} — that message has no stored attachment. ` +
          "Check get_history for rows carrying an attachments array, or pass file_id directly.",
        true,
      );
    }
  } else if (fileIdArg) {
    att = await findAttachmentByFileId(fileIdArg);
  }

  if (att) assertAllowedChat(att.chat_id);

  if (att?.local_path && existsSync(att.local_path)) {
    return textResult(`downloaded to: ${att.local_path}`);
  }

  const fileId = fileIdArg ?? att!.file_id;
  const chatId = (args.chat_id as string) ?? att?.chat_id ?? "unknown";
  const localPath = await download(fileId, chatId);
  if (att) {
    // Persist so the next call (and get_history consumers) short-circuit.
    // Log-only on failure: the download itself succeeded and the caller
    // must still get the path.
    try {
      await markAttachmentDownloaded(
        att.message_row_id,
        att.file_id,
        localPath,
      );
    } catch (err) {
      log("tools", "failed to record download on attachment row", {
        error: String(err),
        fileId: att.file_id,
      });
    }
  }
  return textResult(`downloaded to: ${localPath}`);
}
