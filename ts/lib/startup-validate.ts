/**
 * Pure, unit-testable startup validation for the Telegram MCP server.
 *
 * Two concerns live here — deliberately as PURE functions with injectable
 * inputs (no network, no filesystem, no process.exit) so the whole
 * classification surface is covered by `bun test` without mocking the DB:
 *
 *   1. validateBotToken() — classify a raw getMe response into OK / definitive
 *      bad-token / transient. Wired at NORMAL startup (telegram-server.ts) so a
 *      present-but-invalid/revoked token FAILS LOUD instead of starting a
 *      poller that silently 404s every Bot API call. That silent-404 mode was
 *      a real incident: an agent showed only "✘ failed" for a long debugging
 *      session because the true cause (a bad token) was buried — see the
 *      operator directive (constitution §2, fail-loud-and-actionable).
 *
 *   2. describeAccessGating() — evaluate the effective DM gating posture at
 *      startup and, when it is fail-CLOSED (the DEFAULT: dmPolicy=allowlist +
 *      empty allow list ⇒ every DM rejected, so the bot looks dead), emit a
 *      loud WARN that names the exact env var and the fix. Previously this
 *      warning only fired LAZILY on the first message-time loadAccess() ENOENT,
 *      so a misconfigured bot looked silently dead until (and unless) someone
 *      messaged it.
 *
 * Both message strings already contain the ACTIONABLE text (var name + fix
 * hint) so callers only have to print them. Hints prefer the short `CCT_`
 * spelling (the preferred alias per lib/env.ts) and mention the canonical
 * `CLAUDE_CODE_TELEGRAMMER_` form parenthetically.
 */

/**
 * A raw Telegram getMe response, parsed from JSON, WITHOUT the ok:false→throw
 * that lib/telegram-api.ts's tgApi() applies (which loses the error_code and
 * makes 401-vs-transient indistinguishable). The bound raw getMe may still
 * REJECT on a network/DNS failure — that rejection is what maps to "transient".
 */
export interface RawTgResponse {
  ok: boolean;
  // On ok:true, the getMe result (bot identity).
  result?: { id?: number; username?: string; [k: string]: unknown };
  // On ok:false, Telegram's numeric error code + human description.
  error_code?: number;
  description?: string;
}

/**
 * The outcome of classifying a getMe response.
 *   - ok:true            → token is valid; carries the resolved @username/id.
 *   - kind:invalid_token → DEFINITIVE bad token (401/404). FATAL at startup.
 *   - kind:transient     → network throw / 429 / 5xx. NON-fatal (a Telegram
 *                          outage must not permanently kill the poller).
 * `message` always carries the actionable text so the caller just prints it.
 */
export type TokenCheck =
  | { ok: true; username?: string; id?: number }
  | { ok: false; kind: "invalid_token" | "transient"; message: string };

/** The exact env var the operator must fix — short (preferred) + canonical. */
const BOT_TOKEN_VAR = "CCT_BOT_TOKEN";
const BOT_TOKEN_VAR_CANONICAL = "CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN";
const ALLOWED_USERS_VAR = "CCT_ALLOWED_USERS";
const ALLOWED_USERS_VAR_CANONICAL = "CLAUDE_CODE_TELEGRAMMER_ALLOWED_USERS";

/**
 * Loud, actionable startup WARNING for the DISABLED state: CCT_BOT_TOKEN is
 * empty/absent, so telegram is off for this agent. The channel is a universal
 * default in every agent spec, so a tokenless agent loads connected-but-DISABLED
 * (honest status, not a hard "✘ failed") — and this WARN, emitted prominently on
 * every startup (never deduped), keeps the state VISIBLE so it is never a silent
 * "connected-and-fine". A PRESENT-but-invalid token is a real misconfiguration
 * and still fails loud (see validateBotToken).
 */
export function buildDisabledWarning(agentId: string): string {
  return (
    `[WARN] claude-code-telegrammer disabled for agent "${agentId}": ` +
    `${BOT_TOKEN_VAR} empty — define ${BOT_TOKEN_VAR}_<NAME> in secrets ` +
    `(~/.bash.d/secrets/010_scitex/01_claude-code-telegrammer.src; papers ` +
    `PAPER_<NAME>, else bare <NAME>) and restart.`
  );
}

/**
 * Classify the result of a getMe call against Telegram.
 *
 * `rawGetMe` is injected (the caller binds it to a real fetch-based getMe, or a
 * stub in tests). It returns the parsed Telegram JSON on any HTTP response, and
 * THROWS only on a transport-level failure (fetch reject: DNS/connect/reset).
 *
 * Classification:
 *   - ok:true                         → { ok:true, username, id }
 *   - ok:false, error_code 401 or 404 → invalid_token (FATAL). The token is
 *                                        present but not accepted — invalid or
 *                                        revoked. Message names CCT_BOT_TOKEN
 *                                        and includes Telegram's own description
 *                                        (the incident-class regression asserts
 *                                        BOTH appear).
 *   - ok:false, any other code        → transient (429 flood-wait, 5xx, or an
 *                                        unexpected code we should not treat as
 *                                        a permanent kill).
 *   - throw                           → transient (network/DNS).
 */
