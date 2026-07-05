"""Visitor mixins for :class:`scitex_dev.linter.checker.SciTeXChecker`.

``checker.py`` was a single ~1000-line class mixing import, call, error
-handling and test-quality concerns. Each concern now lives in a focused
mixin here; ``SciTeXChecker`` composes them. Shared helpers (``_add``,
``_get_source``, config/state) remain on ``SciTeXChecker`` so mixins call
``self._add(...)`` exactly as before.
"""

from ._calls import CallChecksMixin
from ._eh import ErrorHandlingMixin
from ._imports import ImportChecksMixin, own_scitex_package
from ._test_quality import TestQualityMixin

__all__ = [
    "CallChecksMixin",
    "ErrorHandlingMixin",
    "ImportChecksMixin",
    "TestQualityMixin",
    "own_scitex_package",
]
