/** SciTeX status-protocol adapters for native operating-system failures. */

export interface NativeStatusCode {
  kind: "errno";
  code: string;
  message: string;
}

export interface ProtocolCheck {
  name: string;
  ok: false;
  detail: string;
  hint: string;
  cause?: NativeStatusCode;
}

/**
 * Preserve a native errno NAME at a process/protocol boundary.
 *
 * Node and Bun put the portable name in `error.code`; nested fetch/database
 * errors commonly put it on `error.cause.code`.  Never send the numeric
 * `errno`: its meaning is platform-local.
 */
export function errnoCause(err: unknown): NativeStatusCode | undefined {
  let current: unknown = err;
  const seen = new Set<unknown>();
  for (let depth = 0; current != null && depth < 4; depth++) {
    if (seen.has(current)) break;
    seen.add(current);
    const value = current as { code?: unknown; cause?: unknown; message?: unknown };
    if (typeof value.code === "string" && /^E[A-Z0-9]+$/.test(value.code)) {
      const message =
        typeof value.message === "string" && value.message.trim()
          ? value.message
          : String(err);
      return { kind: "errno", code: value.code, message };
    }
    current = value.cause;
  }
  return undefined;
}

export function errorDetail(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export function failingCheck(
  name: string,
  detail: string,
  hint: string,
  err?: unknown,
): ProtocolCheck {
  const cause = err === undefined ? undefined : errnoCause(err);
  return { name, ok: false, detail, hint, ...(cause ? { cause } : {}) };
}

/** MCP error content: structured, actionable, and still readable as text. */
export function toolErrorResult(
  tool: string,
  err: unknown,
  detail?: string,
  hint = "Resolve the reported cause, then retry the same tool call.",
) {
  const check = failingCheck(
    `${tool}_completed`,
    detail ?? `${tool} failed: ${errorDetail(err)}`,
    hint,
    err,
  );
  return {
    content: [{ type: "text" as const, text: JSON.stringify(check) }],
    isError: true,
  };
}

