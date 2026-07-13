/**
 * Background download queue for Telegram file attachments.
 * Rate-limited: max 1 download per 500ms.
 * On failure: log error, mark for retry on next restart (don't retry immediately).
 */

import { join } from "path";
import { mkdirSync } from "fs";
import { Database } from "bun:sqlite";
import { ATTACHMENT_DIR } from "./config.js";
import { DB_PATH } from "./store.js";
import { getFile, downloadFile } from "./telegram-api.js";
import { log } from "./log.js";

interface QueueItem {
  messageRowId: number;
  fileId: string;
  kind: string;
  chatId: string;
}

const queue: QueueItem[] = [];
let processing = false;

// ── DB access (reuse the same DB file as store.ts) ────────────────────────

function getDb(): Database {
  const db = new Database(DB_PATH);
  // busy_timeout is per-CONNECTION, not persisted in the file — WAL mode
  // (set once, at schema-creation time) does NOT imply every later
  // connection inherits a nonzero busy_timeout (adversarial-review finding
  // #6: this ad hoc handle had none, defaulting to 0 — zero tolerance for
  // lock contention against the poller's own writes).
  db.exec("PRAGMA busy_timeout = 5000;");
  return db;
}

// ── Public API ────────────────────────────────────────────────────────────

export function queueDownload(
  messageRowId: number,
  fileId: string,
  kind: string,
  chatId: string,
): void {
  queue.push({ messageRowId, fileId, kind, chatId });
  if (!processing) {
    void processQueue();
  }
}

/**
 * Immediately download a single file (bypasses queue).
 * Returns the local path on success.
 */
export async function downloadNow(
  fileId: string,
  chatId: string,
): Promise<string> {
  const { file_path } = await getFile(fileId);
  const now = new Date();
  const monthDir = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const localDir = join(ATTACHMENT_DIR, chatId, monthDir);
  mkdirSync(localDir, { recursive: true });
  const localPath = await downloadFile(file_path, localDir);
  return localPath;
}

// ── Background loop ──────────────────────────────────────────────────────

async function processQueue(): Promise<void> {
  processing = true;
  while (queue.length > 0) {
    const item = queue.shift()!;
    try {
      const localPath = await downloadNow(item.fileId, item.chatId);

      // Update attachments table
      try {
        const db = getDb();
        db.prepare(
          `UPDATE attachments SET local_path = ?, downloaded_at = datetime('now')
           WHERE message_row_id = ? AND file_id = ?`,
        ).run(localPath, item.messageRowId, item.fileId);
        db.close();
      } catch (dbErr) {
        log("attachments", "failed to update DB after download", {
          error: String(dbErr),
          fileId: item.fileId,
        });
      }

      log("attachments", "downloaded", {
        fileId: item.fileId,
        localPath,
      });
    } catch (err) {
      log("attachments", "download failed (will retry on restart)", {
        error: String(err),
        fileId: item.fileId,
        kind: item.kind,
      });
    }

    // Rate limit: 500ms between downloads
    if (queue.length > 0) {
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  processing = false;
}
