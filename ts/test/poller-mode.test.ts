import { describe, expect, test } from "bun:test";
import { externalPollerEnabled } from "../lib/poller-mode.js";

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
});
