/**
 * The poller's death must be LOUD and SELF-HEALING.
 *
 * This fired live on 2026-07-14, while the incident it belongs to was still
 * open. The poller (spawned 37 minutes earlier) vanished. Inbound Telegram
 * delivery stopped dead. NOTHING noticed:
 *
 *   - the supervisor early-returned ("aliveMs >= graceMs → ordinary lifecycle"),
 *   - the poller's stderr went to /dev/null (spawned stdio:"ignore"), so its
 *     cause of death was unrecoverable by construction,
 *   - poll-watchdog.ts runs INSIDE the poller, so it died with it,
 *   - ensurePollerRunning only runs at MCP-server startup, so nothing respawned.
 *
 * The operator saw silence, and had no way to tell it apart from us having
 * nothing to say. That IS the incident, recurring in a new shape after the
 * first fix.
 *
 * The age gate bought nothing: what actually separates a crash from a
 * legitimate "newest wins" takeover is whether a DIFFERENT live poller now
 * holds the pidfile — equally answerable at 37 minutes as at 300ms.
 */

import { describe, test, expect } from "bun:test";
import {
  ensurePollerRunning,
  type SpawnedProcessHandle,
} from "../lib/poller-supervisor.js";

/** A handle whose exit we control. */
function controllable(pid: number) {
  let settle: (code: number) => void = () => {};
  const exited = new Promise<number>((resolve) => {
    settle = resolve;
  });
  const handle: SpawnedProcessHandle = { pid, unref: () => {}, exited };
  return { handle, die: (code = 1) => settle(code) };
}

const flush = () => new Promise((r) => setTimeout(r, 20));

describe("poller death is loud and self-healing", () => {
  test("a poller that dies LONG after the grace window is respawned, not ignored", async () => {
    const spawned: number[] = [];
    const first = controllable(1111);
    const second = controllable(2222);

    ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "deadbeef",
      readPid: () => null, // no incumbent, and nobody takes over after the death
      isAlive: () => false,
      graceMs: 1, // the death below is FAR outside the grace window
      spawn: () => {
        const h = spawned.length === 0 ? first.handle : second.handle;
        spawned.push(h.pid);
        return h;
      },
      logFn: () => {},
    });

    expect(spawned).toEqual([1111]);

    // The poller dies. Under the old code this was "ordinary lifecycle" and
    // inbound delivery silently stopped forever.
    first.die(1);
    await flush();

    expect(spawned).toEqual([1111, 2222]); // respawned
  });

  test("a death WITH a live takeover is not treated as a crash", async () => {
    const spawned: number[] = [];
    const first = controllable(1111);

    ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "deadbeef",
      // After the exit, the pidfile names a DIFFERENT, live poller: the
      // signature of a legitimate newest-wins takeover. Delivery is fine.
      readPid: () =>
        spawned.length > 0 ? { pid: 9999, startMs: 1 } : null,
      isAlive: (pid) => pid === 9999,
      graceMs: 1,
      spawn: () => {
        spawned.push(first.handle.pid);
        return first.handle;
      },
      logFn: () => {},
    });

    first.die(0);
    await flush();

    // Exactly one spawn: no respawn, because delivery never stopped. Crying
    // wolf here is what teaches people to ignore the alarm that matters.
    expect(spawned).toEqual([1111]);
  });

  test("a poller that crashes on every start gives up instead of fork-bombing", async () => {
    const spawned: SpawnedProcessHandle[] = [];
    const dies: Array<(code: number) => void> = [];

    ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "deadbeef",
      readPid: () => null,
      isAlive: () => false,
      graceMs: 1,
      spawn: () => {
        const c = controllable(1000 + spawned.length);
        spawned.push(c.handle);
        dies.push(c.die);
        return c.handle;
      },
      logFn: () => {},
    });

    // Kill every replacement as fast as it appears.
    for (let i = 0; i < 12; i++) {
      const die = dies[i];
      if (!die) break;
      die(1);
      await flush();
    }

    // 1 original + MAX_RESPAWNS (5) = 6, then it stops and pages instead of
    // spinning forever.
    expect(spawned.length).toBe(6);
  });
});
