---
description: |
  [TOPIC] Interface Cli Config Env
  [DETAILS] SciTeX CLI config and env vars — SCITEX_<PKG>_* namespace, config.yaml precedence (--config > env > project > user).
tags: [scitex-general-interface-cli-config-and-env]
---

# §6. Config + env vars

## §6a. Env var namespace

- All scitex-owned env vars **must** be `SCITEX_<PACKAGE>_*`.
- Bare package-name prefixes are forbidden.
- Out of scope: third-party tools (`POSTGRES_*`, `DJANGO_*`, `VITE_*`, `CI`, `PATH`).

### Adapter pattern for framework env vars

- Define the canonical value as `SCITEX_<PKG>_*`.
- Translate inside the framework's settings file.
- Never let framework names leak into SciTeX-owned code.

### Per-package opt-out: `[tool.scitex_dev] env_allowlist`

Some packages legitimately ship operator-facing env vars that pre-date
the SciTeX ecosystem (acronym brands like `SAC_*`, integrations with
external operator tooling) and cannot be renamed to `SCITEX_<PKG>_*`
without breaking every running deployment. Such packages declare the
prefix in their own `pyproject.toml`:

```toml
[tool.scitex_dev]
env_allowlist = ["SAC_"]
```

Semantics — entries apply "equal-to-stripped or prefix-match", same
shape as the universal allowlist in scitex-dev's audit-cli `§6a` rule:

- `"SAC_"`     → matches any `SAC_*` var (`SAC_FOO`, `SAC_LISTEN_BASE_URL`, …)
- `"GH_TOKEN"` → matches only the exact name `GH_TOKEN`

Mirror of `[tool.scitex_dev] mcp_parity_exempt = true` (the §6
MCP-parity opt-out documented in
[`../03_interface/03_mcp/07_python-api-parity.md`](../03_mcp/07_python-api-parity.md));
same namespace, same checked-out-tree resolution, same
sparingly-used contract.

**Use sparingly.** Each entry shrinks the audit surface for the
package, so the brand-prefix justification must be real
(operator-facing shell exports / hooks / dotfiles / agent specs that
predate the SciTeX adoption), **not** a catch-all noise silencer for
new code that could have been written with the canonical
`SCITEX_<PKG>_*` prefix. The audit's universal allowlist
(`PATH`, `HOME`, `CI`, `GITHUB_*`, `ANTHROPIC_*`, `CLAUDE_*`, …)
already covers the common third-party shapes — reach for
`env_allowlist` only when none of those fit.

## §6b. Config file location

Precedence (highest first):

1. `--config PATH`
2. `$SCITEX_<PKG>_CONFIG`
3. `<project>/.scitex/<pkg-short>/config.yaml`
4. `~/.scitex/<pkg-short>/config.yaml`

### Notes

- Canonical filename is always `config.yaml`.
- Project scope overrides user scope.
- CLI flags and env vars override both.
- Full layout rule (two roots, prefix-stripping `scitex-dev` → `dev`, `SCITEX_DIR`, `PathManager`) lives in [`../01_ecosystem/06_dot_scitex_directory.md`](../../01_ecosystem/06_dot_scitex_directory.md).
- Document the fallback order in `--help`.
