"""Call-expression visitor for SciTeXChecker (Phase 2 call rules)."""

from __future__ import annotations

import ast
from pathlib import Path

from .. import rules
from .._rule_tables import AXES_HINTS as _AXES_HINTS
from .._rule_tables import AXES_SKIP as _AXES_SKIP
from .._rule_tables import CALL_RULES as _CALL_RULES
from .._rule_tables import PRINT_RULE as _PRINT_RULE

# STX-NET001 — outbound network HTTP-ish verb methods. `session.get(...)` /
# `httpx_client.request(...)` etc. all take `timeout=` as a keyword; the value
# maps method-name -> None because those APIs have NO positional timeout slot
# we can rely on (timeout is keyword-only in practice). `urlopen` and
# `create_connection` are handled separately since they take timeout
# positionally.
_NET_HTTP_METHODS = frozenset(
    {"get", "post", "put", "delete", "patch", "head", "options", "request"}
)
# Module names whose HTTP verbs we attribute confidently (requests.get,
# httpx.post, ...). Names outside this set are only matched when the receiver
# variable looks like an http client/session (see `_net_looks_like_client`).
_NET_HTTP_MODULES = frozenset({"requests", "httpx"})
# Receiver-variable name hints for `<var>.get(...)` — only these variable
# names are treated as HTTP clients, so arbitrary `d.get(key)` (dict.get) is
# never flagged.
_NET_CLIENT_HINTS = ("session", "client", "http", "requests", "httpx", "sess")


