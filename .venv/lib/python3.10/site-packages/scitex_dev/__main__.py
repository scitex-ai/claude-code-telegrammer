"""Module entry point so `python -m scitex_dev` works.

Mirrors the `scitex-dev` console script registered in pyproject.toml.
"""

from ._cli import main

if __name__ == "__main__":
    main()
