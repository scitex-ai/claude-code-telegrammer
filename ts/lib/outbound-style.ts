/** Thin adapter to the operator's canonical Telegram rule.
 *
 * The shell hook and every CCT send path must use the SAME rule and refusal
 * wording. Keep policy in _telegram_rules.py; do not add a second regexp here.
 * Its issue references, repeated-description inheritance, URL/code/colour
 * exceptions and ASCII/fullwidth parentheses remain authoritative.
 *
 * CCT ships the canonical predicate beside its packaged TypeScript runtime.
 * The normal Python launcher supplies its own interpreter; HOME is irrelevant.
 * An unavailable or malformed rule response is a validation failure, before
 * delivery. This adapter never formats a PR title or rewrites message text.
 */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

interface Verdict {
  ok: boolean;
  token?: string;
  message?: string;
}

function checkMessage(text: string): Verdict {
  const python = process.env._CCT_PYTHON_EXECUTABLE;
  if (!python) {
    throw new Error("Cannot validate CCT message: use the packaged Python CLI launcher.");
  }
  const packaged = join(import.meta.dir, "..", "..", "_telegram_rules.py");
  const source = join(import.meta.dir, "..", "..", "src", "claude_code_telegrammer", "_telegram_rules.py");
  const rules = existsSync(packaged) ? packaged : source;
  const result = spawnSync(python, [rules, "--text-stdin"], {
    input: text,
    encoding: "utf8",
    timeout: 2000,
    maxBuffer: 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    throw new Error("Cannot validate CCT message: canonical Telegram rule is unavailable.");
  }
  let verdict: Verdict;
  try {
    verdict = JSON.parse(result.stdout);
  } catch {
    throw new Error("Cannot validate CCT message: canonical Telegram rule returned invalid JSON.");
  }
  if (verdict?.ok === true) return verdict;
  if (verdict?.ok === false && typeof verdict.token === "string" && typeof verdict.message === "string" && verdict.message.length > 0) return verdict;
  throw new Error("Cannot validate CCT message: canonical Telegram rule returned an invalid verdict.");
}

/** The canonical rule reports its first unreadable reference. */
export function unlabeledPrReferences(text: string): string[] {
  const verdict = checkMessage(text);
  return verdict.ok ? [] : [verdict.token!];
}

export function assertLabeledPrReferences(text: string): void {
  const verdict = checkMessage(text);
  if (!verdict.ok) throw new Error(verdict.message);
}
