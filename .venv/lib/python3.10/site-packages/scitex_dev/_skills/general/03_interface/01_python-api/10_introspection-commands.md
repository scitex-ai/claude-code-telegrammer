---
description: |
  [TOPIC] Interface Python Api Introspection
  [DETAILS] The `list-python-apis -v|-vv|-vvv` ladder + `--json` flag mandated for every package. Module-level via `scitex introspect api <pkg>`. CLI parity with `mcp list-tools` ladder. Used by ecosystem audit tools and LLM agents to discover API.
tags: [scitex-general-interface-python-api-introspection-commands]
---

# API Introspection Commands

Every package ships a CLI command that lists its public Python API at four verbosity levels.

## The ladder

```bash
# Package-level (standalone CLI)
scitex-io list-python-apis              # names only
scitex-io list-python-apis -v           # + signatures
scitex-io list-python-apis -vv          # + one-line docstrings
scitex-io list-python-apis -vvv         # + full docstrings + source path
scitex-io list-python-apis --json       # machine-readable

# Module-level (umbrella CLI)
scitex audio list-python-apis           # if scitex-audio installed
scitex introspect api scitex.audio      # alternative phrasing
```

## What each level returns

| Level    | Output                                               | Use case                                         |
|----------|------------------------------------------------------|--------------------------------------------------|
| (bare)   | `save\nload\nload_configs\nregister_saver\n...`     | quick `dir`-style enumeration                    |
| `-v`     | `save(obj, path, *, dry_run=False, overwrite=False) -> Path` | check call signatures              |
| `-vv`    | `+ first sentence of docstring`                      | scan for relevance                               |
| `-vvv`   | `+ full NumPy docstring + src/scitex_io/_save.py:42` | full reference / debug / open in editor          |
| `--json` | `[{name, signature, doc, source}, ...]`              | feed to LLMs, audit tools, doc generators        |

## Why this matters

- **LLM agents** discover what a package can do without ingesting the source.
- **`scitex-dev introspect api`** uses the same machinery to compare two installs (drift detection).
- **`audit-cli` / `audit-mcp-tools`** consume `--json` to verify the four interfaces are in sync.
- **Sphinx skills** can pre-render the `-vvv` output as a reference page.

## Parity with other interfaces

The `-v|-vv|-vvv` + `--json` shape is identical across:

| Interface | Command                              | Spec leaf                                                                             |
|-----------|--------------------------------------|---------------------------------------------------------------------------------------|
| Python    | `<cli> list-python-apis`             | this file                                                                             |
| CLI       | `<cli> list-cli-commands`            | [03_interface/02_cli/03_required-introspection-commands.md](../02_cli/03_required-introspection-commands.md) |
| MCP       | `<cli> mcp list-tools`               | [03_interface/03_mcp/05_list-tools-ladder.md](../03_mcp/05_list-tools-ladder.md) |

If you implement one, you owe the others. The `-v` level boundaries are identical (signatures vs docstrings vs full).

## Implementation hint

```python
# scitex_io/_cli/_list_python_apis.py (sketch)
import importlib
from . import scitex_io

def run(verbosity: int, as_json: bool):
    names = scitex_io.__all__
    items = []
    for name in names:
        obj = getattr(scitex_io, name)
        item = {"name": name}
        if verbosity >= 1:
            item["signature"] = str(inspect.signature(obj))
        if verbosity >= 2:
            item["doc"] = (obj.__doc__ or "").splitlines()[0]
        if verbosity >= 3:
            item["doc_full"] = obj.__doc__
            item["source"] = inspect.getsourcefile(obj) + f":{inspect.getsourcelines(obj)[1]}"
        items.append(item)
    if as_json:
        print(json.dumps(items, indent=2))
    else:
        # render text per verbosity level
        ...
```

scitex-dev provides a helper: `scitex_dev.introspect.api.render(items, verbosity, as_json)` — packages can delegate to it instead of reimplementing the renderer.

## Audit

```bash
scitex-io list-python-apis --json | jq 'length'   # count public API
scitex-io list-python-apis -vvv | grep -c "Parameters"   # how many docstrings have NumPy block
```

Failure modes:

- Command absent → required-introspection-commands rule violation.
- `--json` not implemented → forces ad-hoc parsing.
- `-vvv` source path missing → inspect didn't resolve (likely a `try/except ImportError` branch where `obj is None`).
