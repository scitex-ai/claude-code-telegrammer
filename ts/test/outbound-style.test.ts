import { describe, expect, test } from "bun:test";
import {
  assertLabeledPrReferences,
  unlabeledPrReferences,
} from "../lib/outbound-style.js";

describe("operator-facing PR references", () => {
  test("allows messages with no PR reference", () => {
    expect(unlabeledPrReferences("Landing is live in development.")).toEqual([]);
  });

  test("rejects a bare PR number", () => {
    expect(unlabeledPrReferences("Fixing #1503 now.")).toEqual(["#1503"]);
  });

  test("accepts each supported content label form", () => {
    const text = [
      "#1503 — agentic ACK protocol",
      "#201: project context contract",
      "#958 (Landing V2)",
    ].join("\n");
    expect(unlabeledPrReferences(text)).toEqual([]);
  });

  test("requires a label for every number in a multi-PR update", () => {
    const text = "#1503 — agentic ACK protocol / #1512";
    expect(unlabeledPrReferences(text)).toEqual(["#1512"]);
  });

  test("accepts Japanese labels", () => {
    expect(unlabeledPrReferences("#1512 — エージェント画面の非同期化")).toEqual([]);
  });

  test("throws an actionable send-boundary error", () => {
    expect(() => assertLabeledPrReferences("#409")).toThrow(
      "Write each as '#123 — what it changes'",
    );
  });
});
