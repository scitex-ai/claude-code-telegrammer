#!/usr/bin/env bun
/**
 * Host-level gateway supervisor — owns ONE poller for ONE bot (the LEAD
 * slot) OUTSIDE any agent lifecycle.
 *
 * WHY THIS EXISTS (plan cct-standalone-supervision, 2026-10-09): the
 * poller is today a child of agent boot (`hermes_tui.start()` →
 * `start_cct_poller()`; `stop()` SIGTERMs it) — zero agents up means zero
 * pollers, by construction, and the outage alarm itself routes through the
 * dead lead, so a lead-down outage is silent on every rail that matters.
 * This supervisor runs as `cct-gateway.service` (systemd user unit on the
 * gateway host) and is outside apptainer and outside `sac agents
 * start/stop`. SAC never starts, stops, or restarts it; SAC only observes
 * it (status file below).
 *
 * What it does:
 *   1. Resolves the gateway token via lib/gateway-resolve.ts (direct
 *      `CCT_BOT_TOKEN` with config.ts precedence, else the `LEAD` pool
 *      slot from the environment / `SAC_SECRETS_ENVRC` files). Only slot
 *      NAMES and pool PATHS are ever logged — never values; rotations are
 *      compared by fingerprint.
 *   2. Injects a pool-resolved token as `CCT_BOT_TOKEN` (short form wins;
 *      injected ONLY when no direct spelling is set, so it can never
 *      conflict) and spawns `ts/telegram-poller.ts` DETACHED with
 *      stderr appended to the poller log — the same spawn shape
 *      lib/poller-supervisor.ts `defaultSpawn` uses, so the orphan reaper
 *      and log conventions keep matching.
 *   3. Single-poller enforcement stays with lib/takeover.ts newest-wins:
 *      the poller claims the per-token pidfile inside `startPolling()`, so
 *      spawning here preempts (never duplicates) any stray agent-booted
 *      poller for the same token. This supervisor only OBSERVES the claim
 *      (pid + liveness) for the status file.
 *   4. Restart policy reuses the shared exit-code contract
 *      (lib/exit-codes.ts) and the operator-copy helpers
 *      (lib/supervisor-messages.ts):
 *        STALL_EXIT_CODE (75) → planned stall self-heal: log only
 *          (the watchdog already spoke), fast respawn, no page.
 *        SIGTERM/SIGINT (143/130) → deliberate stop: stand down, exit 0.
 *        anything else → crash: page once via lib/loudfail.ts
 *          `broadcastSystemAlert`, back off (lib/gateway-resolve.ts
 *          `backoffForAttempt`), respawn. Respawns are BOUNDED (same 5 as
 *          the MCP-side supervisor — a poller that crashes on every start
 *          must not fork-bomb); exhaustion pages the fatal alarm and exits
 *          non-zero so systemd (`Restart=on-failure`) becomes the outer
 *          loop with a fresh counter.
 *   5. Re-resolves on an interval and on SIGHUP; on a fingerprint change
 *      it hot-rotates (SIGTERM the old child, spawn a successor carrying
 *      the new env). LIMITATION, stated plainly: this process's own
 *      already-imported `config.ts`/`loudfail.ts` bindings keep the OLD
 *      token (module state is fixed at import), so supervisor-emitted
 *      Telegram alarms during rotation turbulence still go out on the old
 *      bot. The NEW poller resolves everything fresh from its env, which
 *      is what carries inbound delivery.
 *   6. Writes `gateway-status.json` into the agent state dir after every
 *      transition — the file SAC's doctor / `cct-audit` read. Invalid or
 *      revoked token → the POLLER fails loud itself (its own startup
 *      guards); the supervisor never runs degraded-silently: no token at
 *      all means a loud log + exit 1 (systemd retries), never a fake-ok.
 *
 * Config-dependent modules (config, loudfail, poll-watchdog) are
 * DYNAMICALLY imported AFTER the token is resolved+injected, because their
 * bindings (`TOKEN`, `BOT_TOKEN_HASH`, alert sender) fix at import time.
 */

