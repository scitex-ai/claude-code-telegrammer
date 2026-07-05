"""PS-501 / PS-502 / PS-503 / PS-504 / PS-505 / PS-506 / PS-507 — examples conventions.

PS-501: every `.py` example whose stem starts with NN_ should decorate
its `main()` with `@stx.session`. The reference is
`~/proj/figrecipe/examples/01_bundle_format.py` and
`~/proj/scitex-python/examples/01_session.py`. The decorator gives
auto-CLI, SDIR_RUN-managed output, config injection, reproducibility.

PS-502: an example file `<n>.py` with a sibling directory `<n>_out/`
that is empty (or contains only `__pycache__`) means the example was
never run end-to-end — fix the example or delete the empty stub.

PS-503: an example file `<n>.py` with a sibling `<n>_out/` directory
that has no `FINISHED_SUCCESS/<session_id>/` subdir. Once `@stx.session`
runs the example to completion it writes a session-id directory under
`FINISHED_SUCCESS/`; the rule enforces that directory's presence so
GitHub viewers see real demo artefacts. (PS-502 only checks
"some content"; PS-503 checks the `FINISHED_SUCCESS` shape specifically.)

PS-504: `.ipynb` examples must commit their cell outputs. GitHub renders
cell outputs inline, so an `nbstripped` notebook is invisible to
viewers. Detected by walking notebook cells and looking for any
non-empty `outputs` list on a `code` cell.

PS-505: `tests/examples/test_<stem>.py` for an `.ipynb` example must run
the notebook via `nbconvert --execute` or `pytest --nbval` (importing
or `runpy`-ing won't execute notebook cells). Detected by string-search
in the test file.

PS-506: a `.ipynb` example that imports matplotlib must include the
`%matplotlib inline` cell magic; otherwise figure outputs aren't
embedded in cell outputs and the rendered notebook on GitHub will not
show plots.

PS-507: a `.ipynb` example that imports matplotlib must call `plt.show()`
at least once. Even with `%matplotlib inline`, deferring display can
leave figures un-rendered in cell outputs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


_NUMBERED_PY_EXAMPLE_RE = re.compile(r"^\d+_[A-Za-z0-9_]+\.py$")
_NUMBERED_IPYNB_EXAMPLE_RE = re.compile(r"^\d+_[A-Za-z0-9_]+\.ipynb$")
_STX_SESSION_RE = re.compile(r"@\s*stx\.session\b|@\s*stx\.module\b")
_HAS_DEF_MAIN = re.compile(r"^\s*(?:async\s+)?def\s+main\s*\(", re.MULTILINE)

_NB_EXEC_RE = re.compile(r"nbconvert\b.{0,80}--execute|--nbval(?:-lax)?\b", re.DOTALL)
_MPL_IMPORT_RE = re.compile(r"\b(?:import\s+matplotlib|from\s+matplotlib\b)")
_PLT_SHOW_RE = re.compile(r"\bplt\.show\s*\(")
_INLINE_MAGIC_RE = re.compile(r"^\s*%matplotlib\s+inline\b", re.MULTILINE)

# PS-508: any of these in stderr/error outputs flags as a committed warning.
_WARNING_CLASS_RE = re.compile(
    r"\b("
    r"DeprecationWarning|UserWarning|FutureWarning|RuntimeWarning|"
    r"PendingDeprecationWarning|ImportWarning|ResourceWarning|SyntaxWarning|"
    r"Warning"
    r")\b:"
)


def _is_empty_or_pycache_only(d: Path) -> bool:
    if not d.is_dir():
        return False
    children = [p for p in d.iterdir() if p.name != "__pycache__"]
    return not children


def _has_finished_success(d: Path) -> bool:
    """True iff `<n>_out/FINISHED_SUCCESS/<session_id>/` exists with content."""
    fs_dir = d / "FINISHED_SUCCESS"
    if not fs_dir.is_dir():
        return False
    for child in fs_dir.iterdir():
        if child.is_dir() and any(child.iterdir()):
            return True
    return False


def _ipynb_cells_text_and_outputs(nb_path: Path):
    """Yield (cell_dict, joined_source) pairs from a notebook, or empty on error."""
    try:
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for cell in nb.get("cells", []):
        if not isinstance(cell, dict):
            continue
        src = cell.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        yield cell, src


def _notebook_has_outputs(nb_path: Path) -> bool:
    """True iff any `code` cell in the notebook has a non-empty outputs list."""
    for cell, _src in _ipynb_cells_text_and_outputs(nb_path):
        if cell.get("cell_type") != "code":
            continue
        outputs = cell.get("outputs", [])
        if outputs:
            return True
    return False


def _notebook_imports_matplotlib(nb_path: Path) -> bool:
    for cell, src in _ipynb_cells_text_and_outputs(nb_path):
        if cell.get("cell_type") != "code":
            continue
        if _MPL_IMPORT_RE.search(src):
            return True
    return False


def _notebook_has_inline_magic(nb_path: Path) -> bool:
    for cell, src in _ipynb_cells_text_and_outputs(nb_path):
        if cell.get("cell_type") != "code":
            continue
        if _INLINE_MAGIC_RE.search(src):
            return True
    return False


def _notebook_has_plt_show(nb_path: Path) -> bool:
    for cell, src in _ipynb_cells_text_and_outputs(nb_path):
        if cell.get("cell_type") != "code":
            continue
        if _PLT_SHOW_RE.search(src):
            return True
    return False


def _output_text(output: dict) -> str:
    """Best-effort flatten of any cell-output payload to a string."""
    text = output.get("text", "")
    if isinstance(text, list):
        text = "".join(text)
    data = output.get("data", {})
    if isinstance(data, dict):
        plain = data.get("text/plain", "")
        if isinstance(plain, list):
            plain = "".join(plain)
        text = (text + "\n" + plain) if text else plain
    return text or ""


def _notebook_warning_outputs(nb_path: Path):
    """Yield (cell_index, snippet) for each committed warning output."""
    for idx, (cell, _src) in enumerate(_ipynb_cells_text_and_outputs(nb_path)):
        if cell.get("cell_type") != "code":
            continue
        for output in cell.get("outputs", []) or []:
            otype = output.get("output_type")
            if otype == "error":
                # Only flag deprecation/etc warnings, not real exceptions
                # (those are PS-level test failures, not warning hygiene).
                ename = output.get("ename", "")
                if "Warning" in ename:
                    yield idx, f"{ename}: {output.get('evalue', '')[:80]}"
                continue
            if otype != "stream":
                continue
            # Stream outputs: stderr stream commonly carries warnings.
            if output.get("name") != "stderr":
                continue
            text = _output_text(output)
            if _WARNING_CLASS_RE.search(text):
                snippet = text.strip().splitlines()[0][:120]
                yield idx, snippet


def check_examples_conventions(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS-501–PS-507 violations for examples/ contents."""
    examples = repo / "examples"
    if not examples.is_dir():
        return

    for child in examples.iterdir():
        if not child.is_file():
            continue

        # ---------- .py rules: PS-501 (@stx.session) ------------------------
        if _NUMBERED_PY_EXAMPLE_RE.match(child.name):
            try:
                text = child.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _HAS_DEF_MAIN.search(text) and not _STX_SESSION_RE.search(text):
                out.append(
                    violation_cls(
                        "PS-501",
                        str(child),
                        (
                            "main() not decorated with @stx.session. Wrap it: "
                            "`import scitex as stx; @stx.session\\n"
                            "def main(CONFIG=stx.session.INJECTED, "
                            "logger=stx.session.INJECTED): ...` and use "
                            "`Path(CONFIG.SDIR_RUN)` for outputs."
                        ),
                    )
                )

        # ---------- .ipynb rules: PS-504 / PS-506 / PS-507 --------------------
        if _NUMBERED_IPYNB_EXAMPLE_RE.match(child.name):
            if not _notebook_has_outputs(child):
                out.append(
                    violation_cls(
                        "PS-504",
                        str(child),
                        (
                            "notebook has no committed cell outputs (looks "
                            "nbstripped). GitHub renders outputs inline; the "
                            "demo is invisible without them. Re-run with "
                            "`jupyter nbconvert --execute --to notebook "
                            "--output <name>.ipynb <name>.ipynb` and commit."
                        ),
                    )
                )
            if _notebook_imports_matplotlib(child):
                if not _notebook_has_inline_magic(child):
                    out.append(
                        violation_cls(
                            "PS-506",
                            str(child),
                            (
                                "imports matplotlib but missing the "
                                "`%matplotlib inline` cell magic. Add it "
                                "near the top of the notebook so figures "
                                "embed in cell outputs."
                            ),
                        )
                    )
                if not _notebook_has_plt_show(child):
                    out.append(
                        violation_cls(
                            "PS-507",
                            str(child),
                            (
                                "imports matplotlib but does not call "
                                "`plt.show()`. Without it figures may not "
                                "land in cell outputs. Add `plt.show()` "
                                "after each figure."
                            ),
                        )
                    )

            # PS-508: warning text in committed cell outputs.
            warnings_found = list(_notebook_warning_outputs(child))
            if warnings_found:
                idx, snippet = warnings_found[0]
                more = (
                    f" (and {len(warnings_found) - 1} more)"
                    if len(warnings_found) > 1
                    else ""
                )
                out.append(
                    violation_cls(
                        "PS-508",
                        str(child),
                        (
                            f"committed warning in cell {idx}{more}: "
                            f"{snippet!r}. Demos must run cleanly — silence "
                            "the warning at the source, filter it with "
                            "`warnings.filterwarnings`, or fix the cause "
                            "and re-run before committing."
                        ),
                    )
                )

            # PS-505: matched test must use nbconvert / nbval.
            stem = child.stem
            test_path = repo / "tests" / "examples" / f"test_{stem}.py"
            if test_path.is_file():
                try:
                    test_text = test_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    test_text = ""
                if not _NB_EXEC_RE.search(test_text):
                    out.append(
                        violation_cls(
                            "PS-505",
                            str(test_path),
                            (
                                "notebook smoke-test must invoke "
                                "`jupyter nbconvert --execute` or "
                                "`pytest --nbval[-lax]` — runpy / "
                                "subprocess `python …` does not execute "
                                ".ipynb cells."
                            ),
                        )
                    )

    # ---------- _out/ dir rules: PS-502 (empty), PS-503 (FINISHED_SUCCESS) ---
    #
    # Skip both when a `.ipynb` example owns the stem instead of (or
    # alongside) a `.py` example — for notebooks, the rendered cell
    # outputs ARE the demo, so an `_out/` sibling is optional. The
    # rules only apply to `.py` examples that produce side artefacts.
    for child in examples.iterdir():
        if not child.is_dir() or not child.name.endswith("_out"):
            continue
        stem = child.name[: -len("_out")]
        py_sibling = examples / f"{stem}.py"
        ipynb_sibling = examples / f"{stem}.ipynb"
        if not py_sibling.is_file() and ipynb_sibling.is_file():
            # `.ipynb`-only example — `_out/` is legacy; rules don't apply.
            continue
        if not py_sibling.is_file():
            # No matching example at all; treat as orphan (out of scope).
            continue
        if _is_empty_or_pycache_only(child):
            out.append(
                violation_cls(
                    "PS-502",
                    str(child),
                    (
                        "empty examples output dir — the example was never "
                        "run end-to-end. Run it once to populate the "
                        "FINISHED_SUCCESS marker, or delete the empty stub."
                    ),
                )
            )
            continue
        if not _has_finished_success(child):
            out.append(
                violation_cls(
                    "PS-503",
                    str(child),
                    (
                        "no FINISHED_SUCCESS/<session_id>/ subdir — the "
                        "example was never run via @stx.session. Run it "
                        "once and commit the FINISHED_SUCCESS contents so "
                        "GitHub viewers see real demo artefacts."
                    ),
                )
            )
