/**
 * A pidfile naming a DEAD process is not a successor.
 *
 * THE ACTUAL MECHANISM of the 2026-07-14 outages, found last:
 *
 * ts/test/poller-supervisor.test.ts imports the REAL, env-derived STATE_DIR from
 * lib/config.js and calls claimAuthoritative() against it. Run WITHOUT the
 * hermetic preload — i.e. `bun test` from the repo root, where Bun never found
 * ts/bunfig.toml — STATE_DIR resolved to the LIVE bridge, and the test stamped
 * the RUNNING poller's pidfile with the TEST process's pid.
 *
 * The test then exited, as tests do. The real, healthy poller read a pidfile
 * naming a pid that no longer existed, concluded it had been preempted, logged
 * "preempted by newer poller — exiting cleanly", and killed itself.
 *
 * The operator's only channel to the fleet died for a corpse.
 *
 * #85 stops the test ever touching the live state dir again. #87 taught the
 * poller that a VANISHED pidfile is not a successor. This closes the last hole:
 * a pidfile that names a DEAD pid is the same lie wearing a disguise — the
 * record exists, so it LOOKS like someone took over, but nobody is there.
 *
 * Preemption is only real if the preemptor is ALIVE.
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { claimAuthoritative, checkAuthority } from "../lib/takeover.js";

const TOKEN = "feedface";
const OUR_PID = 4242;
const DEAD_PID = 999_001;
const LIVE_PID = 999_002;

let stateDir: string;
beforeEach(() => {
  stateDir = mkdtempSync(join(tmpdir(), "cct-stale-"));
});
afterEach(() => {
  rmSync(stateDir, { recursive: true, force: true });
});

/** Only LIVE_PID is alive. DEAD_PID is a corpse. */
const isAlive = (pid: number) => pid === LIVE_PID;

describe("checkAuthority: a dead preemptor is not preemption", () => {
  // THE BUG. Everything else here is bookkeeping.
  test("a pidfile naming a DEAD pid is 'stale', not 'preempted'", () => {
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN,
      pid: DEAD_PID, // e.g. a test process that has since exited
      signalOutgoing: false,
    });

    const a = checkAuthority({
      stateDir,
      tokenHash: TOKEN,
      pid: OUR_PID,
      isAlive,
    });

    expect(a.kind).toBe("stale");
    expect(a.kind).not.toBe("preempted"); // <-- this is what killed the bridge
    if (a.kind === "stale") expect(a.byPid).toBe(DEAD_PID);
  });

  test("a pidfile naming a LIVE pid is still genuine preemption", () => {
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN,
      pid: LIVE_PID,
      signalOutgoing: false,
    });

    const a = checkAuthority({
      stateDir,
      tokenHash: TOKEN,
      pid: OUR_PID,
      isAlive,
    });

    // The 409 guard MUST survive this fix: two pollers on one bot token make
    // Telegram answer with a Conflict storm (getUpdates is single-consumer), so
    // a real successor must still stand us down at once.
    expect(a.kind).toBe("preempted");
    if (a.kind === "preempted") expect(a.byPid).toBe(LIVE_PID);
  });

  test("re-claiming over a stale pid restores ownership (what the loop now does)", () => {
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN,
      pid: DEAD_PID,
      signalOutgoing: false,
    });

    // The poll loop's response to "stale": re-claim and keep polling.
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN,
      pid: OUR_PID,
      signalOutgoing: false,
    });

    expect(
      checkAuthority({ stateDir, tokenHash: TOKEN, pid: OUR_PID, isAlive }).kind,
    ).toBe("ours");
  });

  test("our own pidfile is still 'ours' regardless of the liveness probe", () => {
    claimAuthoritative({ stateDir, tokenHash: TOKEN, pid: OUR_PID });

    expect(
      checkAuthority({ stateDir, tokenHash: TOKEN, pid: OUR_PID, isAlive }).kind,
    ).toBe("ours");
  });
});
