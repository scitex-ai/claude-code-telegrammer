/**
 * Standalone outbound self-healing for claude-code-telegrammer (no SAC dependency).
 *
 * WHAT THIS CLOSES: `executeDurableSend` (lib/send-cli.ts) proves a message
 * was recorded locally after ONE sendMessage call. If that call throws
 * (transport black-hole, 429, 5xx) or Telegram accepts it but the backup
 * route was the one that was actually alive, the operator still goes silent —
 * and the caller cannot tell "failed, retry me" from "sent". This module adds
 * the three missing pieces, all dependency-injectable so they are
 * unit-testable with no token and no network:
 *
 *   1. DELIVERY-CONFIRM LOOP — {@link confirmDelivery}. The Bot API has no
 *      "did the human read it" (bots cannot see reads on their own messages),
 *      so "confirmed" here is honestly scoped: Telegram persisted it
 *      (sendMessage ok:true + message_id) AND the chat is still reachable
 *      afterwards (getChat succeeds — catches "accepted then bot blocked /
 *      kicked / chat deleted", which surfaces as 403/400 on the very next
 *      call). A failed verify marks the send UNCONFIRMED, never silently OK.
 *
 *   2. BOUNDED RETRY WITH BACKOFF — {@link sendWithRetry}. Transport errors,
 *      429 and 5xx are retried up to `maxAttempts` with exponential backoff
 *      (baseMs * 2^attempt, capped at maxDelayMs); 400/401/403/404 fail fast.
 *      The bound is the point: an unbounded loop wedges the CLI past every
 *      caller timeout, an unthrottled loop earns a 429 ban.
 *
 *   3. ROUTE-SWITCH FALLBACK — {@link sendWithFailover}. A route is
 *      { token, apiRoot }: primary comes from BOT_TOKEN / TELEGRAM_API_BASE,
 *      backup from BOT_TOKEN_BACKUP / TELEGRAM_API_BASE_BACKUP (same getenv
 *      alias system as everything else, env-injectable for tests). Route A is
 *      retried to exhaustion, then route B is tried once through the same
 *      retry policy. A 401 on route A skips straight to route B (a dead token
 *      never heals by waiting). No backup configured = single-route behaviour,
 *      unchanged from today.
 *
 * Nothing here imports sac, TURN_URL, wake, notify-relay, or the MCP server.
 * The only seams are env (getenv), log, and caller-supplied send/verify
 * functions — CCT heals itself with its own Bot API access.
 */

import { getenv } from "./env.js";
import { log } from "./log.js";
import { DEFAULT_API_ROOT } from "./api-root.js";

// ── Routes ───────────────────────────────────────────────────────────────────

/** One outbound path: which token, against which Bot API origin. */
export interface OutboundRoute {
  /** Human label for logs ("primary" / "backup"). */
  label: string;
  /** Bot token used for `.../bot<token>/...` on this route. */
  token: string;
  /** Origin BEFORE `/bot<token>` (default https://api.telegram.org). */
  apiRoot: string;
}

/**
 * Resolve the outbound routes from the environment. Primary token is
 * REQUIRED (empty/absent → empty array, caller fails loud). Backup token is
 * optional; backup API root defaults to the primary root when unset.
 */
export function resolveOutboundRoutes(
  env: Record<string, string | undefined> = process.env,
): OutboundRoute[] {
  const primaryToken = getenv("BOT_TOKEN", undefined, env) ?? "";
  if (primaryToken.length === 0) return [];
  const primaryRoot =
    getenv("TELEGRAM_API_BASE", undefined, env) ?? DEFAULT_API_ROOT;
  const routes: OutboundRoute[] = [
    { label: "primary", token: primaryToken, apiRoot: primaryRoot },
  ];
  const backupToken = getenv("BOT_TOKEN_BACKUP", undefined, env) ?? "";
  if (backupToken.length > 0) {
    const backupRoot =
      getenv("TELEGRAM_API_BASE_BACKUP", undefined, env) ?? primaryRoot;
    routes.push({ label: "backup", token: backupToken, apiRoot: backupRoot });
  }
  return routes;
}

// ── Retry classification ─────────────────────────────────────────────────────

/** A send failure carrying enough structure to classify retryability. */
export interface SendFailure {
  /** Transport-level failure (DNS/connect/reset/timeout): always retryable. */
  transport?: unknown;
  /** Telegram error_code (429/5xx retryable; 400/401/403/404 terminal). */
  errorCode?: number;
  message: string;
}

export function isRetryableFailure(f: SendFailure): boolean {
  if (f.transport !== undefined) return true;
  const code = f.errorCode;
  if (code === undefined) return true; // unknown shape: retry, bounded anyway
  if (code === 429) return true;
  if (code >= 500) return true;
  return false;
}

/** 401 (bad token) means the route itself is dead — never healed by waiting. */
export function isRouteDeadFailure(f: SendFailure): boolean {
  return f.errorCode === 401;
}

