/**
 * Telegram forward-metadata parser.
 *
 * Captures provenance for FORWARDED messages so the agent sees
 * "[forwarded from <whom>, <when>]" instead of plain text with no
 * context.
 *
 * Handles BOTH:
 *
 *   - Bot API >=7.0:   message.forward_origin (MessageOrigin)
 *       type=user         | sender_user
 *       type=hidden_user  | sender_user_name
 *       type=chat         | sender_chat, author_signature?
 *       type=channel      | chat, message_id, author_signature?
 *       date (unix seconds)
 *
 *   - Legacy (pre-7.0): message.forward_from / forward_from_chat /
 *                       forward_sender_name / forward_from_message_id /
 *                       forward_signature / forward_date
 *
 * Real Telegram clients still surface forward_origin for new updates,
 * but stored history and some bot frameworks emit legacy fields; we
 * handle both for safety.
 */

export type ForwardKind = "user" | "hidden_user" | "chat" | "channel";

export interface ForwardInfo {
  /** Origin classification. */
  kind: ForwardKind;
  /** Human-readable "from whom" string for the banner. */
  from_name: string;
  /** User or chat id (as string) when available. */
  from_id?: string;
  /** @handle when available. */
  from_username?: string;
  /** Original channel post id (channel forwards only). */
  original_message_id?: string;
  /** author_signature (channel posts / anonymous chat admins). */
  signature?: string;
  /** ISO-8601 timestamp of the original message. */
  date_iso: string;
  /** Raw forward block (forward_origin object OR legacy fields). */
  raw: Record<string, unknown>;
}

function isoFromUnix(seconds: unknown): string {
  const n = typeof seconds === "number" ? seconds : Number(seconds) || 0;
  return new Date(n * 1000).toISOString();
}

function fullName(user: any): string {
  if (!user) return "";
  const parts = [user.first_name, user.last_name].filter(
    (v) => typeof v === "string" && v.length > 0,
  );
  const joined = parts.join(" ").trim();
  if (joined) return joined;
  if (typeof user.username === "string" && user.username.length > 0) {
    return user.username;
  }
  return user.id !== undefined ? String(user.id) : "user";
}

/**
 * Extract forward metadata from a Telegram Message object.
 * Returns null when the message is NOT a forward.
 */
export function parseForward(msg: any): ForwardInfo | null {
  if (!msg || typeof msg !== "object") return null;

  // ── Modern: Bot API >=7.0 (forward_origin) ────────────────────────────
  const origin = msg.forward_origin;
  if (origin && typeof origin === "object") {
    const date_iso = isoFromUnix(origin.date);

    if (origin.type === "user") {
      const u = origin.sender_user ?? {};
      return {
        kind: "user",
        from_name: fullName(u),
        from_id: u.id !== undefined ? String(u.id) : undefined,
        from_username: typeof u.username === "string" ? u.username : undefined,
        date_iso,
        raw: origin,
      };
    }

    if (origin.type === "hidden_user") {
      const name =
        typeof origin.sender_user_name === "string" &&
        origin.sender_user_name.length > 0
          ? origin.sender_user_name
          : "hidden user";
      return {
        kind: "hidden_user",
        from_name: name,
        date_iso,
        raw: origin,
      };
    }

    if (origin.type === "chat") {
      const c = origin.sender_chat ?? {};
      const name =
        (typeof c.title === "string" && c.title) ||
        (typeof c.username === "string" && c.username) ||
        (c.id !== undefined ? String(c.id) : "chat");
      return {
        kind: "chat",
        from_name: String(name),
        from_id: c.id !== undefined ? String(c.id) : undefined,
        from_username: typeof c.username === "string" ? c.username : undefined,
        signature:
          typeof origin.author_signature === "string"
            ? origin.author_signature
            : undefined,
        date_iso,
        raw: origin,
      };
    }

    if (origin.type === "channel") {
      const c = origin.chat ?? {};
      const name =
        (typeof c.title === "string" && c.title) ||
        (typeof c.username === "string" && c.username) ||
        (c.id !== undefined ? String(c.id) : "channel");
      return {
        kind: "channel",
        from_name: String(name),
        from_id: c.id !== undefined ? String(c.id) : undefined,
        from_username: typeof c.username === "string" ? c.username : undefined,
        original_message_id:
          origin.message_id !== undefined
            ? String(origin.message_id)
            : undefined,
        signature:
          typeof origin.author_signature === "string"
            ? origin.author_signature
            : undefined,
        date_iso,
        raw: origin,
      };
    }

    // Unknown origin.type — still record it so provenance isn't lost
    return {
      kind: "user",
      from_name:
        typeof origin.type === "string"
          ? `unknown (${origin.type})`
          : "unknown",
      date_iso,
      raw: origin,
    };
  }

  // ── Legacy: pre-7.0 forward_* fields ──────────────────────────────────
  const hasLegacy =
    msg.forward_from ||
    msg.forward_from_chat ||
    typeof msg.forward_sender_name === "string";
  if (!hasLegacy) return null;

  const date_iso = isoFromUnix(msg.forward_date);
  const legacyRaw: Record<string, unknown> = {};
  if (msg.forward_from !== undefined) legacyRaw.forward_from = msg.forward_from;
  if (msg.forward_from_chat !== undefined)
    legacyRaw.forward_from_chat = msg.forward_from_chat;
  if (msg.forward_from_message_id !== undefined)
    legacyRaw.forward_from_message_id = msg.forward_from_message_id;
  if (msg.forward_sender_name !== undefined)
    legacyRaw.forward_sender_name = msg.forward_sender_name;
  if (msg.forward_signature !== undefined)
    legacyRaw.forward_signature = msg.forward_signature;
  if (msg.forward_date !== undefined) legacyRaw.forward_date = msg.forward_date;

  if (msg.forward_from) {
    const u = msg.forward_from;
    return {
      kind: "user",
      from_name: fullName(u),
      from_id: u.id !== undefined ? String(u.id) : undefined,
      from_username: typeof u.username === "string" ? u.username : undefined,
      date_iso,
      raw: legacyRaw,
    };
  }

  if (msg.forward_from_chat) {
    const c = msg.forward_from_chat;
    const kind: ForwardKind = c.type === "channel" ? "channel" : "chat";
    const name =
      (typeof c.title === "string" && c.title) ||
      (typeof c.username === "string" && c.username) ||
      (c.id !== undefined ? String(c.id) : kind);
    return {
      kind,
      from_name: String(name),
      from_id: c.id !== undefined ? String(c.id) : undefined,
      from_username: typeof c.username === "string" ? c.username : undefined,
      original_message_id:
        msg.forward_from_message_id !== undefined
          ? String(msg.forward_from_message_id)
          : undefined,
      signature:
        typeof msg.forward_signature === "string"
          ? msg.forward_signature
          : undefined,
      date_iso,
      raw: legacyRaw,
    };
  }

  // forward_sender_name only (hidden user, legacy)
  return {
    kind: "hidden_user",
    from_name:
      typeof msg.forward_sender_name === "string" &&
      msg.forward_sender_name.length > 0
        ? msg.forward_sender_name
        : "hidden user",
    date_iso,
    raw: legacyRaw,
  };
}

