"""GUI smoke tests for the main window.

These tests need a display. On Linux CI they run under Xvfb; elsewhere they
skip automatically when Tk cannot open a window.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Iterator

import pytest

from redscribe.db import Vault
from redscribe.ui.mainwindow import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture
def window(
    vault: Vault,
) -> Iterator[tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]]]:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk is unavailable in this environment")
    root.withdraw()
    errors: list[tuple[object, ...]] = []
    root.report_callback_exception = lambda *args: errors.append(args)
    app = MainWindow(root, vault)
    app.pack(fill="both", expand=True)
    root.update()
    try:
        yield app, root, vault, errors
    finally:
        with contextlib.suppress(tk.TclError):
            app.close()
        try:
            root.update_idletasks()
            root.destroy()
        except tk.TclError:
            pass


def test_window_constructs_on_dashboard(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, _root, _vault, errors = window
    assert app._note is None
    assert app.dashboard.winfo_manager() == "grid"
    assert app._theme_name in {"dark", "light"}
    assert not errors


def test_open_note_switch_views_and_save(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, root, vault, errors = window
    node = vault.create_node("Smoke note", None, content="# Smoke\n\nhello **world**\n")
    app._refresh_tree()
    assert app.open_node(node.id)
    root.update()
    assert app._note is not None
    assert app._note.id == node.id
    assert app.title_var.get() == "Smoke note"
    assert "hello **world**" in app.editor.get_text()

    app.editor.insert_text("\n- item one\n")
    app._on_editor_change()
    assert app.save_now(notify=True)
    saved = vault.get_node(node.id)
    assert saved is not None
    assert "- item one" in saved.content

    for mode in ("write", "preview", "split"):
        app._set_view_mode(mode)
        root.update()

    assert app._show_dashboard()
    root.update()
    assert app._note is None
    assert not errors


def test_theme_toggle_rebuilds_and_persists(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, root, vault, errors = window
    before = app._theme_name
    app._toggle_theme()
    root.update()
    assert app._theme_name != before
    assert vault.get_setting("ui.theme") == app._theme_name
    assert app.dashboard.winfo_manager() == "grid"
    assert not errors


def test_layout_restores_sidebar_and_split(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, root, vault, errors = window
    root.deiconify()
    root.update()
    app._apply_sashes()
    assert app.panes.sashpos(0) >= 220

    node = vault.create_node("Layout note", None, content="# Layout\n")
    app._refresh_tree()
    assert app.open_node(node.id)
    root.update()
    app._apply_sashes()
    assert app.body_panes.sashpos(0) > 100
    assert not errors
