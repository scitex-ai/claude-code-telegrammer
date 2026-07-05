"""Textual TUI for the ecosystem dashboard.

Brings htop-style live filtering + key navigation to
`scitex-dev ecosystem dashboard tui`. The data layer
(`gather_ecosystem_state`) and rendering helpers
(`_cell`, `_column_header`) are shared with the Rich one-shot
view in `_render.py` so there's only one source of truth for
cell formatting.

Keys:
    /          start filter (type to narrow rows by package name)
    Escape     clear filter
    r          re-run enrichers (refresh data)
    q          quit
    j / ↓      next row
    k / ↑      previous row
    g          jump to top
    G          jump to bottom

Lazy import: `textual` is an optional dep in scitex-dev's `[tui]`
extra. If missing, the CLI command tells the user how to install.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from rich.text import Text

from ._render import (
    _cell,
    _column_header,
    cols_for_verbosity,
    enrichers_for_cols,
)

if TYPE_CHECKING:
    from ._state import PackageState


def _require_textual():
    """Raise a friendly error if textual isn't installed."""
    try:
        import textual  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "The TUI dashboard requires the `textual` package.\n"
            "Install with: pip install textual\n"
            "(or `pip install -e .[tui]` if scitex-dev is editable-installed)"
        ) from exc


def run_tui(
    *,
    verbosity: int = 1,
    packages: list[str] | None = None,
    workers: int = 16,
) -> None:
    """Entry point for the Textual TUI. Imports textual lazily so the
    rest of scitex-dev doesn't pay the dep cost.
    """
    _require_textual()

    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container
    from textual.widgets import DataTable, Footer, Header, Input, Static

    from ._state import gather_ecosystem_state

    class DashboardApp(App):
        """Live ecosystem dashboard with keystroke filter."""

        CSS = """
        Screen { layout: vertical; }
        #table-wrap { height: 1fr; }
        DataTable { height: 100%; }
        #filter-bar { height: 3; display: none; padding: 0 1; }
        #filter-bar.visible { display: block; }
        Input { border: solid $accent; }
        #status { height: 1; padding: 0 1; color: $text-muted; }
        """

        BINDINGS = [
            Binding("/", "show_filter", "Filter", show=True),
            Binding("escape", "clear_filter", "Clear"),
            Binding("r", "refresh", "Refresh"),
            Binding("q", "quit", "Quit"),
            Binding("j,down", "cursor_down", "Down", show=False),
            Binding("k,up", "cursor_up", "Up", show=False),
            Binding("g", "cursor_top", "Top", show=False),
            Binding("G", "cursor_bottom", "Bottom", show=False),
        ]

        def __init__(self):
            super().__init__()
            self._verbosity = verbosity
            self._packages = packages
            self._workers = workers
            self._cols = cols_for_verbosity(verbosity)
            self._enrichers = enrichers_for_cols(self._cols)
            self._states: list[PackageState] = []
            self._filter_text = ""
            self._refresh_thread: threading.Thread | None = None
            self._refresh_lock = threading.Lock()

        # ----- Layout ------------------------------------------------

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Container(id="filter-bar"):
                yield Input(placeholder="Filter by package name…", id="filter")
            with Container(id="table-wrap"):
                yield DataTable(zebra_stripes=True, cursor_type="row")
            yield Static("Loading…", id="status")
            yield Footer()

        def on_mount(self) -> None:
            self.title = "SciTeX ecosystem"
            self.sub_title = f"v={self._verbosity}"
            table = self.query_one(DataTable)
            for i, c in enumerate(self._cols):
                table.add_column(_column_header(self._cols, i), key=c)
            # Initial async gather.
            self._kick_refresh()

        # ----- Data flow --------------------------------------------

        def _kick_refresh(self) -> None:
            with self._refresh_lock:
                if self._refresh_thread is not None and self._refresh_thread.is_alive():
                    return  # one refresh at a time
                self._refresh_thread = threading.Thread(
                    target=self._refresh_worker, daemon=True
                )
                self._refresh_thread.start()

        def _refresh_worker(self) -> None:
            def _on_update(states):
                # Snapshot the states list and schedule a redraw on
                # the Textual event loop.
                snap = list(states)
                self.call_from_thread(self._apply_states, snap)

            self._set_status("Refreshing…")
            gather_ecosystem_state(
                verbosity=self._verbosity,
                packages=self._packages,
                workers=self._workers,
                on_update=_on_update,
                enrichers=self._enrichers,
            )
            self.call_from_thread(self._set_status, "Ready · press / to filter")

        def _apply_states(self, states) -> None:
            self._states = states
            self._rebuild_rows()

        def _set_status(self, msg: str) -> None:
            try:
                self.query_one("#status", Static).update(msg)
            except Exception:
                pass

        # ----- Rendering --------------------------------------------

        def _filtered_states(self) -> list:
            if not self._filter_text:
                return self._states
            needle = self._filter_text.lower()
            return [s for s in self._states if needle in s.pkg.lower()]

        def _rebuild_rows(self) -> None:
            table = self.query_one(DataTable)
            table.clear()
            ordered = sorted(
                self._filtered_states(),
                key=lambda s: (
                    not s.last_commit_iso,
                    -ord(s.last_commit_iso[0]) if s.last_commit_iso else 0,
                    s.pkg,
                ),
            )
            # Above sort is approximate (lexical reverse); apply the
            # cleaner two-pass sort matching the Rich renderer:
            dated = sorted(
                [s for s in self._filtered_states() if s.last_commit_iso],
                key=lambda s: (s.last_commit_iso, s.pkg),
                reverse=True,
            )
            undated = sorted(
                [s for s in self._filtered_states() if not s.last_commit_iso],
                key=lambda s: s.pkg,
            )
            ordered = dated + undated
            for state in ordered:
                cells = []
                for col in self._cols:
                    raw = _cell(state, col)
                    cells.append(raw if isinstance(raw, Text) else Text(str(raw)))
                table.add_row(*cells)

        # ----- Actions ----------------------------------------------

        def action_show_filter(self) -> None:
            bar = self.query_one("#filter-bar")
            bar.add_class("visible")
            self.query_one("#filter", Input).focus()

        def action_clear_filter(self) -> None:
            self._filter_text = ""
            inp = self.query_one("#filter", Input)
            inp.value = ""
            self.query_one("#filter-bar").remove_class("visible")
            self._rebuild_rows()
            self.query_one(DataTable).focus()

        def action_refresh(self) -> None:
            self._kick_refresh()

        def action_cursor_top(self) -> None:
            table = self.query_one(DataTable)
            table.move_cursor(row=0)

        def action_cursor_bottom(self) -> None:
            table = self.query_one(DataTable)
            table.move_cursor(row=table.row_count - 1)

        # ----- Filter input -----------------------------------------

        def on_input_changed(self, event) -> None:
            if event.input.id == "filter":
                self._filter_text = event.value
                self._rebuild_rows()

        def on_input_submitted(self, event) -> None:
            if event.input.id == "filter":
                # Enter returns focus to the table but keeps the filter.
                self.query_one(DataTable).focus()

    DashboardApp().run()


__all__ = ["run_tui"]
