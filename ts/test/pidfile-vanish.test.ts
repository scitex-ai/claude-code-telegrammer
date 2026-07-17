/**
 * A vanished pidfile must NOT kill a healthy poller.
 *
 * THIS IS THE ROOT CAUSE OF 2026-07-14, and I chased it all day while it was
 * writing its own confession into a log I had disabled.
 *
 * The poll loop asked `isAuthoritative()` — a boolean — and treated `false` as
 * "a newer poller took over, stand down". But isAuthoritative() returns false
 * for TWO different worlds:
 *
 *     takeover.ts:241    const snap = readPidfile(path);
 *                        if (!snap) return false;          <-- file is GONE
 *                        return snap.pid === pid;          <-- someone else owns it
 *
 * A file that VANISHED is not a successor. Nobody preempted us; nobody owns the
 * pidfile at all. The poller logged "preempted by newer poller — exiting
 * cleanly" and killed itself, and the operator's only channel to the fleet died
 * with it. From the real log, verbatim:
 *
 *   01:39:44.660  "preempted by newer poller (pidfile no longer records our
 *                  PID) — exiting cleanly"      ourPid=117370
 *   01:39:44.979  "claimed pidfile (NO PRIOR POLLER RECORDED)"  ourPid=124271
 *
 * The successor found NO PRIOR POLLER. Nobody had taken over. The first poller
 * died for a deleted file.
 *
 * Deleting a file must never kill a healthy process.
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtempSync, rmSync, existsSync, unlinkSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import {
  claimAuthoritative,
  checkAuthority,
  pollerPidfilePath,
  readPidfile,
} from "../lib/takeover.js";

const TOKEN = "cafebabe";
let stateDir: string;

beforeEach(() => {
  stateDir = mkdtempSync(join(tmpdir(), "cct-pidfile-"));
});
afterEach(() => {
  rmSync(stateDir, { recursive: true, force: true });
});

describe("checkAuthority: tells the three worlds apart", () => {
  test("VACANT — no pidfile at all. Nobody preempted us.", () => {
    const a = checkAuthority({ stateDir, tokenHash: TOKEN, pid: 4242 });
    expect(a.kind).toBe("vacant");
  });

  test("OURS — the pidfile records us", () => {
    claimAuthoritative({ stateDir, tokenHash: TOKEN, pid: 4242 });
    const a = checkAuthority({ stateDir, tokenHash: TOKEN, pid: 4242 });
    expect(a.kind).toBe("ours");
  });

  // NOTE: preemption requires the preemptor to be ALIVE (see
  // ts/test/stale-preemptor.test.ts — a pidfile naming a DEAD pid is a stale
  // claim, not a successor, and standing down for it is what killed the
  // operator's bridge). These fake pids do not exist, so liveness is injected.
  const preemptorIsAlive = (pid: number) => pid !== 4242;

  test("PREEMPTED — the pidfile records a DIFFERENT, LIVE pid", () => {
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN,
      pid: 9999,
      signalOutgoing: false,
    });
    const a = checkAuthority({
      stateDir,
      tokenHash: TOKEN,
      pid: 4242,
      isAlive: preemptorIsAlive,
    });
    expect(a.kind).toBe("preempted");
    if (a.kind === "preempted") expect(a.byPid).toBe(9999);
  });

  // THE BUG. Before checkAuthority existed, both of these looked identical to
  // the poll loop — a bare `false` — and it stood down for both.
  test("a DELETED pidfile is 'vacant', NOT 'preempted' — they must never be confused", () => {
    claimAuthoritative({ stateDir, tokenHash: TOKEN, pid: 4242 });
    expect(checkAuthority({ stateDir, tokenHash: TOKEN, pid: 4242 }).kind).toBe(
      "ours",
    );

    // Something deletes it out from under the running poller.
    unlinkSync(pollerPidfilePath(stateDir, TOKEN));

    const after = checkAuthority({ stateDir, tokenHash: TOKEN, pid: 4242 });
    expect(after.kind).toBe("vacant"); // NOT "preempted"
    expect(after.kind).not.toBe("preempted");
  });

  test("re-claiming a vanished pidfile restores ownership (what the loop now does)", () => {
    claimAuthoritative({ stateDir, tokenHash: TOKEN, pid: 4242 });
    unlinkSync(pollerPidfilePath(stateDir, TOKEN));
    expect(existsSync(pollerPidfilePath(stateDir, TOKEN))).toBe(false);

    // The poll loop's response to "vacant": re-claim and keep polling.
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN,
      pid: 4242,
      signalOutgoing: false,
    });

    expect(checkAuthority({ stateDir, tokenHash: TOKEN, pid: 4242 }).kind).toBe(
      "ours",
    );
    expect(readPidfile(pollerPidfilePath(stateDir, TOKEN))?.pid).toBe(4242);
  });

  // The correct behaviour is PRESERVED: a genuine takeover must still stand the
  // loser down immediately, or two pollers hit one bot token and Telegram
  // answers with a 409 Conflict storm (getUpdates is single-consumer).
  test("a genuine (LIVE) takeover still preempts — the 409 guard is not weakened", () => {
    claimAuthoritative({ stateDir, tokenHash: TOKEN, pid: 4242 });
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN,
      pid: 5555,
      signalOutgoing: false,
    });

    const a = checkAuthority({
      stateDir,
      tokenHash: TOKEN,
      pid: 4242,
      isAlive: preemptorIsAlive,
    });
    expect(a.kind).toBe("preempted");
  });
});
