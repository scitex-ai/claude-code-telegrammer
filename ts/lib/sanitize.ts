/**
 * Neutralize envelope-breaking markup in inbound message text.
 *
 * Inbound Telegram messages are handed to Claude Code wrapped in a
 *   <channel source="claude-code-telegrammer" ...>...TEXT...</channel>
 * envelope. On the MCP path the Claude Code CLI adds that envelope; on the
 * wake path lib/wake.ts builds it directly. In BOTH cases the user's message
 * body is interpolated verbatim — so a body that itself contains
 * `<channel ...>` or `</channel>` (or other `<channel>`-token markup) can
 * open or, worse, prematurely CLOSE the surrounding envelope. The CLI then
 * mis-parses the inbound: a pasted/echoed `<channel ...>` block is treated as
 * a real channel notification (the operator-observed delivery corruption),
 * and it is a prompt-injection vector (cf. anthropics/claude-code #68220
 * "message text not XML-escaped", #61010).
 *
 * Fix strategy — TARGETED, low-collateral. The envelope is delimited solely
 * by the `<channel` and `</channel>` tokens, so we make ONLY those specific
 * sequences non-parseable rather than blanket-escaping every `<...>` (which
 * would mangle legitimate angle brackets in users' code snippets / math like
 * `a < b`). We rewrite a leading `<` that begins a `channel` open- or close-
 * tag token (case-insensitively, on a word boundary: `<channel` / `</channel`)
 * to the HTML entity `&lt;`. The tag can no longer open or close the real
 * envelope, while the visible text the agent reads still reads as `&lt;channel`
 * — clearly a literal, not a directive. Every other `<` in the body
 * (`a < b`, `<div>`, `<=`, `<3`, …) is left untouched.
 *
 * Applied to the COPY handed to the CLI only (channel content + wake payload).
 * The stored DB text and meta are NOT mutated — history stays faithful.
 */

/**
 * Rewrite `<channel` / `</channel` envelope-token openings (case-insensitive,
 * word-boundary on the `channel` token) so the text cannot open or close a
 * `<channel ...>` envelope. The leading `<` becomes `&lt;`; nothing else is
 * altered. Returns the input unchanged when no such token is present.
 */
export function neutralizeChannelEnvelope(text: string): string {
  // Match a literal `<`, an optional `/` (close tag), then `channel` followed
  // by a word boundary (so `<channels>` or `<channeling>` are NOT touched —
  // only the exact envelope token `channel` as a whole word). Case-insensitive
  // and global. Only the leading `<` is captured/replaced; the rest of the
  // match is preserved via the `$1` backref.
  return text.replace(/<(\/?channel\b)/gi, "&lt;$1");
}
