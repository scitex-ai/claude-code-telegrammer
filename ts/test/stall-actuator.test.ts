/**
 * The stall watchdog must ACT, not just shout.
 *
 * grant, 2026-07-14 — the sharpest review note of the day:
 *
 *   "an alarm with no actuator, that shouts and then leaves the bridge wedged
 *    for a human, will still get ignored eventually — not because it lies, but
 *    because it is not actionable by the agent that receives it."
 *
 * The alarm used to end with "ACTION: restart the bridge to recover" and then
 * leave it wedged. A wedged poller cannot fix itself in place — the getUpdates
 * await never resolves, so there is nothing to retry from inside. But it can
 * DIE, and the supervisor (#82) already respawns a poller that exits with
 * nobody holding the pidfile.
 *
 * Detector we had. Actuator we had. This pins the wire between them.
 */

import { describe, test, expect } from "bun:test";
import { createStallWatchdog } from "../lib/poll-watchdog.js";

describe("stall watchdog: actuator", () => {
  function harness(opts: { pollAt: number; nowAt: number }) {
    const emitted: string[] = [];
    let stalls = 0;
    const wd = createStallWatchdog({
      now: () => opts.nowAt,
      getLastPoll: () => opts.pollAt,
      isPolling: () => true,
      thresholdMs: 180_000,
      emit: (c) => emitted.push(c),
      onStall: () => {
        stalls += 1;
      },
    });
    return { wd, emitted, stalls: () => stalls };
  }

  test("a stall fires the actuator, not just the alarm", () => {
    const h = harness({ pollAt: 0, nowAt: 200_000 }); // 200s > 180s threshold
    h.wd.tick();

    expect(h.emitted.length).toBe(1);
    expect(h.stalls()).toBe(1); // <-- the whole point
  });

  test("the alarm text no longer tells a human to go restart it", () => {
    const h = harness({ pollAt: 0, nowAt: 200_000 });
    h.wd.tick();

    expect(h.emitted[0]).toContain("SELF-HEALING");
    expect(h.emitted[0]).not.toContain("ACTION: restart the bridge");
  });

  test("a healthy bridge neither alarms nor actuates", () => {
    // A 30s long-poll stamps the heartbeat 6x more often than the 180s
    // threshold, so an IDLE-but-healthy bridge must never trip this. (Both of
    // grant's false-positive hypotheses died on exactly this arithmetic.)
    const h = harness({ pollAt: 100_000, nowAt: 130_000 }); // 30s since last poll
    h.wd.tick();

    expect(h.emitted.length).toBe(0);
    expect(h.stalls()).toBe(0);
  });

  test("does not actuate twice for one stall (latched until a poll resumes)", () => {
    const h = harness({ pollAt: 0, nowAt: 200_000 });
    h.wd.tick();
    h.wd.tick();
    h.wd.tick();

    expect(h.stalls()).toBe(1);
  });

  // SAFETY: the pure factory must never be able to end the process. Production
  // wiring (startStallWatchdog) is the only place the real terminate is
  // injected — a default that exited would kill the test runner itself.
  test("onStall defaults to a no-op — the factory can never kill the process", () => {
    const emitted: string[] = [];
    const wd = createStallWatchdog({
      now: () => 200_000,
      getLastPoll: () => 0,
      isPolling: () => true,
      thresholdMs: 180_000,
      emit: (c) => emitted.push(c),
      // onStall deliberately omitted
    });

    expect(() => wd.tick()).not.toThrow();
    expect(emitted.length).toBe(1); // it still alarms
  });
});