import { openSync, closeSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { log } from "./lib/log.js";
import { STALL_EXIT_CODE, SIGTERM_EXIT } from "./lib/exit-codes.js";
import {
  plannedRestartNote,
  standDownNote,
  crashAlarm,
  fatalAlarm,
} from "./lib/supervisor-messages.js";
import { pollerLogPath } from "./lib/poller-paths.js";
import {
  pollerPidfilePath,
  readPidfile,
  isProcessMatching,
} from "./lib/takeover.js";
import {
  resolveGatewayToken,
  resolveSecretFiles,
  tokenFingerprint,
  backoffForAttempt,
  DEFAULT_SLOT,
} from "./lib/gateway-resolve.js";
import type { GatewayTokenResolution } from "./lib/gateway-resolve.js";

const SELF = "gateway-supervisor";
/** Same bound as the MCP-side supervisor: a poller that crashes on every
 * start must page, not fork-bomb. Exhaustion exits non-zero; systemd is the
 * outer loop. */
const MAX_RESPAWNS = 5;
/** Token re-resolution cadence (rotation pickup without a restart). */
const RESOLVE_INTERVAL_MS = 5 * 60 * 1000;
const SIGINT_EXIT = 130; // 128 + 2, mirroring lib/exit-codes.ts convention

const THIS_DIR = dirname(fileURLToPath(import.meta.url));
const POLLER_SCRIPT = join(THIS_DIR, "telegram-poller.ts");

interface Status {
  updated_at: string;
  state: string;
  supervisor_pid: number;
  poller_pid: number | null;
  poller_started_at: string | null;
  token_fp: string;
  slot: string;
  source: string;
  pool_paths: string[];
  claim_pid: number | null;
  claim_live: boolean;
  restarts: number;
  last_exit: number | null;
  stall_threshold_ms: number | null;
}

let statusPath = "";
let status: Status | null = null;
let stallThresholdMs: number | null = null;
let broadcastAlert: ((text: string) => Promise<void>) | null = null;

function writeStatus(patch: Partial<Status>): void {
  if (!statusPath || !status) return;
  status = { ...status, ...patch, updated_at: new Date().toISOString() };
  try {
    void Bun.write(statusPath, JSON.stringify(status, null, 2) + "\n");
  } catch (err) {
    // A status write must never kill supervision — degraded observability
    // beats no inbound delivery (same posture as the spawn log-fd below).
    log(SELF, "WARNING: failed to write status file", {
      level: "warning",
      path: statusPath,
      error: String(err),
    });
  }
}

/** Per-token pidfile claim observation (names/pids only — no values). */
function readClaim(stateDir: string, tokenHash: string): void {
  let claimPid: number | null = null;
  let claimLive = false;
  try {
    const snap = readPidfile(pollerPidfilePath(stateDir, tokenHash));
    if (snap) {
      claimPid = snap.pid;
      claimLive = isProcessMatching(snap.pid, POLLER_SCRIPT);
    }
  } catch {
    // Best-effort observability only; the takeover protocol itself lives in
    // the poller and needs nothing from here.
  }
  writeStatus({ claim_pid: claimPid, claim_live: claimLive });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function usage(): string {
  return (
    "usage: cct-gateway [--help] | [status]\n" +
    "\n" +
    "Host-level CCT gateway supervisor: resolves the LEAD-slot bot token\n" +
    "(CCT_BOT_TOKEN precedence per ts/lib/config.ts, else CCT_BOT_TOKEN_<SLOT>\n" +
    "from the environment / SAC_SECRETS_ENVRC pool files) and owns one\n" +
    "detached ts/telegram-poller.ts for it, restarting on crash with backoff.\n" +
    "Normally run as cct-gateway.service, not by hand.\n" +
    "\n" +
    "  (no args)  supervise the gateway poller (foreground; systemd owns restarts)\n" +
    "  status     print gateway-status.json and exit\n" +
    "  --help     this text\n"
  );
}

async function main(): Promise<number> {
  const args = process.argv.slice(2);
  if (args.includes("--help") || args.includes("-h")) {
    process.stdout.write(usage());
    return 0;
  }

  // ── Resolve the gateway token (names/paths only in logs) ─────────────
  let resolved: GatewayTokenResolution | null = null;
  try {
    resolved = resolveGatewayToken();
  } catch (err) {
    process.stderr.write(
      `${SELF}: FATAL refusing to start — ${(err as Error).message}\n`,
    );
    return 1;
  }
  if (!resolved) {
    const poolPaths = resolveSecretFiles();
    process.stderr.write(
      `${SELF}: FATAL no gateway token resolves — ` +
        `CCT_BOT_TOKEN is empty and pool slot CCT_BOT_TOKEN_${DEFAULT_SLOT} ` +
        `is absent from the environment and from ` +
        `${poolPaths.length > 0 ? poolPaths.join(", ") : "(no secret files resolved)"}. ` +
        `Refusing to run degraded; not starting a poller.\n`,
    );
    return 1;
  }
  if (resolved.source !== "direct") {
    // Pool-resolved: inject as the short form so the whole downstream
    // module graph (config TOKEN, poller child env) resolves it with
    // config.ts precedence. Injected ONLY when no direct spelling is set
    // (resolveGatewayToken returns pool sources only then), so this can
    // never alias-conflict.
    process.env["CCT_BOT_TOKEN"] = resolved.token;
  }
  const tokenFp = tokenFingerprint(resolved.token);

  // ── Config-dependent imports AFTER the token is fixed ─────────────────
  const { STATE_DIR, BOT_TOKEN_HASH } = await import("./lib/config.js");
  const loudfail = await import("./lib/loudfail.js");
  broadcastAlert = (text: string) => loudfail.broadcastSystemAlert(text);
  try {
    // Reuse the watchdog's own threshold (lib/poll-watchdog.ts) for the
    // status file so the observed cadence and the reported one cannot
    // drift. Best-effort: a failure here must not stop supervision.
    const watchdog = await import("./lib/poll-watchdog.js");
    stallThresholdMs =
      watchdog.resolveStallThresholdMs?.() ?? stallThresholdMs;
  } catch {
    stallThresholdMs = null;
  }

  statusPath = join(STATE_DIR, "gateway-status.json");
  status = {
    updated_at: new Date().toISOString(),
    state: "starting",
    supervisor_pid: process.pid,
    poller_pid: null,
    poller_started_at: null,
    token_fp: tokenFp,
    slot: resolved.slot || DEFAULT_SLOT,
    source: resolved.source,
    pool_paths: resolved.poolPaths,
    claim_pid: null,
    claim_live: false,
    restarts: 0,
    last_exit: null,
    stall_threshold_ms: stallThresholdMs,
  };
  writeStatus({});

  if (args[0] === "status") {
    process.stdout.write(JSON.stringify(status, null, 2) + "\n");
    return 0;
  }

  log(SELF, "gateway supervisor starting", {
    slot: status.slot,
    source: status.source,
    token_fp: tokenFp,
    pool_paths: resolved.poolPaths,
    state_dir: STATE_DIR,
  });

  // A live claim at startup is normally a stray agent-booted poller for the
  // same token. Logged, not fought: our first spawn's claimAuthoritative()
  // preempts it via newest-wins and it stands down on its next tick.
  readClaim(STATE_DIR, BOT_TOKEN_HASH);
  if (status.claim_pid && status.claim_live) {
    log(SELF, "pre-existing live poller claim — first spawn will preempt it", {
      claim_pid: status.claim_pid,
    });
  }

  // ── Supervision loop ──────────────────────────────────────────────────
  let child: ReturnType<typeof Bun.spawn> | null = null;
  let restarts = 0;
  let rotating = false;
  let hupRequested = false;
  let lastResolveMs = Date.now();
  process.on("SIGHUP", () => {
    hupRequested = true;
  });

  const forwardSignal = (sig: "SIGTERM" | "SIGINT"): void => {
    log(SELF, `received ${sig} — forwarding to poller and exiting`, {});
    try {
      child?.kill(sig);
    } catch {
      // Best-effort; the poller also stands down via takeover release.
    }
    // The timer must keep the loop alive until it fires (we still exit even
    // if the child ignores the signal), so it is deliberately NOT unref'd.
    setTimeout(
      () => process.exit(sig === "SIGTERM" ? SIGTERM_EXIT : SIGINT_EXIT),
      2500,
    );
  };
  process.on("SIGTERM", () => forwardSignal("SIGTERM"));
  process.on("SIGINT", () => forwardSignal("SIGINT"));

  const resolveTimer = setInterval(() => {
    void maybeReresolve();
  }, 60_000);

  async function maybeReresolve(): Promise<void> {
    const due =
      hupRequested || Date.now() - lastResolveMs >= RESOLVE_INTERVAL_MS;
    if (!due) return;
    hupRequested = false;
    lastResolveMs = Date.now();
    let next: GatewayTokenResolution | null = null;
    try {
      next = resolveGatewayToken();
    } catch (err) {
      log(SELF, "re-resolution failed — keeping current token", {
        level: "warning",
        error: String(err),
      });
      return;
    }
    if (!next) {
      log(SELF, "re-resolution found no token — keeping current poller", {
        level: "warning",
        slot: status?.slot,
      });
      return;
    }
    if (tokenFingerprint(next.token) === status?.token_fp) return;
    // Rotation: retire the old child, then respawn carrying the new env.
    log(SELF, "token fingerprint changed — hot-rotating the poller", {
      slot: next.slot || DEFAULT_SLOT,
      source: next.source,
    });
    rotating = true;
    process.env["CCT_BOT_TOKEN"] = next.token;
    try {
      child?.kill("SIGTERM");
      const exited = child?.exited;
      if (exited) await Promise.race([exited, sleep(10_000)]);
    } catch {
      // The exit-path below respawns regardless.
    }
    writeStatus({
      token_fp: tokenFingerprint(next.token),
      slot: next.slot || DEFAULT_SLOT,
      source: next.source,
      pool_paths: next.poolPaths,
    });
  }

  function spawnPoller(): ReturnType<typeof Bun.spawn> | null {
    // Same shape as lib/poller-supervisor.ts defaultSpawn: detached so the
    // poller survives OUR restarts, stderr appended to the per-token log so
    // a dead poller can still say why it died, env explicit.
    let stderr: "ignore" | number = "ignore";
    let logFd = -1;
    try {
      logFd = openSync(pollerLogPath(STATE_DIR, BOT_TOKEN_HASH), "a");
      stderr = logFd;
    } catch {
      stderr = "ignore";
    }
    try {
      const proc = Bun.spawn([process.execPath, "run", POLLER_SCRIPT], {
        stdio: ["ignore", "ignore", stderr],
        detached: true,
        env: process.env,
      });
      proc.unref();
      return proc;
    } catch (err) {
      const msg =
        `FATAL: failed to spawn the gateway poller (${POLLER_SCRIPT}): ` +
        `${(err as Error).message} — inbound Telegram delivery is NOT running.`;
      log(SELF, msg);
      void broadcastAlert?.(msg);
      return null;
    } finally {
      if (logFd >= 0) {
        try {
          closeSync(logFd);
        } catch {
          // The child holds its own dup; a close failure here changes nothing.
        }
      }
    }
  }

  // NOTE on the fd above: openSync gives the CHILD its stderr; closing our
  // copy after spawn is correct (the dup stays open in the child). An
  // unwritable log path degrades to "ignore" rather than blocking startup.

  for (;;) {
    await maybeReresolve();
    child = spawnPoller();
    if (!child) {
      await sleep(backoffForAttempt(restarts + 1));
      restarts += 1;
      if (restarts > MAX_RESPAWNS) {
        const msg = fatalAlarm(process.pid, null, "0s", restarts);
        log(SELF, msg);
        await broadcastAlert?.(msg);
        writeStatus({ state: "fatal", last_exit: null, restarts });
        clearInterval(resolveTimer);
        return 1;
      }
      continue;
    }
    const startMs = Date.now();
    const startedAt = new Date(startMs).toISOString();
    writeStatus({
      state: "running",
      poller_pid: child.pid,
      poller_started_at: startedAt,
    });
    readClaim(STATE_DIR, BOT_TOKEN_HASH);
    log(SELF, "spawned gateway poller", { pid: child.pid });

    const code: number = await child.exited;
    child = null;
    const lived = `${((Date.now() - startMs) / 1000).toFixed(1)}s`;
    writeStatus({ poller_pid: null, last_exit: code });
    readClaim(STATE_DIR, BOT_TOKEN_HASH);

    if (rotating) {
      // Our own hot-rotation SIGTERM, not a death: respawn immediately with
      // the already-updated env, without burning a restart or paging.
      rotating = false;
      log(SELF, "rotation retire complete — respawning with new token", {});
      restarts = 0;
      continue;
    }

    if (code === STALL_EXIT_CODE) {
      // Planned stall self-heal (lib/poll-watchdog.ts contract): the
      // watchdog already told the operator; log only, fast respawn.
      log(SELF, plannedRestartNote(process.pid, `exit ${code}`));
      restarts = 0;
      await sleep(1000);
      continue;
    }

    if (code === SIGTERM_EXIT || code === SIGINT_EXIT) {
      // Deliberate external stop with nobody taking over: stay dead.
      // (Our own rotation SIGTERM is handled by the `rotating` branch
      // above and never reaches here.)
      log(SELF, standDownNote(process.pid, `exit ${code}`));
      writeStatus({ state: "standing-down" });
      clearInterval(resolveTimer);
      return 0;
    }

    restarts += 1;
    if (restarts > MAX_RESPAWNS) {
      const msg = fatalAlarm(process.pid, code, lived, restarts);
      log(SELF, msg);
      await broadcastAlert?.(msg);
      writeStatus({ state: "fatal", restarts });
      clearInterval(resolveTimer);
      return 1;
    }
    const waitMs = backoffForAttempt(restarts);
    const msg = crashAlarm(process.pid, code, lived, restarts, MAX_RESPAWNS);
    log(SELF, msg, { backoff_ms: waitMs });
    await broadcastAlert?.(msg);
    writeStatus({ state: "running", restarts });
    await sleep(waitMs);
  }
}

if (import.meta.main) {
  void main().then(
    (code) => process.exit(code),
    (err) => {
      process.stderr.write(`${SELF}: FATAL unhandled error: ${String(err?.stack ?? err)}\n`);
      process.exit(1);
    },
  );
}
