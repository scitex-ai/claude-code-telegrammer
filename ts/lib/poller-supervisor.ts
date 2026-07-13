/**
 * Cross-process poller supervisor for the MCP server process.
 *
 * Architecture fix (incident-cct-inbound-dies-silently-with-mcp-server-
 * 20260711 follow-up, 2026-07): the MCP server (ts/telegram-server.ts) no
 * longer runs the getUpdates poll loop on its own event loop — see
 * docs/architecture.md. Instead, at startup it calls ensurePollerRunning()
 * to check whether a standalone poller process (ts/telegram-poller.ts) is
 * already alive for this bot token (via the lib/takeover.ts per-token
 * pidfile) and, if not, spawns a fresh one DETACHED (stdio:"ignore",
 * detached:true) + unref()'d so the MCP server's own event loop never waits
 * on it. This is what makes the poller survive an MCP-server restart: an
 * MCP-child recycle (Claude Code restarting its own MCP child under host
 * load — the ORIGINAL incident) no longer tears down inbound Telegram
 * delivery, because the poller is a wholly separate OS process by then (see
 * telegram-server.ts's shutdown(), which no longer calls stopPolling() /
 * releaseAuthoritative() for exactly this reason).
 *
 * Every dependency is injectable so the conditional-spawn DECISION is unit-
 * testable without ever forking a real process — the same injectable-seam
 * pattern poller-batch.ts / poll-watchdog.ts already use for their own
 * network/timer/notification seams. The default spawn primitive is
 * Bun.spawn (this codebase is Bun-first throughout — bun:sqlite,
 * Bun.CryptoHasher, Bun.write — and has zero prior child_process usage to
 * follow instead), invoked via process.execPath (the actual bun binary
 * currently running us, resolved the same way the Python CLI wrapper's
 * _resolve_bun() avoids assuming "bun" is on PATH) rather than a bare
 * "bun" string.
 *
 * env is passed EXPLICITLY as `process.env` (empirically verified — see
 * ts/test/poller-supervisor.test.ts — NOT to be assumed): omitting the
 * `env` key entirely still inherits whatever was present in the OS
 * environment at THIS process's own startup, but does NOT reflect any
 * later runtime `process.env.X = ...` mutation, at least on Bun 1.3.11.
 * The realistic launch path (env vars set by the container/shell before
 * `bun run ts/telegram-server.ts` even starts) would have worked either
 * way, but making this explicit removes any doubt — this env is exactly
 * what scitex-agent-container's orphan reaper matches
 * SAC_NAME/SCITEX_AGENT_CONTAINER_NAME against (see lib/poller-teardown.ts)
 * to eventually reap this detached process on genuine agent teardown, so
 * "probably inherited" was not good enough here.
 */

import {
  pollerPidfilePath,
  readPidfile,
  isProcessMatching,
} from "./takeover.js";
import { log } from "./log.js";
import { broadcastSystemAlert } from "./loudfail.js";

/** Minimal shape ensurePollerRunning needs from a spawned child handle —
 * satisfied by Bun.Subprocess, and trivially fakeable in tests. */
export interface SpawnedProcessHandle {
  pid: number;
  unref(): void;
  /** Resolves with the child's exit code once it exits — used for the
   * post-spawn grace-window death check (adversarial-review finding #4). */
  exited: Promise<number>;
}

/**
 * How long after a successful spawn() call an early exit is treated as a
 * POSSIBLE startup failure worth investigating (see the pidfile re-check
 * in the exit observer below — this window is NOT itself proof of a
 * crash). RECONCILED (round-2 adversarial review: two comments in this
 * file previously disagreed on this): a legitimate "newest wins" takeover
 * preemption (lib/takeover.ts::claimAuthoritative's SIGTERM) does NOT
 * happen "much later" — it happens as soon as a newer poller's own
 * startPolling() runs claimAuthoritative(), which is the FIRST thing that
 * function does, i.e. essentially immediately after that newer poller's
 * own process starts. Combined with the losing poller's own shutdown()
 * taking a fixed 2000ms (ts/telegram-poller.ts), a clean, correct
 * preemption routinely lands INSIDE this 3000ms window. That is exactly
 * why the exit observer below does not alert on aliveMs<graceMs alone.
 */
const SPAWN_GRACE_MS = 3000;

