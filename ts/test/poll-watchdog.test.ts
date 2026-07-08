/**
 * Ingestion-stall alarm (PR-A): the getUpdates poller can stay ALIVE
 * (process up, kill-0 passes, pidfile records a live PID) yet stop
 * ingesting because getUpdates itself is WEDGED — a hung socket / network
 * black-hole / long-poll whose await never resolves. kill-0 liveness
 * checks miss it; this watchdog turns that silent stall LOUD.
 *
 * These tests drive poll-watchdog.ts::createStallWatchdog directly — the
 * stateful checker that owns the "fire vs stay silent" decision. The clock
 * (`now`), the heartbeat getter (`getLastPoll`), the polling predicate
 * (`isPolling`) and the loud-notification sink (`emit`) are all injected,
 * so the alarm / re-arm / shutdown logic is exercised with NO timers and
 * NO network — the same injectable-seam approach poller-batch.ts uses for
 * processBatch.
 */

import { describe, test, expect, beforeAll, beforeEach } from "bun:test";
import {
  createStallWatchdog,
  resolveStallThresholdMs,
  recordSuccessfulPoll,
  getLastSuccessfulPoll,
  _resetHeartbeat,
  DEFAULT_STALL_SECONDS,
} from "../lib/poll-watchdog.js";
import { initStore, loadLastPollTs } from "../lib/store.js";

const THRESHOLD_MS = 180_000;

/**
 * A watchdog driven by a virtual clock + heartbeat. `poll()` stamps the
 * heartbeat to "now" (a successful getUpdates return); `advance()` moves
 * the clock forward WITHOUT a poll (the stall); `stop()` flips the
 * polling predicate false (clean shutdown).
 */
function harness() {
  let clock = 0;
  let lastPoll = 0;
  let polling = true;
  const alarms: string[] = [];
  const wd = createStallWatchdog({
    now: () => clock,
    getLastPoll: () => lastPoll,
    emit: (content) => alarms.push(content),
    isPolling: () => polling,
    thresholdMs: THRESHOLD_MS,
  });
  return {
    wd,
    alarms,
    advance: (ms: number) => {
      clock += ms;
    },
    poll: () => {
      lastPoll = clock;
    },
    stop: () => {
      polling = false;
    },
  };
}

describe("createStallWatchdog — fires once per stall episode", () => {
  test("(a) no alarm while polls stay fresh", () => {
    const h = harness();
    h.poll(); // initial successful poll at t=0
    // Ten healthy long-poll cycles: advance ~30s then poll each time.
    for (let i = 0; i < 10; i++) {
      h.advance(30_000);
      h.poll();
      h.wd.tick();
    }
    expect(h.alarms.length).toBe(0);
  });

  test("(b) EXACTLY ONE loud alarm once the stall threshold is crossed", () => {
    const h = harness();
    h.poll(); // last successful poll at t=0
    // No further polls — getUpdates has wedged. Cross the threshold.
    h.advance(THRESHOLD_MS + 5_000);
    h.wd.tick(); // alarm #1

    // Keep ticking while still stalled — must NOT re-fire this episode.
    h.advance(30_000);
    h.wd.tick();
    h.advance(30_000);
    h.wd.tick();

    expect(h.alarms.length).toBe(1);
    const msg = h.alarms[0];
    expect(msg).toContain("INGESTION STALL");
    expect(msg).toContain("ALIVE");
    expect(msg.toLowerCase()).toContain("restart");
    // Names the stall duration (~185s) in the message.
    expect(msg).toMatch(/~1\d\ds/);
  });

  test("no alarm just BELOW the threshold", () => {
    const h = harness();
    h.poll();
    h.advance(THRESHOLD_MS - 1_000); // still under threshold
    h.wd.tick();
    expect(h.alarms.length).toBe(0);
  });

  test("(c) the alarm RE-ARMS after a fresh poll, then fires again", () => {
    const h = harness();
    h.poll();
    h.advance(THRESHOLD_MS + 5_000);
    h.wd.tick(); // alarm #1
    expect(h.alarms.length).toBe(1);

    // A successful poll resumes → heartbeat advances → re-arm.
    h.advance(10_000);
    h.poll();
    h.wd.tick(); // fresh again: no alarm
    expect(h.alarms.length).toBe(1);

    // A LATER stall must alarm again (proves the latch reset).
    h.advance(THRESHOLD_MS + 5_000);
    h.wd.tick(); // alarm #2
    expect(h.alarms.length).toBe(2);
  });

  test("(d) no alarm after shutdown / preemption (isPolling false)", () => {
    const h = harness();
    h.poll();
    h.stop(); // poller released authority / clean shutdown
    h.advance(THRESHOLD_MS + 60_000); // long stall AFTER shutdown
    h.wd.tick();
    h.wd.tick();
    expect(h.alarms.length).toBe(0);
  });
});

describe("resolveStallThresholdMs — env alias + default", () => {
  test("unset → default", () => {
    expect(resolveStallThresholdMs({})).toBe(DEFAULT_STALL_SECONDS * 1000);
  });

  test("empty string is treated as absent → default", () => {
    expect(resolveStallThresholdMs({ CCT_POLL_STALL_SECONDS: "" })).toBe(
      DEFAULT_STALL_SECONDS * 1000,
    );
  });

  test("short alias CCT_POLL_STALL_SECONDS wins", () => {
    expect(resolveStallThresholdMs({ CCT_POLL_STALL_SECONDS: "60" })).toBe(
      60_000,
    );
  });

  test("canonical CLAUDE_CODE_TELEGRAMMER_POLL_STALL_SECONDS resolves", () => {
    expect(
      resolveStallThresholdMs({
        CLAUDE_CODE_TELEGRAMMER_POLL_STALL_SECONDS: "90",
      }),
    ).toBe(90_000);
  });

  test("invalid / non-positive value → default", () => {
    expect(resolveStallThresholdMs({ CCT_POLL_STALL_SECONDS: "abc" })).toBe(
      DEFAULT_STALL_SECONDS * 1000,
    );
    expect(resolveStallThresholdMs({ CCT_POLL_STALL_SECONDS: "0" })).toBe(
      DEFAULT_STALL_SECONDS * 1000,
    );
  });
});

describe("recordSuccessfulPoll — in-process + persisted heartbeat", () => {
  beforeAll(() => {
    initStore();
  });
  beforeEach(() => {
    _resetHeartbeat();
  });

  test("stamps the in-process heartbeat and persists it to the DB", () => {
    const t = 1_720_500_000_000;
    recordSuccessfulPoll(t);
    expect(getLastSuccessfulPoll()).toBe(t);
    // Persisted so an out-of-band health probe can read poll-freshness.
    expect(loadLastPollTs()).toBe(t);
  });

  test("a later poll advances both the in-process and persisted stamps", () => {
    recordSuccessfulPoll(1_000);
    recordSuccessfulPoll(2_000);
    expect(getLastSuccessfulPoll()).toBe(2_000);
    expect(loadLastPollTs()).toBe(2_000);
  });
});
