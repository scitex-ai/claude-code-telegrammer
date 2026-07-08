/**
 * Tests for the one-time legacy → scitex-standard state-dir migration
 * (lib/migrate-state.ts).
 *
 * Data safety is the whole point of this module (it moves the operator's real
 * Telegram history), so these exercise the real fs with TEMP dirs — no mocks,
 * no writes under the real ~. Every case injects `env` / `home` / `newDir` /
 * `oldDir` so nothing touches the developer's actual state dir.
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { join } from "path";
import { tmpdir } from "os";
import { mkdirSync, writeFileSync, readFileSync, existsSync, rmSync } from "fs";
import {
  migrateLegacyStateDir,
  resolveOldDefaultDir,
} from "../lib/migrate-state.js";

const silent = () => {};
const FIXED = new Date("2026-07-09T00:00:00.000Z");

let root: string;
let home: string;
let newDir: string;

beforeEach(() => {
  root = join(
    tmpdir(),
    `cct-migtest-${process.pid}-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2)}`,
  );
  home = join(root, "home");
  newDir = join(root, "newstate");
  mkdirSync(home, { recursive: true });
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

/** Populate a legacy state dir with a full complement of files. */
function seedLegacy(dir: string): void {
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "messages.db"), "MAIN-DB-BYTES");
  writeFileSync(join(dir, "messages.db-wal"), "WAL-BYTES");
  writeFileSync(join(dir, "messages.db-shm"), "SHM-BYTES");
  mkdirSync(join(dir, "attachments", "photos"), { recursive: true });
  writeFileSync(join(dir, "attachments", "photos", "a.jpg"), "IMG");
  writeFileSync(join(dir, "access.json"), '{"dmPolicy":"allowlist"}');
}

