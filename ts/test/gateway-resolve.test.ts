/**
 * Tests for the gateway token/slot self-resolution (lib/gateway-resolve.ts).
 *
 * resolveGatewayToken() accepts an injected `env` object plus injected file
 * seams, so these tests pass fake environments directly — no process.env
 * mutation, no disk access. The token VALUE is only ever compared, never
 * logged; these tests assert fingerprints compare equal for equal tokens.
 */

import { describe, test, expect } from "bun:test";
import {
  backoffForAttempt,
  DEFAULT_SLOT,
  parseEnvFile,
  resolveGatewayToken,
  resolveSecretFiles,
  tokenFingerprint,
} from "../lib/gateway-resolve.js";
import type { FileReader, DirLister } from "../lib/gateway-resolve.js";

const nullReader: FileReader = () => null;
const emptyLister: DirLister = () => [];

describe("resolveGatewayToken: direct token (config.ts precedence)", () => {
  test("reads the short CCT_BOT_TOKEN form", () => {
    const r = resolveGatewayToken(
      { CCT_BOT_TOKEN: "direct-short" },
      nullReader,
      emptyLister,
    );
    expect(r?.token).toBe("direct-short");
    expect(r?.source).toBe("direct");
    expect(r?.slot).toBe("");
  });

  test("reads the canonical CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN form", () => {
    const r = resolveGatewayToken(
      { CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "direct-canon" },
      nullReader,
      emptyLister,
    );
    expect(r?.token).toBe("direct-canon");
    expect(r?.source).toBe("direct");
  });

  test("direct token beats a pool slot value", () => {
    const r = resolveGatewayToken(
      {
        CCT_BOT_TOKEN: "direct-wins",
        [`CCT_BOT_TOKEN_${DEFAULT_SLOT}`]: "pool-loses",
      },
      nullReader,
      emptyLister,
    );
    expect(r?.token).toBe("direct-wins");
    expect(r?.source).toBe("direct");
  });

  test("an empty short form does not shadow a real canonical value", () => {
    const r = resolveGatewayToken(
      {
        CCT_BOT_TOKEN: "",
        CLAUDE_CODE_TELEGRAMMER_BOT_TOKEN: "canon",
      },
      nullReader,
      emptyLister,
    );
    expect(r?.token).toBe("canon");
    expect(r?.source).toBe("direct");
  });
});

describe("resolveGatewayToken: pool slot", () => {
  test("defaults to the LEAD slot from the environment", () => {
    const r = resolveGatewayToken(
      { CCT_BOT_TOKEN_LEAD: "pool-lead-token" },
      nullReader,
      emptyLister,
    );
    expect(r?.token).toBe("pool-lead-token");
    expect(r?.slot).toBe("LEAD");
    expect(r?.source).toBe("pool-env");
  });

  test("honours an explicit CCT_BOT_TOKEN_SLOT", () => {
    const r = resolveGatewayToken(
      { CCT_BOT_TOKEN_SLOT: "cards", CCT_BOT_TOKEN_CARDS: "pool-cards" },
      nullReader,
      emptyLister,
    );
    expect(r?.token).toBe("pool-cards");
    expect(r?.slot).toBe("CARDS");
    expect(r?.source).toBe("pool-env");
  });

  test("reads the slot from a SAC_SECRETS_ENVRC pool file", () => {
    const files: Record<string, string> = {
      "/secrets/pool.src": "# comment\n\nCCT_BOT_TOKEN_LEAD=file-lead-token\nOTHER=1\n",
    };
    const reader: FileReader = (p) => files[p] ?? null;
    const r = resolveGatewayToken(
      { SAC_SECRETS_ENVRC: "/secrets/pool.src" },
      reader,
      emptyLister,
    );
    expect(r?.token).toBe("file-lead-token");
    expect(r?.slot).toBe("LEAD");
    expect(r?.source).toBe("pool-file");
    expect(r?.poolPaths).toEqual(["/secrets/pool.src"]);
    expect(r?.poolTrusted).toBe(true);
  });

  test("env pool value beats the pool file (same key, no conflict)", () => {
    const files: Record<string, string> = {
      "/secrets/pool.src": "CCT_BOT_TOKEN_LEAD=file-token\n",
    };
    const reader: FileReader = (p) => files[p] ?? null;
    const r = resolveGatewayToken(
      {
        SAC_SECRETS_ENVRC: "/secrets/pool.src",
        CCT_BOT_TOKEN_LEAD: "env-token",
      },
      reader,
      emptyLister,
    );
    expect(r?.token).toBe("env-token");
    expect(r?.source).toBe("pool-env");
  });

  test("returns null when nothing resolves", () => {
    expect(resolveGatewayToken({}, nullReader, emptyLister)).toBeNull();
    expect(
      resolveGatewayToken(
        { SAC_SECRETS_ENVRC: "/missing.src" },
        nullReader,
        emptyLister,
      ),
    ).toBeNull();
  });
});

describe("resolveSecretFiles", () => {
  test("explicit SAC_SECRETS_ENVRC wins verbatim, missing entries skipped", () => {
    const reader: FileReader = (p) => (p === "/a.src" ? "K=V" : null);
    expect(
      resolveSecretFiles({ SAC_SECRETS_ENVRC: "/a.src:/gone.src" }, reader),
    ).toEqual(["/a.src"]);
  });

  test("falls back to the canonical $HOME default glob, sorted", () => {
    const lister: DirLister = () => ["b.src", "a.src", "notes.txt"];
    const reader: FileReader = () => "K=V";
    expect(
      resolveSecretFiles({ HOME: "/home/op" }, reader, lister),
    ).toEqual([
      "/home/op/.bash.d/secrets/010_scitex/a.src",
      "/home/op/.bash.d/secrets/010_scitex/b.src",
    ]);
  });
});

describe("parseEnvFile", () => {
  test("tolerates blanks, comments, and values containing =", () => {
    expect(
      parseEnvFile("# c\n\nA=1\nB=x=y\n  C = padded \nNOEQUALS\n=noname\n"),
    ).toEqual({ A: "1", B: "x=y", C: "padded" });
  });
});

describe("tokenFingerprint", () => {
  test("is stable, 8-hex, and empty for empty input", () => {
    const fp = tokenFingerprint("some:token");
    expect(fp).toMatch(/^[0-9a-f]{8}$/);
    expect(tokenFingerprint("some:token")).toBe(fp);
    expect(tokenFingerprint("other:token")).not.toBe(fp);
    expect(tokenFingerprint("")).toBe("");
  });
});

describe("backoffForAttempt", () => {
  test("doubles from 2s and caps at 60s", () => {
    expect(backoffForAttempt(1)).toBe(2000);
    expect(backoffForAttempt(2)).toBe(4000);
    expect(backoffForAttempt(3)).toBe(8000);
    expect(backoffForAttempt(6)).toBe(60_000);
    expect(backoffForAttempt(100)).toBe(60_000);
    expect(backoffForAttempt(0)).toBe(2000);
  });
});
