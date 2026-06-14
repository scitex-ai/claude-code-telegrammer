/**
 * Tests for forward-metadata parser (forward.ts).
 *
 * Fixtures are REAL Telegram update-JSON shapes — no mocking layer.
 * Covers:
 *   - Bot API >=7.0 forward_origin variants: user, hidden_user, chat, channel
 *   - Legacy pre-7.0 forward_from / forward_from_chat / forward_sender_name
 *   - Forwarded media (document) + caption → attachment + caption + banner
 *     all survive together
 *   - Plain document + caption (no forward) — caption preserved
 *   - Non-forward message → returns null
 */

import { describe, test, expect } from "bun:test";
import {
  parseForward,
  forwardBanner,
  buildInboundText,
} from "../lib/forward.js";

// ── forward_origin (Bot API >=7.0) ─────────────────────────────────────────

describe("parseForward — forward_origin (Bot API >=7.0)", () => {
  test("type=user: visible user with first_name + last_name + username", () => {
    const update = {
      update_id: 100001,
      message: {
        message_id: 50,
        from: { id: 123, is_bot: false, first_name: "Bob" },
        chat: { id: 456, type: "private" },
        date: 1717564800,
        forward_origin: {
          type: "user",
          date: 1717564700,
          sender_user: {
            id: 789,
            is_bot: false,
            first_name: "Alice",
            last_name: "Smith",
            username: "alice_s",
          },
        },
        text: "Original message text",
      },
    };

    const info = parseForward(update.message);
    expect(info).not.toBeNull();
    expect(info!.kind).toBe("user");
    expect(info!.from_name).toBe("Alice Smith");
    expect(info!.from_id).toBe("789");
    expect(info!.from_username).toBe("alice_s");
    expect(info!.date_iso).toBe(new Date(1717564700 * 1000).toISOString());
  });

  test("type=user: falls back to username when no first/last name", () => {
    const msg = {
      message_id: 1,
      from: { id: 1, first_name: "x" },
      chat: { id: 1, type: "private" },
      date: 1717564800,
      forward_origin: {
        type: "user",
        date: 1717564700,
        sender_user: { id: 789, username: "namelessbot" },
      },
      text: "hi",
    };
    const info = parseForward(msg);
    expect(info!.from_name).toBe("namelessbot");
  });

  test("type=hidden_user: sender_user_name preserved", () => {
    const msg = {
      message_id: 51,
      from: { id: 123, first_name: "Bob" },
      chat: { id: 456, type: "private" },
      date: 1717564800,
      forward_origin: {
        type: "hidden_user",
        date: 1717564000,
        sender_user_name: "Private User",
      },
      text: "Forwarded from someone with privacy settings",
    };

    const info = parseForward(msg);
    expect(info!.kind).toBe("hidden_user");
    expect(info!.from_name).toBe("Private User");
    expect(info!.from_id).toBeUndefined();
    expect(info!.date_iso).toBe(new Date(1717564000 * 1000).toISOString());
  });

  test("type=chat: sender_chat with title + author_signature", () => {
    const msg = {
      message_id: 52,
      from: { id: 123, first_name: "Bob" },
      chat: { id: 456, type: "private" },
      date: 1717564800,
      forward_origin: {
        type: "chat",
        date: 1717564500,
        sender_chat: {
          id: -1001234567890,
          type: "supergroup",
          title: "Engineering",
          username: "eng_group",
        },
        author_signature: "anon-admin",
      },
      text: "From the eng group",
    };

    const info = parseForward(msg);
    expect(info!.kind).toBe("chat");
    expect(info!.from_name).toBe("Engineering");
    expect(info!.from_id).toBe("-1001234567890");
    expect(info!.from_username).toBe("eng_group");
    expect(info!.signature).toBe("anon-admin");
  });

  test("type=channel: chat + original message_id + author_signature", () => {
    const msg = {
      message_id: 53,
      from: { id: 123, first_name: "Bob" },
      chat: { id: 456, type: "private" },
      date: 1717564800,
      forward_origin: {
        type: "channel",
        date: 1717564400,
        chat: {
          id: -1009876543210,
          type: "channel",
          title: "News Channel",
          username: "news_ch",
        },
        message_id: 999,
        author_signature: "Editor",
      },
      text: "Channel post body",
    };

    const info = parseForward(msg);
    expect(info!.kind).toBe("channel");
    expect(info!.from_name).toBe("News Channel");
    expect(info!.from_id).toBe("-1009876543210");
    expect(info!.from_username).toBe("news_ch");
    expect(info!.original_message_id).toBe("999");
    expect(info!.signature).toBe("Editor");
  });
});

