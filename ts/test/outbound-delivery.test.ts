/**
 * Standalone outbound self-healing (lib/outbound-delivery.ts): delivery-confirm
 * loop, bounded retry with backoff, route-switch fallback — no SAC, no token,
 * no network. Every seam (send, verify, sleep, env) is injected; sleeps are
 * recorded by a virtual clock, never awaited.
 */

import { describe, test, expect } from "bun:test";
import {
  backoffDelayMs,
  confirmDelivery,
  isRetryableFailure,
  isRouteDeadFailure,
  resolveOutboundRoutes,
  sendWithFailover,
  sendWithRetry,
  toSendFailure,
  type OutboundRoute,
} from "../lib/outbound-delivery.js";

/** Virtual sleep: records delays, advances instantly. */
function virtualClock() {
  const delays: number[] = [];
  return {
    delays,
    sleep: (ms: number): Promise<void> => {
      delays.push(ms);
      return Promise.resolve();
    },
  };
}

const PRIMARY: OutboundRoute = {
  label: "primary",
  token: "primary:token",
  apiRoot: "https://api.telegram.org",
};
const BACKUP: OutboundRoute = {
  label: "backup",
  token: "backup:token",
  apiRoot: "https://api.telegram.org",
};

function tgError(code: number, what = "fail"): Error {
  return new Error(`Telegram API sendMessage failed (error_code ${code}): ${what}`);
}

describe("backoffDelayMs", () => {
  test("doubles per attempt and caps at the ceiling", () => {
    expect(backoffDelayMs(1, 500, 10_000)).toBe(500);
    expect(backoffDelayMs(2, 500, 10_000)).toBe(1000);
    expect(backoffDelayMs(3, 500, 10_000)).toBe(2000);
    expect(backoffDelayMs(10, 500, 10_000)).toBe(10_000);
  });
});

describe("isRetryableFailure / isRouteDeadFailure", () => {
  test("transport, 429 and 5xx retry; 400/401/403/404 do not", () => {
    expect(isRetryableFailure({ transport: new Error("x"), message: "x" })).toBe(true);
    expect(isRetryableFailure({ errorCode: 429, message: "r" })).toBe(true);
    expect(isRetryableFailure({ errorCode: 500, message: "s" })).toBe(true);
    expect(isRetryableFailure({ errorCode: 400, message: "b" })).toBe(false);
    expect(isRetryableFailure({ errorCode: 401, message: "u" })).toBe(false);
    expect(isRetryableFailure({ errorCode: 403, message: "f" })).toBe(false);
    expect(isRetryableFailure({ errorCode: 404, message: "n" })).toBe(false);
  });

  test("only 401 marks a route dead", () => {
    expect(isRouteDeadFailure({ errorCode: 401, message: "u" })).toBe(true);
    expect(isRouteDeadFailure({ errorCode: 403, message: "f" })).toBe(false);
    expect(isRouteDeadFailure({ transport: new Error("x"), message: "x" })).toBe(false);
  });

  test("toSendFailure recovers error_code from a TelegramApiError-shaped message", () => {
    expect(toSendFailure(tgError(429)).errorCode).toBe(429);
    expect(toSendFailure(tgError(401)).errorCode).toBe(401);
    const t = toSendFailure(new Error("fetch failed"));
    expect(t.transport).toBeDefined();
  });
});

describe("sendWithRetry", () => {
  test("succeeds first try with no sleep", async () => {
    const clock = virtualClock();
    const r = await sendWithRetry(() => Promise.resolve(42), {}, clock);
    expect(r).toEqual({ messageId: 42, attempts: 1 });
    expect(clock.delays).toEqual([]);
  });

  test("retries a 429 with exponential backoff, then succeeds", async () => {
    const clock = virtualClock();
    let n = 0;
    const r = await sendWithRetry(
      () => (++n < 3 ? Promise.reject(tgError(429, "slow down")) : Promise.resolve(7)),
      { baseMs: 500, maxDelayMs: 10_000 },
      clock,
    );
    expect(r).toEqual({ messageId: 7, attempts: 3 });
    expect(clock.delays).toEqual([500, 1000]);
  });

  test("a 403 fails fast with NO sleep and NO further attempt", async () => {
    const clock = virtualClock();
    let n = 0;
    await expect(
      sendWithRetry(
        () => {
          n += 1;
          return Promise.reject(tgError(403, "bot blocked"));
        },
        { maxAttempts: 5 },
        clock,
      ),
    ).rejects.toThrow("terminal");
    expect(n).toBe(1);
    expect(clock.delays).toEqual([]);
  });

  test("exhaustion is bounded: exactly maxAttempts, then the last failure", async () => {
    const clock = virtualClock();
    let n = 0;
    await expect(
      sendWithRetry(
        () => {
          n += 1;
          return Promise.reject(new Error("fetch failed: black hole"));
        },
        { maxAttempts: 3, baseMs: 100 },
        clock,
      ),
    ).rejects.toThrow("exhausted after 3 attempt(s)");
    expect(n).toBe(3);
    expect(clock.delays).toEqual([100, 200]);
  });
});

describe("confirmDelivery", () => {
  test("verify success → confirmed", async () => {
    const r = await confirmDelivery("1", 9, { verifyChat: () => Promise.resolve({}) });
    expect(r).toEqual({ state: "confirmed", messageId: 9 });
  });

  test("verify failure → unconfirmed with reason, never thrown", async () => {
    const r = await confirmDelivery("1", 9, {
      verifyChat: () => Promise.reject(new Error("Forbidden: bot was blocked")),
    });
    expect(r.state).toBe("unconfirmed");
    expect(r.reason).toContain("blocked");
  });
});

