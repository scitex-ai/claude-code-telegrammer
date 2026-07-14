/**
 * "I asked and got nothing" is not "dead".
 *
 * sac, 2026-07-14 — after their health watchdog restarted a HEALTHY daemon
 * three times out of three, because a probe that timed out was read as DOWN
 * rather than UNKNOWN. Same shape as the bug that killed this bridge's poller
 * all day (a missing pidfile read as "preempted"), and the one I then wrote
 * into the release guard (an empty version read as "ghost").
 *
 * kill(pid, 0) has two distinct failure modes:
 *
 *   ESRCH — no such process              -> genuinely DEAD
 *   EPERM — it EXISTS, we may not signal  -> ALIVE, just not ours
 *
 * The old bare `catch { return false }` swallowed both. Reporting EPERM as dead
 * makes checkAuthority() return `stale`, which makes the poll loop RE-CLAIM the
 * pidfile — starting a second poller against a bot token that already has a live
 * consumer, which Telegram answers with a 409 Conflict storm.
 *
 * SCOPE, stated honestly: latent, not reproduced. Every cct process runs as the
 * same user and I could not provoke a real EPERM here. Fixed anyway, because a
 * bare catch that collapses a distinguishable error into a wrong answer is a
 * silent fallback on the liveness check guarding the operator's only channel.
 */

import { describe, test, expect } from "bun:test";
import { isPidAlive } from "../lib/takeover.js";

describe("isPidAlive: EPERM means ALIVE, not dead", () => {
  test("our own pid is alive", () => {
    expect(isPidAlive(process.pid)).toBe(true);
  });

  test("a pid that does not exist (ESRCH) is dead", () => {
    // 2^22 is above the default pid_max on Linux, so this cannot be a live pid.
    expect(isPidAlive(4_194_305)).toBe(false);
  });

  // THE CASE. Reproduced by making kill() throw the way the kernel would, since
  // every cct process runs as the same user and a genuine EPERM is not
  // provokable here.
  test("EPERM is reported ALIVE — the process exists, we just may not signal it", () => {
    const realKill = process.kill;
    try {
      process.kill = (() => {
        const e = new Error("kill EPERM") as NodeJS.ErrnoException;
        e.code = "EPERM";
        throw e;
      }) as typeof process.kill;

      // Old behaviour: false ("dead") -> checkAuthority says `stale` -> the poll
      // loop re-claims -> a SECOND poller on one bot token -> 409 storm.
      expect(isPidAlive(12345)).toBe(true);
    } finally {
      process.kill = realKill;
    }
  });

  test("ESRCH is reported DEAD", () => {
    const realKill = process.kill;
    try {
      process.kill = (() => {
        const e = new Error("kill ESRCH") as NodeJS.ErrnoException;
        e.code = "ESRCH";
        throw e;
      }) as typeof process.kill;

      expect(isPidAlive(12345)).toBe(false);
    } finally {
      process.kill = realKill;
    }
  });

  // FAIL-SAFE direction: a false "alive" only DELAYS a takeover; a false "dead"
  // DUPLICATES a poller. So anything we cannot interpret must mean "gone".
  test("an uninterpretable error is treated as dead (the safe direction)", () => {
    const realKill = process.kill;
    try {
      process.kill = (() => {
        throw new Error("something exotic with no code");
      }) as typeof process.kill;

      expect(isPidAlive(12345)).toBe(false);
    } finally {
      process.kill = realKill;
    }
  });
});
