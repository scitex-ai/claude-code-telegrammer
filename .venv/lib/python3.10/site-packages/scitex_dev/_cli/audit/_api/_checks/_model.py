"""Rule registry, Violation dataclass, and shared heuristic constants for the
Python API auditor.

Split out of `_audit.py` — pure refactor, no behaviour change (mirrors the
`_project/_registry.py` + `_project/_violation.py` split from issue #103 and
`_django/_checks.py`). These symbols have NO dependency on `_audit`, so both
the per-section check modules and the `_audit` orchestrator can import them at
module level with no import cycle. `_audit` re-exports `Rule`, `RULES`, and
`Violation` for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    code: str
    section: str
    message: str
    slug: str = ""  # short, human-readable kebab-case name
    severity: str = "warning"  # "warning" | "error" — drives audit headline


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # §1 Naming and visibility
        Rule("PA-101", "§1", "`__all__` is missing from __init__.py", "all-missing"),
        Rule(
            "PA-102",
            "§1",
            "name listed in __all__ is not bound in __init__.py",
            "all-name-unbound",
        ),
        Rule(
            "PA-103",
            "§1",
            "name in __all__ starts with underscore",
            "all-private-name",
        ),
        Rule(
            "PA-104",
            "§1",
            "third-party symbol is re-exported via __all__",
            "all-third-party",
        ),
        # §2 Version strategy
        Rule(
            "PA-201",
            "§2",
            "`__version__` is missing from __all__",
            "version-not-in-all",
        ),
        Rule(
            "PA-202",
            "§2",
            "`__version__` not derived from importlib.metadata.version(...)",
            "version-not-from-metadata",
        ),
        Rule(
            "PA-203",
            "§2",
            'fallback for __version__ should be "0.0.0+local"',
            "version-fallback-wrong",
        ),
        # §3 Lazy imports / optional deps
        Rule(
            "PA-301",
            "§3",
            "top-level `import` outside try/except may break on missing optional dep",
            "top-level-optional-import",
        ),
        Rule(
            "PA-304",
            "§3",
            "umbrella import `scitex.<sub>` / `import scitex` inside standalone "
            "source — drags the umbrella `__init__.py` and its lazy re-export "
            "machinery into every call. Use `scitex_<sub>` (peer standalone) "
            "instead. See _skills/general/03_interface/01_python-api/"
            "11_import-conventions.md.",
            "umbrella-import-in-standalone",
        ),
        Rule(
            "PA-305",
            "§3",
            "module imports `playwright.async_api` (live browser automation) "
            "but does not call `capture_debug_artifacts_async` — every "
            "decision point in a Playwright flow must capture screenshot + "
            "HTML so selector regressions are diagnosable post-mortem. See "
            "`_skills/general/02_package/09_browser-automation-debugging.md`. "
            "Wire via `from scitex_browser.debugging import "
            "capture_debug_artifacts_async`.",
            "playwright-without-debug-capture",
        ),
        # §3 No mocks (no exceptions)
        Rule(
            "PA-306",
            "§3",
            "mock library / symbol / fixture in package source — the SciTeX "
            "ecosystem forbids mocks without exception. Replace with a real "
            "fake, real fixture (tmp_path, subprocess), or hand-rolled stub "
            "class. Covers `unittest.mock` / `mock` / `pytest_mock` imports, "
            "Mock/MagicMock/AsyncMock/patch/mock_open/PropertyMock/"
            "create_autospec/MockerFixture symbols, and pytest "
            "`mocker`/`monkeypatch` fixture parameters. See the linter rule "
            "`STX-NM001/NM002/NM003` for the in-process equivalent.",
            "no-mocks",
            severity="error",
        ),
        # §3 Test quality (post-no-mock theater guards)
        Rule(
            "PA-307",
            "§3",
            "test-quality violation — every test in this package's test "
            "tree must satisfy: (TQ001) at least one assertion; (TQ002) "
            "`# Arrange`/`# Act`/`# Assert` marker comments in order; "
            "(TQ003) descriptive name (≥3 word-tokens after `test_`); "
            "(TQ004) no state mutation in session/module/package-scope "
            "fixtures; (TQ005) yield (not return) for resource-acquiring "
            "fixtures; (TQ006) no top-level if/else in parametrized test "
            "bodies; (TQ007) exactly one assertion per test. Detected by "
            "running the linter's `STX-TQ001-007` rules across tests/ + "
            "conftest.py. The combination ensures CI red names exactly "
            "which behaviour broke. See `_skills/general/"
            "02_package/13_test-quality.md`.",
            "test-quality",
            severity="error",
        ),
        # §5 Type hints
        Rule(
            "PA-501",
            "§5",
            "`from __future__ import annotations` is missing",
            "missing-future-annotations",
        ),
    ]
}


@dataclass
class Violation:
    rule: str
    where: str
    detail: str

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        slug = f" {r.slug}" if r and r.slug else ""
        return f"  [{self.rule} {section}{slug}] {self.where}: {self.detail}"


# Heuristic: imports from these packages are "third-party" — symbols pulled
# from them and re-exported via __all__ violate PA-104.
_THIRD_PARTY_ROOTS = frozenset(
    {
        "numpy",
        "np",
        "pandas",
        "pd",
        "torch",
        "scipy",
        "sklearn",
        "matplotlib",
        "plotly",
        "h5py",
        "xarray",
        "polars",
    }
)

# Stdlib roots whose top-level `import x` is benign and should not trigger
# PA-301 even outside try/except.
_STDLIB_SAFE_ROOTS = frozenset(
    {
        "os",
        "sys",
        "io",
        "re",
        "json",
        "logging",
        "pathlib",
        "typing",
        "warnings",
        "functools",
        "itertools",
        "dataclasses",
        "enum",
        "collections",
        "contextlib",
        "inspect",
        "importlib",
        "abc",
        "math",
        "datetime",
        "time",
        "string",
        "textwrap",
        "shutil",
        "tempfile",
        "subprocess",
        "ast",
        "copy",
        "weakref",
        "traceback",
        "uuid",
        "hashlib",
        "base64",
        "struct",
        "operator",
        "asyncio",
        "socket",
        "threading",
        "queue",
        "select",
        "signal",
        "fcntl",
        "termios",
        "platform",
        "getpass",
        "argparse",
        "csv",
        "shlex",
        "glob",
        "fnmatch",
        "pickle",
        "random",
        "secrets",
        "ssl",
        "urllib",
        "http",
        "email",
        "html",
        "xml",
        "configparser",
        "tomllib",
        "zipfile",
        "tarfile",
        "gzip",
        "bz2",
        "lzma",
    }
)

_MOCK_MODULES_AUDIT = frozenset({"mock", "unittest.mock", "pytest_mock"})
_MOCK_SYMBOLS_AUDIT = frozenset(
    {
        "Mock",
        "MagicMock",
        "AsyncMock",
        "NonCallableMock",
        "NonCallableMagicMock",
        "PropertyMock",
        "patch",
        "mock_open",
        "create_autospec",
        "sentinel",
        "ANY",
        "MockerFixture",
    }
)
_MOCK_FIXTURE_PARAMS_AUDIT = frozenset({"mocker", "monkeypatch"})


__all__ = [
    "Rule",
    "RULES",
    "Violation",
    "_THIRD_PARTY_ROOTS",
    "_STDLIB_SAFE_ROOTS",
    "_MOCK_MODULES_AUDIT",
    "_MOCK_SYMBOLS_AUDIT",
    "_MOCK_FIXTURE_PARAMS_AUDIT",
]