// ── Bounded retry with backoff ───────────────────────────────────────────────

export interface RetryPolicy {
  /** Total attempts including the first (default 5). Must be >= 1. */
  maxAttempts?: number;
  /** Base delay ms; attempt n waits baseMs * 2^(n-1), capped (default 500). */
  baseMs?: number;
  /** Delay ceiling ms (default 10_000). */
  maxDelayMs?: number;
}

export const DEFAULT_MAX_ATTEMPTS = 5;
export const DEFAULT_BASE_MS = 500;
export const DEFAULT_MAX_DELAY_MS = 10_000;

/** Backoff delay before attempt `attempt` (1-indexed) — pure, unit-testable. */
export function backoffDelayMs(
  attempt: number,
  baseMs: number = DEFAULT_BASE_MS,
  maxDelayMs: number = DEFAULT_MAX_DELAY_MS,
): number {
  return Math.min(baseMs * 2 ** (attempt - 1), maxDelayMs);
}

export interface RetryDeps {
  sleep?: (ms: number) => Promise<void>;
}

export interface AttemptOutcome {
  messageId: number;
  attempts: number;
}

/**
 * Run `send` until it succeeds, fails terminally, or exhausts `maxAttempts`.
 * Terminal (non-retryable) failures and a dead route reject immediately
 * WITHOUT sleeping. Exhaustion rejects with the LAST failure. `onAttempt`
 * observes each failure (for route-switch logging upstream).
 */
export async function sendWithRetry(
  send: () => Promise<number>,
  policy: RetryPolicy = {},
  deps: RetryDeps = {},
  onAttempt?: (attempt: number, failure: SendFailure) => void,
): Promise<AttemptOutcome> {
  const maxAttempts = Math.max(1, policy.maxAttempts ?? DEFAULT_MAX_ATTEMPTS);
  const baseMs = policy.baseMs ?? DEFAULT_BASE_MS;
  const maxDelayMs = policy.maxDelayMs ?? DEFAULT_MAX_DELAY_MS;
  const sleep = deps.sleep ?? ((ms: number) => new Promise((r) => setTimeout(r, ms)));

  let last: SendFailure | undefined;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const messageId = await send();
      return { messageId, attempts: attempt };
    } catch (err) {
      const failure = toSendFailure(err);
      last = failure;
      onAttempt?.(attempt, failure);
      const exhausted = attempt >= maxAttempts;
      if (exhausted || !isRetryableFailure(failure)) {
        throw failureAsError(failure, attempt, exhausted);
      }
      await sleep(backoffDelayMs(attempt, baseMs, maxDelayMs));
    }
  }
  // Unreachable (loop always returns or throws) — kept for type-safety.
  throw failureAsError(last ?? { message: "unknown send failure" }, maxAttempts, true);
}

/** Normalise anything a send seam throws into a classifiable SendFailure. */
export function toSendFailure(err: unknown): SendFailure {
  if (
    typeof err === "object" &&
    err !== null &&
    ("transport" in err || "errorCode" in err)
  ) {
    const e = err as Partial<SendFailure> & { message?: unknown };
    return {
      transport: e.transport,
      errorCode: typeof e.errorCode === "number" ? e.errorCode : undefined,
      message: typeof e.message === "string" ? e.message : String(err),
    };
  }
  if (err instanceof Error) {
    // TelegramApiError message shape: "... (error_code N) ..." — recover N.
    const m = err.message.match(/error_code\s+(\d{3})/);
    const errorCode = m ? Number(m[1]) : undefined;
    // Transport-shaped errors (fetch rejections, aborts) carry no code.
    const transport =
      errorCode === undefined &&
      /fetch failed|ECONN|ENOTFOUND|ETIMEDOUT|timeout|abort|network/i.test(err.message)
        ? err
        : undefined;
    return { transport, errorCode, message: err.message };
  }
  return { message: String(err) };
}

function failureAsError(f: SendFailure, attempt: number, exhausted: boolean): Error {
  const why =
    f.errorCode !== undefined
      ? `Telegram error_code ${f.errorCode}`
      : f.transport !== undefined
        ? `transport failure (${f.message})`
        : f.message;
  const err = new Error(
    `outbound send ${exhausted ? `exhausted after ${attempt} attempt(s)` : `refused (terminal) on attempt ${attempt}`}: ${why}`,
  );
  err.cause = f;
  return err;
}

// ── Delivery-confirm loop ────────────────────────────────────────────────────

export type DeliveryState = "confirmed" | "unconfirmed";

export interface ConfirmDeps {
  /**
   * Read-back proving the chat is still reachable AFTER the send
   * (production: getChat(chatId)). Resolves on reachable, rejects otherwise.
   */
  verifyChat: (chatId: string) => Promise<unknown>;
}

export interface ConfirmResult {
  state: DeliveryState;
  messageId: number;
  /** Present only when unconfirmed: why the verify failed. */
  reason?: string;
}

