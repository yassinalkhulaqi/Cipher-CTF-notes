from __future__ import annotations

import contextlib
import tkinter as tk

import pytest

from redscribe.ui.theme import DARK, build_theme
from redscribe.ui.widgets import SearchBox

pytestmark = pytest.mark.gui


def test_search_box_shows_focus_and_placeholder_states() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk is unavailable in this environment")
    root.withdraw()
    try:
        theme = build_theme(root, "dark")
        box = SearchBox(root, theme, "Search notes")
        assert str(box.cget("highlightbackground")) == DARK.border
        assert box._placeholder.winfo_manager() == "place"

        box._on_focus_in()
        assert str(box.cget("highlightbackground")) == DARK.accent

        box.set_value("smb")
        assert box._placeholder.winfo_manager() == ""

        box.set_value("")
        assert box._placeholder.winfo_manager() == "place"

        box._on_focus_out()
        assert str(box.cget("highlightbackground")) == DARK.border
    finally:
        with contextlib.suppress(tk.TclError):
            root.destroy()
