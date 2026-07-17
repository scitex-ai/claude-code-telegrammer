/**
 * Cross-process poller supervisor (architecture fix, incident-cct-inbound-
 * dies-silently-with-mcp-server-20260711 follow-up, 2026-07).
 *
 * These tests drive lib/poller-supervisor.ts::ensurePollerRunning directly
 * with every dependency injected (pidfile reader, liveness check, spawn
 * primitive) — NO real process is ever forked here, matching the task's
 * explicit ask to exercise the conditional-spawn DECISION without spawning
 * real detached processes in unit tests. Calls are tracked with plain
 * closures/arrays (the same injectable-seam style poller-batch.ts /
 * poll-watchdog.ts / takeover.test.ts already use throughout this repo),
 * not a test-framework mocking helper.
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
import { STALL_EXIT_CODE } from "../lib/exit-codes.js";

// broadcastSystemAlert (used by the spawn-failure / early-death alerts
// below) defaults its recipients to loadAccess().allowFrom — give it a
// non-empty allowlist so these tests actually exercise the send path.
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
  // Defaults to a promise that never resolves within a test's lifetime —
  // "this child hasn't exited" (the common case: a healthy, long-running
  // poller). Tests exercising the grace-window death check pass an
  // already-resolved (or soon-to-resolve) promise instead.
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

describe("ensurePollerRunning: already-running case", () => {
  test("does NOT spawn when the pidfile records a live PID", () => {
    let spawnCalls = 0;
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "deadbeef",
      readPid: () => ({ pid: 4242 }),
      isAlive: (pid) => pid === 4242,
      spawn: () => {
        spawnCalls += 1;
        return fakeSpawnHandle(999);
      },
    });

    expect(result).toEqual({ action: "already-running", pid: 4242 });
    expect(spawnCalls).toBe(0);
  });
});

describe("ensurePollerRunning: spawn case", () => {
  test("spawns when the pidfile is absent", () => {
    let spawnCalls = 0;
    const spawnedHandle = fakeSpawnHandle(5555);
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "deadbeef",
      readPid: () => null,
      isAlive: () => {
        throw new Error("isAlive should not be called when readPid is null");
      },
      spawn: () => {
        spawnCalls += 1;
        return spawnedHandle;
      },
    });

    expect(result).toEqual({ action: "spawned", pid: 5555 });
    expect(spawnCalls).toBe(1);
    // .unref() must be called so the MCP server's own event loop never
    // waits on the spawned poller.
    expect(spawnedHandle.unrefCalled).toBe(true);
  });

  test("spawns when the pidfile records a PID that is NOT alive (stale)", () => {
    let spawnCalls = 0;
    let isAliveArg: number | undefined;
    const spawnedHandle = fakeSpawnHandle(6666);
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "deadbeef",
      readPid: () => ({ pid: 1234 }),
      isAlive: (pid) => {
        isAliveArg = pid;
        return false;
      },
      spawn: () => {
        spawnCalls += 1;
        return spawnedHandle;
      },
    });

    expect(result).toEqual({ action: "spawned", pid: 6666 });
    expect(isAliveArg).toBe(1234);
    expect(spawnCalls).toBe(1);
    expect(spawnedHandle.unrefCalled).toBe(true);
  });

  test("spawn command uses the current bun executable + the given script path", () => {
    let capturedCmd: string[] | undefined;
    ensurePollerRunning({
      pollerScriptPath: "/abs/path/to/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "cafef00d",
      readPid: () => null,
      isAlive: () => false,
      spawn: (cmd) => {
        capturedCmd = cmd;
        return fakeSpawnHandle(7777);
      },
    });

    expect(capturedCmd).toEqual([
      process.execPath,
      "run",
      "/abs/path/to/telegram-poller.ts",
    ]);
  });

  test("passes (stateDir, tokenHash) through to the injected pidfile reader", () => {
    let seen: [string, string] | undefined;
    ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/some/state/dir",
      tokenHash: "abc12345",
      readPid: (stateDir, tokenHash) => {
        seen = [stateDir, tokenHash];
        return null;
      },
      isAlive: () => false,
      spawn: () => fakeSpawnHandle(1),
    });

    expect(seen).toEqual(["/some/state/dir", "abc12345"]);
  });
});

describe("ensurePollerRunning: real takeover.ts pidfile (no mocked reader)", () => {
  test("uses the real pidfile default when readPid is omitted", async () => {
    // Exercise the DEFAULT readPid wiring (lib/takeover.ts) against a real
    // temp state dir, without mocking the pidfile layer itself. isAlive IS
    // explicitly injected here (this test's job is the pidfile, not
    // identity verification — that gets its own describe block below and
    // its own direct coverage in takeover.test.ts): the real DEFAULT
    // isAlive is now identity-aware (isProcessMatching against
    // POLLER_CMDLINE_MARKER), and this bun:test process's own cmdline
    // legitimately does NOT contain "telegram-poller", so asserting
    // against the real default here would be testing the wrong thing.
    const { mkdtempSync, rmSync } = await import("fs");
    const { tmpdir } = await import("os");
    const { join } = await import("path");
    const { claimAuthoritative } = await import("../lib/takeover.js");

    const stateDir = mkdtempSync(join(tmpdir(), "cct-supervisor-real-"));
    try {
      // No prior claim recorded → must spawn.
      let spawnCalls = 0;
      const r1 = ensurePollerRunning({
        pollerScriptPath: "/fake/telegram-poller.ts",
        stateDir,
        tokenHash: "realpidfile",
        isAlive: () => true,
        spawn: () => {
          spawnCalls += 1;
          return fakeSpawnHandle(1111);
        },
      });
      expect(r1).toEqual({ action: "spawned", pid: 1111 });
      expect(spawnCalls).toBe(1);

      // Our OWN pid is guaranteed alive — claim it, then ensurePollerRunning
      // (real pidfile reader) must see it as already running and NOT spawn.
      claimAuthoritative({
        stateDir,
        tokenHash: "realpidfile",
        pid: process.pid,
        signalOutgoing: false,
      });
      let spawnCalls2 = 0;
      const r2 = ensurePollerRunning({
        pollerScriptPath: "/fake/telegram-poller.ts",
        stateDir,
        tokenHash: "realpidfile",
        isAlive: () => true,
        spawn: () => {
          spawnCalls2 += 1;
          return fakeSpawnHandle(2222);
        },
      });
      expect(r2).toEqual({ action: "already-running", pid: process.pid });
      expect(spawnCalls2).toBe(0);
    } finally {
      rmSync(stateDir, { recursive: true, force: true });
    }
  });
});

describe("ensurePollerRunning: identity-aware default isAlive (adversarial-review finding #2)", () => {
  test("a stale pidfile PID reused by an unrelated (non-poller) process is NOT trusted — spawns anyway", async () => {
    // The exact failure mode this fix closes: a pidfile recording a PID
    // that is alive (kill-0 succeeds) but does NOT look like our poller
    // (no "telegram-poller" in its cmdline) must NOT be trusted as
    // "already running" — otherwise ensurePollerRunning would silently,
    // permanently never spawn a real poller. Uses the REAL default isAlive
    // (identity-aware) against our OWN, definitely-alive, definitely-NOT-
    // a-poller test process pid.
    let spawnCalls = 0;
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "reused-pid",
      readPid: () => ({ pid: process.pid }), // alive, but not a poller
      // isAlive omitted deliberately — exercises the REAL default.
      spawn: () => {
        spawnCalls += 1;
        return fakeSpawnHandle(9999);
      },
    });
    expect(result).toEqual({ action: "spawned", pid: 9999 });
    expect(spawnCalls).toBe(1);
  });
});

describe("ensurePollerRunning: default spawn inherits the parent environment", () => {
  // scitex-todo card cct-mcp-server-periodic-drop-20260712 (see
  // lib/poller-teardown.ts): sac's orphan reaper for a genuinely
  // decommissioned agent matches on SAC_NAME/SCITEX_AGENT_CONTAINER_NAME env
  // + a cmdline substring — which only works if the spawned poller actually
  // carries those env vars.
  //
  // EMPIRICALLY VERIFIED (not assumed) while building this: omitting the
  // `env` key from Bun.spawn entirely still inherits whatever was in the OS
  // environment at THIS process's own startup, but does NOT reflect a
  // LATER runtime `process.env.X = ...` mutation (Bun 1.3.11) — the first
  // version of both this fix and this test wrongly assumed it did, and this
  // exact test caught that. lib/poller-supervisor.ts's default spawn
  // therefore passes `env: process.env` EXPLICITLY; this test pins that
  // corrected contract using a real, NON-detached, near-instant child
  // (never the actual poller script) so it is trivially awaited and reaped,
  // unlike a real detached spawn would be.
  test("explicit env: process.env correctly carries a runtime-set var into the child", async () => {
    const marker = `cct-supervisor-env-test-${process.pid}-${Date.now()}`;
    process.env.CCT_SUPERVISOR_ENV_TEST_MARKER = marker;
    try {
      const child = Bun.spawn(
        [
          process.execPath,
          "-e",
          "console.log(process.env.CCT_SUPERVISOR_ENV_TEST_MARKER ?? '')",
        ],
        { stdout: "pipe", env: process.env }, // mirrors the FIXED defaultSpawn()
      );
      const [exitCode, out] = await Promise.all([
        child.exited,
        new Response(child.stdout as ReadableStream).text(),
      ]);
      expect(exitCode).toBe(0);
      expect(out.trim()).toBe(marker);
    } finally {
      delete process.env.CCT_SUPERVISOR_ENV_TEST_MARKER;
    }
  });

  test("REGRESSION GUARD: omitting `env` entirely does NOT reflect a runtime process.env mutation — this is exactly why defaultSpawn must pass env explicitly", async () => {
    const marker = `cct-supervisor-env-test-omitted-${process.pid}-${Date.now()}`;
    process.env.CCT_SUPERVISOR_ENV_TEST_MARKER_OMITTED = marker;
    try {
      const child = Bun.spawn(
        [
          process.execPath,
          "-e",
          "console.log(process.env.CCT_SUPERVISOR_ENV_TEST_MARKER_OMITTED ?? '')",
        ],
        { stdout: "pipe" }, // deliberately NO `env` key
      );
      const [exitCode, out] = await Promise.all([
        child.exited,
        new Response(child.stdout as ReadableStream).text(),
      ]);
      expect(exitCode).toBe(0);
      // If this ever starts passing (out.trim() === marker), Bun's default
      // spawn behaviour changed — safe to simplify defaultSpawn() back to
      // omitting `env`, but until then this documents WHY it isn't omitted.
      expect(out.trim()).toBe("");
    } finally {
      delete process.env.CCT_SUPERVISOR_ENV_TEST_MARKER_OMITTED;
    }
  });
});

describe("ensurePollerRunning: spawn() throwing is loud, not silent (adversarial-review finding #4)", () => {
  test("a spawn failure returns spawn-failed, logs, and broadcasts a system alert", () => {
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "spawn-fails",
      readPid: () => null,
      isAlive: () => false,
      spawn: () => {
        throw new Error("ENOMEM: cannot fork");
      },
    });

    expect(result).toEqual({
      action: "spawn-failed",
      error: "ENOMEM: cannot fork",
    });
    expect(alerts.length).toBe(1);
    expect(alerts[0]).toContain("FATAL");
    expect(alerts[0]).toContain("failed to spawn");
    expect(alerts[0]).toContain("ENOMEM: cannot fork");
  });
});

describe("ensurePollerRunning: post-spawn grace-window death check (adversarial-review finding #4)", () => {
  test("a child that exits almost immediately triggers a loud alert", async () => {
    const spawnedHandle = fakeSpawnHandle(5050, Promise.resolve(1));
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "dies-immediately",
      readPid: () => null,
      isAlive: () => false,
      spawn: () => spawnedHandle,
      graceMs: 50, // tiny window — this test does not wait 3 real seconds
    });
    expect(result).toEqual({ action: "spawned", pid: 5050 });

    // The exit-observer is fire-and-forget (`void child.exited.then(...)`)
    // — give its microtask/short-timer chain a tick to run before asserting.
    await new Promise((r) => setTimeout(r, 60));

    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts[0]).toContain("exited with code 1");
    expect(alerts[0]).toContain("stopped unexpectedly");
    // Not DOWN — it is being respawned right now. See #92.
    expect(alerts[0]).not.toContain("DOWN");
  });

  // BEHAVIOUR CHANGE, and the whole point of the fix.
  //
  // This test used to assert `alerts.length === 0` — it PINNED THE BUG as a
  // requirement: a poller that died any time after the grace window produced no
  // alert, no log and no respawn, and inbound Telegram delivery just stopped.
  //
  // That is not a hypothetical. It fired live on 2026-07-14: the poller vanished
  // 37 minutes in, and the operator's only channel to the fleet went silent with
  // every safety net downstream of the process being alive. "Ordinary lifecycle"
  // was never a safe reading of a dead poller.
  //
  // The age of the corpse is not the signal. Whether ANOTHER live poller took
  // over the pidfile is — and that question is just as answerable at 37 minutes
  // as at 300ms (see the takeover test below, which still expects silence).
  test("a child that exits well AFTER the grace window now alerts too (it used to be silent — that was the bug)", async () => {
    const spawnedHandle = fakeSpawnHandle(
      6060,
      new Promise<number>((resolve) => setTimeout(() => resolve(0), 60)),
    );
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "dies-later",
      readPid: () => null, // nobody took over ⇒ delivery really is down
      isAlive: () => false,
      spawn: () => spawnedHandle,
      graceMs: 10, // the child "survives" past this before exiting
    });
    expect(result).toEqual({ action: "spawned", pid: 6060 });

    await new Promise((r) => setTimeout(r, 100));

    // Still alerts — an unexplained exit is news whenever it happens. But it no
    // longer claims DOWN: the supervisor respawns it on the spot (#92).
    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts[0]).toContain("stopped unexpectedly");
    expect(alerts[0]).not.toContain("DOWN");
  });

  test("a still-running child (exited never resolves) never alerts", async () => {
    const spawnedHandle = fakeSpawnHandle(7070); // default: never-resolving exited
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "still-running",
      readPid: () => null,
      isAlive: () => false,
      spawn: () => spawnedHandle,
      graceMs: 20,
    });
    expect(result).toEqual({ action: "spawned", pid: 7070 });

    await new Promise((r) => setTimeout(r, 60));

    expect(alerts.length).toBe(0);
  });

  test("a legitimate newest-wins takeover (a DIFFERENT live PID now holds the pidfile) does NOT alert — round-2 adversarial-review finding #2", async () => {
    // Mechanics being reproduced: claimAuthoritative() SIGTERMs a losing
    // poller almost immediately after a newer one starts (its very first
    // action in startPolling()), and the losing poller's own shutdown()
    // takes a fixed 2000ms — landing comfortably inside the exit
    // observer's grace window. Naively alerting on aliveMs<graceMs alone
    // would cry wolf on this entirely correct, self-healing outcome.
    const spawnedHandle = fakeSpawnHandle(8080, Promise.resolve(0));
    let readPidCalls = 0;
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "legit-takeover",
      // First call (the initial "is one already running?" check): no
      // pidfile yet. Second call (the exit observer's re-check, AFTER our
      // spawned pid 8080 already exited): a DIFFERENT, live pid — the
      // newer poller that won the race.
      readPid: () => {
        readPidCalls += 1;
        return readPidCalls === 1 ? null : { pid: 9090 };
      },
      isAlive: (pid) => pid === 9090, // only the newer poller is alive
      spawn: () => spawnedHandle,
      graceMs: 50,
    });
    expect(result).toEqual({ action: "spawned", pid: 8080 });

    await new Promise((r) => setTimeout(r, 20));

    expect(alerts.length).toBe(0);
    expect(readPidCalls).toBe(2);
  });

  test("an early exit with NO other live poller in the pidfile still alerts (genuine crash, not a takeover)", async () => {
    const spawnedHandle = fakeSpawnHandle(8181, Promise.resolve(1));
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "genuine-crash",
      // The pidfile still names OUR OWN (now-dead) pid — no takeover.
      readPid: () => ({ pid: 8181 }),
      isAlive: () => false,
      spawn: () => spawnedHandle,
      graceMs: 50,
    });
    expect(result).toEqual({ action: "spawned", pid: 8181 });

    await new Promise((r) => setTimeout(r, 60));

    // An unexplained crash IS worth telling him about — that contract stands.
    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts[0]).toContain("stopped unexpectedly");
    // ...but it must NOT claim DOWN. This test used to assert it did. That
    // assertion was the bug, pinned: the respawn happens in the same function,
    // so the real gap is about a second. DOWN is reserved for the FATAL path,
    // where it is true (#92).
    expect(alerts[0]).not.toContain("DOWN");
  });

  /**
   * THE BUG THE OPERATOR SCREENSHOTTED (#92, 2026-07-17).
   *
   * poll-watchdog exits STALL_EXIT_CODE (75) to ASK for a respawn, having
   * already told him "recovering by itself, no action needed". The supervisor
   * then reported that same event as "inbound Telegram delivery is DOWN" —
   * because it never looked at the exit code, despite 75 having been chosen
   * precisely so it could be told apart from a crash.
   *
   * Two messages, seconds apart, one event, opposite meanings — and the second
   * one false, as he could see for himself:
   * 「そのメッセージがあっても普通に届きますからね」.
   *
   * This is the alarm channel. A false alarm here teaches him to mute it, and
   * then a REAL outage reaches nobody. Silence on a planned restart is not a
   * missing feature; it is the feature.
   */
  test("a PLANNED stall restart (exit 75) respawns SILENTLY — the watchdog already spoke", async () => {
    // The real sequence: the poller stalls ONCE, self-terminates asking for a
    // respawn, and its replacement comes up healthy (never exits). Handing the
    // same instantly-exiting handle back on every respawn would instead model a
    // poller that can NEVER start — which burns all 5 attempts and correctly
    // pages via the FATAL path. That is a different scenario, covered below.
    const stalled = fakeSpawnHandle(8282, Promise.resolve(STALL_EXIT_CODE));
    const healthy = fakeSpawnHandle(8283, new Promise<number>(() => {}));
    let spawnCount = 0;
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "planned-stall-restart",
      // Same situation as the genuine-crash case above — nobody took over.
      // The ONLY difference is the exit code, and that must be enough.
      readPid: () => ({ pid: 8282 }),
      isAlive: () => false,
      spawn: () => {
        spawnCount += 1;
        return spawnCount === 1 ? stalled : healthy;
      },
      graceMs: 50,
    });
    expect(result).toEqual({ action: "spawned", pid: 8282 });

    await new Promise((r) => setTimeout(r, 60));

    // Not one word to the operator...
    expect(alerts).toEqual([]);
    // ...and it still gets fixed. Silence here must mean "handled", never
    // "ignored" — the respawn is what earns the right to stay quiet.
    expect(spawnCount).toBe(2);
  });

  /**
   * The other half of the contract: staying quiet about a planned restart must
   * NOT extend to a poller that cannot come back. If every respawn stalls again,
   * the supervisor exhausts MAX_RESPAWNS and pages — loudly, and truthfully,
   * because by then delivery really is down.
   */
  test("a poller that stalls forever still ends up paging via the FATAL path", async () => {
    const alwaysStalls = fakeSpawnHandle(8484, Promise.resolve(STALL_EXIT_CODE));
    const result = ensurePollerRunning({
      pollerScriptPath: "/fake/telegram-poller.ts",
      stateDir: "/fake/state",
      tokenHash: "stalls-forever",
      readPid: () => ({ pid: 8484 }),
      isAlive: () => false,
      spawn: () => alwaysStalls,
      graceMs: 50,
    });
    expect(result).toEqual({ action: "spawned", pid: 8484 });

    await new Promise((r) => setTimeout(r, 100));

    expect(alerts.length).toBeGreaterThan(0);
    // Here — and only here — "DOWN" is the truth.
    expect(alerts[alerts.length - 1]).toContain("DOWN");
  });
});
