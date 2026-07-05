"""Optional-import helper for SciTeX standalone packages.

Use in a `__init__.py` to replace inline `try/except ImportError` blocks:

    from scitex_dev import try_import_optional

    h5py = try_import_optional("h5py", extra="hdf5", pkg="scitex-io")
    ndarray = try_import_optional("numpy", attr="ndarray")  # always installed
    rel_mod = try_import_optional(".sub.thing", package="scitex_io")

Returns the imported object on success and ``None`` on ``ImportError``.
The original failure (module name + extra/pkg metadata) is recorded on the
returned ``None`` is impossible — instead, callers can read the registry via
``last_install_hint(name)`` to construct precise error messages at the
use-site without re-raising.

The `NotInstalled` sentinel proposal (see python-api skill TODO.md) is
deferred — Pattern A (`X = None` always present in `__all__`) plus a
companion `XXX_AVAILABLE = X is not None` flag covers all current use cases.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

__all__ = ["try_import_optional", "last_install_hint", "InstallHint"]


@dataclass(frozen=True)
class InstallHint:
    """Metadata to help a caller surface a useful install message."""

    module: str
    extra: str | None
    pkg: str | None
    # The REAL exception text when the dependency is PRESENT but failed to
    # import cleanly (e.g. a numpy-ABI-broken C-extension). None for a plain
    # "module absent" miss. Preserved so a degraded import stays diagnosable
    # instead of being silently masked.
    cause: str | None = None

    def message(self) -> str:
        if self.pkg and self.extra:
            base = (
                f"`{self.module}` is required. "
                f"Install with: pip install '{self.pkg}[{self.extra}]'"
            )
        elif self.extra:
            base = (
                f"`{self.module}` is required. "
                f"Re-install with the '{self.extra}' extra."
            )
        else:
            base = (
                f"`{self.module}` is required. "
                f"Install with: pip install {self.module}"
            )
        if self.cause:
            base += f"\n  underlying import error: {self.cause}"
        return base


_HINTS: dict[str, InstallHint] = {}


def last_install_hint(name: str) -> InstallHint | None:
    """Return the most recently recorded install hint for ``name`` (or ``None``)."""
    return _HINTS.get(name)


_NUMPY_ABI_SIGNATURES = ("_ARRAY_API not found", "Failed to initialize NumPy")


def _numpy_abi_cause(exc: BaseException) -> str | None:
    """Return an actionable hint if ``exc`` looks like a numpy ABI mismatch.

    A C-extension (torch, etc.) built against a different numpy MAJOR fails to
    import with a non-``ImportError`` (often ``RuntimeError``) whose text
    carries numpy's array-API signature — the SAME string numpy emits in its
    ``UserWarning``. Matching the RAISED exception text catches ANY numpy-ABI-
    broken extension without a per-package functional probe. Returns ``None``
    when ``exc`` carries no such signature.
    """
    text = str(exc)
    if not any(sig in text for sig in _NUMPY_ABI_SIGNATURES):
        return None
    try:
        import numpy as _np

        npv = _np.__version__
    except Exception:  # noqa: BLE001 — numpy itself absent/broken
        npv = "unknown"
    return (
        f"{type(exc).__name__}: {exc} -- likely a numpy ABI mismatch "
        f"(installed numpy {npv}; the C-extension was built for a different "
        f"numpy major). Reinstall the extension with a build matching this "
        f"numpy (e.g. a numpy-2-compatible wheel)."
    )


def try_import_optional(
    module_path: str,
    attr: str | None = None,
    *,
    extra: str | None = None,
    pkg: str | None = None,
    package: str | None = None,
) -> Any:
    """Import ``module_path``; return ``None`` on ANY import failure.

    A dependency that is absent (``ImportError``) OR present-but-broken (any
    other exception at import time, e.g. a numpy-ABI-incompatible C-extension
    raising ``RuntimeError``) degrades to ``None`` rather than propagating. The
    real failure is recorded on the install hint (``cause``) so it stays
    diagnosable via :func:`last_install_hint`.

    Parameters
    ----------
    module_path : str
        Module to import. Leading ``.`` triggers relative resolution against
        ``package`` (mirrors :func:`importlib.import_module`).
    attr : str, optional
        If given, return ``getattr(module, attr)`` instead of the module.
        A missing attribute is treated identically to a failed import.
    extra : str, optional
        Name of the pip extra that pulls this dependency (used for the
        install hint surfaced via :func:`last_install_hint`).
    pkg : str, optional
        Distribution name owning the extra (e.g. ``"scitex-io"``).
    package : str, optional
        Anchor for relative imports.

    Returns
    -------
    object or None
        The imported module/attribute, or ``None`` on failure.
    """
    if module_path.startswith(".") and package is None:
        raise ValueError(
            "relative imports require an explicit `package=` argument "
            f"(got module_path={module_path!r})"
        )
    try:
        mod = importlib.import_module(module_path, package=package)
    except ImportError as exc:
        # Dependency genuinely absent / unresolved — the normal optional-miss
        # path. Record an ABI cause only if the text carries the signature
        # (a plain "No module named X" leaves cause=None, message unchanged).
        _HINTS[module_path] = InstallHint(
            module=module_path, extra=extra, pkg=pkg, cause=_numpy_abi_cause(exc)
        )
        return None
    except Exception as exc:  # noqa: BLE001
        # The dependency IS installed but fails to import CLEANLY (e.g. a torch
        # built for numpy<2 raising RuntimeError under numpy>=2). Without this
        # branch the RuntimeError escapes and crashes EVERY feature that lazily
        # touches the dep (neurovista: stx.io.save via a stack->getmodule import
        # of torch). Degrade to None like any optional miss, but RECORD the real
        # exception so the failure is diagnosable via last_install_hint() — never
        # silently masked.
        _HINTS[module_path] = InstallHint(
            module=module_path,
            extra=extra,
            pkg=pkg,
            cause=_numpy_abi_cause(exc) or f"{type(exc).__name__}: {exc}",
        )
        return None

    if attr is None:
        return mod
    try:
        return getattr(mod, attr)
    except AttributeError:
        _HINTS[module_path] = InstallHint(module=module_path, extra=extra, pkg=pkg)
        return None
