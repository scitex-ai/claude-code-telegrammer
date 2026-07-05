"""Brand-audit rules (PS-2xx).

Three rules wired into ``scitex-dev ecosystem audit-brand <pkg>``:

  - PS-201 no-local-brand-glue: registered brands (e.g. figrecipe, socialia)
    must not contain a standalone ``_branding.py`` module or a
    ``_BRAND_ALIAS`` setattr loop. They must consult ``scitex_dev._branding``.
  - PS-202 umbrella-brand-symmetry: if ``brands.X.umbrella_brand == Y`` then
    ``brands.Y.native_brand == X`` (and vice versa).
  - PS-203 method-prefix-pair: in a counterpart-pair, if one side declares
    ``method_prefix`` the other must too.

Pure-data rules (PS-202/203) run on the registry alone; PS-201 needs the
package's local checkout. ``audit_brand_package(pkg_root, brand_key)``
returns a list of violation dicts. The CLI prints them and exits non-zero
on any violation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

from ._helpers import _load_registry, get_brand

# PS-201 detects the two canonical anti-patterns this registry replaces:
#
#   1. The ``setattr(cls, f"{_BRAND_ALIAS}_{s}", ...)`` method-aliasing loop
#      that ``register_method_aliases`` replaces.
#   2. A local ``_branding.py`` that pulls brand identity from environment
#      variables (i.e. duplicates the central helper). A ``_branding.py``
#      with *only* unrelated utilities (e.g. docstring rebranding text
#      substitution) is left alone — narrow the registry's responsibility
#      to brand-identity translation, not arbitrary text munging.
_FORBIDDEN_SETATTR_LOOP = re.compile(r"setattr\([^)]*_BRAND_ALIAS", re.MULTILINE)
# A local _branding.py is flagged only when it re-implements helpers the
# central registry now owns: get_env / get_mcp_server_name. Packages may
# keep a _branding.py with only unrelated utilities (docstring rebranding
# via text-substitution etc.) until a future scope-extension folds those in.
_FORBIDDEN_BRANDING_FILE_MARKER = re.compile(r"^\s*def\s+get_env\s*\(", re.MULTILINE)


def audit_registry_consistency() -> list[dict]:
    """PS-202 + PS-203 — pure-data audits on the registry."""
    violations: list[dict] = []
    registry = _load_registry()
    for key, entry in registry.items():
        # PS-202 umbrella-brand-symmetry
        if "umbrella_brand" in entry:
            other = entry["umbrella_brand"]
            other_entry = registry.get(other)
            if other_entry is None:
                violations.append(
                    {
                        "code": "PS-202",
                        "brand": key,
                        "message": (
                            f"umbrella_brand={other!r} points at a missing "
                            f"registry entry"
                        ),
                    }
                )
            elif other_entry.get("native_brand") != key:
                violations.append(
                    {
                        "code": "PS-202",
                        "brand": key,
                        "message": (
                            f"umbrella_brand={other!r} but "
                            f"brands.{other}.native_brand="
                            f"{other_entry.get('native_brand')!r} (expected "
                            f"{key!r})"
                        ),
                    }
                )
        if "native_brand" in entry:
            other = entry["native_brand"]
            other_entry = registry.get(other)
            if other_entry is None:
                violations.append(
                    {
                        "code": "PS-202",
                        "brand": key,
                        "message": (
                            f"native_brand={other!r} points at a missing registry entry"
                        ),
                    }
                )
            elif other_entry.get("umbrella_brand") != key:
                violations.append(
                    {
                        "code": "PS-202",
                        "brand": key,
                        "message": (
                            f"native_brand={other!r} but "
                            f"brands.{other}.umbrella_brand="
                            f"{other_entry.get('umbrella_brand')!r} "
                            f"(expected {key!r})"
                        ),
                    }
                )

        # PS-203 method-prefix-pair
        counterpart_key = entry.get("umbrella_brand") or entry.get("native_brand")
        if counterpart_key and counterpart_key in registry:
            has_self = "method_prefix" in entry
            has_other = "method_prefix" in registry[counterpart_key]
            if has_self != has_other:
                violations.append(
                    {
                        "code": "PS-203",
                        "brand": key,
                        "message": (
                            f"method_prefix is set on {key!r}={has_self} but "
                            f"on counterpart {counterpart_key!r}={has_other}"
                        ),
                    }
                )
    return violations


def _iter_source_files(pkg_root: Path) -> Iterable[Path]:
    """Walk a package source tree, skipping build artefacts and tests."""
    src = pkg_root / "src"
    if not src.exists():
        return
    for path in src.rglob("*.py"):
        # Skip build/, dist/, __pycache__, tests/
        parts = set(path.parts)
        if parts & {"__pycache__", "build", "dist", "tests"}:
            continue
        yield path


def audit_local_brand_glue(pkg_root: Path, brand_key: str) -> list[dict]:
    """PS-201 — forbid local brand-glue files / setattr loops."""
    violations: list[dict] = []
    entry = get_brand(brand_key)
    import_name = entry.get("import_") or brand_key.replace("-", "_")
    pkg_dir = pkg_root / "src" / import_name
    if not pkg_dir.exists():
        return [
            {
                "code": "PS-201",
                "brand": brand_key,
                "message": (
                    f"package source dir {pkg_dir} not found "
                    f"(expected src/{import_name}/)"
                ),
            }
        ]
    for path in _iter_source_files(pkg_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(pkg_root))
        # A local _branding.py is flagged only when it defines get_env
        # WITHOUT delegating to scitex_dev._branding. A file that imports
        # the central registry and exposes thin wrappers (for back-compat)
        # is the intended migration end-state.
        if (
            path.name == "_branding.py"
            and _FORBIDDEN_BRANDING_FILE_MARKER.search(text)
            and "scitex_dev._branding" not in text
        ):
            violations.append(
                {
                    "code": "PS-201",
                    "brand": brand_key,
                    "file": rel,
                    "message": (
                        "local _branding.py re-implements get_env; use "
                        "scitex_dev._branding.get_env() instead"
                    ),
                }
            )
        # setattr(_BRAND_ALIAS ...) method-aliasing loop.
        if _FORBIDDEN_SETATTR_LOOP.search(text):
            violations.append(
                {
                    "code": "PS-201",
                    "brand": brand_key,
                    "file": rel,
                    "message": (
                        "setattr loop using _BRAND_ALIAS for method aliases; "
                        "use scitex_dev._branding.register_method_aliases()"
                    ),
                }
            )
    return violations


def audit_brand_package(pkg_root: Path, brand_key: str) -> list[dict]:
    """All PS-2xx rules for one brand. Returns flat list of violations."""
    violations: list[dict] = []
    violations.extend(audit_registry_consistency())
    violations.extend(audit_local_brand_glue(pkg_root, brand_key))
    return violations


def find_package_root(
    brand_key: str, search_paths: Optional[list[Path]] = None
) -> Path:
    """Locate the local checkout of a brand's package.

    Tries (in order):
      1. ``$SCITEX_PROJECTS_ROOT/<brand_key>``
      2. each path in *search_paths*
      3. ``~/proj/<brand_key>``
    """
    import os

    candidates: list[Path] = []
    env_root = os.environ.get("SCITEX_PROJECTS_ROOT")
    if env_root:
        candidates.append(Path(env_root) / brand_key)
    if search_paths:
        candidates.extend(Path(p) / brand_key for p in search_paths)
    candidates.append(Path.home() / "proj" / brand_key)

    for c in candidates:
        if (c / "pyproject.toml").exists():
            return c
    raise FileNotFoundError(
        f"Could not locate local checkout of {brand_key!r}; tried: "
        + ", ".join(str(c) for c in candidates)
    )