// ── Legacy forward fields (pre-Bot API 7.0) ────────────────────────────────

describe("parseForward — legacy pre-7.0 fields", () => {
  test("forward_from: visible user", () => {
    const msg = {
      message_id: 60,
      from: { id: 123, first_name: "Bob" },
      chat: { id: 456, type: "private" },
      date: 1717564800,
      forward_from: {
        id: 789,
        is_bot: false,
        first_name: "Carol",
        last_name: "Jones",
      },
      forward_date: 1717560000,
      text: "Legacy forward body",
    };

    const info = parseForward(msg);
    expect(info!.kind).toBe("user");
    expect(info!.from_name).toBe("Carol Jones");
    expect(info!.from_id).toBe("789");
    expect(info!.date_iso).toBe(new Date(1717560000 * 1000).toISOString());
  });

  test("forward_sender_name only: hidden user", () => {
    const msg = {
      message_id: 61,
      from: { id: 123, first_name: "Bob" },
      chat: { id: 456, type: "private" },
      date: 1717564800,
      forward_sender_name: "Anonymous",
      forward_date: 1717560000,
      text: "Hidden legacy forward",
    };

    const info = parseForward(msg);
    expect(info!.kind).toBe("hidden_user");
    expect(info!.from_name).toBe("Anonymous");
    expect(info!.from_id).toBeUndefined();
  });

  test("forward_from_chat (channel): legacy channel forward", () => {
    const msg = {
      message_id: 62,
      from: { id: 123, first_name: "Bob" },
      chat: { id: 456, type: "private" },
      date: 1717564800,
      forward_from_chat: {
        id: -1009876543210,
        type: "channel",
        title: "Old News Channel",
        username: "oldnews_ch",
      },
      forward_from_message_id: 4242,
      forward_signature: "Reporter",
      forward_date: 1717560000,
      text: "Legacy channel post",
    };

    const info = parseForward(msg);
    expect(info!.kind).toBe("channel");
    expect(info!.from_name).toBe("Old News Channel");
    expect(info!.from_id).toBe("-1009876543210");
    expect(info!.original_message_id).toBe("4242");
    expect(info!.signature).toBe("Reporter");
  });

  test("forward_from_chat (supergroup): treated as chat (not channel)", () => {
    const msg = {
      message_id: 63,
      from: { id: 123, first_name: "Bob" },
      chat: { id: 456, type: "private" },
      date: 1717564800,
      forward_from_chat: {
        id: -1001111,
        type: "supergroup",
        title: "Some Group",
      },
      forward_date: 1717560000,
      text: "Body",
    };

    const info = parseForward(msg);
    expect(info!.kind).toBe("chat");
    expect(info!.from_name).toBe("Some Group");
  });
});

// ── Negative cases ────────────────────────────────────────────────────────

describe("parseForward — non-forward messages", () => {
  test("plain text message returns null", () => {
    const msg = {
      message_id: 70,
      from: { id: 123, first_name: "Bob" },
      chat: { id: 456, type: "private" },
      date: 1717564800,
      text: "Hello, this was typed by Bob himself",
    };
    expect(parseForward(msg)).toBeNull();
  });

  test("message with reply_to_message but no forward returns null", () => {
    const msg = {
      message_id: 71,
      from: { id: 123, first_name: "Bob" },
      chat: { id: 456, type: "private" },
      date: 1717564800,
      reply_to_message: { message_id: 70, text: "Earlier" },
      text: "A reply, not a forward",
    };
    expect(parseForward(msg)).toBeNull();
  });

  test("null/undefined safe", () => {
    expect(parseForward(null)).toBeNull();
    expect(parseForward(undefined)).toBeNull();
    expect(parseForward({})).toBeNull();
  });
});

// ── forwardBanner format ──────────────────────────────────────────────────

describe("forwardBanner", () => {
  test("renders concise '[forwarded from <name>, <ts>]'", () => {
    const info = parseForward({
      forward_origin: {
        type: "user",
        date: 1717564700,
        sender_user: { id: 789, first_name: "Alice" },
      },
    })!;
    expect(forwardBanner(info)).toBe(
      `[forwarded from Alice, ${new Date(1717564700 * 1000).toISOString()}]`,
    );
  });
});

// ── buildInboundText: integration — caption + attachment + forward ───────

