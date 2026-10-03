/**
 * Common-boundary style gates: the shared telegram-api.ts send paths must
 * enforce the parenthetical PR rule BEFORE any signing, splitting, file read
 * or API delivery — covering native/API callers, not just MCP tools.
 *
 * Proof is on the wire: a REAL local fake Telegram server (no mocks, no
 * fetch patching). Invalid bodies must throw with zero recorded requests;
 * valid bodies must arrive intact. The config module is redirected at the
 * fake server via mock.module (bun built-in); nothing leaves loopback.
 */

import { describe, test, expect, mock, afterAll } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { startFakeTelegram } from "./helpers/fake-telegram.js";

const fake = startFakeTelegram();

mock.module("../lib/config.js", () => ({
  API_BASE: `${fake.url}/botTESTTOKEN`,
  FILE_BASE: `${fake.url}/file/botTESTTOKEN`,
  MAX_TEXT: 4096,
}));

import {
  sendMessage,
  editMessageText,
  sendDocument,
} from "../lib/telegram-api.js";

afterAll(async () => {
  await fake.stop();
});

describe("common send boundary rejects malformed PR bodies pre-delivery", () => {
  test("sendMessage throws before any API call", async () => {
    const before = fake.calls("sendMessage").length;
    await expect(sendMessage("11", "#409 fix it")).rejects.toThrow(
      "unlabeled PR reference",
    );
    expect(fake.calls("sendMessage")).toHaveLength(before);
  });

  test("editMessageText throws before any API call", async () => {
    const before = fake.calls("editMessageText").length;
    await expect(editMessageText("11", 5, "#409: fix it")).rejects.toThrow(
      "unlabeled PR reference",
    );
    expect(fake.calls("editMessageText")).toHaveLength(before);
  });

  test("sendDocument throws before file read or API call", async () => {
    const before = fake.calls("sendDocument").length;
    await expect(
      sendDocument("11", "/nonexistent-file-xyz.bin", "#409 (oops"),
    ).rejects.toThrow("unlabeled PR reference");
    expect(fake.calls("sendDocument")).toHaveLength(before);
  });

  test("full-width numeric-only parenthetical throws pre-delivery", async () => {
    const beforeMsg = fake.calls("sendMessage").length;
    await expect(sendMessage("11", "See #409（４２）")).rejects.toThrow(
      "unlabeled PR reference",
    );
    expect(fake.calls("sendMessage")).toHaveLength(beforeMsg);
    const beforeEdit = fake.calls("editMessageText").length;
    await expect(editMessageText("11", 5, "See #409（４２）")).rejects.toThrow(
      "unlabeled PR reference",
    );
    expect(fake.calls("editMessageText")).toHaveLength(beforeEdit);
  });
});

describe("common send boundary preserves valid delivery behavior", () => {
  test("valid parenthetical body arrives intact", async () => {
    const id = await sendMessage("11", "Shipped #409 (empty-root init fix)");
    expect(typeof id).toBe("number");
    const [call] = fake.calls("sendMessage").slice(-1);
    expect(call.body?.text).toBe("Shipped #409 (empty-root init fix)");
  });

  test("long valid body still splits into chunks", async () => {
    const before = fake.calls("sendMessage").length;
    await sendMessage("11", `${"x".repeat(5000)} #409 (chunk proof)`);
    expect(fake.calls("sendMessage").length).toBeGreaterThan(before + 1);
  });

  test("valid edit arrives intact", async () => {
    await editMessageText("11", 7, "Corrected #409 (empty-root init fix)");
    const [call] = fake.calls("editMessageText").slice(-1);
    expect(call.body?.text).toBe("Corrected #409 (empty-root init fix)");
  });

  test("valid caption delivers the document", async () => {
    const dir = mkdtempSync(join(tmpdir(), "cct-cap-"));
    try {
      const file = join(dir, "note.txt");
      writeFileSync(file, "hello");
      const id = await sendDocument("11", file, "Notes #409 (review pack)");
      expect(typeof id).toBe("number");
      expect(fake.calls("sendDocument").length).toBeGreaterThan(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("empty caption still delivers without PR text", async () => {
    const dir = mkdtempSync(join(tmpdir(), "cct-cap-"));
    try {
      const file = join(dir, "note.txt");
      writeFileSync(file, "hello");
      const before = fake.calls("sendDocument").length;
      await sendDocument("11", file);
      expect(fake.calls("sendDocument")).toHaveLength(before + 1);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
