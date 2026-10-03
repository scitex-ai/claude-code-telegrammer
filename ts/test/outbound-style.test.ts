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

  test("accepts the complete parenthetical form", () => {
    const text = ["#1503 (agentic ACK protocol)", "#958 (Landing V2)"].join(
      "\n",
    );
    expect(unlabeledPrReferences(text)).toEqual([]);
  });

  test("rejects dash and colon labels", () => {
    expect(unlabeledPrReferences("#1503 — agentic ACK protocol")).toEqual([
      "#1503",
    ]);
    expect(unlabeledPrReferences("#201: project context contract")).toEqual([
      "#201",
    ]);
  });

  test("rejects unclosed, empty and numeric-only parentheses", () => {
    expect(unlabeledPrReferences("#1503 (Landing V2")).toEqual(["#1503"]);
    expect(unlabeledPrReferences("#1503 ()")).toEqual(["#1503"]);
    expect(unlabeledPrReferences("#1503 (1503)")).toEqual(["#1503"]);
  });

  test("rejects newline-split descriptions", () => {
    expect(unlabeledPrReferences("#1503 (\nLanding V2)")).toEqual(["#1503"]);
  });

  test("rejects line breaks between number and parenthetical", () => {
    expect(unlabeledPrReferences("#1503\n(Landing V2)")).toEqual(["#1503"]);
    expect(unlabeledPrReferences("#1503\r\n(Landing V2)")).toEqual(["#1503"]);
    expect(unlabeledPrReferences("#1503\r(Landing V2)")).toEqual(["#1503"]);
  });

  test("rejects Unicode line separators around and inside the description", () => {
    const LS = String.fromCharCode(0x2028);
    const PS = String.fromCharCode(0x2029);
    expect(unlabeledPrReferences(`#1503${LS}(Landing V2)`)).toEqual(["#1503"]);
    expect(unlabeledPrReferences(`#1503${PS}(Landing V2)`)).toEqual(["#1503"]);
    expect(unlabeledPrReferences(`#1503 (a${LS}b)`)).toEqual(["#1503"]);
    expect(unlabeledPrReferences(`#1503 (a${PS}b)`)).toEqual(["#1503"]);
    expect(unlabeledPrReferences("#1503 (a\rb)")).toEqual(["#1503"]);
  });

  test("rejects full-width numeric-only descriptions", () => {
    expect(unlabeledPrReferences("#1503（１２３）")).toEqual(["#1503"]);
    expect(unlabeledPrReferences("#1503（）")).toEqual(["#1503"]);
  });

  test("rejects ideographic-space separation as non-clause", () => {
    // Deliberately narrow: only ASCII space/tab join number and paren.
    expect(unlabeledPrReferences("#1503　(Landing V2)")).toEqual(["#1503"]);
  });

  test("keeps space and tab separation", () => {
    expect(unlabeledPrReferences("#1503 (Landing V2)")).toEqual([]);
    expect(unlabeledPrReferences("#1503\t(Landing V2)")).toEqual([]);
  });

  test("accepts full-width parentheses with Japanese descriptions", () => {
    expect(unlabeledPrReferences("#1512（エージェント画面の非同期化）")).toEqual(
      [],
    );
  });

  test("rejects mixed parentheses", () => {
    expect(unlabeledPrReferences("#1512（Landing V2)")).toEqual(["#1512"]);
  });

  test("requires a label for every number in a multi-PR update", () => {
    const text = "#1503 (agentic ACK protocol) / #1512";
    expect(unlabeledPrReferences(text)).toEqual(["#1512"]);
  });

  test("accepts Japanese labels", () => {
    expect(unlabeledPrReferences("#1512 (エージェント画面の非同期化)")).toEqual(
      [],
    );
  });

  test("throws an actionable send-boundary error", () => {
    expect(() => assertLabeledPrReferences("#409")).toThrow(
      "Write each as '#123 (what it changes)'",
    );
  });
});
