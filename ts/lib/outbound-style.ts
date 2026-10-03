/** Operator-facing outbound message style gates.
 *
 * PR numbers are not useful on a phone without their meaning. Every `#123`
 * reference must therefore carry an immediate parenthetical description in
 * the same clause:
 *
 *   #123 (Landing V2)
 *   #1512 (Japanese description here)
 *
 * Full-width parentheses are accepted with the same rules. Dash, colon
 * and em-dash labels, unclosed or empty parentheses, numeric-only labels
 * (ASCII and full-width digits alike) and line-split descriptions are all
 * rejected, as is every unlabeled reference in a multi-PR update. A URL may
 * still be sent without a hash token. Ordinary text with no PR reference
 * always passes. This validator rejects before Telegram delivery; it does
 * not rewrite text or guess a title.
 */

// U+2028 LINE SEPARATOR and U+2029 PARAGRAPH SEPARATOR, built from code
// points so no invisible characters ever enter this source file.
const WIDE_TERMINATORS = String.fromCharCode(0x2028, 0x2029);

const PR_REFERENCE = /#\d+\b/g;

// The description must stay in the SAME clause: horizontal spacing only
// before the paren, and no line terminators (\n, \r, U+2028, U+2029) inside
// either delimiter form.
const PARENTHETICAL = new RegExp(
  "^[ \\t]*(\\(([^()\\n\\r" +
    WIDE_TERMINATORS +
    "]*)\\)|（([^（）\\n\\r" +
    WIDE_TERMINATORS +
    "]*)）)",
);

function hasMeaningfulText(label: string): boolean {
  return label.replace(/[\s\d　０-９._()[\]{}:;,#/\\-]/g, "").length > 0;
}

/** True when s holds no line terminator: the same-clause check shared with chunk repair. */
export function hasNoLineTerminator(s: string): boolean {
  return (
    !/[\n\r]/.test(s) &&
    !s.includes(WIDE_TERMINATORS[0]) &&
    !s.includes(WIDE_TERMINATORS[1])
  );
}

export function unlabeledPrReferences(text: string): string[] {
  const failures: string[] = [];
  const matcher = new RegExp(PR_REFERENCE.source, "g");
  let match: RegExpExecArray | null;
  while ((match = matcher.exec(text)) !== null) {
    const suffix = text.slice(match.index + match[0].length);
    const paren = suffix.match(PARENTHETICAL);
    const label = paren ? (paren[2] ?? paren[3] ?? "") : "";
    if (!hasMeaningfulText(label)) failures.push(match[0]);
  }
  return failures;
}

export function assertLabeledPrReferences(text: string): void {
  const failures = unlabeledPrReferences(text);
  if (!failures.length) return;
  throw new Error(
    `unlabeled PR reference(s): ${failures.join(", ")}. ` +
      "Write each as '#123 (what it changes)' with a nonempty description " +
      "in matching parentheses. Bare numbers, dash/colon labels, unclosed " +
      "or empty parentheses, and numeric-only labels are forbidden in " +
      "operator-facing CCT messages.",
  );
}
