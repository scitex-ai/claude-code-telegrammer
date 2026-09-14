/**
 * The REAL poller, stopped with SIGTERM, must EXIT 143 — the code the
 * supervisor reads as a deliberate stop.
 *
 * lib/exit-codes.ts: SIGTERM_EXIT = 143 is sac's deliberate-stop signal, and
 * poller-supervisor.ts STANDS DOWN on it (no respawn, no page). 143 is what a
 * process KILLED by SIGTERM reports. But telegram-poller.ts installs its own
 * SIGTERM handler (to release the per-token pidfile cleanly), and a handler
 * replaces the default disposition: the process then exits with whatever it
 * passes to process.exit(). It passed 0. The supervisor has no case for 0, so a
 * deliberate stop with no successor took the CRASH path — respawn the poller
 * sac just stopped, and page the operator about a crash that was a stop.
 *
 * poller-supervisor-sigterm.test.ts could not see this: it feeds the
 * supervisor 143 by hand. The two processes disagreed about the number, which
 * is exactly the failure exit-codes.ts was extracted to prevent. So this test
 * stops the REAL poller, against a fake Telegram, and reads the exit code the
 * supervisor would have read.
 */

import { describe, test, expect } from "bun:test";
import { mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { startFakeTelegram } from "./helpers/fake-telegram.js";
import { SIGTERM_EXIT } from "../lib/exit-codes.js";

const POLLER = join(import.meta.dir, "..", "telegram-poller.ts");

describe("the real poller reports a deliberate SIGTERM as SIGTERM_EXIT", () => {
  test("SIGTERM while polling → exit 143, the supervisor's stand-down code — not 0", async () => {
    const fake = startFakeTelegram();
    const stateDir = mkdtempSync(join(tmpdir(), "cct-sigterm-poller-"));
    const child = Bun.spawn([process.execPath, "run", POLLER], {
      env: {
        ...process.env,
        CLAUDE_CODE_TELEGRAMMER_AGENT_STATE_DIR: stateDir,
        CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "sigterm-exit:token",
        // Non-empty: the poller refuses to start on an empty allowlist.
        CLAUDE_CODE_TELEGRAMMER_ALLOWED_USERS: "424242",
        CCT_TELEGRAM_API_BASE: fake.url,
      },
      stdout: "ignore",
      stderr: "pipe",
    });
    const stderrText = new Response(child.stderr as ReadableStream).text();

    try {
      // Signal it only once it is really polling, so the SIGTERM lands on the
      // installed handler rather than on a process still starting up.
      try {
        await fake.waitFor("getUpdates", { timeoutMs: 20_000 });
      } catch (err) {
        child.kill("SIGKILL");
        throw new Error(`${err}\n--- poller stderr ---\n${await stderrText}`);
      }

      child.kill("SIGTERM");
      const code = await child.exited;
      expect(code).toBe(SIGTERM_EXIT);
    } finally {
      child.kill("SIGKILL");
      await child.exited;
      await stderrText;
      await fake.stop();
      rmSync(stateDir, { recursive: true, force: true });
    }
  }, 45_000);
});