export interface EnsurePollerDeps {
  /** Absolute path to the standalone poller entrypoint script
   * (ts/telegram-poller.ts) to spawn when no live poller is found. */
  pollerScriptPath: string;
  stateDir: string;
  tokenHash: string;
  /** Injectable pidfile reader; defaults to the real lib/takeover.ts pidfile
   * at (stateDir, tokenHash). */
  readPid?: (stateDir: string, tokenHash: string) => { pid: number } | null;
  /** Injectable liveness check; defaults to an IDENTITY-AWARE check
   * (lib/takeover.ts::isProcessMatching against THIS agent's own
   * pollerScriptPath, not the generic POLLER_CMDLINE_MARKER — round-2
   * adversarial review: the generic "telegram-poller" substring would
   * also match a genuinely-real telegram-poller process belonging to a
   * DIFFERENT agent on a busy multi-agent host, if a stale pidfile's PID
   * got reused for one. Matching the full, agent-specific script path
   * closes that almost for free), not a bare kill(pid,0) — a stale
   * pidfile's PID can be reused by the OS for an unrelated process, which
   * a plain existence check can't tell apart from the real poller. */
  isAlive?: (pid: number) => boolean;
  /** Injectable spawn primitive; defaults to a detached, stdio-ignored
   * Bun.spawn of [process.execPath, "run", pollerScriptPath]. */
  spawn?: (cmd: string[]) => SpawnedProcessHandle;
  /** Injectable grace-window threshold (ms) for the post-spawn early-death
   * alert; defaults to SPAWN_GRACE_MS. Tests inject a tiny value instead
   * of waiting out the real 3s default. */
  graceMs?: number;
  logFn?: typeof log;
}

export type EnsurePollerResult =
  | { action: "already-running"; pid: number }
  | { action: "spawned"; pid: number }
  | { action: "spawn-failed"; error: string };

function defaultReadPid(
  stateDir: string,
  tokenHash: string,
): { pid: number } | null {
  return readPidfile(pollerPidfilePath(stateDir, tokenHash));
}

function defaultSpawn(cmd: string[]): SpawnedProcessHandle {
  // detached:true (POSIX setsid) so the child survives this process exiting
  // /restarting; stdio:"ignore" so it never blocks on an inherited pipe
  // nobody is reading; env:process.env EXPLICITLY (not omitted — see the
  // module header) so the spawned poller reliably carries
  // SAC_NAME/SCITEX_AGENT_CONTAINER_NAME and every CCT_*/
  // CLAUDE_CODE_TELEGRAMMER_* var this MCP-server process itself resolved
  // from. See the module header for why Bun.spawn specifically.
  return Bun.spawn(cmd, {
    stdio: ["ignore", "ignore", "ignore"],
    detached: true,
    env: process.env,
  });
}

/**
 * Ensure a standalone poller process is running for (stateDir, tokenHash).
 *
 * If the takeover.ts pidfile already records a live PID, this is a no-op —
 * an external poller is already running (most commonly: a PREVIOUS
 * telegram-server.ts incarnation's spawn, still alive across this MCP-server
 * restart, which is precisely the property this whole architecture change
 * exists to provide). Otherwise spawns a fresh detached poller process and
 * returns immediately without awaiting or otherwise waiting on it — the
 * newly-spawned poller performs its own "newest wins" takeover claim inside
 * startPolling() (lib/poller.ts, unchanged), so even a missed-liveness race
 * here (TOCTOU between the read and the spawn) self-heals: at worst two
 * pollers briefly race and the older one is preempted, never both running
 * forever.
 *
 * NOTED, NOT ACTED ON (adversarial review, follow-up pass): the SAME
 * TOCTOU also applies between two SEPARATE ensurePollerRunning() calls
 * (e.g. two near-simultaneous MCP-server starts) both reading "no live
 * poller" and both deciding to spawn. Reviewed and assessed as benign in
 * practice — the DB-level dedup (takeover.ts's pidfile "newest wins"
 * claim) plus the poll loop's own per-iteration isAuthoritative() check
 * already resolve it the same way, self-healing rather than silent. Left
 * as documented behaviour rather than adding a redundant guard here.
 */
