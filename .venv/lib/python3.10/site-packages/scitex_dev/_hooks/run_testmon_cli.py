"""Console-script shim that execs the bundled ``run_testmon.sh`` wrapper.

pre-commit's ``entry:`` is whitespace-split and NOT run through a shell, so
``entry: bash $(scitex-dev hooks print-path run_testmon)`` cannot expand the
command substitution. This shim gives repos a host-agnostic entry point that
needs no shell expansion and no hand-resolved absolute path:

    # .pre-commit-config.yaml (language: system)
    entry: scitex-dev-testmon            # console script, OR
    entry: python -m scitex_dev._hooks.run_testmon_cli

All extra args are passed straight through to the wrapper (which adds
``--testmon``), so a repo keeps its own pytest flags / ``--ignore`` paths.
"""

from __future__ import annotations

import os
import sys

from . import run_testmon_sh_path


def main() -> None:
    """Exec the bundled run_testmon.sh, forwarding all CLI args.

    Uses ``execvp`` (PATH lookup for ``bash``) so the process is replaced and
    the wrapper's exit code propagates unchanged to pre-commit.
    """
    os.execvp("bash", ["bash", run_testmon_sh_path(), *sys.argv[1:]])


if __name__ == "__main__":
    main()
