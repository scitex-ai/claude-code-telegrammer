---
description: |
  [TOPIC] Interface Python Api Imports And Shadowing
  [DETAILS] Import resolution rules for scitex submodules that intentionally shadow stdlib names (`scitex.os`, `scitex.io`, `scitex.logging`, `scitex.path`). Bare `import os` always resolves to stdlib (PEP 328 absolute imports); scitex submodules require an explicit `from . import` or full path. Aliasing rules to preserve the visual distinction. When `importlib.import_module` is justified.
tags: [scitex-general-interface-python-api-imports-and-shadowing]
---

# Imports and Stdlib Shadowing

scitex submodules intentionally overlap stdlib names — `scitex.os`, `scitex.io`, `scitex.logging`, `scitex.path`. This file describes how Python resolves these and the conventions that keep both forms unambiguous in source code.

## The good news: bare `import` is absolute

Per **PEP 328** (mandatory since Python 3.0), all top-level `import X` statements are *absolute* — Python resolves through `sys.path`, never through the current package. So inside any scitex source file:

```python
# inside scitex/<anywhere>/_module.py
import os         # ✅ stdlib — sys.path resolution, never scitex.os
import io         # ✅ stdlib — never scitex.io
import logging    # ✅ stdlib — never scitex.logging
import pathlib    # ✅ stdlib
```

**There is no shadowing risk for bare imports.** A scitex contributor writing `import os` always gets stdlib, regardless of how many submodules scitex defines.

## Resolving scitex's own submodule

The submodule requires an explicit reference:

```python
from . import os               # relative — resolves within current package
from scitex import os          # absolute path — full module name
import scitex.os               # absolute import statement
import scitex.os as sos        # absolute import with alias
```

All four forms have a visible cue (`from .`, `scitex.`) that distinguishes them from stdlib. Reading the source, the maintainer can tell at a glance which `os` is which.

## Aliasing rules

### Rule 1 — Always use absolute imports for stdlib

```python
import os               # ✅ stdlib
from os import path     # ✅ stdlib
import logging          # ✅ stdlib
```

Never `from . import os` when you mean stdlib (relative gets the scitex submodule).

### Rule 2 — Use relative imports only for package-local navigation

```python
from . import _utils                # ✅ sibling private module
from .._registry import SAVERS      # ✅ parent-package internal
from . import os                    # ✅ scitex.os submodule (clearly intentional)
```

The leading `.` is the visual cue — anywhere you see it, you're in scitex code.

### Rule 3 — NEVER alias a scitex submodule back to its stdlib name

```python
# ❌ Anti-pattern — destroys the visual distinction
from scitex import os as os
from scitex import io as io
import scitex.logging as logging

# ✅ Correct — alias to a clearly-scitex name
import scitex.os as sos
from scitex import io as scitex_io
import scitex.logging as slogging
```

After the bad form, every subsequent `os.path.join(...)` is ambiguous to a reader: is this stdlib or scitex? After the good form, `sos.<...>` and `os.<...>` coexist clearly.

### Rule 4 — NEVER alias stdlib to a scitex-like name

```python
# ❌ Anti-pattern — same confusion in reverse
import os as scitex_os
import io as scitex_io_module
```

If a name starts with `scitex_`, it should *be* scitex code. Don't repurpose the prefix.

## User-facing pattern (in research scripts)

Both stdlib and scitex submodules can coexist in one file:

```python
# user research script
import os                          # stdlib — process env, file ops
import scitex.os as sos            # scitex — extended path utilities
import logging                     # stdlib — basic logger
import scitex.logging as slogging  # scitex — session logger, structured

os.environ["SCITEX_DIR"] = "/tmp/runs"
sos.path.expand_template("{HOME}/data/{run_id}")    # scitex helper
logger = slogging.get_session_logger()
```

Document this pattern in package READMEs whenever the package shadows a stdlib name. Show one stdlib usage and one scitex usage side by side.

## When `importlib.import_module` is justified

The bare `import os` form covers 99% of cases. Reach for `importlib.import_module` only when:

1. **The module name is computed at runtime** — plugin loaders, format dispatchers, optional-extra resolution:
   ```python
   def _get_handler(format_name: str):
       return importlib.import_module(f"scitex_io._formats._{format_name}")
   ```
2. **You're forcing a reload** — debugging, hot-reload during interactive development:
   ```python
   importlib.reload(my_module)
   ```
3. **You need to bypass `sys.modules` caching for a controlled re-import** — rare, mostly testing infrastructure.

For everyday `import os`, `importlib.import_module("os")` is verbose without benefit. Don't use it as a "more explicit" form — `import os` is already unambiguous in Python 3.

`__import__("os")` is the low-level builtin behind `import`. Even more verbose than `importlib.import_module` and returns the *top-level* package (not the deepest); use `importlib.import_module` instead when you need dynamic imports.

## scitex packages that shadow stdlib

Current shadowing inventory (audit and update when adding a new scitex submodule):

| scitex submodule       | Stdlib equivalent      | Notes                                              |
|------------------------|------------------------|----------------------------------------------------|
| `scitex.os`            | `os`                   | Path/env helpers — extends, doesn't replace        |
| `scitex.io`            | `io`                   | File I/O dispatch (CSV, NPY, PKL, ...)             |
| `scitex.logging`       | `logging`              | Session-aware structured logging                   |
| `scitex.path`          | `pathlib` (kind of)    | PathManager, SCITEX_DIR resolution                 |
| `scitex.dict` (if any) | `dict` (builtin)       | DotDict — borderline; consider renaming if drift   |

When proposing a new scitex submodule that shadows stdlib, weigh:

- **Does it extend or replace?** Extension (`scitex.os` adds path-template helpers) is friendlier than replacement.
- **Will users want both in one file?** If yes, the alias-to-clearly-scitex-name pattern above must be documented in the package README.
- **Is there a non-shadowing alternative?** `scitex.pathman` could replace `scitex.path`. Discuss before merging the new name.

## Audit

Static checks:

- Grep package source for `from scitex import <name> as <name>` where `<name>` matches a stdlib module name → flag.
- Grep for `import os as scitex_*`, `import io as scitex_*`, etc. → flag.
- Verify package README documents the alias pattern when the package's namespace appears in the shadowing inventory above.

Linter rule (planned): **PA-011** — flag stdlib-name aliasing patterns above; suggest the canonical form.

## See also

- [02_naming-and-visibility.md](02_naming-and-visibility.md) — the underscore-alias pattern (`import numpy as _np`) for keeping third-party names out of `dir()`.
- [11_import-conventions.md](11_import-conventions.md) — standalone vs umbrella import paths from a user's perspective.