/**
 * Confirm one accepted send. `messageId` is the Telegram-accepted id from
 * sendMessage; a verify failure marks the send UNCONFIRMED (loud, with
 * reason) rather than silently OK — the caller decides whether to retry or
 * route-switch on it.
 */
export async function confirmDelivery(
  chatId: string,
  messageId: number,
  deps: ConfirmDeps,
): Promise<ConfirmResult> {
  try {
    await deps.verifyChat(chatId);
    return { state: "confirmed", messageId };
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    log("outbound-delivery", "send accepted but delivery UNCONFIRMED", {
      level: "warning",
      chat_id: chatId,
      message_id: messageId,
      reason,
    });
    return { state: "unconfirmed", messageId, reason };
  }
}

// ── Route-switch failover ────────────────────────────────────────────────────

export interface FailoverSendDeps extends RetryDeps {
  /**
   * Send one message via ONE route. Production wiring builds the
   * `https://<root>/bot<token>/sendMessage` call from `route`.
   */
  sendVia: (route: OutboundRoute, chatId: string, text: string) => Promise<number>;
  verifyChatVia?: (route: OutboundRoute, chatId: string) => Promise<unknown>;
  /** Confirm each accepted send (default: accept = confirmed, no read-back). */
  confirm?: boolean;
}

export interface FailoverResult {
  messageId: number;
  /** Which route delivered ("primary" when no switch was needed). */
  route: string;
  /** Total send attempts across all routes. */
  attempts: number;
  delivery: DeliveryState;
}

/**
 * Send with bounded retry per route, then switch routes. Behaviour:
 *
 *   - Route A retried to exhaustion (unless terminal/dead).
 *   - 401 on route A skips remaining retries → straight to route B.
 *   - 400/403/404 (terminal, not route-death) fail fast with NO switch:
 *     the request is bad, not the route — a backup token would 403 too.
 *   - Each accepted send is confirm-looped when `confirm: true`; an
 *     UNCONFIRMED accept on the primary also tries the backup (the chat may
 *     be reachable from the other identity) before reporting unconfirmed.
 *   - No backup route = single-route retry + confirm. Zero routes = loud
 *     refusal (empty token), never a disguised Telegram 404.
 */
export async function sendWithFailover(
  routes: OutboundRoute[],
  chatId: string,
  text: string,
  policy: RetryPolicy = {},
  deps: FailoverSendDeps,
): Promise<FailoverResult> {
  if (routes.length === 0) {
    throw new Error(
      `outbound send refused: no routes (CCT_BOT_TOKEN is EMPTY — refusing to send). ` +
        `This is NOT a Telegram problem: with no token the request URL would be ` +
        `https://api.telegram.org/bot/sendMessage, which Telegram answers "Not Found".`,
    );
  }
  const maxAttempts = Math.max(1, policy.maxAttempts ?? DEFAULT_MAX_ATTEMPTS);
  let attempts = 0;
  let lastError: unknown;

  for (let r = 0; r < routes.length; r++) {
    const route = routes[r];
    const isLast = r === routes.length - 1;
    let routeAttempts = 0;
    try {
      const outcome = await sendWithRetry(
        () => {
          routeAttempts += 1;
          return deps.sendVia(route, chatId, text);
        },
        { ...policy, maxAttempts },
        deps,
      );
      attempts += outcome.attempts;
      if (r > 0) {
        log("outbound-delivery", `route-switch: delivered via ${route.label}`, {
          route: route.label,
          chat_id: chatId,
        });
      }
      if (deps.confirm && deps.verifyChatVia) {
        const c = await confirmDelivery(chatId, outcome.messageId, {
          verifyChat: (cId) => deps.verifyChatVia!(route, cId),
        });
        if (c.state === "unconfirmed" && !isLast) {
          lastError = new Error(`unconfirmed on route ${route.label}: ${c.reason}`);
          log("outbound-delivery", `route ${route.label} UNCONFIRMED — switching`, {
            level: "warning",
            route: route.label,
          });
          continue;
        }
        return { messageId: outcome.messageId, route: route.label, attempts, delivery: c.state };
      }
      return { messageId: outcome.messageId, route: route.label, attempts, delivery: "confirmed" as DeliveryState };
    } catch (err) {
      // Exact attempts this route burned (a 401 burns 1: terminal, so
      // sendWithRetry stops immediately and we switch without waiting).
      attempts += routeAttempts;
      lastError = err;
      const f = err instanceof Error && (err.cause as SendFailure | undefined)?.errorCode !== undefined
        ? (err.cause as SendFailure)
        : toSendFailure(err);
      const terminal = !isRetryableFailure(f);
      if (terminal && !isRouteDeadFailure(f)) {
        // Bad request, not a bad route — backup would fail identically.
        throw err;
      }
      if (!isLast) {
        log("outbound-delivery", `route ${route.label} exhausted — switching`, {
          level: "warning",
          route: route.label,
          error: String(err),
        });
      }
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error(`outbound send failed on all routes: ${String(lastError)}`);
}
