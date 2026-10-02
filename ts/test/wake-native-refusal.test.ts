/** Exercise the actual HTTP/status parser with the native SAC wire shape. */
import { describe, test, expect } from "bun:test";
import { setTurnPoster, wakeTurn } from "../lib/wake.js";

const busyCheck = {
  name: "tui_turn_admitted",
  ok: null,
  detail: "agent busy; turn NOT delivered. NOTHING WAS QUEUED",
  hint: "Retry this exact delivery when the agent is idle.",
  cause: { kind: "http", code: 502, message: "native admission not proven" },
};

async function throughHttp(status: number, body: unknown) {
  const server = Bun.serve({
    hostname: "127.0.0.1", port: 0,
    fetch: () => new Response(JSON.stringify(body), {
      status, headers: { "Content-Type": "application/json" },
    }),
  });
  const previous = setTurnPoster(async (_url, payload) => {
    const response = await fetch(`http://127.0.0.1:${server.port}/v1/turn`, {
      method: "POST", body: JSON.stringify(payload),
      headers: { "Content-Type": "application/json" },
    });
    return { status: response.status, body: await response.text() };
  });
  try {
    return await wakeTurn("synthetic boundary message", {
      chat_id: "test-chat", message_id: "test-message",
    });
  } finally {
    setTurnPoster(previous);
    server.stop(true);
  }
}

describe("native SAC admission refusal", () => {
  test("real HTTP 502 preserves unknown admission and the no-queue reason", async () => {
    const result = await throughHttp(502, {
      check: busyCheck, receipt: { state: "retryable", final: false },
    });

    expect(result).toMatchObject({
      ok: false, status: 502, category: "server_error", check: busyCheck,
    });
    if (result.ok) throw new Error("busy refusal was reported as delivery");
    expect(result.reason).toContain("NOTHING WAS QUEUED");
  });

  test("a transport 200 cannot promote an explicit unknown refusal to delivery", async () => {
    const result = await throughHttp(200, { check: busyCheck });

    expect(result.ok).toBe(false);
  });

  test("an explicit false refusal retains its native errno through HTTP", async () => {
    const check = {
      ...busyCheck, ok: false,
      cause: { kind: "errno", code: "ENOSPC", message: "no space left" },
    };
    const result = await throughHttp(507, { check });

    expect(result).toMatchObject({ ok: false, category: "resource_exhausted", check });
  });

  test("a positive final native receipt is delivered", async () => {
    const result = await throughHttp(200, {
      receipt: { state: "delivered", final: true },
    });

    expect(result).toEqual({ ok: true, status: 200 });
  });
});
