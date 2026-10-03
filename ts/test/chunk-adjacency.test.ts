/**
 * Chunk adjacency: a split must never strand a bare PR reference in one
 * chunk and its parenthetical description in the next.
 *
 * Proof is on the wire against the local fake server. The style gate now
 * delegates to the canonical Python rule; these cases exercise the
 * TypeScript chunk repair plus per-chunk validation around it.
 */

import { describe, test, expect, mock, afterAll } from "bun:test";
import { startFakeTelegram } from "./helpers/fake-telegram.js";

const fake = startFakeTelegram();

mock.module("../lib/config.js", () => ({
  API_BASE: `${fake.url}/botTESTTOKEN`,
  FILE_BASE: `${fake.url}/file/botTESTTOKEN`,
  MAX_TEXT: 4096,
}));

import {
  sendMessage,
  keepPrParentheticalTogether,
  splitText,
} from "../lib/telegram-api.js";

afterAll(async () => {
  await fake.stop();
});

describe("chunk adjacency keeps number and parenthetical together", () => {
  test("witness: token stranded by the cut is rejoined before delivery", async () => {
    const text = `${"x".repeat(4089)} #1 (desc)`;
    const raw = splitText(text);
    expect(raw.length).toBeGreaterThan(1);
    expect(raw[0].endsWith("#1")).toBe(true);
    const before = fake.calls("sendMessage").length;
    await sendMessage("11", text);
    const sent = fake.calls("sendMessage").slice(before);
    expect(sent.length).toBeGreaterThan(0);
    for (const call of sent) {
      const body = String(call.body?.text ?? "");
      expect(body.includes("#1") && !body.includes("#1 (desc)")).toBe(false);
    }
    const joined = sent.map((c) => String(c.body?.text ?? "")).join("");
    expect(joined.replace(/\s+/g, " ")).toContain("#1 (desc)");
  });

  test("repair is a pure function on chunk arrays", () => {
    expect(keepPrParentheticalTogether(["abc #1", " (desc) def"])).toEqual([
      "abc",
      "#1 (desc) def",
    ]);
    expect(keepPrParentheticalTogether(["no refs here", "plain"])).toEqual([
      "no refs here",
      "plain",
    ]);
  });
});
