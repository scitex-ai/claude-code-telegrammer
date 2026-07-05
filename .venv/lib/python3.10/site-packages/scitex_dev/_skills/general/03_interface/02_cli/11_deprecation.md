---
description: |
  [TOPIC] Interface Cli Deprecation
  [DETAILS] SciTeX CLI deprecation policy — renamed commands hard-error with redirect (exit 2). Parameter-level deprecation warns once per shell session.
tags: [scitex-general-interface-cli-deprecation]
---

# §5. Deprecation redirect — hard error

- Renamed commands do **not** keep working with a warning.
- Old form exits non-zero with a redirect.

```
$ <cli> <old-name>
error: `<cli> <old-name>` was renamed to `<cli> <noun> <verb>`.
Re-run with: <cli> <noun> <verb>
```

- Exit code: `2`.
- Soft warnings let stale scripts persist indefinitely.
- Hard errors force the fix in one iteration.
- No `-W ignore`-style silencer — the only way forward is to update the caller.

## §5a. Parameter-level deprecation

- For `--foo` → `--bar` where both still accept the same value:
  - Emit one stderr warning per shell session.
  - Stay silent for the rest of the session.
- Keyed by **the parent shell's PID** (i.e. `$PPID` from inside the CLI process) and command name. Using `$PPID` gives one warning per interactive shell, not per CLI invocation.
- Marker file: `${XDG_RUNTIME_DIR:-/tmp}/scitex-cli-dep-${USER}-${PPID}-<cmd>.flag`.
