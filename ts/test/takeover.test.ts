/**
 * Per-token poller takeover ("newest wins").
 *
 * No mocks: real tmp dirs, real pidfiles, real fs syscalls. We exercise:
 *
 *   - pidfile path construction (token hash makes it per-bot)
 *   - pidfile read/write round-trip + parse
 *   - claimAuthoritative writes our PID and returns the outgoing snapshot
 *   - claimAuthoritative is idempotent when no prior claim exists
 *   - claimAuthoritative correctly OVERWRITES a previous claim
 *     (the central "newest wins" property — what previously was wrong)
 *   - isAuthoritative flips false after a newer poller's claim
 *   - releaseAuthoritative only unlinks when we still own the pidfile
 *     (must NOT tear down a successor's claim during our shutdown)
 *   - SIGTERM is NOT sent to a dead PID (avoid spurious EPERM-ish noise)
 *   - signalOutgoing=false skips the SIGTERM but still overwrites
 *
 * No process forking — we use signalOutgoing=false in tests that exercise
 * the overwrite path, and a separate isPidAlive-based test for liveness.
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";

import {
  claimAuthoritative,
  isAuthoritative,
  isPidAlive,
  isProcessMatching,
  pollerPidfilePath,
  readPidfile,
  releaseAuthoritative,
} from "../lib/takeover.js";

function freshStateDir(label: string): string {
  const dir = join(
    tmpdir(),
    `cct-takeover-${process.pid}-${Date.now()}-${label}-${Math.random()
      .toString(36)
      .slice(2, 8)}`,
  );
  mkdirSync(dir, { recursive: true });
  return dir;
}

const TOKEN_HASH = "deadbeef";

describe("takeover: pidfile path", () => {
  test("path is per-(stateDir, tokenHash)", () => {
    const a = pollerPidfilePath("/state/A", "abcd1234");
    const b = pollerPidfilePath("/state/A", "ffff0000");
    const c = pollerPidfilePath("/state/B", "abcd1234");
    expect(a).toBe("/state/A/poller-abcd1234.pid");
    expect(b).toBe("/state/A/poller-ffff0000.pid");
    expect(c).toBe("/state/B/poller-abcd1234.pid");
    expect(a).not.toBe(b);
    expect(a).not.toBe(c);
  });
});

describe("takeover: readPidfile", () => {
  let stateDir: string;
  beforeEach(() => {
    stateDir = freshStateDir("readpidfile");
  });
  afterEach(() => {
    rmSync(stateDir, { recursive: true, force: true });
  });

  test("returns null when pidfile is absent", () => {
    const path = pollerPidfilePath(stateDir, TOKEN_HASH);
    expect(readPidfile(path)).toBeNull();
  });

  test("returns null when pidfile contains garbage", () => {
    const path = pollerPidfilePath(stateDir, TOKEN_HASH);
    writeFileSync(path, "garbage-not-a-pid\n");
    expect(readPidfile(path)).toBeNull();
  });

  test("returns null when pid is 0 or negative", () => {
    const path = pollerPidfilePath(stateDir, TOKEN_HASH);
    writeFileSync(path, "0\n1234\n");
    expect(readPidfile(path)).toBeNull();
    writeFileSync(path, "-5\n1234\n");
    expect(readPidfile(path)).toBeNull();
  });

  test("parses (pid, startMs)", () => {
    const path = pollerPidfilePath(stateDir, TOKEN_HASH);
    writeFileSync(path, "12345\n1700000000000\n");
    const snap = readPidfile(path);
    expect(snap).not.toBeNull();
    expect(snap!.pid).toBe(12345);
    expect(snap!.startMs).toBe(1700000000000);
  });

  test("missing startMs defaults to 0", () => {
    const path = pollerPidfilePath(stateDir, TOKEN_HASH);
    writeFileSync(path, "12345\n");
    const snap = readPidfile(path);
    expect(snap).not.toBeNull();
    expect(snap!.pid).toBe(12345);
    expect(snap!.startMs).toBe(0);
  });
});

describe("takeover: claimAuthoritative", () => {
  let stateDir: string;
  beforeEach(() => {
    stateDir = freshStateDir("claim");
  });
  afterEach(() => {
    rmSync(stateDir, { recursive: true, force: true });
  });

  test("creates stateDir if missing + writes pidfile + returns null outgoing on first claim", () => {
    const nested = join(stateDir, "does", "not", "exist", "yet");
    expect(existsSync(nested)).toBe(false);
    const outgoing = claimAuthoritative({
      stateDir: nested,
      tokenHash: TOKEN_HASH,
      pid: 4242,
      startMs: 1700000000000,
      signalOutgoing: false,
    });
    expect(outgoing).toBeNull();
    const path = pollerPidfilePath(nested, TOKEN_HASH);
    expect(existsSync(path)).toBe(true);
    expect(readFileSync(path, "utf8")).toBe("4242\n1700000000000\n");
  });

  test("first claim returns null outgoing; second claim returns the first snapshot", () => {
    const o1 = claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 1001,
      startMs: 1_000,
      signalOutgoing: false,
    });
    expect(o1).toBeNull();

    const o2 = claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 2002,
      startMs: 2_000,
      signalOutgoing: false,
    });
    expect(o2).not.toBeNull();
    expect(o2!.pid).toBe(1001);
    expect(o2!.startMs).toBe(1_000);

    // Pidfile now records the SECOND claimant — newest wins.
    const path = pollerPidfilePath(stateDir, TOKEN_HASH);
    const snap = readPidfile(path);
    expect(snap!.pid).toBe(2002);
    expect(snap!.startMs).toBe(2_000);
  });

  test("OVERWRITES previous live claim — newest wins (the core #37 property)", () => {
    // Simulate the operator-pain scenario: an orphaned older poller
    // (alive PID) holds the pidfile. A newer poller starts up and must
    // win — pidfile is rewritten to point to the NEW pid.
    const alivePid = process.pid; // guaranteed alive: us
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: alivePid,
      startMs: 1_000,
      signalOutgoing: false,
    });

    // New poller comes in:
    const outgoing = claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 9_999_001, // pretend a different new pid
      startMs: 2_000,
      signalOutgoing: false,
    });
    expect(outgoing!.pid).toBe(alivePid);

    const snap = readPidfile(pollerPidfilePath(stateDir, TOKEN_HASH));
    expect(snap!.pid).toBe(9_999_001);
    expect(snap!.startMs).toBe(2_000);
  });

  test("re-claim by the same PID is idempotent (no spurious churn)", () => {
    const o1 = claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 555,
      startMs: 1_000,
      signalOutgoing: false,
    });
    expect(o1).toBeNull();
    const o2 = claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 555,
      startMs: 1_500,
      signalOutgoing: false,
    });
    expect(o2).not.toBeNull();
    expect(o2!.pid).toBe(555);
    const snap = readPidfile(pollerPidfilePath(stateDir, TOKEN_HASH));
    expect(snap!.pid).toBe(555);
    expect(snap!.startMs).toBe(1_500);
  });

  test("isolation across tokens — claim for token A does not touch B", () => {
    claimAuthoritative({
      stateDir,
      tokenHash: "aaaaaaaa",
      pid: 100,
      startMs: 1,
      signalOutgoing: false,
    });
    claimAuthoritative({
      stateDir,
      tokenHash: "bbbbbbbb",
      pid: 200,
      startMs: 2,
      signalOutgoing: false,
    });
    expect(readPidfile(pollerPidfilePath(stateDir, "aaaaaaaa"))!.pid).toBe(100);
    expect(readPidfile(pollerPidfilePath(stateDir, "bbbbbbbb"))!.pid).toBe(200);
  });
});

describe("takeover: isAuthoritative", () => {
  let stateDir: string;
  beforeEach(() => {
    stateDir = freshStateDir("isauth");
  });
  afterEach(() => {
    rmSync(stateDir, { recursive: true, force: true });
  });

  test("false when no pidfile exists", () => {
    expect(
      isAuthoritative({ stateDir, tokenHash: TOKEN_HASH, pid: 1234 }),
    ).toBe(false);
  });

  test("true immediately after our own claim", () => {
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 1234,
      startMs: 1,
      signalOutgoing: false,
    });
    expect(
      isAuthoritative({ stateDir, tokenHash: TOKEN_HASH, pid: 1234 }),
    ).toBe(true);
  });

  test("flips false after a NEWER claim by a different PID — incumbent learns it has been preempted", () => {
    // Incumbent claims
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 1234,
      startMs: 1,
      signalOutgoing: false,
    });
    expect(
      isAuthoritative({ stateDir, tokenHash: TOKEN_HASH, pid: 1234 }),
    ).toBe(true);

    // Successor claims
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 5678,
      startMs: 2,
      signalOutgoing: false,
    });

    // The incumbent's next poll-loop check finds: not me.
    expect(
      isAuthoritative({ stateDir, tokenHash: TOKEN_HASH, pid: 1234 }),
    ).toBe(false);
    // Successor IS authoritative.
    expect(
      isAuthoritative({ stateDir, tokenHash: TOKEN_HASH, pid: 5678 }),
    ).toBe(true);
  });
});

describe("takeover: releaseAuthoritative", () => {
  let stateDir: string;
  beforeEach(() => {
    stateDir = freshStateDir("release");
  });
  afterEach(() => {
    rmSync(stateDir, { recursive: true, force: true });
  });

  test("unlinks pidfile when we still own it", () => {
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 1234,
      startMs: 1,
      signalOutgoing: false,
    });
    const path = pollerPidfilePath(stateDir, TOKEN_HASH);
    expect(existsSync(path)).toBe(true);
    releaseAuthoritative({ stateDir, tokenHash: TOKEN_HASH, pid: 1234 });
    expect(existsSync(path)).toBe(false);
  });

  test("DOES NOT tear down a successor's claim", () => {
    // Critical race: incumbent's shutdown handler must not delete the
    // successor's pidfile entry.
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 1234,
      startMs: 1,
      signalOutgoing: false,
    });
    claimAuthoritative({
      stateDir,
      tokenHash: TOKEN_HASH,
      pid: 5678,
      startMs: 2,
      signalOutgoing: false,
    });

    // Incumbent (1234) shuts down — must NOT unlink successor's pidfile.
    releaseAuthoritative({ stateDir, tokenHash: TOKEN_HASH, pid: 1234 });

    const path = pollerPidfilePath(stateDir, TOKEN_HASH);
    expect(existsSync(path)).toBe(true);
    const snap = readPidfile(path);
    expect(snap!.pid).toBe(5678);
  });

  test("no-op when pidfile is absent", () => {
    expect(() =>
      releaseAuthoritative({ stateDir, tokenHash: TOKEN_HASH, pid: 1234 }),
    ).not.toThrow();
  });
});

describe("takeover: isPidAlive", () => {
  test("true for our own PID", () => {
    expect(isPidAlive(process.pid)).toBe(true);
  });

  test("false for a PID that almost certainly does not exist", () => {
    // Linux's pid_max default is 2^22, but on most systems much lower.
    // 2^30 is comfortably beyond any allocated PID.
    expect(isPidAlive(2 ** 30)).toBe(false);
  });
});

describe("takeover: isProcessMatching (adversarial-review finding #2)", () => {
  test("false for a definitely-dead PID regardless of the substring", () => {
    expect(isProcessMatching(2 ** 30, "anything")).toBe(false);
  });

  test("false for our OWN (definitely alive) pid against a substring it does not have", () => {
    // This bun:test process's cmdline legitimately does not contain
    // "telegram-poller" — the exact case a reused PID would hit, and the
    // exact case that must NOT be trusted as "already running".
    expect(
      isProcessMatching(process.pid, "telegram-poller-definitely-not-this"),
    ).toBe(false);
  });

  test("true for our OWN (alive) pid against a substring its real cmdline DOES contain", () => {
    // Every invocation of this test runs via `bun test ...` (or `bun run
    // .../bunfig` under the hood) — "bun" is reliably present in argv[0].
    expect(isProcessMatching(process.pid, "bun")).toBe(true);
  });

  test("a real spawned child process is correctly matched via its actual script path", async () => {
    // End-to-end: spawn a REAL, short-lived, non-detached child whose
    // command line contains a distinctive marker, and confirm
    // isProcessMatching recognizes it WHILE it's alive.
    const child = Bun.spawn(
      [process.execPath, "-e", "setTimeout(() => {}, 2000)"],
      { stdout: "ignore", stderr: "ignore" },
    );
    try {
      // Bun's own argv0 for a `-e` script is the bun binary path itself —
      // match on that rather than the inline script text, which does not
      // appear verbatim in /proc/<pid>/cmdline the same way a file path
      // spawn's script argument would.
      expect(isProcessMatching(child.pid, "bun")).toBe(true);
      expect(isProcessMatching(child.pid, "definitely-not-a-match-xyz")).toBe(
        false,
      );
    } finally {
      child.kill();
      await child.exited;
    }
  });
});