export async function validateBotToken(
  rawGetMe: () => Promise<RawTgResponse>,
): Promise<TokenCheck> {
  let res: RawTgResponse;
  try {
    res = await rawGetMe();
  } catch (err) {
    // A fetch reject is a transport problem (DNS/connect/reset), NOT a verdict
    // on the token — treat as transient so a Telegram/network blip does not
    // permanently kill an otherwise-valid poller.
    const detail = err instanceof Error ? err.message : String(err);
    return {
      ok: false,
      kind: "transient",
      message:
        `could not reach Telegram to validate ${BOT_TOKEN_VAR}: ${detail} — ` +
        `treating as a transient network/Telegram outage and continuing; the ` +
        `poller will retry.`,
    };
  }

  if (res.ok) {
    return { ok: true, username: res.result?.username, id: res.result?.id };
  }

  const description = res.description ?? "no description";
  if (res.error_code === 401 || res.error_code === 404) {
    // Definitive: Telegram positively rejected the token. Fail loud so the
    // real cause is surfaced up front (sac's boot preflight relays our stderr)
    // instead of buried under a long run of "✘ failed" Bot API calls.
    return {
      ok: false,
      kind: "invalid_token",
      message:
        `Telegram rejected the bot token (getMe ${res.error_code}: ${description}). ` +
        `The token in ${BOT_TOKEN_VAR} (a.k.a. ${BOT_TOKEN_VAR_CANONICAL}) is ` +
        `invalid or revoked — re-issue it via @BotFather and update ` +
        `${BOT_TOKEN_VAR}.`,
    };
  }

  // Any other non-ok code (429 flood-wait, 5xx, or an unexpected one) is not a
  // permanent token verdict — do not kill the poller over it.
  return {
    ok: false,
    kind: "transient",
    message:
      `Telegram getMe returned a transient error (${res.error_code}: ${description}) ` +
      `while validating ${BOT_TOKEN_VAR} — continuing; the poller will retry.`,
  };
}

/** Inputs describing the effective DM-gating posture at startup. */
export interface AccessGatingInput {
  accessFileExists: boolean;
  envAllowedCount: number;
  dmPolicy: "allowlist" | "pairing" | "disabled";
  /** Optional path to access.json, surfaced in the fix hint when known. */
  accessFilePath?: string;
}

/** Verdict from describeAccessGating: a log level + a ready-to-print message. */
export interface AccessGatingResult {
  level: "warn" | "info";
  message: string;
}

/**
 * Describe the effective DM-gating posture without touching the filesystem.
 *
 * The DEFAULT posture is fail-CLOSED: dmPolicy `allowlist` with an EMPTY allow
 * list (no access.json AND an empty CCT_ALLOWED_USERS) ⇒ every DM is REJECTED,
 * so the bot looks completely dead to a first-time messager. That is the case
 * that must WARN loudly at startup, naming the exact var and the fix. When the
 * allowlist has entries (from access.json or CCT_ALLOWED_USERS), or the policy
 * is not the fail-closed allowlist, the posture is fine → info.
 */
export function describeAccessGating(
  input: AccessGatingInput,
): AccessGatingResult {
  const { accessFileExists, envAllowedCount, dmPolicy, accessFilePath } = input;
  const pathHint = accessFilePath ?? "access.json in the state dir";

  // Fail-closed allowlist: no allow entries from either source.
  if (dmPolicy === "allowlist" && !accessFileExists && envAllowedCount === 0) {
    return {
      level: "warn",
      message:
        `access gating is FAIL-CLOSED: dmPolicy=allowlist with an EMPTY allow ` +
        `list (no access.json and ${ALLOWED_USERS_VAR} is empty) — every DM ` +
        `will be REJECTED, so the bot will look dead / unresponsive. Fix: set ` +
        `${ALLOWED_USERS_VAR}=<your numeric telegram id> (a.k.a. ` +
        `${ALLOWED_USERS_VAR_CANONICAL}), or create ${pathHint} with an ` +
        `allowFrom list.`,
    };
  }

  // Otherwise the posture is workable — report it as a positive diagnostic.
  const source = accessFileExists
    ? "access.json"
    : `${ALLOWED_USERS_VAR} (${envAllowedCount} entr${
        envAllowedCount === 1 ? "y" : "ies"
      })`;
  return {
    level: "info",
    message: `access gating: dmPolicy=${dmPolicy}, allow list sourced from ${source}.`,
  };
}