/**
 * Render the concise provenance banner the operator sees:
 *   "[forwarded from <name>, <iso-ts>]"
 */
export function forwardBanner(info: ForwardInfo): string {
  return `[forwarded from ${info.from_name}, ${info.date_iso}]`;
}

/**
 * Compute the text the agent sees, given a raw Telegram message:
 *   - text/caption are the BODY
 *   - every attached media yields a PLACEHOLDER ("(document: x)", "(photo)", …)
 *   - placeholder + body coexist when both are present; body alone otherwise
 *   - forward banner prepended last (always on top when present)
 *
 * Why placeholder + body MUST coexist (operator-confirmed bug 2026-06-07):
 *   Previously `text = text || "(document: …)"` short-circuited: once
 *   `text` was the caption (truthy) the placeholder was DROPPED. The DB
 *   row had the caption + the attachments table had the file_id, but the
 *   agent-visible text never mentioned the document. Worse, the wake-on-
 *   push /v1/turn body carries only the rendered `text` string (no
 *   meta.attachment_kind / attachment_file_id), so an IDLE SDK-runner
 *   agent woken via /v1/turn had NO way to know a file was attached when
 *   the sender included a caption. Repro: a .md sent ALONE arrived as
 *   "(document: foo.md)" → agent knew; the SAME .md WITH "please review"
 *   arrived as just "please review" → document silently dropped from
 *   agent awareness. Fix: concatenate placeholder THEN body so the agent
 *   reads e.g. "(document: foo.md) please review".
 *
 * Centralised so poller.ts and tests exercise identical logic.
 */
export function buildInboundText(msg: any): string {
  const body: string = msg?.text ?? msg?.caption ?? "";

  const placeholders: string[] = [];
  if (msg?.photo) placeholders.push("(photo)");
  if (msg?.document)
    placeholders.push(`(document: ${msg.document.file_name ?? "file"})`);
  if (msg?.voice) placeholders.push("(voice message)");
  if (msg?.audio) placeholders.push("(audio)");
  if (msg?.video) placeholders.push("(video)");
  if (msg?.sticker) {
    const emoji = msg.sticker.emoji ? ` ${msg.sticker.emoji}` : "";
    placeholders.push(`(sticker${emoji})`);
  }

  let text: string;
  if (placeholders.length && body) {
    text = `${placeholders.join(" ")} ${body}`;
  } else if (placeholders.length) {
    text = placeholders.join(" ");
  } else {
    text = body;
  }

  const fwd = parseForward(msg);
  if (fwd) {
    const banner = forwardBanner(fwd);
    text = text ? `${banner}\n${text}` : banner;
  }
  return text;
}

/**
 * Render the bracketed attachment descriptor appended to the DELIVERED
 * content line for media messages (incident
 * cct-inbound-images-20260707).
 *
 * Why this must ride in the CONTENT string and not only in meta: the
 * Claude Code harness renders a WHITELIST of meta keys (source, chat_id,
 * message_id, row_id, user, ts) into the <channel> tag — the
 * attachment_kind / attachment_file_id meta poller.ts sets is silently
 * dropped (live-verified 2026-07-07: a real photo rendered as bare
 * "(photo)"). The content string is always rendered, so the file_id and
 * the retrieval instruction travel there. meta keeps the structured
 * copy for forward-compat.
 *
 * One line, deterministic, greppable:
 *   [attachment kind=photo file_id=AgACAg... — call
 *    download_attachment(file_id) for the local path]
 * file name + mime are included when present (documents).
 */
export function attachmentDescriptor(
  kind: string,
  att: { file_id: string; file_name?: string; mime_type?: string },
): string {
  const parts = [`kind=${kind}`, `file_id=${att.file_id}`];
  if (att.file_name) parts.push(`name=${att.file_name}`);
  if (att.mime_type) parts.push(`mime=${att.mime_type}`);
  return `[attachment ${parts.join(" ")} — call download_attachment(file_id) for the local path]`;
}
