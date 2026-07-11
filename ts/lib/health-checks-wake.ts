/**
 * Health check ("doctor") — the two wake-delivery check builders (11 + 12
 * of the twelve total; see lib/health-checks.ts for the other ten). Split
 * into their own file because health-checks.ts was already near the repo's
 * 512-line cap.
 *
 * poller_alive proves the getUpdates FETCH loop lives; it says nothing
 * about whether the WAKE POST to the agent's own /v1/turn actually lands.
 * A dead turn-bridge (nothing listening on the configured TURN_URL) makes
 * every wake fail while poller_alive stays green — the exact gap that let
 * an outage go undetected while the doctor reported every other check ok
 * (incident incident-cct-inbound-dies-silently-with-mcp-server-20260711).
 * These two checks close it: one probes reachability live, the other
 * exposes the durable backlog signal so a health check run AFTER the fact
 * can still see it, even if the operator missed the per-message loud-fail
 * reply (lib/loudfail.ts).
 */

import type { WakeReachabilityProbe } from "./health.js";
import type { WakeFailureState } from "./wake-health.js";
import { type CheckOutcome } from "./health-checks.js";

/**
 * Detail for checks skipped because wake is disabled (no TURN_URL) — a
 * gate independent of bot_token_present's "telegram disabled (no token)"
 * skip, so it needs its own accurate wording rather than reusing that
 * message for a different reason.
 */
export const SKIPPED_WAKE_DISABLED_DETAIL =
  "skipped: wake disabled (no CCT_TURN_URL) — interactive-CLI mode, not a token/telegram issue";

function skippedWakeDisabled(name: string): CheckOutcome {
  return {
    entry: {
      name,
      ok: true,
      detail: SKIPPED_WAKE_DISABLED_DETAIL,
      hint: null,
    },
    warn: false,
  };
}

/** 11. wake_target_reachable — TCP-probes the configured wake target. */
export function checkWakeTargetReachable(
  probe: WakeReachabilityProbe,
): CheckOutcome {
  if (probe.kind === "disabled") return skippedWakeDisabled("wake_target_reachable");
  if (probe.kind === "invalid_url") {
    return {
      entry: {
        name: "wake_target_reachable",
        ok: false,
        detail: `configured wake target is not a valid URL (${probe.url}): ${probe.detail}`,
        hint:
          "fix CCT_TURN_URL (a.k.a. CLAUDE_CODE_TELEGRAMMER_TURN_URL) — it " +
          "must be a full http(s) URL naming the agent's own /v1/turn.",
      },
      warn: false,
    };
  }
  if (probe.kind === "unreachable") {
    return {
      entry: {
        name: "wake_target_reachable",
        ok: false,
        detail: `nothing is listening on ${probe.host}:${probe.port} (the configured wake target): ${probe.detail}`,
        hint:
          `the agent's own turn-bridge is down — restart it (e.g. ` +
          `\`sac agent restart <agent>\`) so ${probe.host}:${probe.port} ` +
          "accepts connections again. Until then every inbound message's " +
          "wake POST will fail silently to the naked eye — see " +
          "wake_delivery_backlog for how many already have.",
      },
      warn: false,
    };
  }
  return {
    entry: {
      name: "wake_target_reachable",
      ok: true,
      detail: `${probe.host}:${probe.port} accepts connections`,
      hint: null,
    },
    warn: false,
  };
}

/**
 * 12. wake_delivery_backlog — consecutive wake failures since the last
 * success. The durable signal a health check run AFTER the fact can still
 * see: even if the operator missed the per-message loud-fail reply, this
 * check makes it impossible for the doctor to report ok while messages
 * sit accepted-but-never-delivered.
 */
export function checkWakeDeliveryBacklog(
  state: WakeFailureState | null,
): CheckOutcome {
  if (state === null) return skippedWakeDisabled("wake_delivery_backlog");
  if (state.count === 0) {
    return {
      entry: {
        name: "wake_delivery_backlog",
        ok: true,
        detail: "no undelivered messages — the last wake attempt succeeded",
        hint: null,
      },
      warn: false,
    };
  }
  const since =
    state.lastAtMs !== null ? new Date(state.lastAtMs).toISOString() : "unknown";
  return {
    entry: {
      name: "wake_delivery_backlog",
      ok: false,
      detail:
        `${state.count} consecutive wake failure(s) since ${since} ` +
        `(most recent: ${state.lastCategory ?? "unknown"} — ` +
        `${state.lastReason ?? "no detail"}). Every one of these inbound ` +
        "messages was accepted by the bridge but never reached the agent.",
      hint:
        "check wake_target_reachable for the likely cause. The operator " +
        "already received a per-message loud-fail reply for each of these, " +
        "but this is the signal a health check run afterwards can still see.",
    },
    warn: false,
  };
}
