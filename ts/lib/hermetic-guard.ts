/**
 * Refuse to open a PRODUCTION database from inside a test run.
 *
 * WHAT HAPPENED (2026-07-14, and it was me):
 *
 * Bun reads bunfig.toml from the CURRENT WORKING DIRECTORY. The only bunfig
 * lived in ts/, so:
 *
 *     cd ts && bun test                 -> preload APPLIES -> hermetic
 *     bun test ts/test/...  (repo root) -> preload NEVER LOADS
 *
 * ts/test/preload.ts is correct and thorough — it deletes every CCT_* /
 * CLAUDE_CODE_TELEGRAMMER_* var and points AGENT_STATE_DIR at a temp dir. But
 * when it does not run, the suite silently inherits the real environment of
 * whatever shell invoked it. On an agent host that resolves to the LIVE bridge
 * state dir, and the tests open the PRODUCTION database.
 *
 * ts/test/store.test.ts:174 calls `saveOffset(99999)`. Run that way, it
 * executed against the operator's real bridge and overwrote the live Telegram
 * getUpdates watermark (348318289 -> 99999) plus the wake-health state. Nothing
 * warned. It just worked, against the wrong database — while I spent hours
 * hunting a "mysterious" poller failure that I was very likely causing.
 *
 * A repo-root bunfig.toml removes the cwd dependency. THIS removes the silence:
 * losing the preload must be LOUD, because the failure mode is destroying
 * production and being told nothing.
 *
 * `bun test` sets NODE_ENV="test" (verified empirically on Bun 1.3.11 — not
 * assumed). So: if we are in a test and the store we are about to open is NOT
 * under the temp dir, the preload did not run, and we must abort rather than
 * write.
 */

/**
 * Throws when a test run is about to open a store outside the temp dir.
 *
 * Pure and fully injectable so it can be tested without touching env, cwd, or
 * a real database — the same seam pattern the rest of lib/ uses.
 *
 * @param nodeEnv  process.env.NODE_ENV ("test" under `bun test`)
 * @param stateDir the resolved STATE_DIR the store is about to open
 * @param tmpDir   os.tmpdir()
 */
export function assertHermeticTestStore(
  nodeEnv: string | undefined,
  stateDir: string,
  tmpDir: string,
): void {
  if (nodeEnv !== "test") return; // production: nothing to police
  if (stateDir.startsWith(tmpDir)) return; // the preload ran — hermetic

  throw new Error(
    `REFUSING TO OPEN THE STORE: NODE_ENV=test, but STATE_DIR is not under ` +
      `the temp dir.\n` +
      `  STATE_DIR = ${stateDir}\n` +
      `  tmpdir    = ${tmpDir}\n` +
      `\n` +
      `The hermetic test preload (ts/test/preload.ts) did NOT run, so this ` +
      `test process inherited a real environment and is about to WRITE TO A ` +
      `LIVE PRODUCTION DATABASE.\n` +
      `\n` +
      `Cause: Bun reads bunfig.toml from the CURRENT WORKING DIRECTORY. Run ` +
      `the suite from the repo root or from ts/ (both now carry a bunfig), ` +
      `never from a directory without one.\n` +
      `\n` +
      `This is not hypothetical: on 2026-07-14 a run without the preload ` +
      `overwrote the live Telegram getUpdates offset on the operator's own ` +
      `bridge (store.test.ts calls saveOffset(99999)).`,
  );
}
