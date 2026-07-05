#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: /home/ywatanabe/proj/scitex-ssh/src/scitex_ssh/__main__.py

"""Entry point for `python -m scitex_ssh`.

Per scitex-dev audit-project PS105: every distribution must be runnable
via `python -m <package>`. Delegates to the Click CLI defined in
`scitex_ssh._cli`.
"""

from scitex_ssh._cli import main

if __name__ == "__main__":
    main()
