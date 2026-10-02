/** Process evidence for health only; never used to grant poller authority. */
import { readFileSync } from "fs";
import { matchesAgentIdentity } from "./takeover.js";

/**
 * A pidfile can contain a HOST pid which is invisible in an MCP container's
 * PID namespace. ESRCH there proves absence only in the observer's namespace,
 * not death of the recorded poller. Unreadable identity is likewise unknown.
 * Keep takeover's fail-closed boolean separate from this three-valued report.
 */
export function observeHealthProcess(
  pid: number,
  marker: string,
  expectedAgentId: string,
): boolean | null {
  try {
    process.kill(pid, 0);
  } catch (err) {
    if ((err as NodeJS.ErrnoException | undefined)?.code !== "EPERM") {
      return null;
    }
  }
  let cmdline: string;
  try {
    cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf8");
  } catch {
    return null;
  }
  // A process racing exec/exit has no inspectable identity yet.
  if (!cmdline) return null;
  if (!cmdline.includes(marker)) return false;
  if (!expectedAgentId) return true;
  try {
    return matchesAgentIdentity(
      expectedAgentId,
      readFileSync(`/proc/${pid}/environ`, "utf8"),
    );
  } catch {
    return null;
  }
}
