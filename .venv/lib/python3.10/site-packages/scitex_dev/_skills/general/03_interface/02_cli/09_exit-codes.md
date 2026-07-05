---
description: |
  [TOPIC] Interface Cli Exit Codes
  [DETAILS] SciTeX CLI exit code semantics — 0 success, 1 runtime, 2 usage, 3-9 domain, ≥10 reserved.
tags: [scitex-general-interface-cli-exit-codes]
---

# §3. Exit codes

| Code  | Meaning                                                  |
|-------|----------------------------------------------------------|
| `0`   | Success                                                  |
| `1`   | Generic runtime error                                    |
| `2`   | Usage error (bad flags, missing arg, precondition unmet) |
| `3-9` | Domain-specific (document in `--help`)                   |
| `≥10` | Reserved for signal translation / shell conventions      |
