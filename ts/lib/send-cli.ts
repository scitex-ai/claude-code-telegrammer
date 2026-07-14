/**
 * Argument parsing for the one-shot outbound `send` mode.
 *
 * WHY THIS MODE EXISTS (card cct-cli-send-outbound-path-independent-of-mcp,
 * reported by `grant` after it cost a real deadline):
 *
 * Inbound (operator -> agent) is now robust — the poller is a separate process
 * (v0.5.6) and a failed wake falls back to the MCP-notify relay with
 * redelivery. Outbound (agent -> operator) had NO such redundancy: it went
 * exclusively through the cct MCP server's `reply` tool. When that server drops
 * — or, as `grant` observed, when its instructions load but its TOOLS do not
 * resolve — the agent has no way to reach the operator at all. It goes MUTE.
 *
 * The operator reads that silence as being ignored; he escalated exactly that
 * ("なぜ返事をしないのでしょうか"). The agents were not ignoring him. They
 * could not speak.
 *
 * `health` is not a way out of this: it is itself an MCP tool, so in the very
 * failure mode we care about it is unreachable too. The tool IS the signal, and
 * when the tools vanish the signal vanishes with them.
 *
 * A CLI does not depend on MCP tool-schema exposure. Bash is always there. So
 * an agent that finds mcp__claude-code-telegrammer__reply unresolvable can
 * still shell out:
 *
 *     claude-code-telegrammer send --chat-id <id> --text "..."
 *
 * Parsing lives here, separate from telegram-server.ts, so it is unit-testable
 * without a bot token or a network call — the same seam pattern the rest of
 * lib/ uses.
 */

export interface SendArgs {
  chatId: string;
  text: string;
  replyTo?: number;
}

export type SendArgsResult =
  | { ok: true; args: SendArgs }
  | { ok: false; error: string };

/** Read `--flag value` from argv. Returns undefined when absent. */
function flagValue(argv: string[], flag: string): string | undefined {
  const i = argv.indexOf(flag);
  if (i === -1) return undefined;
  const value = argv[i + 1];
  // A flag whose value is missing, or is itself the next flag, is an ERROR the
  // caller must surface — not a silently-absent value. `--text --chat-id 5`
  // must not quietly send the literal string "--chat-id".
  if (value === undefined || value.startsWith("--")) return undefined;
  return value;
}

/** True when the flag is present but its value is missing/another flag. */
function flagPresentButEmpty(argv: string[], flag: string): boolean {
  return argv.includes(flag) && flagValue(argv, flag) === undefined;
}

export function parseSendArgs(argv: string[]): SendArgsResult {
  for (const required of ["--chat-id", "--text"]) {
    if (flagPresentButEmpty(argv, required)) {
      return { ok: false, error: `${required} requires a value` };
    }
  }

  const chatId = flagValue(argv, "--chat-id");
  const text = flagValue(argv, "--text");

  if (!chatId) return { ok: false, error: "--chat-id is required" };
  if (!text) return { ok: false, error: "--text is required" };

  const args: SendArgs = { chatId, text };

  if (argv.includes("--reply-to")) {
    const raw = flagValue(argv, "--reply-to");
    if (raw === undefined) {
      return { ok: false, error: "--reply-to requires a value" };
    }
    const replyTo = Number(raw);
    // Fail loud rather than silently dropping an unparseable --reply-to and
    // sending an unthreaded message the caller did not ask for.
    if (!Number.isInteger(replyTo) || replyTo <= 0) {
      return {
        ok: false,
        error: `--reply-to must be a positive integer message id (got ${raw})`,
      };
    }
    args.replyTo = replyTo;
  }

  return { ok: true, args };
}

export const SEND_USAGE =
  "usage: claude-code-telegrammer send --chat-id <id> --text <message> " +
  "[--reply-to <message_id>]\n" +
  "\n" +
  "Send one outbound Telegram message and exit. Does NOT start the MCP\n" +
  "server or the poller.\n" +
  "\n" +
  "Use this when the cct MCP tools are unavailable (server down, or tools\n" +
  "not resolvable) and an agent would otherwise be unable to reach the\n" +
  "operator at all. Prints {\"ok\":true,\"message_id\":N} on success; exits\n" +
  "non-zero with a reason on failure.\n";