describe("resolveOutboundRoutes", () => {
  test("empty token → no routes (caller refuses loud, never a disguised 404)", () => {
    expect(resolveOutboundRoutes({})).toEqual([]);
    expect(resolveOutboundRoutes({ CCT_BOT_TOKEN: "" })).toEqual([]);
  });

  test("primary only without backup vars", () => {
    const routes = resolveOutboundRoutes({ CCT_BOT_TOKEN: "tok:abc" });
    expect(routes).toEqual([
      { label: "primary", token: "tok:abc", apiRoot: "https://api.telegram.org" },
    ]);
  });

  test("backup token adds a second route; backup root falls back to primary root", () => {
    const routes = resolveOutboundRoutes({
      CCT_BOT_TOKEN: "tok:primary",
      CCT_BOT_TOKEN_BACKUP: "tok:backup",
    });
    expect(routes.map((r) => r.label)).toEqual(["primary", "backup"]);
    expect(routes[1].apiRoot).toBe("https://api.telegram.org");
  });

  test("canonical long spelling also resolves", () => {
    const routes = resolveOutboundRoutes({
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "tok:long",
      CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN_BACKUP: "tok:long-bak",
    });
    expect(routes.map((r) => r.token)).toEqual(["tok:long", "tok:long-bak"]);
  });
});

describe("sendWithFailover", () => {
  test("zero routes → loud refusal naming the empty token", async () => {
    await expect(
      sendWithFailover([], "1", "hi", {}, { sendVia: () => Promise.resolve(1) }),
    ).rejects.toThrow("no routes");
  });

  test("primary success needs no switch", async () => {
    const clock = virtualClock();
    const seen: string[] = [];
    const r = await sendWithFailover(
      [PRIMARY, BACKUP],
      "1",
      "hi",
      {},
      {
        ...clock,
        sendVia: (route) => {
          seen.push(route.label);
          return Promise.resolve(11);
        },
      },
    );
    expect(r).toEqual({ messageId: 11, route: "primary", attempts: 1, delivery: "confirmed" });
    expect(seen).toEqual(["primary"]);
  });

  test("primary exhaustion switches to backup; attempts counted across routes", async () => {
    const clock = virtualClock();
    const seen: string[] = [];
    const r = await sendWithFailover(
      [PRIMARY, BACKUP],
      "1",
      "hi",
      { maxAttempts: 2, baseMs: 10 },
      {
        ...clock,
        sendVia: (route) => {
          seen.push(route.label);
          return route.label === "primary"
            ? Promise.reject(new Error("fetch failed: hole"))
            : Promise.resolve(22);
        },
      },
    );
    expect(r.route).toBe("backup");
    expect(r.messageId).toBe(22);
    expect(r.attempts).toBe(3); // 2 burned on primary + 1 on backup
    expect(seen).toEqual(["primary", "primary", "backup"]);
  });

  test("401 on primary switches after ONE attempt (no waiting on a dead token)", async () => {
    const clock = virtualClock();
    const seen: string[] = [];
    const r = await sendWithFailover(
      [PRIMARY, BACKUP],
      "1",
      "hi",
      { maxAttempts: 5, baseMs: 1000 },
      {
        ...clock,
        sendVia: (route) => {
          seen.push(route.label);
          return route.label === "primary"
            ? Promise.reject(tgError(401, "unauthorized"))
            : Promise.resolve(33);
        },
      },
    );
    expect(r.route).toBe("backup");
    expect(seen).toEqual(["primary", "backup"]);
    expect(clock.delays).toEqual([]); // terminal failure never sleeps
  });

  test("403 fails fast with NO switch (bad request, not a bad route)", async () => {
    const seen: string[] = [];
    await expect(
      sendWithFailover(
        [PRIMARY, BACKUP],
        "1",
        "hi",
        { maxAttempts: 5 },
        {
          sendVia: (route) => {
            seen.push(route.label);
            return Promise.reject(tgError(403, "bot blocked by user"));
          },
        },
      ),
    ).rejects.toThrow("terminal");
    expect(seen).toEqual(["primary"]);
  });

  test("all routes exhausted → rejects with the last failure", async () => {
    await expect(
      sendWithFailover(
        [PRIMARY, BACKUP],
        "1",
        "hi",
        { maxAttempts: 1, baseMs: 1 },
        {
          sleep: () => Promise.resolve(),
          sendVia: () => Promise.reject(new Error("fetch failed")),
        },
      ),
    ).rejects.toThrow("exhausted after 1 attempt(s)");
  });

  test("unconfirmed accept on primary tries backup before reporting", async () => {
    const seen: string[] = [];
    const r = await sendWithFailover(
      [PRIMARY, BACKUP],
      "1",
      "hi",
      { maxAttempts: 1 },
      {
        sleep: () => Promise.resolve(),
        sendVia: (route) => {
          seen.push(`send:${route.label}`);
          return Promise.resolve(44);
        },
        verifyChatVia: (route) => {
          seen.push(`verify:${route.label}`);
          return route.label === "primary"
            ? Promise.reject(new Error("Forbidden: bot was kicked"))
            : Promise.resolve({});
        },
        confirm: true,
      },
    );
    expect(r.route).toBe("backup");
    expect(r.delivery).toBe("confirmed");
    expect(seen).toEqual(["send:primary", "verify:primary", "send:backup", "verify:backup"]);
  });

  test("unconfirmed on the LAST route reports unconfirmed, not throw", async () => {
    const r = await sendWithFailover(
      [PRIMARY],
      "1",
      "hi",
      { maxAttempts: 1 },
      {
        sleep: () => Promise.resolve(),
        sendVia: () => Promise.resolve(55),
        verifyChatVia: () => Promise.reject(new Error("chat not found")),
        confirm: true,
      },
    );
    expect(r.delivery).toBe("unconfirmed");
    expect(r.messageId).toBe(55);
  });
});
