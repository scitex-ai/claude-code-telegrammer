/**
 * Filesystem questions about the poller: where its log lives, and how fresh its
 * code on disk is.
 *
 * Split out of poller-supervisor.ts, which had grown past the line limit by
 * mixing three jobs: supervising a child process, deciding what to tell the
 * operator (now lib/supervisor-messages.ts), and stat'ing files (here). None of
 * these needs the others to be understood.
 */

import { readdirSync, statSync } from "fs";
import { dirname, join } from "path";

/**
 * Newest mtime (ms) across the poller's own source: its entrypoint plus every
 * ts/lib/*.ts it imports. Returns 0 if nothing can be stat'd.
 *
 * Used to answer one question: "could the running poller possibly have loaded
 * the code that is on disk right now?" If a source file was modified AFTER the
 * poller claimed the pidfile, then no — that process is running stale code.
 */
export function newestCodeMtimeMs(pollerScriptPath: string): number {
  let newest = 0;
  const consider = (path: string) => {
    try {
      const { mtimeMs } = statSync(path);
      if (mtimeMs > newest) newest = mtimeMs;
    } catch {
      // Unreadable file — ignore it rather than let one bad stat decide that
      // a healthy poller is stale. See the fail-safe note in the caller.
    }
  };

  consider(pollerScriptPath);
  const libDir = join(dirname(pollerScriptPath), "lib");
  try {
    for (const entry of readdirSync(libDir)) {
      if (entry.endsWith(".ts")) consider(join(libDir, entry));
    }
  } catch {
    // No lib dir (unexpected layout) — the entrypoint mtime alone still works.
  }
  return newest;
}

/** Where the detached poller's stderr is persisted. */
export function pollerLogPath(stateDir: string, tokenHash: string): string {
  return join(stateDir, `poller-${tokenHash}.log`);
}
