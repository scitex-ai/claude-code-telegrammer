/**
 * search_messages, get_context, get_history and get_unread, exercised THROUGH
 * THE MCP TOOL HANDLER.
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
import { writeFileSync, rmSync, mkdirSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { registerTools } from "../lib/tools.js";
import {
  initStore,
  saveInbound,
  saveOutbound,
  getUnread,
  insertAttachment,
  markAttachmentDownloaded,
} from "../lib/store.js";
import { ACCESS_FILE } from "../lib/config.js";
import { _resetCache } from "../lib/access.js";

// Unique per process: bun shares ONE store across every test file, so other
// files' rows are present. Locate by content, never by position.
const CHAT = `tools-read-${process.pid}`;
const TOKEN = `needle${process.pid}x${Date.now()}`;
const SEEDED_TEXT = `the ${TOKEN} is in this message`;

// A second chat for the paging cases: five messages in a known order, so a
// page is checked by CONTENT, not by how many rows came back.
const HCHAT = `tools-history-${process.pid}`;
const HTOKEN = `hist${process.pid}x${Date.now()}`;
const HTEXTS = [1, 2, 3, 4, 5].map((i) => `m${i} ${HTOKEN}`);

// mark_read cases. MCHAT and NCHAT are allowlisted; XCHAT deliberately is not.
const MCHAT = `tools-mark-${process.pid}`;
const NCHAT = `tools-mark-all-${process.pid}`;
const XCHAT = `tools-mark-denied-${process.pid}`;
const rows: Record<string, number> = {};

// download_attachment cases: cached files for one allowed and one denied row.
const FILES = join(tmpdir(), `cct-tools-read-files-${process.pid}`);
const ALLOWED_FILE = join(FILES, "allowed.jpg");
const DENIED_FILE = join(FILES, "denied.jpg");
const ALLOWED_FILE_ID = `fid-allowed-${process.pid}`;
const DENIED_FILE_ID = `fid-denied-${process.pid}`;

let client: Client;
let server: Server;

function textOf(result: { content?: unknown }): unknown {
  const content = result.content as Array<{ type: string; text: unknown }>;
  return content?.[0]?.text;
}

async function callJson(name: string, args: Record<string, unknown>) {
  const result = await client.callTool({ name, arguments: args });
  expect(result.isError).toBeFalsy();
  return JSON.parse(textOf(result) as string);
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
  // Sequential on purpose: row ids must ascend in the order of HTEXTS.
  for (const [i, text] of HTEXTS.entries()) {
    await saveInbound({
      chat_id: HCHAT,
      message_id: String(i + 1),
      user_id: "42",
      username: "tester",
      text,
      telegram_ts: `2026-09-14T00:00:0${i + 1}Z`,
      host: "testhost",
      project: "/test",
      agent_id: "test",
      bot_token_hash: "test-hash",
      raw_json: "{}",
    });
  }

  const seed = async (chat: string, messageId: string): Promise<number> =>
    (await saveInbound({
      chat_id: chat,
      message_id: messageId,
      user_id: "42",
      username: "tester",
      text: `mark ${messageId}`,
      telegram_ts: "2026-09-14T00:01:00Z",
      host: "testhost",
      project: "/test",
      agent_id: "test",
      bot_token_hash: "test-hash",
      raw_json: "{}",
    }))!;
  rows.a = await seed(MCHAT, "a");
  rows.b = await seed(MCHAT, "b");
  rows.c = await seed(MCHAT, "c");
  rows.outbound = await saveOutbound(MCHAT, "an outbound row");
  rows.denied = await seed(XCHAT, "x");
  await seed(NCHAT, "n1");
  await seed(NCHAT, "n2");

  // Cached attachments, one in an allowlisted chat and one in XCHAT, each with
  // a real file on disk so download_attachment short-circuits without network.
  mkdirSync(FILES, { recursive: true });
  for (const [row, fileId, path] of [
    [rows.a, ALLOWED_FILE_ID, ALLOWED_FILE],
    [rows.denied, DENIED_FILE_ID, DENIED_FILE],
  ] as const) {
    writeFileSync(path, "bytes");
    await insertAttachment(row, { kind: "photo", file_id: fileId });
    await markAttachmentDownloaded(row, fileId, path);
  }

  // The handlers call assertAllowedChat(). loadAccess() caches a MISSING
  // access.json for 5s, so a file written after an earlier test's read would
  // be ignored for that window — a test that passes alone and fails in the
  // suite. Reset the cache after writing.
  writeFileSync(
    ACCESS_FILE,
    JSON.stringify({ allowFrom: [CHAT, HCHAT, MCHAT, NCHAT] }),
  );
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
  rmSync(FILES, { recursive: true, force: true });
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
 * get_unread: `{coverage, count, total, messages}` (lib/tools-messages.ts
 * messagesResult — "Every message read answers in ONE shape").
 *
 * #140 fixed the missing await and left search on a bare ARRAY. That stopped
 * the `{}` but kept the original ambiguity those two tools were moved off on
 * 2026-08-15: `[]` cannot say whether nothing matched or the store recorded
 * nothing for the window. `coverage` is the store's own statement about that,
 * and it is what saved the one reader of three who happened to bring a
 * control. The empty result has to describe itself.
 */
