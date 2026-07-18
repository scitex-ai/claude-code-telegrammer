/**
 * The stall watchdog must ACT and LOG — and must NOT message the operator.
 *
 * grant, 2026-07-14: "an alarm with no actuator, that shouts and then leaves the
 * bridge wedged for a human, will still get ignored." So it acts: onStall
 * self-terminates and the supervisor (#82) respawns.
 *
 * The operator, 2026-07-18, after receiving 8 "INGESTION STALL — recovering by
 * itself, no action needed" messages in 6 minutes from a stall-LOOP
 * (「こんなゴミみたいなメッセージが来ても困る」): 「対応不要なら送るべきでない」 —
 * if no action is needed, do not send. A self-healing stall is not actionable,
 * so the watchdog now LOGS and acts but sends the operator NOTHING. The only
 * Telegram message about stalls is the supervisor's bounded FATAL when recovery
 * genuinely fails (lib/poller-supervisor.ts, #92). There is no `emit`/operator
 * seam on the watchdog at all — its absence IS the fix.
 */

import { describe, test, expect } from "bun:test";
import { createStallWatchdog } from "../lib/poll-watchdog.js";

describe("stall watchdog: acts + logs, never messages the operator", () => {
  function harness(opts: { pollAt: number; nowAt: number }) {
    let stalls = 0;
    const wd = createStallWatchdog({
      now: () => opts.nowAt,
      getLastPoll: () => opts.pollAt,
      isPolling: () => true,
      thresholdMs: 180_000,
      onStall: () => {
        stalls += 1;
      },
    });
    return { wd, stalls: () => stalls };
  }

  test("a stall fires the actuator", () => {
    const h = harness({ pollAt: 0, nowAt: 200_000 }); // 200s > 180s threshold
    h.wd.tick();

    expect(h.stalls()).toBe(1); // <-- the whole point: it ACTS
  });

  test("a healthy bridge neither actuates nor stalls", () => {
    // A 30s long-poll stamps the heartbeat 6x more often than the 180s
    // threshold, so an IDLE-but-healthy bridge must never trip this. (Both of
    // grant's false-positive hypotheses died on exactly this arithmetic.)
    const h = harness({ pollAt: 100_000, nowAt: 130_000 }); // 30s since last poll
    h.wd.tick();

    expect(h.stalls()).toBe(0);
  });

  test("does not actuate twice for one stall (latched until a poll resumes)", () => {
    const h = harness({ pollAt: 0, nowAt: 200_000 });
    h.wd.tick();
    h.wd.tick();
    h.wd.tick();

    expect(h.stalls()).toBe(1);
  });

  /**
   * THE INCIDENT REGRESSION (2026-07-18). A poller that cannot recover — e.g.
   * token contention 409ing every getUpdates — stalls, respawns, stalls again:
   * a LOOP. The old watchdog broadcast one "recovering by itself" line per
   * respawn and flooded the operator (8 in 6 minutes). This models the loop:
   * each cycle a poll advances the heartbeat (re-arming the latch), then silence
   * returns and the watchdog actuates again. It acts every cycle — and the
   * watchdog has NO operator-message seam, so none of it can reach his phone.
   * The compiler enforces the absence: StallWatchdogDeps has no `emit`.
   */
  test("a stall LOOP actuates each cycle but has no operator-message path", () => {
    let stalls = 0;
    let lastPoll = 0;
    let clock = 0;
    const wd = createStallWatchdog({
      now: () => clock,
      getLastPoll: () => lastPoll,
      isPolling: () => true,
      thresholdMs: 180_000,
      onStall: () => {
        stalls += 1;
      },
    });

    for (let i = 0; i < 3; i++) {
      lastPoll = clock; // a poll happened — advances heartbeat, re-arms the latch
      wd.tick(); // fresh: not stalled yet
      clock += 200_000; // 200s of silence (poll never returns — the wedge)
      wd.tick(); // stall detected -> actuate (request respawn)
    }

    expect(stalls).toBe(3); // acted on every cycle of the loop...
    // ...and there is simply no emit/operator seam to spam him with. If a future
    // change re-adds an `emit` to StallWatchdogDeps, this file stops compiling
    // (the harnesses omit it), which is the guard against re-introducing the spam.
  });

  // SAFETY: the pure factory must never be able to end the process. Production
  // wiring (startStallWatchdog) is the only place the real terminate is
  // injected — a default that exited would kill the test runner itself.
  test("onStall defaults to a no-op — the factory can never kill the process", () => {
    const wd = createStallWatchdog({
      now: () => 200_000,
      getLastPoll: () => 0,
      isPolling: () => true,
      thresholdMs: 180_000,
      // onStall deliberately omitted
    });

    expect(() => wd.tick()).not.toThrow();
  });
});
