import { describe, expect, test } from "bun:test";
import { errnoCause, toolErrorResult } from "../lib/protocol-status.js";

describe("native errno protocol feedback", () => {
  test("preserves ENOSPC by name with detail and hint", () => {
    const err = Object.assign(new Error("no space left on device"), {
      code: "ENOSPC",
      errno: -28,
    });
    const result = toolErrorResult("reply", err);
    const check = JSON.parse(result.content[0].text);

    expect(result.isError).toBe(true);
    expect(check).toEqual({
      name: "reply_completed",
      ok: false,
      detail: "reply failed: no space left on device",
      hint: "Resolve the reported cause, then retry the same tool call.",
      cause: {
        kind: "errno",
        code: "ENOSPC",
        message: "no space left on device",
      },
    });
    expect(JSON.stringify(check)).not.toContain('"errno":-28');
  });

  test("finds a portable errno name on a nested runtime cause", () => {
    const err = Object.assign(new Error("fetch failed"), {
      cause: Object.assign(new Error("quota exceeded"), { code: "EDQUOT" }),
    });
    expect(errnoCause(err)?.code).toBe("EDQUOT");
  });

  test("preserves another generic errno without ENOSPC-specific code", () => {
    const err = Object.assign(new Error("permission denied"), {
      code: "EACCES",
      errno: -13,
    });
    expect(errnoCause(err)).toEqual({
      kind: "errno",
      code: "EACCES",
      message: "permission denied",
    });
  });
});
