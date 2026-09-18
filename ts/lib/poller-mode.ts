/** Whether a lifecycle manager owns the standalone Telegram poller. */
export function externalPollerEnabled(value: string | undefined): boolean {
  return /^(?:1|true|yes|on)$/i.test(value?.trim() ?? "");
}

/** Whether this MCP process, rather than the declared lifecycle owner, polls. */
export function shouldStartInternalPoller(
  telegramEnabled: boolean,
  externalPoller: boolean,
): boolean {
  return telegramEnabled && !externalPoller;
}
