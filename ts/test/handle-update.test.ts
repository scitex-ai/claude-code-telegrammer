/**
 * lib/handle-update.ts — post-split migration off `mcp` (architecture fix,
 * incident-cct-inbound-dies-silently-with-mcp-server-20260711, 2026-07).
 *
 * handleReaction/handleUpdate no longer take an `mcp: Server` parameter —
 * the standalone poller process (ts/telegram-poller.ts) that now runs them
 * has no mcp/Server object at all. handleReaction's `mcp.notification(...)`
 * push is replaced by reusing the already mcp-independent /v1/turn wake POST
 * (lib/wake.ts::wakeTurn) — these tests pin THAT wiring via wakeTurn's
 * injectable turnPoster seam (setTurnPoster), the same seam ts/test/wake.test.ts
 * already uses.
 *
 * NOTE on coverage limits: ts/test/preload.ts fixes
 * CLAUDE_CODE_TELEGRAMMER_TURN_URL to a non-empty fake URL for the WHOLE test
 * process (TURN_URL is a module-load-time constant — see lib/config.ts), so
 * wakeEnabled() is always true here. This matches wake.test.ts's own
 * documented limitation ("the env-gated branch is exercised via the
 * injectable poster contract that does not depend on TURN_URL being set")
 * — the interactive-CLI (!wakeEnabled(), no TURN_URL) log-only fallback
 * paths in handleReaction/handleUpdate are NOT exercised by this bun:test
 * process for the same structural reason and are covered by code review
 * only (a single `log(...)` call, no branching complexity).
 */

import {
  describe,
  test,
  expect,
  beforeAll,
  beforeEach,
  afterAll,
} from "bun:test";
import { writeFileSync, mkdirSync, rmSync } from "fs";
import { initStore, getHistory } from "../lib/store.js";
import { _resetCache } from "../lib/access.js";
import { ACCESS_FILE, STATE_DIR } from "../lib/config.js";
import { setTurnPoster, wakeEnabled, type WakeMeta } from "../lib/wake.js";
import { handleReaction, handleUpdate } from "../lib/handle-update.js";

const USER_ID = "8675309";
const CHAT_ID = "8675309";

type TurnCall = { url: string; body: { text: string }; bearer: string };

function captureTurnCalls(status: number = 200): TurnCall[] {
  const calls: TurnCall[] = [];
  setTurnPoster(async (url, body, bearer) => {
    calls.push({ url, body, bearer });
    return status;
  });
  return calls;
}

function reactionUpdate(emoji: string, messageId: number) {
  return {
    update_id: 1,
    message_reaction: {
      chat: { id: Number(CHAT_ID), type: "private" },
      message_id: messageId,
      user: { id: Number(USER_ID), username: "alice" },
      date: 1717000000,
      old_reaction: [],
      new_reaction: [{ type: "emoji", emoji }],
    },
  };
}

beforeAll(() => {
  initStore();
  expect(wakeEnabled()).toBe(true); // sanity: see the NOTE above.
  mkdirSync(STATE_DIR, { recursive: true });
  writeFileSync(ACCESS_FILE, JSON.stringify({ allowFrom: [USER_ID] }));
  _resetCache();
});

afterAll(() => {
  rmSync(ACCESS_FILE, { force: true });
  _resetCache();
});

beforeEach(() => {
  captureTurnCalls(); // reset to a fresh, default (200) poster before each test
});

describe("handleReaction: migrated off mcp.notification onto wakeTurn", () => {
  test("an allowlisted reaction is delivered via the /v1/turn wake POST", async () => {
    const calls = captureTurnCalls();
    await handleReaction(reactionUpdate("👍", 42));

    expect(calls.length).toBe(1);
    expect(calls[0].body.text).toContain("<channel");
    expect(calls[0].body.text).toContain("(reaction: 👍 on message 42)");
    expect(calls[0].body.text).toContain(`chat_id="${CHAT_ID}"`);
  });

  test("a reaction from a user NOT in the allowlist is rejected — no wake POST", async () => {
    const calls = captureTurnCalls();
    const update = reactionUpdate("👍", 43);
    update.message_reaction.user.id = 999999999; // not allowlisted
    await handleReaction(update);
    expect(calls.length).toBe(0);
  });

  test("a reaction with no emoji entries is a no-op — no wake POST", async () => {
    const calls = captureTurnCalls();
    const update = reactionUpdate("👍", 44);
    update.message_reaction.new_reaction = []; // stripped
    await handleReaction(update);
    expect(calls.length).toBe(0);
  });

  test("a wakeTurn failure is swallowed — handleReaction never throws", async () => {
    setTurnPoster(async () => {
      throw new Error("simulated connection refused");
    });
    await expect(
      handleReaction(reactionUpdate("🎉", 45)),
    ).resolves.toBeUndefined();
  });

  test("handleUpdate dispatches message_reaction updates to handleReaction and always reports ok", async () => {
    const calls = captureTurnCalls();
    const status = await handleUpdate(reactionUpdate("🔥", 46));
    expect(status).toBe("ok");
    expect(calls.length).toBe(1);
  });
});

describe("handleUpdate: regular text message still reaches wakeTurn (mcp removed from the signature)", () => {
  test("a plain allowlisted text message persists AND wakes the agent", async () => {
    const calls = captureTurnCalls();
    const update = {
      update_id: 2,
      message: {
        message_id: 100,
        from: { id: Number(USER_ID), is_bot: false, username: "alice" },
        chat: { id: Number(CHAT_ID), type: "private" },
        date: 1717000100,
        text: "hello from the split poller",
      },
    };

    const status = await handleUpdate(update);
    expect(status).toBe("ok");

    // Durably persisted regardless of wake outcome.
    const history = getHistory(CHAT_ID, 50, 0);
    expect(history.some((r) => r.text === "hello from the split poller")).toBe(
      true,
    );

    // Delivered via the mcp-independent wake POST — handleUpdate no longer
    // takes (or needs) an mcp/Server argument at all.
    expect(calls.length).toBe(1);
    expect(calls[0].body.text).toContain("hello from the split poller");
  });
});
