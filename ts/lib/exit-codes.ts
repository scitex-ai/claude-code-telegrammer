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