describe("migrateLegacyStateDir", () => {
  test("(1) old-exists + new-absent copies db+wal+shm+attachments+access, renames to the new db, writes markers", () => {
    // "telegram"/default agent → its OLD default is the bare dir.
    const oldDir = join(home, ".claude-code-telegrammer");
    seedLegacy(oldDir);

    const res = migrateLegacyStateDir({
      env: {},
      home,
      newDir,
      now: FIXED,
      logFn: silent,
    });

    expect(res.migrated).toBe(true);
    expect(res.reason).toBe("migrated");

    // Renamed onto the scitex-standard filename, content intact.
    expect(
      readFileSync(join(newDir, "claude-code-telegrammer.db"), "utf8"),
    ).toBe("MAIN-DB-BYTES");
    expect(
      readFileSync(join(newDir, "claude-code-telegrammer.db-wal"), "utf8"),
    ).toBe("WAL-BYTES");
    expect(
      readFileSync(join(newDir, "claude-code-telegrammer.db-shm"), "utf8"),
    ).toBe("SHM-BYTES");
    // Attachments copied recursively + access.json copied.
    expect(
      readFileSync(join(newDir, "attachments", "photos", "a.jpg"), "utf8"),
    ).toBe("IMG");
    expect(readFileSync(join(newDir, "access.json"), "utf8")).toBe(
      '{"dmPolicy":"allowlist"}',
    );

    // Marker in the NEW dir records the old path + timestamp.
    const marker = JSON.parse(
      readFileSync(join(newDir, ".migrated-from"), "utf8"),
    );
    expect(marker.from).toBe(oldDir);
    expect(marker.at).toBe(FIXED.toISOString());
    // Marker in the OLD dir points forward.
    expect(existsSync(join(oldDir, ".migrated-to"))).toBe(true);

    // COPY, not move — the legacy dir is left intact as a backup.
    expect(readFileSync(join(oldDir, "messages.db"), "utf8")).toBe(
      "MAIN-DB-BYTES",
    );
  });

  test("(2) idempotent — a second run is a no-op and does not overwrite", () => {
    const oldDir = join(home, ".claude-code-telegrammer");
    seedLegacy(oldDir);

    migrateLegacyStateDir({ env: {}, home, newDir, now: FIXED, logFn: silent });
    // Mutate legacy so a (buggy) re-copy would be detectable.
    writeFileSync(join(oldDir, "messages.db"), "CHANGED-AFTER-MIGRATION");

    const res2 = migrateLegacyStateDir({
      env: {},
      home,
      newDir,
      logFn: silent,
    });
    expect(res2.migrated).toBe(false);
    expect(res2.reason).toBe("new-db-exists");
    // The already-migrated new DB is untouched.
    expect(
      readFileSync(join(newDir, "claude-code-telegrammer.db"), "utf8"),
    ).toBe("MAIN-DB-BYTES");
  });

  test("(3) new-db-exists → no-op (never clobbers an existing new DB)", () => {
    const oldDir = join(home, ".claude-code-telegrammer");
    seedLegacy(oldDir);
    mkdirSync(newDir, { recursive: true });
    writeFileSync(
      join(newDir, "claude-code-telegrammer.db"),
      "EXISTING-NEW-DB",
    );

    const res = migrateLegacyStateDir({
      env: {},
      home,
      newDir,
      logFn: silent,
    });
    expect(res.migrated).toBe(false);
    expect(res.reason).toBe("new-db-exists");
    expect(
      readFileSync(join(newDir, "claude-code-telegrammer.db"), "utf8"),
    ).toBe("EXISTING-NEW-DB");
  });

  test("(4) old-absent → no-op (nothing to carry forward)", () => {
    const res = migrateLegacyStateDir({
      env: {},
      home,
      newDir,
      logFn: silent,
    });
    expect(res.migrated).toBe(false);
    expect(res.reason).toBe("old-db-absent");
    expect(existsSync(join(newDir, "claude-code-telegrammer.db"))).toBe(false);
  });

  test("(5) explicit AGENT_STATE_DIR set → migration skipped entirely", () => {
    // Even with a full legacy dir present, an explicit state dir means "this
    // dir IS the state dir" — nothing to migrate.
    const oldDir = join(home, ".claude-code-telegrammer");
    seedLegacy(oldDir);

    const res = migrateLegacyStateDir({
      env: { CCT_AGENT_STATE_DIR: join(root, "explicit") },
      home,
      newDir,
      logFn: silent,
    });
    expect(res.migrated).toBe(false);
    expect(res.reason).toBe("explicit-state-dir");
    expect(res.oldDir).toBeNull();
    expect(existsSync(join(newDir, "claude-code-telegrammer.db"))).toBe(false);
  });

  test("(6) cross-contamination guard: a suffixed agent NEVER reads the bare dir", () => {
    // resolveOldDefaultDir must return the SUFFIXED dir for a non-telegram
    // agent — the bare dir belongs to the lead/"telegram" bot.
    expect(resolveOldDefaultDir({ CCT_AGENT_ID: "orochi" }, home)).toBe(
      join(home, ".claude-code-telegrammer-orochi"),
    );

    // Seed the BARE dir (the lead's data). A suffixed agent must not touch it.
    const bare = join(home, ".claude-code-telegrammer");
    seedLegacy(bare);

    const res = migrateLegacyStateDir({
      env: { CCT_AGENT_ID: "orochi" },
      home,
      newDir,
      logFn: silent,
    });
    // Its own suffixed old dir is absent → nothing migrates.
    expect(res.migrated).toBe(false);
    expect(res.reason).toBe("old-db-absent");
    expect(res.oldDir).toBe(join(home, ".claude-code-telegrammer-orochi"));
    // The lead's bare dir is untouched (no new db, no forward marker).
    expect(existsSync(join(newDir, "claude-code-telegrammer.db"))).toBe(false);
    expect(existsSync(join(bare, ".migrated-to"))).toBe(false);
  });

  test("(7) a copy failure leaves NO marker and surfaces the error", () => {
    const oldDir = join(home, ".claude-code-telegrammer");
    seedLegacy(oldDir);

    const boom = () => {
      throw new Error("disk full");
    };
    expect(() =>
      migrateLegacyStateDir({
        env: {},
        home,
        newDir,
        copyFile: boom,
        logFn: silent,
      }),
    ).toThrow("disk full");

    // Fail loud: no success marker written, so a later run retries rather than
    // silently believing a half-migration succeeded.
    expect(existsSync(join(newDir, ".migrated-from"))).toBe(false);
  });
});

describe("resolveOldDefaultDir", () => {
  test("null when an explicit AGENT_STATE_DIR is set", () => {
    expect(
      resolveOldDefaultDir({ CCT_AGENT_STATE_DIR: "/tmp/x" }, "/home/u"),
    ).toBeNull();
  });

  test("bare dir for the default 'telegram' agent", () => {
    expect(resolveOldDefaultDir({}, "/home/u")).toBe(
      "/home/u/.claude-code-telegrammer",
    );
    expect(resolveOldDefaultDir({ CCT_AGENT_ID: "telegram" }, "/home/u")).toBe(
      "/home/u/.claude-code-telegrammer",
    );
  });

  test("suffixed dir for a named agent (sanitized)", () => {
    expect(resolveOldDefaultDir({ CCT_AGENT_ID: "../evil" }, "/home/u")).toBe(
      "/home/u/.claude-code-telegrammer-..-evil",
    );
  });
});
