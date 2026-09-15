/** Whether a lifecycle manager owns the standalone Telegram poller. */
export function externalPollerEnabled(value: string | undefined): boolean {
  return /^(?:1|true|yes|on)$/i.test(value?.trim() ?? "");
}
