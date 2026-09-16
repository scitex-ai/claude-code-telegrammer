import { describe, expect, test } from "bun:test";
import {
  externalPollerEnabled,
  shouldStartInternalPoller,
} from "../lib/poller-mode.js";

describe("external poller contract", () => {
  test("accepts explicit truthy values", () => {
    for (const value of ["1", "true", "YES", " on "]) {
      expect(externalPollerEnabled(value)).toBe(true);
    }
  });

  test("does not activate accidentally", () => {
    for (const value of [undefined, "", "0", "false", "random"]) {
      expect(externalPollerEnabled(value)).toBe(false);
    }
  });

  test("one external owner means this MCP starts zero competing pollers", () => {
    expect(shouldStartInternalPoller(true, true)).toBe(false);
  });

  test("MCP owns the one poller only when no external owner is declared", () => {
    expect(shouldStartInternalPoller(true, false)).toBe(true);
    expect(shouldStartInternalPoller(false, false)).toBe(false);
  });
});
