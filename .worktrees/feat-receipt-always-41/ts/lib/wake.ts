/**
 * Wake-on-push: POST an inbound Telegram message to an SDK-runner's /v1/turn.
 *
 * Inbound delivery via `notifications/claude/channel` renders a <channel> tag
 * for an ACTIVE turn, but does NOT advance an IDLE session. The standard
 * Claude Code CLI has a live event loop that surfaces the notification; an
 * SDK-runner session (e.g. a scitex-agent-container apptainer agent) is parked
 * on its inbox queue and never sees it. The stored message then sits unread /
 * unreplied forever — the "store fills, no turn appears" silent-failure class.
 *
 * When CLAUDE_CODE_TELEGRAMMER_TURN_URL is set, this module additionally POSTs
 * each qualifying inbound message to that endpoint (the agent's own /v1/turn)
 * so the runner enqueues it onto the persistent SDK conversation and drives a
 * turn at once — push behaves like the lead's interactive Telegram channel.
 *
 * Mirrors scitex-agent-container's `sac mcp channel --turn-url` wake primitive
 * (runtimes/_mcp/_channel_wake.py::_wake_turn): same <channel>-framed body so a
 * woken (idle) agent sees the same shape it would have seen mid-turn.
 *
 * Wake is:
 *   - opt-in:      no-op when TURN_URL is empty (interactive-CLI default)
 *   - best-effort: a failed POST is logged loudly at warning, never thrown —
 *                  it must not crash the relay or block delivery
 *   - injectable:  the POST function is overridable in tests (no real network)
 */

import { TURN_URL, TURN_BEARER } from "./config.js";
import { log } from "./log.js";

/** Metadata attached to an inbound message (subset used to frame the turn). */
export interface WakeMeta {
  chat_id?: string;
  message_id?: string;
  row_id?: string;
  user?: string;
  user_id?: string;
  source?: string;
  [key: string]: string | undefined;
}

/**
 * Low-level turn poster. Overridable in tests via setTurnPoster() so the wake
 * path can be exercised without a real /v1/turn server. Returns the HTTP
 * status code (callers only branch on ok/not-ok).
 */
type TurnPoster = (
  url: string,
  body: { text: string },
  bearer: string,
) => Promise<number>;

let turnPoster: TurnPoster = async (url, body, bearer) => {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (bearer) headers["Authorization"] = `Bearer ${bearer}`;
  // No client-side timeout: the runner imposes its own bounded per-turn
  // deadline and answers with a 504 — a short client timeout would abort a
  // legitimately long turn.
  const resp = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  return resp.status;
};

/** Test-only: override the turn poster. Returns the previous poster. */
export function setTurnPoster(poster: TurnPoster): TurnPoster {
  const prev = turnPoster;
  turnPoster = poster;
  return prev;
}

/** Whether wake-on-push is enabled (TURN_URL configured). */
export function wakeEnabled(): boolean {
  return TURN_URL.trim() !== "";
}

/**
 * Render the turn input fed to /v1/turn. Mirrors the <channel ...> framing
 * Claude renders for an in-session push so a woken (idle) agent sees the same
 * shape — source, ids, and the message body — attributed to its sender.
 */
export function wakeText(text: string, meta: WakeMeta): string {
  const attrs = ["source", "chat_id", "message_id", "row_id", "user", "user_id"]
    .filter((k) => meta[k] != null && meta[k] !== "")
    .map((k) => `${k}="${meta[k]}"`)
    .join(" ");
  return `<channel ${attrs}>\n${text}\n</channel>`;
}

/**
 * POST an inbound message to the agent's own /v1/turn to DRIVE a turn now.
 *
 * No-op when TURN_URL is unset. Returns true when the turn was accepted
 * (2xx), false on any failure (logged loudly, never thrown). The boolean lets
 * the caller decide whether to mark the message read on success.
 */
export async function wakeTurn(text: string, meta: WakeMeta): Promise<boolean> {
  if (!wakeEnabled()) return false;
  try {
    const status = await turnPoster(
      TURN_URL,
      { text: wakeText(text, meta) },
      TURN_BEARER,
    );
    if (status >= 200 && status < 300) return true;
    log("wake", `WARNING: /v1/turn returned ${status}`, {
      level: "warning",
      turn_url: TURN_URL,
      status: String(status),
      chat_id: meta.chat_id,
      message_id: meta.message_id,
    });
    return false;
  } catch (err) {
    log("wake", "WARNING: failed to POST /v1/turn", {
      level: "warning",
      turn_url: TURN_URL,
      chat_id: meta.chat_id,
      message_id: meta.message_id,
      error: String(err),
    });
    return false;
  }
}
