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
 *
 * Result shape (#14, 2026-06-07): wakeTurn now returns a WakeResult
 * discriminated union ({ok:true, status} | {ok:false, status?, reason,
 * category}) so the caller can distinguish HTTP 401/403 ("auth"),
 * ECONNREFUSED ("connection_refused"), 5xx ("server_error"), etc. —
 * lib/loudfail.ts maps the category to a human-readable Telegram reply
 * the operator sees on inbound failures ("⚠️ <agent> unavailable: <reason>
 * — retry <when>"). The previous boolean return was lossy: the operator
 * saw ❌ with no detail and could not tell "agent down" from "auth
 * misconfigured" from "transient 502".
 */

import { TURN_URL, TURN_BEARER } from "./config.js";
import { log } from "./log.js";
import { neutralizeChannelEnvelope } from "./sanitize.js";

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
 * Categorised failure modes when wakeTurn cannot deliver to /v1/turn.
 *
 *   - timeout            — fetch throws an AbortError / timeout / network
 *                          stall. Likely cause: agent is mid-turn and over
 *                          its per-turn deadline, OR network partition.
 *   - connection_refused — fetch throws ECONNREFUSED. Likely cause: the
 *                          SDK-runner process is dead and nothing is bound
 *                          to its /v1/turn port.
 *   - auth               — HTTP 401 / 403. Likely cause: TURN_BEARER is
 *                          wrong / expired, or the operator rotated the
 *                          token.
 *   - quota_capped       — HTTP 429 (Too Many Requests). The Claude account
 *                          attached to this agent has hit its 5h or 7d
 *                          rate-limit ceiling. lib/loudfail.ts looks up
 *                          the reset time from usage.json and renders it
 *                          into the operator-facing reply ("retry after
 *                          14:30") so they know when the wall lifts.
 *   - client_error       — any other 4xx. Likely cause: the wake body
 *                          shape changed and the agent doesn't accept it
 *                          (bridge-side bug — fix the wakeText framing).
 *   - server_error       — any 5xx. Likely cause: agent runner crashed
 *                          mid-turn or its dependencies are down.
 *   - unknown            — anything else (a thrown non-Error, an exotic
 *                          status). Surface verbatim in logs.
 */
export type WakeFailCategory =
  | "timeout"
  | "connection_refused"
  | "auth"
  | "quota_capped"
  | "client_error"
  | "server_error"
  | "unknown";

/** Discriminated union — callers branch on result.ok then narrow. */
export type WakeResult =
  | { ok: true; status: number }
  | {
      ok: false;
      status?: number;
      reason: string;
      category: WakeFailCategory;
    };

/**
 * Low-level turn poster. Overridable in tests via setTurnPoster() so the
 * wake path can be exercised without a real /v1/turn server. Returns the
 * HTTP status code on success OR throws an Error subclass on transport
 * failure (the caller categorises the thrown error). Tests pass async
 * functions that either resolve to a number or throw an Error with a
 * descriptive message ("connect ECONNREFUSED", "network timeout", ...) —
 * we match on the error message just like the real fetch path would.
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
 *
 * The body is run through neutralizeChannelEnvelope() FIRST so a message that
 * itself contains `<channel ...>` / `</channel>` cannot open or prematurely
 * close this envelope (which would mis-frame the turn / inject a fake channel
 * notification). Only the `<channel>` envelope tokens are neutralized; all
 * other angle brackets in the body are preserved verbatim.
 */
export function wakeText(text: string, meta: WakeMeta): string {
  const attrs = ["source", "chat_id", "message_id", "row_id", "user", "user_id"]
    .filter((k) => meta[k] != null && meta[k] !== "")
    .map((k) => `${k}="${meta[k]}"`)
    .join(" ");
  const safeBody = neutralizeChannelEnvelope(text);
  return `<channel ${attrs}>\n${safeBody}\n</channel>`;
}

/**
 * Map an HTTP status code returned by /v1/turn to a WakeFailCategory.
 * Exported so loudfail.ts (and tests) can reuse the same classifier.
 */
export function categoriseStatus(status: number): WakeFailCategory {
  if (status === 401 || status === 403) return "auth";
  if (status === 429) return "quota_capped";
  if (status >= 400 && status < 500) return "client_error";
  if (status >= 500 && status < 600) return "server_error";
  return "unknown";
}

/**
 * Map a thrown Error from the fetch path to a WakeFailCategory. Pattern-
 * matches well-known node/undici/Bun error messages; falls back to
 * "unknown" for unrecognised shapes.
 */
export function categoriseError(err: unknown): WakeFailCategory {
  const msg = err instanceof Error ? err.message : String(err);
  const m = msg.toLowerCase();
  if (m.includes("econnrefused") || m.includes("connection refused")) {
    return "connection_refused";
  }
  if (
    m.includes("timeout") ||
    m.includes("timed out") ||
    m.includes("aborterror") ||
    m.includes("etimedout")
  ) {
    return "timeout";
  }
  return "unknown";
}

/**
 * POST an inbound message to the agent's own /v1/turn to DRIVE a turn now.
 *
 * No-op when TURN_URL is unset (returns {ok:false, category:"unknown",
 * reason:"wake disabled (no TURN_URL)"}; the loud-fail path is gated on
 * wakeEnabled() upstream so this branch is unreachable in production).
 *
 * Always logs failures loudly at warning; never throws (must not crash the
 * relay or block delivery). The caller branches on result.ok to advance the
 * receipt reaction and, on failure, to send the loud-fail reply (#14).
 */
export async function wakeTurn(
  text: string,
  meta: WakeMeta,
): Promise<WakeResult> {
  if (!wakeEnabled()) {
    return {
      ok: false,
      reason: "wake disabled (no TURN_URL)",
      category: "unknown",
    };
  }
  try {
    const status = await turnPoster(
      TURN_URL,
      { text: wakeText(text, meta) },
      TURN_BEARER,
    );
    if (status >= 200 && status < 300) return { ok: true, status };
    log("wake", `WARNING: /v1/turn returned ${status}`, {
      level: "warning",
      turn_url: TURN_URL,
      status: String(status),
      chat_id: meta.chat_id,
      message_id: meta.message_id,
    });
    return {
      ok: false,
      status,
      reason: `HTTP ${status}`,
      category: categoriseStatus(status),
    };
  } catch (err) {
    const errStr = err instanceof Error ? err.message : String(err);
    log("wake", "WARNING: failed to POST /v1/turn", {
      level: "warning",
      turn_url: TURN_URL,
      chat_id: meta.chat_id,
      message_id: meta.message_id,
      error: errStr,
    });
    return {
      ok: false,
      reason: errStr,
      category: categoriseError(err),
    };
  }
}
