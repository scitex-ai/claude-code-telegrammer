/**
 * code_current — "am I actually running the code that is on disk?"
 *
 * THE DETECTION GAP (raised by `grant`, 2026-07-14, after three agents hit the
 * same class of bug independently in 24 hours):
 *
 *   - I inferred the running code from PyPI + GitHub. Neither executes.
 *   - scitex-todo inferred it from `git merge-base --is-ancestor`. The repo
 *     squash-merges, so the branch commit never appears in develop's history —
 *     a confident FALSE NEGATIVE.
 *   - grant inferred a code mechanism from a symptom without reading the code.
 *
 * Same disease each time: we inferred an artifact's contents from its HISTORY
 * instead of interrogating the artifact. That is how v0.5.6 could be released,
 * merged, published, reported "live" — and never once execute. The bot was
 * running v0.5.4 the whole time.
 *
 * PR #78 fixed the DEPLOY gap (a stale poller now gets taken over). This closes
 * the DETECTION gap: without it, the next stale-poller incident looks identical
 * from the outside — everything green, nothing running.
 *
 * DELIBERATELY NOT A VERSION STRING. `pyproject.toml`, `package.json` and a
 * `dist-info` all report a number that can be baked, orphaned, or simply older
 * than the code sitting beside it (there is a vestigial claude_code_telegrammer
 * 0.5.0 in ~/.venv right now that nothing launches). A version is a claim ABOUT
 * the code. This check interrogates the code itself, and the processes actually
 * executing it:
 *
 *     could this process possibly have loaded the source that is on disk now?
 *
 * If a source file's mtime is NEWER than the process's start time, then no — it
 * could not have. That is not an inference from history; it is a property of the
 * running process. Same predicate lib/poller-supervisor.ts acts on, surfaced
 * here so a human or an agent can SEE the drift instead of discovering it during
 * an incident.
 */

import type { CheckOutcome } from "./health-checks.js";

export interface CodeCurrencyProbe {
  /** Wall-clock ms at which THIS (MCP server) process started. */
  serverStartMs: number;
  /** Pidfile claim time of the standalone poller; null ⇔ no live poller. */
  pollerStartMs: number | null;
  /** Newest mtime (ms) across the poller/server source. 0 ⇔ could not stat. */
  codeMtimeMs: number;
}

function iso(ms: number): string {
  return new Date(ms).toISOString();
}

/**
 * 13. code_current — fails when a running process CANNOT have loaded the code
 * currently on disk.
 *
 * FAIL-SAFE, matching poller-supervisor.ts: staleness must be positively
 * established. A codeMtimeMs of 0 (nothing could be stat'd) reports ok rather
 * than crying stale on a bad read — a false alarm here would train people to
 * ignore the one check whose entire job is to be believed.
 */
export function checkCodeCurrent(
  probe: CodeCurrencyProbe | null | undefined,
): CheckOutcome {
  // A doctor that CRASHES the whole report is worse than one that skips a
  // check: the other eleven findings are still worth having. Never throw here.
  if (!probe) {
    return {
      entry: {
        name: "code_current",
        ok: true,
        detail: "skipped: no code-currency probe supplied",
        hint: null,
      },
      warn: false,
    };
  }

  const { serverStartMs, pollerStartMs, codeMtimeMs } = probe;

  if (codeMtimeMs <= 0) {
    return {
      entry: {
        name: "code_current",
        ok: true,
        detail:
          "skipped: could not stat the source files (no readable mtime) — " +
          "not treated as drift",
        hint: null,
      },
      warn: false,
    };
  }

  const stale: string[] = [];
  if (serverStartMs > 0 && codeMtimeMs > serverStartMs) {
    stale.push(
      `MCP server (started ${iso(serverStartMs)}) predates the code ` +
        `(modified ${iso(codeMtimeMs)})`,
    );
  }
  if (pollerStartMs !== null && pollerStartMs > 0 && codeMtimeMs > pollerStartMs) {
    stale.push(
      `poller (started ${iso(pollerStartMs)}) predates the code ` +
        `(modified ${iso(codeMtimeMs)})`,
    );
  }

  if (stale.length === 0) {
    return {
      entry: {
        name: "code_current",
        ok: true,
        detail:
          `running processes postdate the source on disk (modified ` +
          `${iso(codeMtimeMs)}) — they are running the current code`,
        hint: null,
      },
      warn: false,
    };
  }

  return {
    entry: {
      name: "code_current",
      ok: false,
      detail:
        `STALE CODE: ${stale.join("; ")}. A process cannot have loaded source ` +
        `written after it started, so the fix on disk is NOT the code that is ` +
        `running.`,
      hint:
        "restart the MCP server (e.g. `/mcp` reconnect, or `sac agents restart " +
        "<agent>`). On start it re-reads the source, and ensurePollerRunning() " +
        "will also take over a poller running stale code (PR #78). Do NOT " +
        "trust a version string here — pyproject/package.json/dist-info can " +
        "report a version the executing code never had.",
    },
    warn: false,
  };
}
