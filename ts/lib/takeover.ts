/**
 * Per-bot-token "newest wins" poller takeover.
 *
 * Background (operator pain, 2026-06-07):
 *   Restarting an agent's container does NOT reliably kill the previous
 *   `bun run telegram-server.ts` poller — Apptainer + tini leave it as an
 *   orphan attached to the host. The next start spawns a NEW poller for
 *   the same bot token; Telegram's getUpdates only allows ONE consumer
 *   per token, so both end up in a 409 conflict loop and the operator's
 *   messages are silently dropped (no 👀 reaction, no reply).
 *
 *   The previous behaviour ("oldest wins" — old poller holds the lock,
 *   new one exits) makes this WORSE: the live, current process loses to
 *   a dead-parent zombie that nothing will ever clean up.
 *
 * Fix:
 *   This module implements "newest wins" via a per-token pidfile.
 *
 *     - claimAuthoritative()  : write our (pid, startMs) into the
 *                               pidfile, atomically replacing whatever
 *                               was there. Best-effort SIGTERM the
 *                               outgoing PID so it can shut down cleanly
 *                               instead of waiting for its next poll
 *                               iteration to notice.
 *     - isAuthoritative()     : read the pidfile and return true iff our
 *                               pid is still the one recorded.
 *     - releaseAuthoritative(): unlink the pidfile (only if we still own
 *                               it; never tear down someone else's
 *                               claim).
 *
 *   The polling loop (poller.ts) calls isAuthoritative() every iteration.
 *   When a newer poller starts up, it overwrites the pidfile; the
 *   incumbent's NEXT loop tick sees its pid is no longer recorded and
 *   exits cleanly — no 409 storm, no orphan.
 *
 *   SIGTERM is best-effort because the incumbent may live in a different
 *   PID namespace (apptainer container vs host vs sibling container);
 *   the pidfile-polling-loop fallback works regardless of namespace as
 *   long as the filesystem path is bind-mounted into both.
 *
 * Pidfile format (newline-separated, plaintext, ASCII):
 *     <pid>
 *     <startMs>
 *
 *   startMs is Date.now() at claim time. Used purely for observability
 *   ("how old is the current claim?") — the takeover protocol itself
 *   only needs the pid line.
 */

import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "fs";
import { join } from "path";

/** Result of reading the pidfile. null when no pidfile / unparseable. */
export interface PidfileSnapshot {
  pid: number;
  startMs: number;
}

/**
 * Compute the canonical pidfile path for a given (stateDir, tokenHash).
 * Public so tests can exercise the path-construction rule directly.
 */
export function pollerPidfilePath(stateDir: string, tokenHash: string): string {
  return join(stateDir, `poller-${tokenHash}.pid`);
}

/**
 * Read the pidfile at `path`. Returns null when:
 *   - the file does not exist,
 *   - the file content is not a parseable (pid, startMs) pair,
 *   - any other read error occurs (best-effort).
 */
export function readPidfile(path: string): PidfileSnapshot | null {
  if (!existsSync(path)) return null;
  let raw: string;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    return null;
  }
  const lines = raw.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length < 1) return null;
  const pid = parseInt(lines[0]!.trim(), 10);
  if (!Number.isFinite(pid) || pid <= 0) return null;
  const startMs = lines[1] !== undefined ? parseInt(lines[1].trim(), 10) : 0;
  return {
    pid,
    startMs: Number.isFinite(startMs) ? startMs : 0,
  };
}

/**
 * Returns true iff `pid` looks alive (process.kill(pid, 0) doesn't
 * throw). Throws nothing — best-effort. May return a stale `true` when
 * called across PID namespaces where the local PID happens to also
 * exist locally; the pidfile-polling fallback handles that.
 */
export function isPidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/**
 * Distinctive cmdline substrings for identity verification beyond plain
 * PID existence (see isProcessMatching). Chosen to match what scitex-
 * agent-container's own orphan reaper
 * (_lifecycle/_orphan_mcp_cleanup.py::kill_orphan_mcp_children) already
 * looks for in a process's cmdline — one shared source of truth for
 * "is this really ours", not two different heuristics maintained
 * separately.
 */
