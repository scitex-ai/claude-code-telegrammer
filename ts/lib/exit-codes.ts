/**
 * Poller exit codes shared between the two processes.
 *
 * These live in their own leaf module because the PRODUCER (the stall watchdog,
 * running inside the standalone poller) and the CONSUMER (the supervisor,
 * running inside the MCP server) are in different processes and must agree on
 * the number. A private copy on each side is a silent drift waiting to happen —
 * and the whole bug this module was extracted for was the two sides NOT
 * agreeing: poll-watchdog picked 75 specifically so a self-terminate could be
 * told apart from a crash, and the supervisor never read it.
 */

/**
 * EX_TEMPFAIL — "transient failure, please retry".
 *
 * The stall watchdog exits with this to ASK THE SUPERVISOR FOR A RESPAWN. It
 * means "I am deliberately standing down so you can restart me", NOT "I died".
 * The supervisor MUST treat it as a planned restart: respawn without paging the
 * operator, because the watchdog has already told them it is self-healing.
 */
export const STALL_EXIT_CODE = 75;

/**
 * Exit codes a process killed BY a signal surfaces as: POSIX shells and Bun's
 * `child.exited` both report 128 + signum. Measured on Bun 1.3.11 (SIGTERM ->
 * 143, SIGKILL -> 137); `child.signalCode` also names the signal, but the
 * supervisor only has the numeric code from `SpawnedProcessHandle.exited`, so it
 * branches on these.
 *
 * SIGTERM (143) is sac's DELIBERATE-STOP signal (contract confirmed with sac,
 * 2026-07-18): `agents stop`, the stop-half of `agents start --force`, and the
 * reaper all send SIGTERM, and it MEANS "stay dead" — sac owns the restart. The
 * supervisor stands down on it (no respawn, no page); respawning would fight the
 * terminator and, against a reaper, loop.
 *
 * SIGKILL (137) is NOT a deliberate stand-down signal: it is what an OOM-killer
 * sends, and what sac escalates to only when a process IGNORES SIGTERM. It is
 * involuntary, so the supervisor treats it as a crash — respawn + a brief page.
 */
export const SIGTERM_EXIT = 143; // 128 + 15 (SIGTERM)
export const SIGKILL_EXIT = 137; // 128 + 9  (SIGKILL) — documented; falls through to the crash path
