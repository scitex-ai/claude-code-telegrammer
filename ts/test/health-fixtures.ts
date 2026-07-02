/**
 * Shared fixtures for the health ("doctor") tests — a fully healthy
 * HealthInputs baseline that individual tests override field-by-field, and a
 * lookup helper. Split out so health.test.ts / health-checks.test.ts stay
 * under the repo's 512-line file cap.
 */

import type { HealthInputs, HealthReport } from "../lib/health.js";
import { SCHEMA_VERSION } from "../lib/store.js";

// preload.ts sets CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN to this value; config.ts's
// TOKEN (which redactToken defaults to) resolves to it.
export const FAKE_TOKEN = "fake:token";

/** A fully healthy baseline; individual tests override single fields. */
export function healthyInputs(
  overrides: Partial<HealthInputs> = {},
): HealthInputs {
  return {
    agentId: "test-agent",
    stateDir: "/tmp/cct-health-test",
    tokenPresent: true,
    unexpandedEnvLines: [],
    renamedEnvLines: [],
    legacyEnvNames: [],
    tokenCheck: { ok: true, username: "my_bot", id: 4242 },
    webhook: { kind: "response", ok: true, url: "" },
    poller: { kind: "self", pid: 1234 },
    access: {
      accessFileExists: true,
      envAllowedCount: 0,
      dmPolicy: "allowlist",
      accessFilePath: "/tmp/cct-health-test/access.json",
    },
    stateDirProbe: {
      path: "/tmp/cct-health-test",
      exists: true,
      writable: true,
    },
    db: {
      exists: true,
      schemaVersion: SCHEMA_VERSION,
      updateOffset: 100,
      maxUpdateId: 99,
      inboundCount: 5,
    },
    ...overrides,
  };
}

/** Find a check entry by name; throws (fails the test) when missing. */
export function byName(report: HealthReport, name: string) {
  const entry = report.checks.find((c) => c.name === name);
  if (!entry) throw new Error(`check ${name} missing from report`);
  return entry;
}