export const POLLER_CMDLINE_MARKER = "telegram-poller";
export const SERVER_CMDLINE_MARKER = "telegram-server";

// Cached once at module load: does this host even have /proc? Avoids a
// syscall per check on platforms where /proc never exists (e.g. macOS).
const HAS_PROC = existsSync("/proc");

/**
 * Identity-aware liveness check beyond isPidAlive's plain existence test
 * (adversarial-review finding: a stale pidfile's PID can be REUSED by the
 * OS for an unrelated process after the original poller exited —
 * plausible on a long-lived, busy, multi-agent host where PIDs wrap. A
 * bare kill(pid,0) can't tell that apart from the real thing, which would
 * make a consumer conclude "already running/alive" and never notice the
 * real process is gone — silently, until something else forces a
 * restart. Both lib/poller-supervisor.ts::ensurePollerRunning and
 * lib/health-adapters.ts::probePoller read this SAME function so there is
 * one shared verification, not two different heuristics.
 *
 * Reads /proc/<pid>/cmdline (Linux) and requires it to contain
 * `cmdlineSubstring`. Biased toward FALSE NEGATIVES over false positives,
 * on purpose: wrongly concluding "not ours" merely triggers an extra
 * poller spawn (self-heals via the newest-wins takeover protocol below);
 * wrongly concluding "alive and ours" is the silent, unrecoverable-until-
 * restart failure this exists to prevent. An unreadable/mismatched
 * cmdline on a /proc-having host therefore returns false, not "assume
 * it's fine".
 *
 * On a platform with no /proc at all (checked once at module load), falls
 * back to the plain existence check — preserves prior behaviour there
 * rather than making every non-Linux host permanently distrust its own
 * processes.
 */
export function isProcessMatching(
  pid: number,
  cmdlineSubstring: string,
): boolean {
  if (!isPidAlive(pid)) return false;
  if (!HAS_PROC) return true;
  try {
    const cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf8").replace(
      /\0/g,
      " ",
    );
    return cmdline.includes(cmdlineSubstring);
  } catch {
    return false;
  }
}

/**
 * Atomically (best-effort) claim authoritativeness for `tokenHash` from
 * inside `stateDir`. Returns a snapshot of the OUTGOING claim (the
 * record that was in the pidfile before we wrote ours), or null if the
 * pidfile was absent / unparseable.
 *
 * Side effects:
 *   1. mkdir -p stateDir
 *   2. read pidfile (capture outgoing snapshot for the caller)
 *   3. if outgoing.pid is alive AND outgoing.pid !== our pid → send
 *      SIGTERM to it (best-effort; ignores ESRCH / EPERM / namespace
 *      isolation). The outgoing poller's signal handler shuts it down
 *      cleanly.
 *   4. write our pidfile (overwriting any previous content) with our
 *      pid on line 1 and the supplied startMs on line 2.
 *
 * `startMs` defaults to Date.now(). Tests pass a deterministic value.
 * `signalOutgoing` defaults to true; tests can pass false to verify the
 * pidfile is rewritten even when no signal is sent.
 */
export function claimAuthoritative(opts: {
  stateDir: string;
  tokenHash: string;
  pid?: number;
  startMs?: number;
  signalOutgoing?: boolean;
}): PidfileSnapshot | null {
  const pid = opts.pid ?? process.pid;
  const startMs = opts.startMs ?? Date.now();
  const signal = opts.signalOutgoing ?? true;
  const path = pollerPidfilePath(opts.stateDir, opts.tokenHash);

  mkdirSync(opts.stateDir, { recursive: true });

  const outgoing = readPidfile(path);

  if (signal && outgoing && outgoing.pid !== pid && isPidAlive(outgoing.pid)) {
    try {
      process.kill(outgoing.pid, "SIGTERM");
    } catch {
      // best-effort — outgoing may be in another PID namespace
    }
  }

  // Atomic-ish overwrite: write tmp + rename. Same-filesystem rename is
  // atomic on POSIX, so a reader either sees the old or the new pidfile,
  // never a partial write.
  const tmp = `${path}.tmp.${pid}.${startMs}`;
  writeFileSync(tmp, `${pid}\n${startMs}\n`, { mode: 0o600 });
  renameSync(tmp, path);

  return outgoing;
}

