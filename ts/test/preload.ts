/**
 * Test preload — sets env vars BEFORE any module imports.
 */

import { join } from "path";
import { tmpdir } from "os";
import { mkdirSync } from "fs";

const TEST_DIR = join(tmpdir(), `cct-test-${process.pid}`);
mkdirSync(TEST_DIR, { recursive: true });

// Hermetic env: drop any telegrammer vars inherited from the operator's shell
// (e.g. a real CLAUDE_CODE_TELEGRAMMER_TELEGRAM_BOT_TOKEN / CCT_* export) so
// getenv()'s conflict detection sees ONLY the canonical test values set below,
// not an ambient legacy value that disagrees with them.
for (const name of Object.keys(process.env)) {
  if (name.startsWith("CCT_") || name.startsWith("CLAUDE_CODE_TELEGRAMMER_")) {
    delete process.env[name];
  }
}

process.env.CLAUDE_CODE_TELEGRAMMER_STATE_DIR = TEST_DIR;
process.env.CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN = "fake:token";
process.env.CLAUDE_CODE_TELEGRAMMER_ALLOWED_USERS = "";
process.env.CLAUDE_CODE_TELEGRAMMER_TURN_URL = "http://fake.localhost/v1/turn";

// Export for tests to reference
(globalThis as any).__CCT_TEST_DIR = TEST_DIR;
