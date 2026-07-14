/**
 * ensurePollerRunning: stale-code takeover.
 *
 * incident-cct-operator-messages-not-arriving-20260714.
 *
 * The detached poller surviving an MCP-server restart is the whole point of
 * the process split — but it means the poller also survives a CODE UPDATE, so
 * "restart the server to deploy" silently does nothing to it. Every agent on
 * the host launches the SAME checkout
 * (/home/ywatanabe/proj/claude-code-telegrammer/ts/telegram-server.ts — 49 of
 * 49 agent .mcp.json files at the time of writing), so a single `git pull`
 * would otherwise leave every poller on the box running pre-pull code
 * indefinitely, each sitting next to a freshly-updated MCP server with no
 * signal that the two disagree.
 *
 * That is precisely the drift that produced the incident: v0.5.6 was released,
 * merged, published — and never actually running.
 *
 * Lives in its own file because ts/test/poller-supervisor.test.ts is already
 * at the project's 512-line ceiling.
 */

import { describe, test, expect } from "bun:test";
import {
  ensurePollerRunning,
  type SpawnedProcessHandle,
} from "../lib/poller-supervisor.js";

function fakeSpawnHandle(pid: number): SpawnedProcessHandle {
  return {
    pid,
    unref: () => {},
    // Never resolves: keeps the grace-window death observer from firing during
    // the test, which is not what these cases are about.
    exited: new Promise<number>(() => {}),
  };
}

describe("ensurePollerRunning: stale-code takeover", () => {
  const POLLER_STARTED = 1_000_000;

  function run(opts: { startMs?: number; codeMtimeMs: number }) {
    let spawnCalls = 0;
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "deadbeef",
      readPid: () => ({ pid: 4242, startMs: opts.startMs }),
      isAlive: (pid) => pid === 4242, // the incumbent IS alive and healthy
      codeMtimeMs: () => opts.codeMtimeMs,
      spawn: () => {
        spawnCalls += 1;
        return fakeSpawnHandle(999);
      },
      logFn: () => {},
    });
    return { action: result.action, spawnCalls };
  }

  test("takes over a live poller whose source was modified after it started", () => {
    const { action, spawnCalls } = run({
      startMs: POLLER_STARTED,
      codeMtimeMs: POLLER_STARTED + 60_000, // a git pull landed after it booted
    });

    // Spawns DESPITE the incumbent being alive: the replacement wins the
    // pidfile via claimAuthoritative() and the incumbent stands down on its
    // next per-iteration isAuthoritative() check (lib/poller.ts).
    expect(action).toBe("spawned");
    expect(spawnCalls).toBe(1);
  });

  test("leaves a live poller alone when its source predates it", () => {
    const { action, spawnCalls } = run({
      startMs: POLLER_STARTED,
      codeMtimeMs: POLLER_STARTED - 60_000,
    });

    expect(action).toBe("already-running");
    expect(spawnCalls).toBe(0);
  });

  // The fail-safe direction is the one that actually matters. An unnecessary
  // respawn of a HEALTHY poller — on every agent on the host at once — is a
  // worse outcome than a late deploy, so anything we cannot positively
  // establish must resolve to "leave the incumbent alone".
  test("FAIL-SAFE: unknown code mtime (stat failed) does not take over", () => {
    const { action, spawnCalls } = run({
      startMs: POLLER_STARTED,
      codeMtimeMs: 0,
    });

    expect(action).toBe("already-running");
    expect(spawnCalls).toBe(0);
  });

  test("FAIL-SAFE: unknown poller start time does not take over", () => {
    const { action, spawnCalls } = run({
      startMs: undefined, // pre-fix or unparseable pidfile
      codeMtimeMs: POLLER_STARTED + 60_000,
    });

    expect(action).toBe("already-running");
    expect(spawnCalls).toBe(0);
  });
});