class CallChecksMixin:
    """Call visitors. Expects host ``_add`` / ``_get_source`` / ``_imports`` /
    ``_plugin_call_rules`` / ``_has_session_decorator`` / ``_MOCK_SYMBOLS`` /
    ``_check_stx_io_path``."""

    def visit_Call(self, node: ast.Call) -> None:
        self._check_call(node)
        self._check_network_timeout(node)
        self.generic_visit(node)

    # -- STX-NET001 — outbound network call without an explicit timeout --

    def _net_is_test_file(self) -> bool:
        """True iff the current file is test code (calls there may be unbounded).

        Mirrors ``_tq001_is_test_file`` intentionally rather than importing it:
        NET001 must skip ``tests/`` dirs and ``test_*.py`` / ``*_test.py``
        regardless of mixin ordering.
        """
        p = Path(self.filepath)
        name = p.name
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or any(seg in {"tests", "test"} for seg in p.parts)
        )

    def _net_has_kw(self, node: ast.Call, name: str = "timeout") -> bool:
        return any(kw.arg == name for kw in node.keywords)

    @staticmethod
    def _net_looks_like_client(recv: str | None) -> bool:
        if not recv:
            return False
        low = recv.lower()
        return any(h in low for h in _NET_CLIENT_HINTS)

    def _net_flag(self, node: ast.Call) -> None:
        line = self._get_source(node.lineno)
        self._add(rules.NET001, node.lineno, node.col_offset, line)

    def _check_network_timeout(self, node: ast.Call) -> None:
        """Flag outbound network calls that omit an explicit ``timeout``.

        Only calls confidently attributable to a network API are flagged —
        attribute/name match against urllib/requests/httpx/socket. When the
        attribution is uncertain (arbitrary ``.get(``), the call is left alone
        to keep false positives near zero.
        """
        if self._net_is_test_file():
            return
        func = node.func

        # bare name: urlopen(url)  ->  timeout is the 3rd POSITIONAL or kw.
        if isinstance(func, ast.Name):
            if func.id == "urlopen":
                # urlopen(url, data=None, timeout=...)
                if len(node.args) >= 3 or self._net_has_kw(node):
                    return
                self._net_flag(node)
            return

        if not isinstance(func, ast.Attribute):
            return

        attr = func.attr
        recv = func.value.id if isinstance(func.value, ast.Name) else None
        # Resolve alias (import urllib.request as R -> R.urlopen).
        resolved = self._imports.get(recv, recv) if recv else None

        # urllib.request.urlopen(...) / <alias>.urlopen(...)
        if attr == "urlopen":
            if len(node.args) >= 3 or self._net_has_kw(node):
                return
            self._net_flag(node)
            return

        # socket.create_connection(address, timeout, source_address)
        #   -> timeout is 2nd POSITIONAL or kw.
        if attr == "create_connection":
            base = recv or ""
            base_resolved = resolved or ""
            if "socket" in base.lower() or "socket" in base_resolved.lower():
                if len(node.args) >= 2 or self._net_has_kw(node):
                    return
                self._net_flag(node)
            return

        # requests / httpx verb methods -> timeout is keyword-only in practice.
        if attr in _NET_HTTP_METHODS:
            mod = (resolved or recv or "").split(".")[0].lower()
            confident = mod in _NET_HTTP_MODULES or self._net_looks_like_client(recv)
            if not confident:
                return
            if self._net_has_kw(node):
                return
            self._net_flag(node)
            return

    def _check_call(self, node: ast.Call) -> None:
        """Check function calls against Phase 2 rules."""
        func = node.func

        # module.func() pattern -- e.g., np.save(), stats.ttest_ind()
        if isinstance(func, ast.Attribute):
            func_name = func.attr
            mod_name = None

            if isinstance(func.value, ast.Name):
                mod_name = func.value.id
            elif isinstance(func.value, ast.Attribute):
                # module.sub.func() -- e.g., scipy.stats.ttest_ind()
                if isinstance(func.value.value, ast.Name):
                    mod_name = func.value.attr  # use "stats" from scipy.stats

            # Check stx.io path patterns before skipping stx.* calls
            if mod_name in ("stx", "scitex", "scitex_io") or (
                isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id in ("stx", "scitex", "scitex_io")
            ):
                self._check_stx_io_path(node)
                return

            # Resolve alias: if user did `import numpy as np`, resolve np -> numpy
            resolved = self._imports.get(mod_name, mod_name)

            # STX-P010 — record any top-level figrecipe call inside a module.
            # `fr.subplots(...)` (alias) and chained `fr.fig.savefig(...)`
            # both resolve to root "figrecipe"; a bare `figrecipe.subplots()`
            # matches directly. Recorded here — BEFORE the FM-category
            # exemption below early-returns on fr/figrecipe — so the
            # get_issues() session-gated emit sees it. Whether it flags
            # depends on the module being @stx.session; that decision is
            # deferred to get_issues().
            if self._figrecipe_call_root(func) == "figrecipe":
                line = self._get_source(node.lineno)
                self._figrecipe_usages.append((node.lineno, node.col_offset, line))

            # Check (module, func) against rule table
            rule = _CALL_RULES.get((mod_name, func_name))
            if rule is None and resolved != mod_name:
                rule = _CALL_RULES.get((resolved, func_name))
            if rule is None:
                rule = _CALL_RULES.get((None, func_name))

            # Fallback to plugin-contributed rules
            if rule is None:
                rule = self._plugin_call_rules.get((mod_name, func_name))
            if rule is None and resolved != mod_name:
                rule = self._plugin_call_rules.get((resolved, func_name))
            if rule is None:
                rule = self._plugin_call_rules.get((None, func_name))

            # Special cases
            if rule is not None:
                # plt.show() -- only flag if mod resolves to matplotlib
                if rule is rules.P004:
                    if mod_name not in ("plt", "pyplot") and resolved not in (
                        "matplotlib.pyplot",
                    ):
                        return

                # to_csv / savefig -- skip on non-data/figure objects
                if rule in (rules.IO004, rules.IO007):
                    if mod_name in ("stx", "scitex", "scitex_io", "os", "sys", "Path"):
                        return

                # FM rules: exempt stx.*/fr.*/figrecipe.* calls
                if rule.category == "figure":
                    _exempt = ("stx", "scitex", "scitex_io", "fr", "figrecipe")
                    if mod_name in _exempt:
                        return
                    # Check root of chained call: fr.fig.set_size_inches()
                    if (
                        isinstance(func.value, ast.Attribute)
                        and isinstance(func.value.value, ast.Name)
                        and func.value.value.id in _exempt
                    ):
                        return

                line = self._get_source(node.lineno)
                self._add(rule, node.lineno, node.col_offset, line)
                return

            # Axes hints: ax.plot(), ax.scatter(), ax.bar()
            if func_name in _AXES_HINTS and mod_name not in _AXES_SKIP:
                # Heuristic: if variable name looks like axes
                if mod_name and (
                    mod_name.startswith("ax") or mod_name in ("axes", "subplot")
                ):
                    line = self._get_source(node.lineno)
                    self._add(
                        _AXES_HINTS[func_name], node.lineno, node.col_offset, line
                    )
                return

            # Path(...).mkdir() pattern
            if func_name == "mkdir" and mod_name not in (
                "os",
                "stx",
                "scitex",
                "sys",
            ):
                # Heuristic: if it's called on something that looks like a Path
                line = self._get_source(node.lineno)
                if "Path" in line or "path" in line.lower():
                    pa003 = getattr(rules, "PA-003", None)
                    if pa003 is not None:
                        self._add(pa003, node.lineno, node.col_offset, line)

        # bare func() pattern -- e.g., print(), open()
        elif isinstance(func, ast.Name):
            if func.id == "print" and self._has_session_decorator:
                line = self._get_source(node.lineno)
                self._add(_PRINT_RULE, node.lineno, node.col_offset, line)
            elif func.id == "open" and self._has_session_decorator:
                line = self._get_source(node.lineno)
                self._add(rules.PA002, node.lineno, node.col_offset, line)
            # NM003 — bare call to a mock symbol: Mock(), MagicMock(), patch(...)
            elif func.id in self._MOCK_SYMBOLS:
                line = self._get_source(node.lineno)
                self._add(rules.NM003, node.lineno, node.col_offset, line)

        # NM003 — attribute call to a mock symbol: mock.patch(...),
        # unittest.mock.MagicMock(...), pytest_mock.MockerFixture(...).
        if isinstance(func, ast.Attribute) and func.attr in self._MOCK_SYMBOLS:
            line = self._get_source(node.lineno)
            self._add(rules.NM003, node.lineno, node.col_offset, line)

    def _figrecipe_call_root(self, func: ast.expr) -> str | None:
        """Resolve the root module name of an attribute-call to its import.

        For ``fr.subplots()`` the root ``Name`` is ``fr``; for the chained
        ``fr.fig.savefig()`` it is still ``fr``. We walk down ``.value``
        until the base ``Name``, then resolve any alias through
        ``self._imports`` (``import figrecipe as fr`` → ``figrecipe``).
        Returns the resolved top-level name, or None when the base is not a
        plain ``Name`` (e.g. ``get_fr().subplots()``).
        """
        cur = func
        # `func` is the Attribute being called (e.g. Attribute(attr=subplots)).
        while isinstance(cur, ast.Attribute):
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return None
        return self._imports.get(cur.id, cur.id)

    def _check_stx_io_path(self, node: ast.Call) -> None:
        from .._path_checker import check_stx_io_path

        check_stx_io_path(self, node)
