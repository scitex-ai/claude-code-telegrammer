/**
 * PERMANENT SAFE-DEFAULT STUB — teardown-vs-restart distinction for the
 * standalone poller process. This function will likely NEVER need real
 * logic; see the RESOLUTION section below.
 *
 * Tracked in scitex-todo card cct-mcp-server-periodic-drop-20260712.
 *
 * Context (architecture fix, incident-cct-inbound-dies-silently-with-mcp-
 * server-20260711 follow-up, 2026-07): the getUpdates poller now runs as its
 * own standalone OS process (ts/telegram-poller.ts), spawned DETACHED
 * (stdio:"ignore", detached:true — lib/poller-supervisor.ts::
 * ensurePollerRunning), independent of the MCP server's lifecycle
 * (ts/telegram-server.ts) — see docs/architecture.md. That decoupling raised
 * an open question: when scitex-agent-container genuinely decommissions an
 * agent (not just restarts its MCP child), does anything reach this now-
 * detached process to tell it to exit?
 *
 * RESOLUTION (scitex-todo card cct-mcp-server-periodic-drop-20260712,
 * comment 2026-07-12T22:37:01Z, sac verified against their OWN source, not
 * memory):
 *
 *   - sac's stop path is single-PID SIGTERM everywhere (tmux kill-session /
 *     os.kill on the apptainer PID / listen-broker delete) — NO process-
 *     group kill anywhere. A detached+unref'd poller is NOT reached by that
 *     signal (this is the real gap the original open question worried about
 *     — confirmed real, not hypothetical).
 *   - BUT sac already ships the fix for exactly this, elsewhere: their own
 *     `_lifecycle/_orphan_mcp_cleanup.py::kill_orphan_mcp_children(name)` is
 *     a psutil scan (matches SAC_NAME/SCITEX_AGENT_CONTAINER_NAME env +a
 *     cmdline containing telegrammer/mcp/bun) whose docstring names THIS
 *     exact bug. It was wired only at pre-start (catches survivors on
 *     restart); sac is wiring the SAME reaper into agent_stop (their own
 *     tracked card) so it also fires on genuine decommission.
 *
 * NET RESULT: this repo needs ZERO listening/polling/signal-marker logic.
 * Teardown is entirely sac's reaper's job, contingent only on THIS
 * process (a) inheriting SAC_NAME/SCITEX_AGENT_CONTAINER_NAME env, and (b)
 * having a cmdline containing telegrammer/mcp/bun. Both are true BY
 * CONSTRUCTION and need no extra code here: (a) Bun.spawn with no `env`
 * override (lib/poller-supervisor.ts's default) inherits the parent's full
 * environment; (b) the spawn command is `<bun binary> run <repo path
 * containing "claude-code-telegrammer">/ts/telegram-poller.ts` — "bun" and
 * "telegrammer" both appear in the cmdline unconditionally. See
 * ts/test/poller-supervisor.test.ts for an explicit assertion of (a); (b)
 * follows from the fixed script path and needs no runtime check.
 *
 * This function therefore stays a PERMANENT safe-default stub: it always
 * resolves false (never self-terminate). It remains wired into
 * ts/telegram-poller.ts as a periodic, harmless no-op check (see that file)
 * so the extension point stays visible rather than becoming dead code, in
 * case a FUTURE sac change ever needs this repo to cooperate more actively
 * — but per the resolution above, that is not expected. Guessing at real
 * teardown-detection logic here (rather than trusting the verified
 * resolution above) is exactly what this stub — and the original task
 * constraint it was built under — exists to prevent.
 *
 * The poller's exit paths remain the existing, already-correct ones: a
 * plain process signal reaching it (SIGTERM/SIGINT — see
 * ts/telegram-poller.ts's shutdown()), sac's orphan reaper (external to
 * this repo, described above), or the newest-wins takeover protocol
 * noticing it has been preempted (lib/takeover.ts::isAuthoritative, checked
 * every poll-loop iteration in lib/poller.ts).
 */
export async function shouldSelfTerminateOnTeardown(): Promise<boolean> {
  return false;
}
