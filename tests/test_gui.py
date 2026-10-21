"""GUI smoke tests for the main window.

These tests need a display. On Linux CI they run under Xvfb; elsewhere they
skip automatically when Tk cannot open a window.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Iterator

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.mainwindow import (
    AUTOSAVE_DEBOUNCE_MS,
    PREVIEW_DEBOUNCE_MS,
    MainWindow,
)

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


def test_tree_drop_planning_moves_and_reorders_nodes(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, _root, vault, errors = window
    folder = vault.create_node("Campaign", None, kind="folder")
    first = vault.create_node("Alpha", None)
    second = vault.create_node("Beta", None)
    third = vault.create_node("Gamma", None)
    app._refresh_tree()

    plan, label = app._tree_drop_plan(second, set(), folder, 0.5)
    assert plan == (folder.id, None)
    assert "Campaign" in label
    assert app._apply_tree_move(second.id, folder.id, None)
    moved = vault.get_node(second.id)
    assert moved is not None
    assert moved.parent_id == folder.id
    assert app.tree.selection() == (str(second.id),)

    plan, _label = app._tree_drop_plan(first, set(), third, 0.75)
    assert plan == (None, None)
    plan, _label = app._tree_drop_plan(first, set(), third, 0.25)
    assert plan == (None, third.id)
    assert not errors


def test_tree_drag_rejects_folder_cycles(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, _root, vault, errors = window
    outer = vault.create_node("Outer", None, kind="folder")
    inner = vault.create_node("Inner", outer.id, kind="folder")
    note = vault.create_node("Child note", inner.id)
    blocked = app._descendant_folder_ids(outer)

    plan, message = app._tree_drop_plan(outer, blocked, inner, 0.5)
    assert plan is None
    assert "inside itself" in message
    plan, _message = app._tree_drop_plan(outer, blocked, note, 0.5)
    assert plan is None
    assert not errors


def test_keyboard_reorders_tree_siblings(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, _root, vault, errors = window
    first = vault.create_node("Alpha", None)
    second = vault.create_node("Beta", None)
    app._refresh_tree()
    app.tree.selection_set(str(first.id))
    app.tree.focus(str(first.id))

    assert app._reorder_selected_tree(1) == "break"
    assert [node.id for node in vault.children(None)] == [second.id, first.id]
    assert app.tree.selection() == (str(first.id),)
    assert not errors


def test_editor_and_preview_share_scroll_when_enabled(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, root, vault, errors = window
    root.deiconify()
    body = "\n\n".join(f"Paragraph {index} with enough text to scroll." for index in range(80))
    node = vault.create_node("Scroll note", None, content=body)
    app._refresh_tree()
    assert app.open_node(node.id)
    app._set_view_mode("split")
    app.editor.set_text(body)
    app.preview.set_markdown(body, preserve_scroll=False)
    root.update()

    app.editor.text.yview_moveto(0.35)
    root.update()
    editor_fraction = app.editor.text.yview()[0]
    app._on_editor_scroll(str(editor_fraction), "0.6")
    root.update()
    assert abs(app.preview.text.yview()[0] - editor_fraction) < 0.02

    preview_fraction = app.preview.text.yview()[0]
    app._sync_scroll_var.set(False)
    app._toggle_sync_scroll()
    app.editor.text.yview_moveto(0.8)
    root.update()
    app._on_editor_scroll(str(app.editor.text.yview()[0]), "0.9")
    assert abs(app.preview.text.yview()[0] - preview_fraction) < 0.02
    assert vault.get_setting("ui.sync_preview_scroll") == "0"
    assert not errors


def test_preview_refresh_does_not_move_the_editor(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, root, vault, errors = window
    root.deiconify()
    body = "\n\n".join(f"Line {index}" for index in range(80))
    node = vault.create_node("Stable scroll", None, content=body)
    app._refresh_tree()
    assert app.open_node(node.id)
    app._set_view_mode("split")
    app.editor.set_text(body)
    app.preview.set_markdown(body)
    root.update()
    app.editor.text.yview_moveto(0.5)
    root.update()
    before = app.editor.text.yview()[0]

    app.preview.set_markdown("# Replaced\n\n" + body)
    root.update()
    assert abs(app.editor.text.yview()[0] - before) < 0.02
    assert not errors


def test_preview_and_autosave_debounce_constants() -> None:
    assert PREVIEW_DEBOUNCE_MS == 250
    assert AUTOSAVE_DEBOUNCE_MS == 1200


def test_dashboard_offers_import_for_a_populated_vault(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, _root, vault, errors = window
    vault.create_node("Existing note", None)
    app.dashboard.refresh()

    def button_labels(widget: tk.Misc) -> list[str]:
        labels = []
        for child in widget.winfo_children():
            if isinstance(child, tk.Widget) and child.winfo_class() == "TButton":
                labels.append(str(child.cget("text")))
            labels.extend(button_labels(child))
        return labels

    labels = button_labels(app.dashboard)
    assert "Import Markdown" in labels
    assert "Load demo vault" not in labels
    assert not errors


def test_editor_continues_quotes_and_lists(
    window: tuple[MainWindow, tk.Tk, Vault, list[tuple[object, ...]]],
) -> None:
    app, _root, _vault, errors = window
    editor = app.editor

    editor.set_text("> quoted")
    editor.text.mark_set("insert", "1.end")
    assert editor._on_return() == "break"
    assert editor.get_text() == "> quoted\n> "

    editor.set_text("  >> nested")
    editor.text.mark_set("insert", "1.end")
    assert editor._on_return() == "break"
    assert editor.get_text() == "  >> nested\n  >> "

    editor.set_text("5. item")
    editor.text.mark_set("insert", "1.end")
    assert editor._on_return() == "break"
    assert editor.get_text() == "5. item\n6. "

    editor.set_text("> ")
    editor.text.mark_set("insert", "1.end")
    assert editor._on_return() == "break"
    assert editor.get_text() == ""
    assert not errors