export function ensurePollerRunning(
  deps: EnsurePollerDeps,
): EnsurePollerResult {
  const readPid = deps.readPid ?? defaultReadPid;
  // Agent-specific: matches THIS agent's own poller script path, not the
  // generic POLLER_CMDLINE_MARKER substring (round-2 adversarial review
  // finding #4) — closes the (admittedly narrow) gap where a stale
  // pidfile's PID gets reused by the OS for a genuinely-real
  // telegram-poller process belonging to a DIFFERENT agent on a busy
  // multi-agent host.
  const isAlive =
    deps.isAlive ??
    ((pid: number) => isProcessMatching(pid, deps.pollerScriptPath));
  const spawn = deps.spawn ?? defaultSpawn;
  const graceMs = deps.graceMs ?? SPAWN_GRACE_MS;
  const logFn = deps.logFn ?? log;

  const snap = readPid(deps.stateDir, deps.tokenHash);
  if (snap && isAlive(snap.pid)) {
    logFn(
      "poller-supervisor",
      "external poller already running — not spawning a new one",
      { pid: snap.pid },
    );
    return { action: "already-running", pid: snap.pid };
  }

  // The spawn call itself can throw (missing binary, exhausted process
  // limits, bad script path, ...) — this must be LOUD, not silent
  // (adversarial-review finding #4): fire-and-forget was previously wired
  // with no try/catch anywhere in the chain, so a failed spawn would
  // vanish until the next MCP-server restart with nobody the wiser.
  let child: SpawnedProcessHandle;
  try {
    child = spawn([process.execPath, "run", deps.pollerScriptPath]);
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    const msg =
      `FATAL: failed to spawn the standalone poller process ` +
      `(${deps.pollerScriptPath}): ${errMsg} — inbound Telegram delivery ` +
      `is NOT running.`;
    logFn("poller-supervisor", msg);
    void broadcastSystemAlert(msg);
    return { action: "spawn-failed", error: errMsg };
  }
  child.unref();
  logFn("poller-supervisor", "spawned standalone poller process", {
    pid: child.pid,
    script: deps.pollerScriptPath,
  });

  // Grace-window death check: a child that exits within SPAWN_GRACE_MS of
  // being spawned is a POSSIBLE sign of an immediate startup failure (e.g.
  // issue #1's migration race, before it was fixed, or any other early
  // crash) — but NOT proof of one. A legitimate "newest wins" takeover
  // preemption (claimAuthoritative()'s SIGTERM, lib/takeover.ts) routinely
  // lands inside this same window (see SPAWN_GRACE_MS's docstring above —
  // it does NOT happen "much later" as an earlier version of this comment
  // wrongly claimed). Round-2 adversarial review finding #2: alerting on
  // aliveMs<graceMs ALONE would cry wolf on that entirely correct,
  // self-healing outcome (a newer poller is alive and driving delivery
  // just fine under a different PID) — exactly the kind of false alarm
  // that undercuts trust in every OTHER alert this PR adds. So before
  // alerting, re-read the pidfile: if it now names a DIFFERENT, live PID,
  // that's the signature of a legitimate takeover, not a crash — log it
  // quietly and do not page anyone. Best-effort throughout: logged +
  // alerted (or not), never thrown — this must not crash the caller.
  const spawnedAt = Date.now();
  void child.exited
    .then((code) => {
      const aliveMs = Date.now() - spawnedAt;
      if (aliveMs >= graceMs) return; // ordinary lifecycle — nothing to check

      const current = readPid(deps.stateDir, deps.tokenHash);
      if (current && current.pid !== child.pid && isAlive(current.pid)) {
        logFn(
          "poller-supervisor",
          "spawned poller exited early, but a DIFFERENT live poller now " +
            "holds the pidfile — legitimate newest-wins takeover, not a " +
            "crash; delivery is still running",
          {
            exitedPid: child.pid,
            currentPid: current.pid,
            aliveMs,
            exitCode: code,
          },
        );
        return;
      }

      const msg =
        `FATAL: standalone poller process (pid ${child.pid}) exited ` +
        `with code ${code} only ${aliveMs}ms after spawning, and no ` +
        `OTHER live poller has taken over the pidfile — inbound Telegram ` +
        `delivery is likely NOT running. Check the poller's own ` +
        `logs/stderr for the real cause.`;
      logFn("poller-supervisor", msg);
      void broadcastSystemAlert(msg);
    })
    .catch((err) => {
      // .exited itself rejecting is exotic but must not go unnoticed either.
      logFn("poller-supervisor", "failed to observe spawned poller exit", {
        pid: child.pid,
        error: String(err),
      });
    });

  return { action: "spawned", pid: child.pid };
}
