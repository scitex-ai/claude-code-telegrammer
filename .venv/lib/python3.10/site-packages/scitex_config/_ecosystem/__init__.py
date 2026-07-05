"""scitex_config._ecosystem — internal helpers for SciTeX package maintainers.

**Not a stable public API.** This namespace contains utilities that
embed SciTeX-ecosystem conventions (`pkg-short` naming, project-scope
walk-up to `.git/`, `_skills/<pkg>/` layout, `SCITEX_<MODULE>_*` env
prefix) defined in
``scitex-python/src/scitex/_skills/general/01_arch_*.md``.

Outside the SciTeX ecosystem, use the top-level ``scitex_config``
public surface (``PriorityConfig``, ``ScitexConfig``, ``ScitexPaths``,
``load_dotenv``) — those are convention-free generic primitives.

Inside the ecosystem (i.e. authoring a ``scitex-*`` package), import
from this private namespace::

    from scitex_config._ecosystem import local_state, env_registry

The public top-level package deliberately does *not* re-export these.
"""

from . import _env_registry as env_registry
from . import _local_state as local_state
from ._env_registry import (
    ENV_REGISTRY,
    EnvVar,
    generate_template,
    get_all_modules,
    get_env_by_module,
    get_env_docs,
)

__all__ = [
    "local_state",
    "env_registry",
    "ENV_REGISTRY",
    "EnvVar",
    "generate_template",
    "get_all_modules",
    "get_env_by_module",
    "get_env_docs",
]