describe("search_messages answers in the declared {coverage, count, total, messages} shape", () => {
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
    expect(parsed.total).toBeGreaterThanOrEqual(parsed.count);
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
    const unread = await callJson("get_unread", { chat_id: CHAT });
    expect(Object.keys(search).sort()).toEqual(Object.keys(history).sort());
    expect(Object.keys(unread).sort()).toEqual(Object.keys(history).sort());
  });
});

/**
 * get_history hands back the LATEST page, oldest-to-newest within it.
 *
 * It used to run `ORDER BY id ASC LIMIT n OFFSET k`, so limit=N on a long chat
 * returned the N OLDEST messages — well-formed, in order, with a `count` that
 * looked like an answer. scitex-hub asked for the recent 14 on 2026-09-05 and
 * got messages from three days earlier, noticed only because it read the
 * timestamps. Both main callers want the newest rows: the restart protocol
 * ("what arrived while I was down") and the server instructions, which send an
 * agent to get_history for the rest of a truncated message.
 *
 * The store tests that stood guard passed at EVERY ordering: "chronological
 * within the result" and "page 1 differs from page 2" are just as true of the
 * oldest page. These pin WHICH rows come back.
 */
describe("get_history returns the LATEST page, not the oldest", () => {
  const texts = (env: { messages: Array<{ text?: string }> }) =>
    env.messages.map((m) => m.text);

  test("limit=N is the newest N, listed oldest-to-newest", async () => {
    const env = await callJson("get_history", { chat_id: HCHAT, limit: 2 });
    expect(texts(env)).toEqual([HTEXTS[3], HTEXTS[4]]);
  });

  test("offset pages BACK from the newest", async () => {
    const page2 = await callJson("get_history", {
      chat_id: HCHAT,
      limit: 2,
      offset: 2,
    });
    expect(texts(page2)).toEqual([HTEXTS[1], HTEXTS[2]]);
    const page3 = await callJson("get_history", {
      chat_id: HCHAT,
      limit: 2,
      offset: 4,
    });
    expect(texts(page3)).toEqual([HTEXTS[0]]);
  });

  test("total says whether older history exists — count alone cannot", async () => {
    const page = await callJson("get_history", { chat_id: HCHAT, limit: 2 });
    expect(page.count).toBe(2);
    expect(page.total).toBe(5);
    const all = await callJson("get_history", { chat_id: HCHAT, limit: 50 });
    expect(all.count).toBe(5);
    expect(all.total).toBe(5);
  });
});

describe("`total` rides on every message read", () => {
  test("search_messages: total counts every match, so a cut is visible", async () => {
    const env = await callJson("search_messages", {
      query: HTOKEN,
      chat_id: HCHAT,
      limit: 2,
    });
    expect(env.count).toBe(2);
    expect(env.total).toBe(5);
  });

  test("get_unread: total equals count — it has no limit to cut with", async () => {
    const env = await callJson("get_unread", { chat_id: HCHAT });
    expect(env.count).toBe(5);
    expect(env.total).toBe(5);
  });
});

/**
 * search_messages and get_context pin WHICH rows come back, not only how many.
 *
 * The get_history bug (#145) was an `ORDER BY id ASC LIMIT` that returned the
 * OLDEST rows, and it survived because its tests checked properties the oldest
 * page shares with the newest one. These two tools were guarded the same way:
 * a count, or a toContain on a chat of one or two rows. Here the chat holds
 * five messages in a known order, so the oldest rows are distinguishable.
 */
describe("search_messages and get_context return the NEWEST rows", () => {
  test("search_messages: limit=2 is the two newest matches, newest first", async () => {
    const env = await callJson("search_messages", {
      query: HTOKEN,
      chat_id: HCHAT,
      limit: 2,
    });
    expect(env.messages.map((m: { text?: string }) => m.text)).toEqual([
      HTEXTS[4],
      HTEXTS[3],
    ]);
  });

  test("get_context: max_messages=2 is the two newest, oldest-to-newest", async () => {
    const result = await client.callTool({
      name: "get_context",
      arguments: { chat_id: HCHAT, max_messages: 2 },
    });
    const text = textOf(result) as string;
    expect(text).toContain(HTEXTS[3]);
    expect(text).toContain(HTEXTS[4]);
    for (const old of HTEXTS.slice(0, 3)) expect(text).not.toContain(old);
    expect(text.indexOf(HTEXTS[3])).toBeLessThan(text.indexOf(HTEXTS[4]));
  });
});

