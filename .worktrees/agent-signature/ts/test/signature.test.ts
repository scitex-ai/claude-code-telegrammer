/**
 * Tests for the outbound agent-signature module (signature.ts) and its
 * integration in the outbound send path (sendMessage chunking + sendDocument
 * caption + editMessageText).
 */

import { describe, test, expect, beforeEach } from "bun:test";
import {
  buildSignature,
  isSigned,
  appendSignature,
} from "../lib/signature.js";
import { AGENT_ID, PROJECT, HOST_NAME } from "../lib/config.js";

describe("signature.buildSignature", () => {
  test("matches the operator-confirmed em-dash + label + cwd@host format", () => {
    const sig = buildSignature();
    expect(sig).toBe(`— ${AGENT_ID} (${PROJECT}@${HOST_NAME})`);
  });

  test("starts with the em-dash marker (visual separator from body)", () => {
    expect(buildSignature().startsWith("— ")).toBe(true);
  });

  test("contains the full workdir path (not the basename)", () => {
    // The operator was explicit: full path, not basename. PROJECT in
    // config.ts defaults to process.cwd() which is the bridge's full cwd.
    expect(buildSignature()).toContain(PROJECT);
    // Sanity: the path is absolute (starts with /) under POSIX.
    expect(PROJECT.startsWith("/")).toBe(true);
  });
});

describe("signature.isSigned", () => {
  test("true for text ending in the exact current signature", () => {
    expect(isSigned(`hello\n\n${buildSignature()}`)).toBe(true);
  });

  test("true with trailing whitespace / newlines (trimEnd-tolerant)", () => {
    expect(isSigned(`hello\n\n${buildSignature()}\n\n`)).toBe(true);
    expect(isSigned(`hello\n\n${buildSignature()}   `)).toBe(true);
  });

  test("false for plain unsigned text", () => {
    expect(isSigned("just a normal message")).toBe(false);
  });

  test("false for a different-shape manual signature (strict match)", () => {
    // Strict match — only OUR format suppresses auto-signing.
    expect(isSigned("hi\n\n-- somebody else (elsewhere)")).toBe(false);
  });
});

describe("signature.appendSignature", () => {
  test("appends signature on a fresh body with a blank-line separator", () => {
    const out = appendSignature("hello world");
    expect(out).toBe(`hello world\n\n${buildSignature()}`);
  });

  test("is idempotent — already-signed text passes through unchanged", () => {
    const once = appendSignature("hello");
    const twice = appendSignature(once);
    expect(twice).toBe(once);
  });

  test("idempotency tolerates trailing whitespace after the signature", () => {
    const once = appendSignature("hello") + "\n\n";
    const twice = appendSignature(once);
    expect(twice).toBe(once);
  });

  test("empty input → bare signature, no leading newlines", () => {
    expect(appendSignature("")).toBe(buildSignature());
  });

  test("preserves the body verbatim above the signature", () => {
    const body = "line1\nline2\n  indented\n```code```";
    const out = appendSignature(body);
    expect(out.startsWith(body)).toBe(true);
    expect(out.endsWith(buildSignature())).toBe(true);
  });
});

describe("signature integration — chunked sendMessage", () => {
  // The integration contract: sendMessage in telegram-api.ts calls
  // appendSignature BEFORE splitText. This test mirrors that ordering and
  // asserts the visible outcome: the LAST chunk carries the signature, and
  // it appears exactly once across the chunks.
  test("when sign+split produces multiple chunks, only the LAST chunk carries the signature", async () => {
    const { splitText } = await import("../lib/telegram-api.js");
    // Build a body large enough to force splitText to produce >= 2 chunks
    // (MAX_TEXT = 4096; 5000 'x' guarantees a split).
    const body = "x".repeat(5000);
    const signed = appendSignature(body);
    const chunks = splitText(signed);
    expect(chunks.length).toBeGreaterThanOrEqual(2);
    const signatureCount = chunks.filter((c) =>
      c.includes(buildSignature()),
    ).length;
    expect(signatureCount).toBe(1);
    expect(chunks[chunks.length - 1].endsWith(buildSignature())).toBe(true);
  });

  test("a short body produces a single chunk that ends with the signature", async () => {
    const { splitText } = await import("../lib/telegram-api.js");
    const signed = appendSignature("hi");
    const chunks = splitText(signed);
    expect(chunks.length).toBe(1);
    expect(chunks[0].endsWith(buildSignature())).toBe(true);
  });
});
