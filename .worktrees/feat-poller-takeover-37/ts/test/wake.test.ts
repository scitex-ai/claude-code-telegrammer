/**
 * Tests for wakeText() — pure <channel> framing (no network).
 *
 * wakeTurn() itself reads TURN_URL from config at import time; the env-gated
 * branch (wakeEnabled / wakeTurn POST) is exercised via the injectable
 * setTurnPoster seam in an integration context, but the env is fixed per
 * process so we keep these tests to the pure framing logic + the injectable
 * poster contract that does not depend on TURN_URL being set.
 */

import { describe, test, expect } from "bun:test";
import { wakeText, setTurnPoster } from "../lib/wake.js";

describe("wakeText", () => {
  test("frames a plain message with source + ids", () => {
    const out = wakeText("hello world", {
      source: "telegram",
      chat_id: "123",
      message_id: "6",
      row_id: "4",
      user: "alice",
      user_id: "999",
    });
    expect(out).toBe(
      '<channel source="telegram" chat_id="123" message_id="6" row_id="4" user="alice" user_id="999">\n' +
        "hello world\n" +
        "</channel>",
    );
  });

  test("omits attributes whose meta values are missing", () => {
    const out = wakeText("hi", { source: "telegram", chat_id: "5" });
    expect(out).toBe('<channel source="telegram" chat_id="5">\nhi\n</channel>');
  });

  test("omits attributes whose meta values are empty strings", () => {
    const out = wakeText("hi", {
      source: "telegram",
      chat_id: "5",
      user: "",
    });
    expect(out).toBe('<channel source="telegram" chat_id="5">\nhi\n</channel>');
  });

  test("preserves the message body verbatim, including newlines", () => {
    const body = "line one\nline two";
    const out = wakeText(body, { source: "telegram" });
    expect(out).toBe(`<channel source="telegram">\n${body}\n</channel>`);
  });
});

describe("setTurnPoster", () => {
  test("returns the previous poster so callers can restore it", () => {
    const sentinel = async () => 200;
    const prev = setTurnPoster(sentinel);
    // Restore immediately; assert we got a callable back.
    const restored = setTurnPoster(prev);
    expect(typeof prev).toBe("function");
    expect(restored).toBe(sentinel);
  });
});