describe("buildInboundText", () => {
  test("plain text (no forward) passes through unchanged", () => {
    const msg = { text: "Hello" };
    expect(buildInboundText(msg)).toBe("Hello");
  });

  test("forwarded text: banner prepended above original text", () => {
    const msg = {
      forward_origin: {
        type: "user",
        date: 1717564700,
        sender_user: { id: 789, first_name: "Alice" },
      },
      text: "Original body",
    };
    expect(buildInboundText(msg)).toBe(
      `[forwarded from Alice, ${new Date(1717564700 * 1000).toISOString()}]\nOriginal body`,
    );
  });

  test("document + caption (no forward): placeholder AND caption both survive", () => {
    // Real-world: user attaches a PDF with a caption.
    // BOTH the (document: …) placeholder AND the caption MUST appear in
    // the agent-visible text. Operator-confirmed bug 2026-06-07: the
    // earlier "caption beats placeholder" behavior dropped the document
    // hint, so a woken SDK-runner agent (whose /v1/turn body carries
    // only the text string, not meta.attachment_*) never knew a file
    // was attached. Fix concatenates them so the agent reads
    // "(document: report.pdf) see attached PDF".
    const msg = {
      caption: "see attached PDF",
      document: {
        file_id: "BQACAgIAAxk_DOC_FILE_ID",
        file_unique_id: "AgADxxx",
        file_name: "report.pdf",
        mime_type: "application/pdf",
        file_size: 12345,
      },
    };
    expect(buildInboundText(msg)).toBe(
      "(document: report.pdf) see attached PDF",
    );
  });

  test("document only (no caption, no forward): placeholder used", () => {
    const msg = {
      document: { file_id: "X", file_name: "report.pdf" },
    };
    expect(buildInboundText(msg)).toBe("(document: report.pdf)");
  });

  test("forwarded media + caption: banner + caption both survive", () => {
    // The hardest case: user forwards a photo from a channel that has
    // a caption. The attachment file_id is checked separately in
    // poller.ts (and verified in the poller-flow test below); here we
    // confirm the AGENT TEXT carries banner + caption together.
    const msg = {
      caption: "Photo caption text",
      photo: [
        {
          file_id: "AgACPhoto_SMALL",
          file_unique_id: "u1",
          file_size: 100,
          width: 90,
          height: 90,
        },
        {
          file_id: "AgACPhoto_LARGE",
          file_unique_id: "u2",
          file_size: 50000,
          width: 1280,
          height: 720,
        },
      ],
      forward_origin: {
        type: "channel",
        date: 1717564400,
        chat: { id: -1009876543210, type: "channel", title: "News Channel" },
        message_id: 999,
      },
    };
    const text = buildInboundText(msg);
    expect(text).toContain("[forwarded from News Channel,");
    expect(text).toContain("Photo caption text");
    // (photo) placeholder MUST also appear so the agent sees the
    // attachment even when carried only by `text` (e.g. wake POST).
    expect(text).toContain("(photo)");
    // Banner must come FIRST
    expect(text.indexOf("[forwarded")).toBe(0);
    expect(text.indexOf("Photo caption text")).toBeGreaterThan(
      text.indexOf("[forwarded"),
    );
    // Placeholder appears before the caption in the body
    expect(text.indexOf("(photo)")).toBeLessThan(
      text.indexOf("Photo caption text"),
    );
  });

  test("forwarded media WITHOUT caption: banner + placeholder", () => {
    const msg = {
      photo: [{ file_id: "AgACPhoto_LARGE" }],
      forward_origin: {
        type: "hidden_user",
        date: 1717564400,
        sender_user_name: "Anon",
      },
    };
    const text = buildInboundText(msg);
    expect(text).toContain("[forwarded from Anon,");
    expect(text).toContain("(photo)");
  });

  test("legacy forwarded document + caption: banner + placeholder + caption", () => {
    const msg = {
      caption: "doc caption legacy",
      document: { file_id: "X", file_name: "spec.pdf" },
      forward_from: { id: 999, first_name: "Dave" },
      forward_date: 1717560000,
    };
    const text = buildInboundText(msg);
    expect(text).toContain("[forwarded from Dave,");
    expect(text).toContain("(document: spec.pdf)");
    expect(text).toContain("doc caption legacy");
    // Order: banner → placeholder → caption
    expect(text.indexOf("[forwarded")).toBeLessThan(
      text.indexOf("(document: spec.pdf)"),
    );
    expect(text.indexOf("(document: spec.pdf)")).toBeLessThan(
      text.indexOf("doc caption legacy"),
    );
  });
});
