---
description: |
  [TOPIC] Quick Start
  [DETAILS] Basic linter usage — check files, list rules.
tags: [scitex-dev-linter-quick-start]
---

# Quick Start

```python
from scitex_dev.linter import list_rules

# List all available rules
rules = list_rules()
for r in rules:
    print(f"{r.id}: {r.description}")

# Filter by category
io_rules = list_rules(category="io")
stats_rules = list_rules(category="stats")
plot_rules = list_rules(category="plot")
```

```bash
# CLI
scitex-dev linter check src/
scitex-dev linter check src/my_script.py
scitex-dev linter list-rules
```
