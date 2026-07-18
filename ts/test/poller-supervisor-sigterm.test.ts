/**
 * The SIGTERM stand-down contract (cct-deliberate-kill-reads-as-crash,
 * 2026-07-18).
 *
 * Split out of poller-supervisor.test.ts, which was already at the 512-line
 * ceiling: a NEW behaviour earns a NEW focused file rather than pushing an
 * over-limit one further over. Same injected-seam style as its sibling — no
 * real process is ever forked.
 *
 * What it pins: sac sends SIGTERM for every DELIBERATE stop (`agents stop`,
 * the stop-half of `agents start --force`, the reaper), escalating to SIGKILL
 * only if ignored. Contract confirmed with sac 2026-07-18: SIGTERM means
 * "stay dead" — sac owns the restart. So a poller that exits 143 (128+SIGTERM)
 * with nobody holding the pidfile must STAND DOWN, not respawn: respawning
 * would fight the terminator, and against a reaper it would loop. It also must
 * not page — a stop that was asked for is not an outage.
 *
 * SIGKILL (137 = 128+9) is the opposite: an OOM-kill or hard `kill -9` is an
 * involuntary death with no restarter behind it, so it keeps the crash path
 * (respawn + page). Only SIGTERM carries sac's "I will restart you" promise.
 */

import {
  describe,
  test,
  expect,
  beforeAll,
  beforeEach,
  afterEach,
  afterAll,
} from "bun:test";
import { writeFileSync, mkdirSync, rmSync } from "fs";
import {
  ensurePollerRunning,
  type SpawnedProcessHandle,
} from "../lib/poller-supervisor.js";
import {
  setSystemAlertSender,
  _resetSystemAlertSender,
} from "../lib/loudfail.js";
import { _resetCache } from "../lib/access.js";
import { ACCESS_FILE, STATE_DIR } from "../lib/config.js";
import { SIGTERM_EXIT, SIGKILL_EXIT } from "../lib/exit-codes.js";

// broadcastSystemAlert defaults its recipients to loadAccess().allowFrom —
// give it a non-empty allowlist so the crash-path send is actually exercised.
beforeAll(() => {
  mkdirSync(STATE_DIR, { recursive: true });
  writeFileSync(ACCESS_FILE, JSON.stringify({ allowFrom: ["424242"] }));
  _resetCache();
});
afterAll(() => {
  rmSync(ACCESS_FILE, { force: true });
  _resetCache();
});

let alerts: string[] = [];
beforeEach(() => {
  alerts = [];
  setSystemAlertSender(async (_chatId, text) => {
    alerts.push(text);
    return { ok: true };
  });
});
afterEach(() => {
  _resetSystemAlertSender();
});

function fakeSpawnHandle(
  pid: number,
  exited: Promise<number> = new Promise<number>(() => {}),
): SpawnedProcessHandle & { unrefCalled: boolean } {
  const handle = {
    pid,
    unrefCalled: false,
    exited,
    unref(): void {
      handle.unrefCalled = true;
    },
  };
  return handle;
}

describe("observePollerExit: the SIGTERM/SIGKILL exit-code contract", () => {
  test("a SIGTERM (exit 143) with NO successor STANDS DOWN — no respawn, no page", async () => {
    // Same nobody-took-over situation as the genuine-crash and planned-restart
    // cases in the sibling file; the ONLY difference is the exit code. 75 asks
    // to be respawned, 143 asks to be left dead — the exit code is the whole
    // decision, exactly as #92 taught.
    const terminated = fakeSpawnHandle(8585, Promise.resolve(SIGTERM_EXIT));
    let spawnCount = 0;
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "deliberate-sigterm",
      // The pidfile still names OUR OWN (now-dead) pid — no takeover.
      readPid: () => ({ pid: 8585 }),
      isAlive: () => false,
      spawn: () => {
        spawnCount += 1;
        return terminated;
      },
      graceMs: 50,
    });
    expect(result).toEqual({ action: "spawned", pid: 8585 });

    await new Promise((r) => setTimeout(r, 60));

    // Not a word — a deliberate stop is not an outage.
    expect(alerts).toEqual([]);
    // And — unlike the planned restart, which respawns silently — it does NOT
    // come back. Standing down is the initial spawn and nothing after it.
    expect(spawnCount).toBe(1);
  });

  test("a SIGKILL (exit 137) still CRASHES — respawns and pages (not a stand-down)", async () => {
    // Only SIGTERM carries sac's "I will restart you" promise. A hard kill has
    // no restarter behind it, so treating 137 as a stand-down would silently
    // abandon a poller nobody is going to bring back.
    const killed = fakeSpawnHandle(8686, Promise.resolve(SIGKILL_EXIT));
    const healthy = fakeSpawnHandle(8687, new Promise<number>(() => {}));
    let spawnCount = 0;
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "hard-sigkill",
      readPid: () => ({ pid: 8686 }),
      isAlive: () => false,
      spawn: () => {
        spawnCount += 1;
        return spawnCount === 1 ? killed : healthy;
      },
      graceMs: 50,
    });
    expect(result).toEqual({ action: "spawned", pid: 8686 });

    await new Promise((r) => setTimeout(r, 60));

    // It recovers by respawning...
    expect(spawnCount).toBe(2);
    // ...and it says so — an involuntary kill is a real, unexplained signal.
    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts[0]).toContain("stopped unexpectedly");
    // But still not "DOWN" — the respawn makes the real gap about a second (#92).
    expect(alerts[0]).not.toContain("DOWN");
  });
});
