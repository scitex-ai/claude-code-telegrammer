/**
 * lib/poller-teardown.ts — the deliberately-stubbed teardown-vs-restart
 * distinction (scitex-todo card cct-mcp-server-periodic-drop-20260712).
 *
 * This pins the ONE contract that matters right now: the stub is a
 * SAFE DEFAULT that never self-terminates, regardless of how many times
 * (or how quickly) it's called. Once scitex-agent-container's answer lands
 * and this stub gains real logic, this test should be replaced with real
 * behavioural coverage — until then, a test asserting anything MORE than
 * "always false" would itself be guessing at the unresolved design
 * question, which is exactly what the stub (and this test) must not do.
 */

import { describe, test, expect } from "bun:test";
import { shouldSelfTerminateOnTeardown } from "../lib/poller-teardown.js";

describe("shouldSelfTerminateOnTeardown: safe-default stub", () => {
  test("resolves false", async () => {
    expect(await shouldSelfTerminateOnTeardown()).toBe(false);
  });

  test("resolves false consistently across repeated calls", async () => {
    for (let i = 0; i < 5; i++) {
      expect(await shouldSelfTerminateOnTeardown()).toBe(false);
    }
  });
});