/**
 * Returns true iff the pidfile still records `pid` as the authoritative
 * owner. The polling loop calls this once per iteration; a newer poller
 * having overwritten the pidfile flips this to false and the incumbent
 * exits cleanly without producing a 409 storm.
 */
export function isAuthoritative(opts: {
  stateDir: string;
  tokenHash: string;
  pid?: number;
}): boolean {
  const pid = opts.pid ?? process.pid;
  const path = pollerPidfilePath(opts.stateDir, opts.tokenHash);
  const snap = readPidfile(path);
  if (!snap) return false;
  return snap.pid === pid;
}

/**
 * Why the pidfile does not name us — the distinction isAuthoritative() throws
 * away, and the one that cost the operator his inbound channel repeatedly on
 * 2026-07-14.
 *
 *   "ours"      — the pidfile records us. Keep polling.
 *   "preempted" — it records a DIFFERENT pid. A newer poller genuinely won the
 *                 race; stand down immediately so we never issue another
 *                 getUpdates and start a 409 storm against the new incumbent.
 *   "vacant"    — there is NO pidfile. Nobody preempted us. Nobody owns it.
 *
 * isAuthoritative() collapses "vacant" and "preempted" into a single `false`,
 * and the poll loop then logged "preempted by newer poller" and killed itself.
 * But a file that VANISHED is not a successor. Deleting a file must never kill
 * a healthy process — and it did: the log shows a poller exiting "cleanly"
 * while its replacement started up finding "no prior poller recorded", i.e.
 * nobody had taken over at all. Inbound Telegram delivery just stopped.
 */
export type AuthorityState =
  | { kind: "ours" }
  | { kind: "vacant" }
  | { kind: "stale"; byPid: number }
  | { kind: "preempted"; byPid: number };

export function checkAuthority(opts: {
  stateDir: string;
  tokenHash: string;
  pid?: number;
  /** Injectable liveness probe (tests); defaults to a kill(pid, 0). */
  isAlive?: (pid: number) => boolean;
}): AuthorityState {
  const pid = opts.pid ?? process.pid;
  const alive = opts.isAlive ?? isPidAlive;

  const snap = readPidfile(pollerPidfilePath(opts.stateDir, opts.tokenHash));
  if (!snap) return { kind: "vacant" };
  if (snap.pid === pid) return { kind: "ours" };

  // A pidfile naming a DEAD process is not a successor either.
  //
  // This is the same mistake as "vacant", wearing a disguise. The record exists,
  // so it LOOKS like someone took over — but the process it names is gone. It is
  // a stale claim, and standing down for it hands the bot token to nobody and
  // takes inbound Telegram delivery with it.
  //
  // This is exactly how it happened on 2026-07-14: a test run whose hermetic
  // preload had not loaded (see lib/hermetic-guard.ts) resolved STATE_DIR to the
  // LIVE bridge and called claimAuthoritative() against it, stamping the live
  // pidfile with the TEST process's pid. The test exited seconds later. The real,
  // healthy poller then read a pidfile naming a pid that no longer existed,
  // concluded it had been preempted, and killed itself. The operator's channel
  // died for a corpse.
  //
  // Preemption is only real if the preemptor is ALIVE.
  if (!alive(snap.pid)) return { kind: "stale", byPid: snap.pid };

  return { kind: "preempted", byPid: snap.pid };
}

/**
 * Release our claim by unlinking the pidfile — but ONLY if we still own
 * it. If a newer poller has overwritten it, we must NOT delete their
 * record. Best-effort; failures are silent.
 */
export function releaseAuthoritative(opts: {
  stateDir: string;
  tokenHash: string;
  pid?: number;
}): void {
  const pid = opts.pid ?? process.pid;
  const path = pollerPidfilePath(opts.stateDir, opts.tokenHash);
  const snap = readPidfile(path);
  if (!snap) return;
  if (snap.pid !== pid) return; // someone else owns it now
  try {
    unlinkSync(path);
  } catch {
    // ignore — best-effort
  }
}
