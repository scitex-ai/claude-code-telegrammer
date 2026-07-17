/**
 * parseSendArgs — the MCP-independent outbound send path.
 *
 * Card cct-cli-send-outbound-path-independent-of-mcp. `grant` had a
 * time-critical finding for the operator, the cct MCP server was down, and it
 * could not deliver. This mode is the path that would have worked.
 *
 * The parse FAILURES are the important cases: an agent reaching for this is
 * already in a degraded state, so a malformed invocation must fail loudly
 * rather than quietly send the wrong thing (or the wrong text) and let the
 * agent believe the operator was reached.
 */

import { describe, test, expect } from "bun:test";
import { parseSendArgs } from "../lib/send-cli.js";

describe("parseSendArgs", () => {
  test("parses the minimal invocation", () => {
    const r = parseSendArgs(["--chat-id", "8379369979", "--text", "hello"]);
    expect(r).toEqual({
      ok: true,
      args: { chatId: "8379369979", text: "hello" },
    });
  });

  test("parses an optional --reply-to", () => {
    const r = parseSendArgs([
      "--chat-id",
      "1",
      "--text",
      "hi",
      "--reply-to",
      "4242",
    ]);
    expect(r).toEqual({
      ok: true,
      args: { chatId: "1", text: "hi", replyTo: 4242 },
    });
  });

  test("rejects a missing --chat-id", () => {
    const r = parseSendArgs(["--text", "hello"]);
    expect(r.ok).toBe(false);
  });

  test("rejects a missing --text", () => {
    const r = parseSendArgs(["--chat-id", "1"]);
    expect(r.ok).toBe(false);
  });

  // `--text --chat-id 5` must NOT quietly send the literal string "--chat-id".
  // A message the agent never wrote reaching the operator is worse than an
  // error it can see and retry.
  test("rejects a flag whose value is the next flag, not a value", () => {
    const r = parseSendArgs(["--text", "--chat-id", "5"]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain("--text");
  });

  test("rejects a trailing flag with no value at all", () => {
    const r = parseSendArgs(["--chat-id", "1", "--text"]);
    expect(r.ok).toBe(false);
  });

  // A garbled --reply-to must not silently degrade into an unthreaded send:
  // the caller asked for a thread, so failing to thread is a failure.
  test("rejects a non-numeric --reply-to instead of dropping it", () => {
    const r = parseSendArgs([
      "--chat-id",
      "1",
      "--text",
      "hi",
      "--reply-to",
      "not-a-number",
    ]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain("--reply-to");
  });

  test("rejects a non-positive --reply-to", () => {
    const r = parseSendArgs([
      "--chat-id",
      "1",
      "--text",
      "hi",
      "--reply-to",
      "0",
    ]);
    expect(r.ok).toBe(false);
  });

  test("accepts text that itself looks like prose with dashes", () => {
    const r = parseSendArgs(["--chat-id", "1", "--text", "done - all green"]);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.args.text).toBe("done - all green");
  });
});