/**
 * mark_read says what it ACTUALLY marked.
 *
 * It answered "marked N message(s) as read" with N = the ids it was GIVEN. The
 * update only touches rows that exist, are inbound and are still unread, so any
 * other id changed nothing and was reported as marked anyway. The likeliest
 * wrong input is a Telegram message_id passed where the DB row id belongs, and
 * both sit in every channel message. The row-id path also never consulted the
 * allowlist, so rows of ANY chat could be marked. No test went through this
 * tool's dispatch, which is why neither was seen.
 */
describe("mark_read reports what it actually marked", () => {
  const NO_SUCH_ROW = 9_000_000_000_000;
  const unreadIds = async (chat: string) =>
    (await getUnread(chat)).map((r) => Number(r.id));
  const markRead = (args: Record<string, unknown>) =>
    client.callTool({ name: "mark_read", arguments: args });

  test("message_ids: counts the rows changed and names the rest", async () => {
    const result = await markRead({
      message_ids: [rows.a, rows.outbound, NO_SUCH_ROW],
    });
    expect(result.isError).toBeFalsy();
    const text = textOf(result) as string;
    expect(text).toContain("marked 1 of 3");
    expect(text).toContain(`not found: ${NO_SUCH_ROW}`);
    expect(text).toContain(`already read or not inbound: ${rows.outbound}`);
    expect(await unreadIds(MCHAT)).not.toContain(rows.a);
    expect(await unreadIds(MCHAT)).toContain(rows.b);
  });

  test("a row already read is not counted a second time", async () => {
    expect(textOf(await markRead({ message_ids: [rows.b] }))).toContain(
      "marked 1 of 1",
    );
    const again = textOf(await markRead({ message_ids: [rows.b] })) as string;
    expect(again).toContain("marked 0 of 1");
    expect(again).toContain(`already read or not inbound: ${rows.b}`);
  });

  test("a row in a chat outside the allowlist is refused, and NOTHING is marked", async () => {
    const result = await markRead({ message_ids: [rows.c, rows.denied] });
    expect(result.isError).toBe(true);
    expect(textOf(result) as string).toContain("not allowlisted");
    expect(await unreadIds(XCHAT)).toContain(rows.denied);
    // No partial write: the allowed row in the same call stays unread too.
    expect(await unreadIds(MCHAT)).toContain(rows.c);
  });

  test("chat_id: the answer carries the count", async () => {
    expect(textOf(await markRead({ chat_id: NCHAT }))).toContain(
      "marked 2 unread message(s)",
    );
    expect(textOf(await markRead({ chat_id: NCHAT }))).toContain(
      "marked 0 unread message(s)",
    );
  });

  test("an id that is not a row id is refused by name", async () => {
    const result = await markRead({ message_ids: ["abc"] });
    expect(result.isError).toBe(true);
    expect(textOf(result) as string).toContain("abc");
    expect(textOf(result) as string).toContain("row id");
  });
});

/**
 * download_attachment checks the allowlist, like every other tool that reaches
 * a chat's data. It checked nothing, and its first move after resolving the
 * attachment was to hand back a cached local_path, so any stored attachment's
 * file was one call away. Rows exist only for chats that were allowlisted when
 * their messages arrived (handle-update rejects the rest before saving), so the
 * exposure was a chat removed from the allowlist since. The positive control
 * proves the check does not over-block an allowed chat.
 */
describe("download_attachment refuses a chat outside the allowlist", () => {
  const download = (args: Record<string, unknown>) =>
    client.callTool({ name: "download_attachment", arguments: args });

  test("row_id of a de-listed chat's attachment is refused, even when cached", async () => {
    const result = await download({ row_id: rows.denied });
    expect(result.isError).toBe(true);
    expect(textOf(result) as string).toContain("not allowlisted");
  });

  test("file_id of that attachment is refused too", async () => {
    const result = await download({ file_id: DENIED_FILE_ID });
    expect(result.isError).toBe(true);
    expect(textOf(result) as string).toContain("not allowlisted");
  });

  test("an allowlisted chat's cached attachment still comes straight back", async () => {
    const result = await download({ row_id: rows.a });
    expect(result.isError).toBeFalsy();
    expect(textOf(result)).toBe(`downloaded to: ${ALLOWED_FILE}`);
  });
});
