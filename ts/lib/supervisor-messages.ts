/**
 * The text the OPERATOR reads when the poller exits.
 *
 * Extracted from poller-supervisor.ts because these strings are a
 * responsibility of their own, and because they were wrong. On 2026-07-17 the
 * operator sent a screenshot and asked whether these messages were even correct
 * (「…あってるんですかね」). They were not:
 *
 *   19:34  "INGESTION STALL … SELF-HEALING … no human action needed"
 *   19:34  "exited with code 75 … inbound Telegram delivery is DOWN."
 *
 * One event. Two messages. Opposite meanings. And the second one was false —
 * he could see for himself that messages were still arriving:
 * 「そのメッセージがあっても普通に届きますからね」.
 *
 * THE RULE THIS FILE EXISTS TO ENFORCE — say DOWN only when it is DOWN.
 * This is the alarm channel. Its one unrecoverable failure mode is the operator
 * muting it, and he has already said twice that he does not want to read these.
 * A false alarm here is not noise; it is the destruction of the only rail a
 * real outage has. poller-supervisor.ts already knew this — "a false alarm here
 * is what teaches people to ignore the alarm that matters" — and then said DOWN
 * about a restart it was fixing three lines later.
 *
 * Three exits, three volumes:
 *   planned  (STALL_EXIT_CODE) → log only. The watchdog already spoke.
 *   crash    (anything else)   → brief. Unexpected, but it IS self-healing.
 *   fatal    (respawns gone)   → loud. Now it really is down.
 */

/** Respawns remaining, planned stall recovery: the LOG's business only. */
export function plannedRestartNote(pid: number, lived: string): string {
  return (
    `poller (pid ${pid}) self-terminated after ${lived} for a planned stall ` +
    `restart — respawning. Not paging the operator: the stall watchdog already ` +
    `told them it is recovering by itself.`
  );
}

/**
 * An UNEXPECTED exit that the supervisor is about to fix.
 *
 * Worth telling him — an unexplained crash is a real signal — but not worth
 * the word DOWN: the respawn happens in the same function, so the actual gap
 * is about a second. Keep it to what he'd act on.
 */
export function crashAlarm(
  pid: number,
  code: number | null,
  lived: string,
  attempt: number,
  maxRespawns: number,
): string {
  return (
    `Poller stopped unexpectedly — restarting it (${attempt}/${maxRespawns}).\n` +
    `1. It exited with code ${code} after ${lived}.\n` +
    `2. Inbound should recover within seconds.\n` +
    `3. You will hear from me again ONLY if it does not.`
  );
}

/**
 * Respawns exhausted. This one is TRUE, and it must stay loud — it is the
 * message every other message in this file exists to protect.
 */
export function fatalAlarm(
  pid: number,
  code: number | null,
  lived: string,
  respawns: number,
): string {
  return (
    `TELEGRAM IS DOWN — this one needs you.\n` +
    `1. The poller died ${respawns} times in a row and I have stopped retrying.\n` +
    `2. Inbound messages are NOT arriving and will not recover on their own.\n` +
    `3. Restart the MCP server.\n` +
    `4. Last exit: code ${code} after ${lived} (pid ${pid}); details in the poller log.`
  );
}
