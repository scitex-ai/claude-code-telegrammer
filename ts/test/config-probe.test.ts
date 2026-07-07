/**
 * Tests for the config identity probe (lib/config-probe.ts).
 *
 * The probe resolves the telegrammer config WITHOUT starting the server, for
 * sac's per-agent-bot preflight (assert token→agent identity, detect two
 * agents resolving to the same bot — incident
 * cct-multiagent-telegram-shared-token-409). config.ts evaluates env at import
 * time and preload.ts sets CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN="fake:token" +
 * a tmp STATE_DIR, so the probe reflects those preload values here.
 */

import { describe, test, expect } from "bun:test";
import { tmpdir } from "os";
import {
  buildConfigProbe,
  resolveConfigProbe,
  wantsGetMe,
} from "../lib/config-probe.js";

describe("buildConfigProbe (local, no network)", () => {
  test("reports a present token without printing it", () => {
    const probe = buildConfigProbe();
    // preload sets a fake token → present:true, an 8-hex hash, but never the
    // token itself anywhere on the object.
    expect(probe.bot_token_present).toBe(true);
    expect(probe.bot_token_hash).toMatch(/^[0-9a-f]{8}$/);
    expect(JSON.stringify(probe)).not.toContain("fake:token");
  });

  test("state_dir comes from the resolved config (preload tmp dir)", () => {
    const probe = buildConfigProbe();
    expect(probe.state_dir.startsWith(tmpdir())).toBe(true);
    expect(probe.state_dir).toContain("cct-test-");
  });

  test("channel_source is the bridge's -system label (distinct from agent id)", () => {
    expect(buildConfigProbe().channel_source).toBe(
      "claude-code-telegrammer-system",
    );
  });

  test("agent_id is null when AGENT_ID is unset (not the 'telegram' default)", () => {
    // preload does not set AGENT_ID, so the raw getenv read is undefined → null.
    expect(buildConfigProbe().agent_id).toBeNull();
  });

  test("turn_url_set is a boolean", () => {
    expect(typeof buildConfigProbe().turn_url_set).toBe("boolean");
  });
});

describe("resolveConfigProbe (--check getMe)", () => {
  test("without check, makes NO getMe call", async () => {
    let called = false;
    const probe = await resolveConfigProbe(false, async () => {
      called = true;
      return { username: "x", id: 1 };
    });
    expect(called).toBe(false);
    expect(probe.bot_username).toBeUndefined();
    expect(probe.bot_id).toBeUndefined();
  });

  test("with check + token present, includes bot_username/bot_id", async () => {
    const probe = await resolveConfigProbe(true, async () => ({
      username: "my_bot",
      id: 4242,
    }));
    expect(probe.bot_username).toBe("my_bot");
    expect(probe.bot_id).toBe(4242);
    expect(probe.getme_error).toBeUndefined();
  });

  test("with check, a getMe failure folds into getme_error (no throw)", async () => {
    const probe = await resolveConfigProbe(true, async () => {
      throw new Error("Telegram API getMe failed: Unauthorized");
    });
    expect(probe.getme_error).toContain("Unauthorized");
    expect(probe.bot_username).toBeUndefined();
  });
});

describe("wantsGetMe", () => {
  test("true for --check or --getme", () => {
    expect(wantsGetMe(["config", "--check"])).toBe(true);
    expect(wantsGetMe(["config", "--getme"])).toBe(true);
  });

  test("false otherwise", () => {
    expect(wantsGetMe(["config"])).toBe(false);
    expect(wantsGetMe([])).toBe(false);
  });
});
