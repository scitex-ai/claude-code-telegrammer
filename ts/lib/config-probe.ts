/**
 * Config identity probe — resolve the telegrammer config WITHOUT starting the
 * MCP server or poller, and print it as JSON to STDOUT.
 *
 * Why this lives here (and not as a reimplementation in the Python CLI):
 *   scitex-agent-container (sac) wires a per-agent Telegram bot — unique
 *   BOT_TOKEN + unique STATE_DIR per agent, sourced from each project's
 *   .envrc. Before starting a poller, sac needs to PREFLIGHT what config an
 *   agent actually resolves to: assert that a given token maps to the
 *   expected agent identity, and detect two agents that accidentally resolve
 *   to the SAME bot (the duplicate-token 409 collision — incident card
 *   cct-multiagent-telegram-shared-token-409).
 *
 *   The canonical resolution (env-prefix precedence in lib/env.ts,
 *   BOT_TOKEN_HASH, STATE_DIR, AGENT_ID, CHANNEL_SOURCE, TURN_URL) is the
 *   single source of truth in TS. The probe reuses it verbatim so the
 *   preflight cannot drift from what the running server would resolve. The
 *   Python CLI merely forwards to this mode.
 *
 * Security:
 *   - The raw bot token is NEVER printed. Only `bot_token_present` (boolean)
 *     and `bot_token_hash` (the first 8 hex chars of sha256(token), already
 *     used as the per-token pidfile key) leave the process.
 *   - The plain `config` mode does NO network IO — it is a pure local dump.
 *   - `--check`/`--getme` opts INTO a single getMe call so the operator can
 *     confirm a token→@username/bot_id mapping; a bad/duplicate token yields
 *     `getme_error` rather than crashing (exit code stays 0 — a bad token is
 *     a finding, not a failure of the probe).
 */

import { getenv } from "./env.js";
import {
  STATE_DIR,
  BOT_TOKEN_HASH,
  CHANNEL_SOURCE,
  TOKEN,
  TURN_URL,
} from "./config.js";

export interface ConfigProbe {
  agent_id: string | null;
  bot_token_present: boolean;
  bot_token_hash: string;
  state_dir: string;
  channel_source: string;
  turn_url_set: boolean;
  // Present only when --check ran AND a token is set:
  bot_username?: string;
  bot_id?: number;
  getme_error?: string;
}

/**
 * Build the local (no-network) config probe. `agent_id` is read via the raw
 * getenv("AGENT_ID") — it deliberately does NOT fall back to the "telegram"
 * default that config.ts's AGENT_ID export uses, because the preflight must
 * distinguish "this agent did not set AGENT_ID" (null) from "this agent is
 * literally named telegram".
 */
export function buildConfigProbe(): ConfigProbe {
  const agentId = getenv("AGENT_ID");
  return {
    agent_id: agentId ?? null,
    bot_token_present: TOKEN.length > 0,
    bot_token_hash: BOT_TOKEN_HASH,
    state_dir: STATE_DIR,
    channel_source: CHANNEL_SOURCE,
    turn_url_set: TURN_URL.length > 0,
  };
}

/**
 * Resolve the config probe and (when `check` is true and a token is set)
 * augment it with the live getMe identity. Never throws on a getMe failure —
 * the error is folded into `getme_error` and the probe still resolves.
 */
export async function resolveConfigProbe(
  check: boolean,
  getMe: () => Promise<any>,
): Promise<ConfigProbe> {
  const probe = buildConfigProbe();
  if (check && probe.bot_token_present) {
    try {
      const me = await getMe();
      probe.bot_username = me?.username;
      probe.bot_id = me?.id;
    } catch (err) {
      probe.getme_error = err instanceof Error ? err.message : String(err);
    }
  }
  return probe;
}

/** True iff argv requests the live getMe enrichment (`--check` or `--getme`). */
export function wantsGetMe(argv: string[]): boolean {
  return argv.includes("--check") || argv.includes("--getme");
}
