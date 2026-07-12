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

import { pollerPidfilePath, readPidfile, isPidAlive } from "./takeover.js";
import { log } from "./log.js";

/** Minimal shape ensurePollerRunning needs from a spawned child handle —
 * satisfied by Bun.Subprocess, and trivially fakeable in tests. */
export interface SpawnedProcessHandle {
  pid: number;
  unref(): void;
}

export interface EnsurePollerDeps {
  /** Absolute path to the standalone poller entrypoint script
   * (ts/telegram-poller.ts) to spawn when no live poller is found. */
  pollerScriptPath: string;
  stateDir: string;
  tokenHash: string;
  /** Injectable pidfile reader; defaults to the real lib/takeover.ts pidfile
   * at (stateDir, tokenHash). */
  readPid?: (stateDir: string, tokenHash: string) => { pid: number } | null;
  /** Injectable liveness check; defaults to kill(pid, 0) (lib/takeover.ts::isPidAlive). */
  isAlive?: (pid: number) => boolean;
  /** Injectable spawn primitive; defaults to a detached, stdio-ignored
   * Bun.spawn of [process.execPath, "run", pollerScriptPath]. */
  spawn?: (cmd: string[]) => SpawnedProcessHandle;
  logFn?: typeof log;
}

export type EnsurePollerResult =
  | { action: "already-running"; pid: number }
  | { action: "spawned"; pid: number };

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
 */
export function ensurePollerRunning(
  deps: EnsurePollerDeps,
): EnsurePollerResult {
  const readPid = deps.readPid ?? defaultReadPid;
  const isAlive = deps.isAlive ?? isPidAlive;
  const spawn = deps.spawn ?? defaultSpawn;
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

  const child = spawn([process.execPath, "run", deps.pollerScriptPath]);
  child.unref();
  logFn("poller-supervisor", "spawned standalone poller process", {
    pid: child.pid,
    script: deps.pollerScriptPath,
  });
  return { action: "spawned", pid: child.pid };
}
