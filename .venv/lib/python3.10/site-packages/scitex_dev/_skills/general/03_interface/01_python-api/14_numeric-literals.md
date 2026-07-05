---
description: |
  [TOPIC] Numeric literals — underscore-separated thousands
  [DETAILS] Numeric literals with four or more digits (>= 1_000) MUST be written with `_` separators (`21_600`, `1_500_000`, not `21600` / `1500000`). PEP 515 syntax; supported in Python 3.6+. Improves readability at the call site and grep-ability for typo hunts. Hex / binary / scientific literals get the same separators where it helps reading.
tags: [scitex-general-interface-python-api-numeric-literals]
---

# Numeric literals — underscore-separated thousands

Numeric literals with **four or more digits** (i.e. ≥ 1_000) MUST be written
with `_` separators. PEP 515 syntax. Python 3.6+ accepts them; runtime
value is identical (`21_600 == 21600`).

```python
# ✅ Required
TIMEOUT_S = 21_600          # 6 hours
MAX_BYTES = 1_048_576       # 1 MiB
ONE_BILLION = 1_000_000_000

# ❌ Forbidden once the literal is ≥ 1_000
TIMEOUT_S = 21600
MAX_BYTES = 1048576
ONE_BILLION = 1000000000
```

## Why

- **Readability at the call site.** `_run(cmd, timeout=21_600)` is
  legible at a glance; `timeout=21600` invites a misread as `2_160` or
  `216_000`. The savings compound at every reviewer's pass.
- **Grep-ability for typo hunts.** Hunting for "exactly 21,600 seconds
  somewhere" works whether you type `21600` or `21_600` — Python's
  tokenizer normalizes both — but the underscore form **also** matches
  human-typed comments / docstrings / commit messages consistently.
- **Communicates intent.** `1_048_576` is obviously a power-of-2
  byte boundary; `1048576` reads like a phone number.

## When the rule does **not** apply

- Literals < 1_000 (three or fewer digits): write them bare. `300`,
  `999` need no underscore.
- Numbers where digit grouping would obscure meaning. Examples:
  - **Years**: write `2026`, not `2_026`. Calendar values are read
    as a whole.
  - **Ports**: write `31291`, not `31_291`. They're memorized as a
    block (the 3129X scheme; see scitex-cloud).
  - **HTTP status codes**: write `2_xx` style is wrong; use `200`
    plainly.

If unsure, ask: "Is this a quantity (count of bytes, seconds, items)?
→ underscore. Is this an identifier (year, port, code)? → bare."

## Hex / binary / scientific

The same `_` syntax works in non-decimal bases. Use where helpful:

```python
RGBA_MAGENTA = 0xFF_00_FF_FF
FLAG_BITS    = 0b_1010_0101
AVOGADRO     = 6.022_140_76e23
```

## Audit

Linter rule (planned): `PA-XYZ` flags integer / float literals with
≥ 4 consecutive digits and no `_`. Until the rule lands, reviewers
catch it by eye and the [readme template](../../04_docs/01_readme_template.md)
points new contributors here.

## Related

- PEP 515 — Underscores in Numeric Literals
- `_skills/general/03_interface/01_python-api/05_docstring-standards.md`
  (sibling section on documentation conventions)
