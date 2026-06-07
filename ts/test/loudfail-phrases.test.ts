/**
 * Loud-fail per-category COPY tests (#14 refinements, 2026-06-07).
 *
 * Pins the wire-format of every non-quota WakeFailCategory per lead's
 * msg ab8d86e4 review:
 *
 *   category            reason_phrase           retry_phrase
 *   ───────────────────────────────────────────────────────────────
 *   auth                "auth refresh needed"   "escalating to lead"
 *   connection_refused  "connection refused"    "retry in ~30s"
 *   timeout             "agent busy"            "retry shortly"
 *   server_error        "agent busy"            "retry shortly"
 *   client_error        "HTTP <status>"         "retry shortly"
 *   unknown             "<result.reason>"       "retry shortly"
 *
 * Quota-capped (the only branch with usage.json side effects) lives in
 * loudfail-quota.test.ts so the temp-fs setup stays isolated.
 */

import { describe, expect, test } from "bun:test";

import {
  buildLoudFailMessage,
  resolveFailPhrases,
  retrySuggestion,
} from "../lib/loudfail.js";
import type { WakeResult } from "../lib/wake.js";

describe("resolveFailPhrases: per-category copy (lead-pinned)", () => {
  test("auth → 'auth refresh needed' + 'escalating to lead'", () => {
    const r: WakeResult = {
      ok: false,
      status: 401,
      reason: "HTTP 401",
      category: "auth",
    };
    expect(resolveFailPhrases(r)).toEqual({
      reason: "auth refresh needed",
      retry: "escalating to lead",
    });
  });

  test("connection_refused → 'connection refused' + 'retry in ~30s'", () => {
    const r: WakeResult = {
      ok: false,
      reason: "connect ECONNREFUSED 127.0.0.1:9876",
      category: "connection_refused",
    };
    expect(resolveFailPhrases(r)).toEqual({
      reason: "connection refused",
      retry: "retry in ~30s",
    });
  });

  test("timeout → 'agent busy' + 'retry shortly'", () => {
    const r: WakeResult = {
      ok: false,
      reason: "network timeout",
      category: "timeout",
    };
    expect(resolveFailPhrases(r)).toEqual({
      reason: "agent busy",
      retry: "retry shortly",
    });
  });

  test("server_error → 'agent busy' + 'retry shortly' (same as timeout)", () => {
    const r: WakeResult = {
      ok: false,
      status: 502,
      reason: "HTTP 502",
      category: "server_error",
    };
    expect(resolveFailPhrases(r)).toEqual({
      reason: "agent busy",
      retry: "retry shortly",
    });
  });

  test("client_error w/status → 'HTTP <status>' + 'retry shortly'", () => {
    const r: WakeResult = {
      ok: false,
      status: 422,
      reason: "HTTP 422",
      category: "client_error",
    };
    expect(resolveFailPhrases(r)).toEqual({
      reason: "HTTP 422",
      retry: "retry shortly",
    });
  });

  test("client_error w/o status → fallback 'client error' reason", () => {
    const r: WakeResult = {
      ok: false,
      reason: "weird thing",
      category: "client_error",
    };
    expect(resolveFailPhrases(r)).toEqual({
      reason: "client error",
      retry: "retry shortly",
    });
  });

  test("unknown → preserves original reason verbatim + 'retry shortly'", () => {
    const r: WakeResult = {
      ok: false,
      reason: "DNS resolution failed",
      category: "unknown",
    };
    expect(resolveFailPhrases(r)).toEqual({
      reason: "DNS resolution failed",
      retry: "retry shortly",
    });
  });

  test("unknown w/empty reason → falls back to 'unknown error'", () => {
    const r: WakeResult = { ok: false, reason: "", category: "unknown" };
    expect(resolveFailPhrases(r)).toEqual({
      reason: "unknown error",
      retry: "retry shortly",
    });
  });
});

describe("retrySuggestion: back-compat thin wrapper", () => {
  test("auth → 'escalating to lead'", () =>
    expect(retrySuggestion("auth")).toBe("escalating to lead"));
  test("connection_refused → 'retry in ~30s'", () =>
    expect(retrySuggestion("connection_refused")).toBe("retry in ~30s"));
  test("timeout → 'retry shortly'", () =>
    expect(retrySuggestion("timeout")).toBe("retry shortly"));
  test("server_error → 'retry shortly'", () =>
    expect(retrySuggestion("server_error")).toBe("retry shortly"));
  test("client_error → 'retry shortly'", () =>
    expect(retrySuggestion("client_error")).toBe("retry shortly"));
  test("unknown → 'retry shortly'", () =>
    expect(retrySuggestion("unknown")).toBe("retry shortly"));
});

describe("buildLoudFailMessage: full wire format (non-quota cases)", () => {
  test("auth (401)", () => {
    const result: WakeResult = {
      ok: false,
      status: 401,
      reason: "HTTP 401",
      category: "auth",
    };
    expect(buildLoudFailMessage(result, "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: auth refresh needed — escalating to lead",
    );
  });

  test("connection_refused", () => {
    const result: WakeResult = {
      ok: false,
      reason: "connect ECONNREFUSED 127.0.0.1:9876",
      category: "connection_refused",
    };
    expect(buildLoudFailMessage(result, "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: connection refused — retry in ~30s",
    );
  });

  test("server_error (502)", () => {
    const result: WakeResult = {
      ok: false,
      status: 502,
      reason: "HTTP 502",
      category: "server_error",
    };
    expect(buildLoudFailMessage(result, "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: agent busy — retry shortly",
    );
  });

  test("timeout", () => {
    const result: WakeResult = {
      ok: false,
      reason: "network timeout",
      category: "timeout",
    };
    expect(buildLoudFailMessage(result, "proj-foo")).toBe(
      "⚠️ proj-foo unavailable: agent busy — retry shortly",
    );
  });

  test("uses AGENT_ID default when agentId is omitted (preload sets 'telegram')", () => {
    const result: WakeResult = {
      ok: false,
      status: 503,
      reason: "HTTP 503",
      category: "server_error",
    };
    expect(buildLoudFailMessage(result)).toBe(
      "⚠️ telegram unavailable: agent busy — retry shortly",
    );
  });
});
