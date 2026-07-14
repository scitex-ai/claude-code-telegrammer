/**
 * The guard that would have stopped me destroying the operator's bridge.
 *
 * On 2026-07-14 I ran `bun test ts/test/...` from the repo root. Bun reads
 * bunfig.toml from the CURRENT WORKING DIRECTORY, the only bunfig lived in ts/,
 * so the hermetic preload never loaded. The suite inherited my real agent
 * environment, resolved STATE_DIR to the LIVE bridge, and store.test.ts's
 * `saveOffset(99999)` overwrote the operator's real Telegram getUpdates
 * watermark (348318289 -> 99999) plus his wake-health state.
 *
 * It printed nothing. It just worked, against the wrong database — while I
 * spent hours hunting a "mysterious" poller failure I was very likely causing.
 *
 * A repo-root bunfig removes the cwd dependency. This removes the SILENCE.
 */

import { describe, test, expect } from "bun:test";
import { assertHermeticTestStore } from "../lib/hermetic-guard.js";

const TMP = "/tmp";
const LIVE = "/home/agent/.scitex/claude-code-telegrammer/runtime/claude-code-telegrammer";

describe("assertHermeticTestStore", () => {
  // THE CASE. Everything else is bookkeeping.
  test("THROWS when a test run would open a live production store", () => {
    expect(() => assertHermeticTestStore("test", LIVE, TMP)).toThrow();
  });

  test("the message names the cause and the fix, not just the symptom", () => {
    let msg = "";
    try {
      assertHermeticTestStore("test", LIVE, TMP);
    } catch (err) {
      msg = err instanceof Error ? err.message : String(err);
    }
    expect(msg).toContain("LIVE PRODUCTION DATABASE");
    expect(msg).toContain("preload");
    expect(msg).toContain("bunfig.toml"); // the actual cause
    expect(msg).toContain(LIVE); // the actual path it refused
  });

  test("allows a hermetic test store (the preload ran)", () => {
    expect(() =>
      assertHermeticTestStore("test", "/tmp/cct-test-1234", TMP),
    ).not.toThrow();
  });

  // The guard must be INERT in production. The real poller and MCP server open
  // the live store on purpose, every time they start — if this ever fired
  // there, it would take down the bridge it exists to protect.
  test("is inert outside a test run — production opens the live store on purpose", () => {
    expect(() => assertHermeticTestStore(undefined, LIVE, TMP)).not.toThrow();
    expect(() => assertHermeticTestStore("production", LIVE, TMP)).not.toThrow();
  });
});
