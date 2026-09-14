/**
 * search_messages and get_context, exercised THROUGH THE MCP TOOL HANDLER.
 *
 * WHY THIS FILE EXISTS. PR #132 moved the store onto PostgreSQL, which made
 * searchMessages() and getConversationContext() async. store.test.ts was
 * updated to await them and stayed green. The two call sites in lib/tools.ts
 * were not updated — and nothing tested them, because no test in this suite
 * went through a tool handler at all. So both tools broke in production while
 * every test passed:
 *
 *   get_context      returned a Promise where the MCP schema requires a string
 *                    -> "expected string, received Promise" (scitex-hub, 09-05)
 *   search_messages  JSON.stringify(<Promise>) is "{}"
 *                    -> a bare {} for every query, which PARSES and reads as
 *                       "nothing found" (scitex-hub + scitex-agent-container,
 *                       09-06; one of them told its user the store was empty)
 *
 * A test at the store layer cannot see a defect in the store's CALLER. So these
 * tests drive a real Client against a real Server over the SDK's in-memory
 * transport, with registerTools() wiring the real handlers onto the real store
 * (the throwaway schema preload.ts mints). No mocks.
 */

import { describe, test, expect, beforeAll, afterAll } from "bun:test";
import { writeFileSync, rmSync } from "fs";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { registerTools } from "../lib/tools.js";
import { initStore, saveInbound } from "../lib/store.js";
import { ACCESS_FILE } from "../lib/config.js";
import { _resetCache } from "../lib/access.js";

// Unique per process: bun shares ONE store across every test file, so other
// files' rows are present. Locate by content, never by position.
const CHAT = `tools-read-${process.pid}`;
const TOKEN = `needle${process.pid}x${Date.now()}`;
const SEEDED_TEXT = `the ${TOKEN} is in this message`;

let client: Client;
let server: Server;

function textOf(result: { content?: unknown }): unknown {
  const content = result.content as Array<{ type: string; text: unknown }>;
  return content?.[0]?.text;
}

beforeAll(async () => {
  await initStore();
  await saveInbound({
    chat_id: CHAT,
    message_id: "1",
    user_id: "42",
    username: "tester",
    text: SEEDED_TEXT,
    telegram_ts: "2026-09-14T00:00:00Z",
    host: "testhost",
    project: "/test",
    agent_id: "test",
    bot_token_hash: "test-hash",
    raw_json: "{}",
  });

  // The handlers call assertAllowedChat(). loadAccess() caches a MISSING
  // access.json for 5s, so a file written after an earlier test's read would
  // be ignored for that window — a test that passes alone and fails in the
  // suite. Reset the cache after writing.
  writeFileSync(ACCESS_FILE, JSON.stringify({ allowFrom: [CHAT] }));
  _resetCache();

  server = new Server(
    { name: "cct-test", version: "0.0.0" },
    { capabilities: { tools: {} } },
  );
  registerTools(server);
  client = new Client({ name: "cct-test-client", version: "0.0.0" });
  const [clientT, serverT] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(serverT), client.connect(clientT)]);
});

afterAll(async () => {
  await client?.close();
  await server?.close();
  // Restore the absent-access.json default later test files expect.
  rmSync(ACCESS_FILE, { force: true });
  _resetCache();
});

describe("get_context returns TEXT, not a Promise", () => {
  test("the result survives the MCP schema and is a string", async () => {
    // Before the fix this call rejected at the transport:
    //   MCP error -32602 ... "expected string, received Promise"
    const result = await client.callTool({
      name: "get_context",
      arguments: { chat_id: CHAT, max_messages: 10 },
    });
    expect(result.isError).toBeFalsy();
    const text = textOf(result);
    expect(typeof text).toBe("string");
    expect(text as string).toContain(TOKEN);
  });
});

/**
 * search_messages answers in the SAME declared shape as get_history and
 * get_unread: `{coverage, count, messages}` (lib/tools-messages.ts
 * messagesResult — "Every message read answers in ONE shape").
 *
 * #140 fixed the missing await and left search on a bare ARRAY. That stopped
 * the `{}` but kept the original ambiguity those two tools were moved off on
 * 2026-08-15: `[]` cannot say whether nothing matched or the store recorded
 * nothing for the window. `coverage` is the store's own statement about that,
 * and it is what saved the one reader of three who happened to bring a
 * control. The empty result has to describe itself.
 */
describe("search_messages answers in the declared {coverage, count, messages} shape", () => {
  function parseEnvelope(text: unknown) {
    expect(typeof text).toBe("string");
    const parsed = JSON.parse(text as string);
    // THE DISCRIMINATING ASSERTIONS. JSON.stringify(<Promise>) is "{}" and a
    // bare array is "[]" — both parse. Neither is this shape.
    expect(Array.isArray(parsed)).toBe(false);
    expect(parsed).toHaveProperty("coverage");
    expect(parsed).toHaveProperty("count");
    expect(Array.isArray(parsed.messages)).toBe(true);
    expect(parsed.count).toBe(parsed.messages.length);
    return parsed;
  }

  test("a matching query returns the rows inside the envelope", async () => {
    const result = await client.callTool({
      name: "search_messages",
      arguments: { query: TOKEN, chat_id: CHAT },
    });
    expect(result.isError).toBeFalsy();
    const env = parseEnvelope(textOf(result));
    expect(env.count).toBeGreaterThanOrEqual(1);
    expect(
      env.messages.some((r: { text?: string }) => r.text === SEEDED_TEXT),
    ).toBe(true);
  });

  test("no match is count:0 WITH coverage — an answer that describes itself", async () => {
    // The reporters' real complaint: {} for "no matches" and {} for "the query
    // never ran" were the same bytes. An empty result must now carry the
    // store's own verdict on whether it can vouch for the window.
    const result = await client.callTool({
      name: "search_messages",
      arguments: { query: `absent-${TOKEN}-absent`, chat_id: CHAT },
    });
    const env = parseEnvelope(textOf(result));
    expect(env.count).toBe(0);
    expect(env.messages).toHaveLength(0);
    expect(typeof env.coverage.verdict).toBe("string");
  });

  test("search and get_history share one shape — same top-level keys", async () => {
    // Guards the invariant, not just this tool: if either drifts, the reader
    // who learned one shape from one tool misreads the other.
    const search = JSON.parse(
      textOf(
        await client.callTool({
          name: "search_messages",
          arguments: { query: TOKEN, chat_id: CHAT },
        }),
      ) as string,
    );
    const history = JSON.parse(
      textOf(
        await client.callTool({
          name: "get_history",
          arguments: { chat_id: CHAT, limit: 5 },
        }),
      ) as string,
    );
    expect(Object.keys(search).sort()).toEqual(Object.keys(history).sort());
  });
});
