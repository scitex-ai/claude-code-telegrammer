/** Operator-facing outbound message style gates.
 *
 * PR numbers are not useful on a phone without their meaning. Every `#123`
 * reference must therefore carry an immediate label in the same clause:
 *
 *   #123 — agentic ACK protocol
 *   #123: fix login redirect
 *   #123 (Landing V2)
 *
 * A URL may still be sent without a hash token. This validator rejects before
 * Telegram delivery; it does not rewrite text or guess a title.
 */

const PR_REFERENCE = /#\d+\b/g;
const LABELED_SUFFIX = /^\s*(?:—|–|-|:|\()\s*([^\n,#;/]{3,})/;

function hasMeaningfulText(label: string): boolean {
  return label.replace(/[\s\d._()[\]{}:;,#/\\-]/g, "").length > 0;
}

export function unlabeledPrReferences(text: string): string[] {
  const failures: string[] = [];
  const matcher = new RegExp(PR_REFERENCE.source, "g");
  let match: RegExpExecArray | null;
  while ((match = matcher.exec(text)) !== null) {
    const suffix = text.slice(match.index + match[0].length);
    const label = suffix.match(LABELED_SUFFIX)?.[1] ?? "";
    if (!hasMeaningfulText(label)) failures.push(match[0]);
  }
  return failures;
}

export function assertLabeledPrReferences(text: string): void {
  const failures = unlabeledPrReferences(text);
  if (!failures.length) return;
  throw new Error(
    `unlabeled PR reference(s): ${failures.join(", ")}. ` +
      "Write each as '#123 — what it changes' (or ': label' / '(label)'). " +
      "Bare PR numbers are forbidden in operator-facing CCT messages.",
  );
}
