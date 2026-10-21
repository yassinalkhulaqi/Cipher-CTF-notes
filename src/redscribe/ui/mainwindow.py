"""The primary RedScribe application window."""

from __future__ import annotations

import logging
import re
import tkinter as tk
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from redscribe.content.templates import TEMPLATES, get_template, render_template
from redscribe.domain.models import STATUSES, Node
from redscribe.domain.utils import humanize_delta, pluralize, truncate, word_count
from redscribe.services.demo import seed_demo
from redscribe.services.exporter import (
    export_note_html,
    export_note_markdown,
    export_vault_html,
    export_vault_markdown,
)
from redscribe.services.importer import import_directory, import_markdown_files
from redscribe.storage.db import Vault
from redscribe.ui.dashboard import Dashboard
from redscribe.ui.dialogs import (
    AboutDialog,
    FlagsDialog,
    FolderPickerDialog,
    NewNoteDialog,
    PromptDialog,
    PropertiesDialog,
    SettingsDialog,
    ShortcutsDialog,
    TrashDialog,
)
from redscribe.ui.editor import MarkdownEditor
from redscribe.ui.preview import MarkdownPreview
from redscribe.ui.quick_switch import QuickSwitch
from redscribe.ui.search_dialog import SearchDialog
from redscribe.ui.snippets_window import SnippetsWindow
from redscribe.ui.theme import (
    HEADER_HEIGHT,
    SIDEBAR_WIDTH,
    STATUSBAR_HEIGHT,
    build_theme,
    configure_styles,
    difficulty_color,
    status_color,
)
from redscribe.ui.widgets import (
    Pill,
    SearchBox,
    TagChip,
    Tooltip,
    divider,
)

LOGGER = logging.getLogger(__name__)

_VIEW_MODES = ("write", "split", "preview")
_GEOMETRY_RE = re.compile(r"^\d+x\d+[+-]\d+[+-]\d+$")
_TREE_DRAG_THRESHOLD = 6
PREVIEW_DEBOUNCE_MS = 250
AUTOSAVE_DEBOUNCE_MS = 1200


@dataclass
class _TreeDrag:
    source: Node
    start_x: int
    start_y: int
    blocked: set[int]
    active: bool = False
    plan: tuple[int | None, int | None] | None = None
    description: str = ""
    hover_iid: str | None = None
    hover_tags: tuple[str, ...] = field(default_factory=tuple)


class MainWindow(tk.Frame):
    """A three-pane notebook with a tree, editor, preview, and dashboard."""

    def __init__(
        self,
        master: tk.Misc,
        vault: Vault,
        *,
        theme_name: str | None = None,
        font_size: int | None = None,
    ) -> None:
        root = master.winfo_toplevel()
        self._toplevel = root
        self._vault = vault
        stored_theme = str(vault.get_setting("ui.theme", "dark") or "dark")
        self._theme_name = theme_name if theme_name in {"dark", "light"} else stored_theme
        if self._theme_name not in {"dark", "light"}:
            self._theme_name = "dark"
        stored_size = self._setting_int("ui.font_size", 11, minimum=9, maximum=18)
        self._font_size = font_size or stored_size
        self._font_size = max(9, min(18, self._font_size))
        self._theme = build_theme(root, self._theme_name, self._font_size)
        configure_styles(root, self._theme)

        super().__init__(master, bg=self._theme.palette.bg)
        self._note: Node | None = None
        self._dirty = False
        self._loading = False
        self._selected_folder_id: int | None = None
        self._collapsed: set[str] = set()
        self._view_mode = str(vault.get_setting("ui.view_mode", "split") or "split")
        if self._view_mode not in _VIEW_MODES:
            self._view_mode = "split"
        self._restore_last = str(vault.get_setting("ui.restore_last_note", "1") or "1") != "0"
        self._sync_preview_scroll = (
            str(vault.get_setting("ui.sync_preview_scroll", "1") or "1") != "0"
        )
        self._syncing_scroll = False
        self._syncing_tree = False
        self._autosave_job: str | None = None
        self._preview_job: str | None = None
        self._tree_job: str | None = None
        self._status_job: str | None = None
        self._layout_job: str | None = None
        self._preview_stale = False
        self._tree_drag: _TreeDrag | None = None
        self.view_buttons: dict[str, ttk.Button] = {}

        root.title("RedScribe")
        root.minsize(1060, 680)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._restore_geometry()
        self._build_menus()
        self._build_ui()
        self._toplevel.bind("<Map>", self._on_toplevel_map, add="+")
        self._refresh_tree()
        self._update_sidebar_stats()
        self._initialize_start_view()
        self._restore_sashes()
        self._set_status("Ready")

    def _setting_int(self, key: str, default: int, *, minimum: int, maximum: int) -> int:
        raw = self._vault.get_setting(key)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(minimum, min(maximum, value))

    def _restore_geometry(self) -> None:
        saved = self._vault.get_setting("ui.window")
        if saved and _GEOMETRY_RE.match(saved):
            self._toplevel.geometry(saved)
            return
        screen_w = self._toplevel.winfo_screenwidth()
        screen_h = self._toplevel.winfo_screenheight()
        width = min(1440, max(1060, screen_w - 120))
        height = min(920, max(680, screen_h - 120))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self._toplevel.geometry(f"{width}x{height}+{x}+{y}")

    def _build_menus(self) -> None:
        menubar = tk.Menu(self._toplevel)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New note", accelerator="Ctrl+N", command=self._new_note)
        file_menu.add_command(
            label="New folder", accelerator="Ctrl+Shift+N", command=self._new_folder
        )
        file_menu.add_separator()
        file_menu.add_command(label="Save note", accelerator="Ctrl+S", command=self._save_clicked)
        file_menu.add_separator()
        file_menu.add_command(label="Import Markdown...", command=self._import_files)
        file_menu.add_command(label="Import folder...", command=self._import_folder)
        file_menu.add_separator()
        file_menu.add_command(
            label="Export note as Markdown...", command=self._export_note_markdown
        )
        file_menu.add_command(label="Export note as HTML...", command=self._export_note_html)
        file_menu.add_command(
            label="Export vault as Markdown...", command=self._export_vault_markdown
        )
        file_menu.add_command(
            label="Export vault as HTML report...", command=self._export_vault_html
        )
        file_menu.add_separator()
        file_menu.add_command(label="Back up vault...", command=self._backup_vault)
        file_menu.add_command(
            label="Settings...", accelerator="Ctrl+,", command=self._open_settings
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(
            label="Undo", accelerator="Ctrl+Z", command=partial(self._editor_event, "<<Undo>>")
        )
        edit_menu.add_command(
            label="Redo", accelerator="Ctrl+Y", command=partial(self._editor_event, "<<Redo>>")
        )
        edit_menu.add_separator()
        for label, sequence in (
            ("Cut", "<<Cut>>"),
            ("Copy", "<<Copy>>"),
            ("Paste", "<<Paste>>"),
        ):
            edit_menu.add_command(
                label=label,
                command=partial(self._editor_event, sequence),
            )
        edit_menu.add_command(label="Select all", accelerator="Ctrl+A", command=self._select_all)
        edit_menu.add_separator()
        edit_menu.add_command(label="Find", accelerator="Ctrl+F", command=self._find_current)
        edit_menu.add_command(
            label="Find and replace", accelerator="Ctrl+H", command=self._replace_current
        )
        edit_menu.add_command(
            label="Search vault", accelerator="Ctrl+Shift+F", command=self._open_search
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Note properties", accelerator="F2", command=self._edit_properties
        )
        menubar.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(
            label="Dashboard",
            accelerator="Ctrl+Shift+D",
            command=self._show_dashboard,
        )
        view_menu.add_separator()
        view_menu.add_command(label="Write mode", command=lambda: self._set_view_mode("write"))
        view_menu.add_command(label="Split mode", command=lambda: self._set_view_mode("split"))
        view_menu.add_command(label="Preview mode", command=lambda: self._set_view_mode("preview"))
        view_menu.add_command(
            label="Cycle view mode", accelerator="Ctrl+E", command=self._cycle_view
        )
        self._sync_scroll_var = tk.BooleanVar(self, value=self._sync_preview_scroll)
        view_menu.add_checkbutton(
            label="Synchronize preview scrolling",
            variable=self._sync_scroll_var,
            command=self._toggle_sync_scroll,
        )
        view_menu.add_separator()
        view_menu.add_command(label="Use dark theme", command=self._use_dark_theme)
        view_menu.add_command(label="Use light theme", command=self._use_light_theme)
        view_menu.add_separator()
        view_menu.add_command(label="Larger text", command=lambda: self._change_font_size(1))
        view_menu.add_command(label="Smaller text", command=lambda: self._change_font_size(-1))
        menubar.add_cascade(label="View", menu=view_menu)

        notes_menu = tk.Menu(menubar, tearoff=0)
        notes_menu.add_command(label="New note", command=self._new_note)
        notes_menu.add_command(label="New folder", command=self._new_folder)
        notes_menu.add_separator()
        notes_menu.add_command(label="Rename...", command=self._rename_current)
        notes_menu.add_command(label="Duplicate", command=self._duplicate_current)
        notes_menu.add_command(label="Move to folder...", command=self._move_current)
        notes_menu.add_command(
            label="Pin or unpin", accelerator="Ctrl+Shift+P", command=self._toggle_pin_current
        )
        notes_menu.add_separator()
        notes_menu.add_command(label="Move to trash", command=self._delete_current)
        notes_menu.add_command(label="Open trash...", command=self._open_trash)
        menubar.add_cascade(label="Notes", menu=notes_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label="Keyboard shortcuts", accelerator="F1", command=self._show_shortcuts
        )
        help_menu.add_command(label="About RedScribe", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self._toplevel.configure(menu=menubar)

    def _build_ui(self) -> None:
        palette = self._theme.palette
        self.configure(bg=palette.bg)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_header()
        self.panes = ttk.PanedWindow(self, orient="horizontal")
        self.panes.grid(row=1, column=0, sticky="nsew")
        self._build_sidebar()
        self._build_content()
        self.panes.add(self.sidebar, weight=0)
        self.panes.add(self.content, weight=1)
        self._build_statusbar()
        self._bind_widget_shortcuts(self.editor.text)
        self._bind_widget_shortcuts(self.preview.text)
        self.editor.bind_change(self._on_editor_change)
        self.editor.text.bind("<KeyRelease>", self._update_cursor, add="+")
        self.editor.text.bind("<ButtonRelease-1>", self._update_cursor, add="+")
        self.title_var.trace_add("write", self._on_title_changed)
        self._apply_view_mode()
        self._bind_shortcuts()

    def _build_header(self) -> None:
        palette = self._theme.palette
        height = max(HEADER_HEIGHT, self._theme.base_size * 3 + 24)
        header = tk.Frame(self, bg=palette.surface, height=height)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(0, weight=1)
        inner = tk.Frame(header, bg=palette.surface)
        inner.pack(fill="both", expand=True, padx=24, pady=11)
        brand = tk.Frame(inner, bg=palette.surface)
        brand.pack(side="left")
        tk.Label(
            brand,
            text="REDSCRIBE",
            bg=palette.surface,
            fg=palette.accent,
            font=self._theme.font(1, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="LOCAL SECURITY NOTEBOOK",
            bg=palette.surface,
            fg=palette.faint,
            font=self._theme.font(-3, "bold"),
            anchor="w",
        ).pack(anchor="w", pady=(1, 0))

        actions = tk.Frame(inner, bg=palette.surface)
        actions.pack(side="right")
        new_button = ttk.Button(
            actions,
            text="+ New note",
            style="Accent.TButton",
            command=self._new_note,
        )
        new_button.pack(side="right", padx=(8, 0))
        jump = ttk.Button(
            actions,
            text="Jump to a note   Ctrl+P",
            style="Jump.TButton",
            width=27,
            command=self._open_quick_switch,
        )
        jump.pack(side="right", padx=(18, 0))
        Tooltip(jump, "Quick switch between notes (Ctrl+P)", self._theme)
        search = ttk.Button(actions, text="Search", style="Tool.TButton", command=self._open_search)
        search.pack(side="right", padx=(8, 0))
        snippets = ttk.Button(
            actions, text="Snippets", style="Tool.TButton", command=self._open_snippets
        )
        snippets.pack(side="right", padx=(8, 0))
        self.theme_button = ttk.Button(
            actions,
            text="☀" if self._theme_name == "dark" else "☾",
            style="Tool.TButton",
            width=3,
            command=self._toggle_theme,
        )
        self.theme_button.pack(side="right", padx=(8, 0))
        Tooltip(
            self.theme_button,
            "Switch to light theme" if self._theme_name == "dark" else "Switch to dark theme",
            self._theme,
        )
        divider(header, self._theme).pack(fill="x", side="bottom")

    def _build_sidebar(self) -> None:
        palette = self._theme.palette
        self.sidebar = tk.Frame(self.panes, bg=palette.surface)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.rowconfigure(2, weight=1)
        head = tk.Frame(self.sidebar, bg=palette.surface)
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(15, 8))
        tk.Label(
            head,
            text="VAULT",
            bg=palette.surface,
            fg=palette.faint,
            font=self._theme.font(-2, "bold"),
            anchor="w",
        ).pack(side="left")
        self.tree_count_label = tk.Label(
            head,
            text="",
            bg=palette.surface,
            fg=palette.faint,
            font=self._theme.font(-2),
        )
        self.tree_count_label.pack(side="left", padx=(8, 0))
        folder_button = ttk.Button(
            head,
            text="+ Folder",
            style="Subtle.TButton",
            command=self._new_folder,
        )
        folder_button.pack(side="right")

        self.tree_filter = SearchBox(
            self.sidebar,
            self._theme,
            "Filter tree or #tag",
            background=palette.surface_alt,
        )
        self.tree_filter.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 9))
        self.tree_filter.bind_change(self._schedule_tree_refresh)
        self.tree_filter.entry.bind("<Down>", self._focus_tree, add="+")
        self.tree_filter.entry.bind("<Escape>", self._clear_tree_filter, add="+")

        tree_host = tk.Frame(self.sidebar, bg=palette.surface)
        tree_host.grid(row=2, column=0, sticky="nsew")
        tree_host.columnconfigure(0, weight=1)
        tree_host.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_host, show="tree", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(tree_host, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.column("#0", width=232, stretch=True)
        self.tree.tag_configure("folder", font=self._theme.font(0, "bold"))
        self.tree.tag_configure(
            "pinned",
            foreground=palette.accent,
            font=self._theme.font(0, "bold"),
        )
        for status in STATUSES:
            if status == "todo":
                continue
            self.tree.tag_configure(
                f"status_{status}",
                foreground=status_color(self._theme, status),
            )
        self.tree.tag_configure(
            "drop_target",
            background=palette.accent_soft,
            foreground=palette.text,
        )
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open, add="+")
        self.tree.bind("<<TreeviewClose>>", self._on_tree_close, add="+")
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._on_tree_context)
        self.tree.bind("<ButtonPress-1>", self._on_tree_drag_start, add="+")
        self.tree.bind("<B1-Motion>", self._on_tree_drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_drag_end, add="+")
        self.tree.bind("<Delete>", lambda _event: self._delete_selected_tree())
        self.tree.bind("<F2>", lambda _event: self._rename_selected_tree())
        self.tree.bind(
            "<Control-Up>",
            lambda _event: self._reorder_selected_tree(-1),
        )
        self.tree.bind(
            "<Control-Down>",
            lambda _event: self._reorder_selected_tree(1),
        )

        footer = tk.Frame(self.sidebar, bg=palette.surface)
        footer.grid(row=3, column=0, sticky="ew")
        divider(footer, self._theme).pack(fill="x")
        footer_inner = tk.Frame(footer, bg=palette.surface)
        footer_inner.pack(fill="x", padx=16, pady=9)
        self.vault_stats_label = tk.Label(
            footer_inner,
            text="",
            bg=palette.surface,
            fg=palette.faint,
            font=self._theme.font(-2),
            anchor="w",
        )
        self.vault_stats_label.pack(side="left")
        self.trash_button = ttk.Button(
            footer_inner,
            text="Trash",
            style="Subtle.TButton",
            command=self._open_trash,
        )
        self.trash_button.pack(side="right")

    def _build_content(self) -> None:
        palette = self._theme.palette
        self.content = tk.Frame(self.panes, bg=palette.bg)
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        self.dashboard = Dashboard(
            self.content,
            self._theme,
            vault=self._vault,
            on_open=self._dashboard_open,
            on_new_note=self._new_note,
            on_search=self._open_search,
            on_snippets=self._open_snippets,
            on_tag=self._filter_by_tag,
            on_view_flags=self._open_flags,
            on_load_demo=self._load_demo,
            on_import=self._import_files,
        )
        self.dashboard.grid(row=0, column=0, sticky="nsew")
        self.note_frame = self._build_note_frame()
        self.note_frame.grid(row=0, column=0, sticky="nsew")
        self.note_frame.grid_remove()

    def _build_note_frame(self) -> tk.Frame:
        palette = self._theme.palette
        frame = tk.Frame(self.content, bg=palette.surface)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        head = tk.Frame(frame, bg=palette.surface)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        self.path_label = tk.Label(
            head,
            text="",
            bg=palette.surface,
            fg=palette.faint,
            font=self._theme.font(-2),
            anchor="w",
        )
        self.path_label.grid(row=0, column=0, sticky="ew", padx=26, pady=(13, 0))
        self.title_var = tk.StringVar()
        self.title_entry = tk.Entry(
            head,
            textvariable=self.title_var,
            bg=palette.surface,
            fg=palette.text,
            insertbackground=palette.accent,
            selectbackground=palette.selection,
            selectforeground=palette.text,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=self._theme.font(6, "bold"),
        )
        self.title_entry.grid(row=1, column=0, sticky="ew", padx=22, pady=(2, 5))
        self.meta_row = tk.Frame(head, bg=palette.surface)
        self.meta_row.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 12))
        divider(head, self._theme).grid(row=3, column=0, sticky="ew")

        toolbar = tk.Frame(frame, bg=palette.surface)
        toolbar.grid(row=1, column=0, sticky="ew")
        view_bar = tk.Frame(toolbar, bg=palette.surface)
        view_bar.pack(side="left", padx=20, pady=8)
        self.view_buttons = {}
        for mode, label in (
            ("write", "Write"),
            ("split", "Split"),
            ("preview", "Preview"),
        ):
            button = ttk.Button(
                view_bar,
                text=label,
                style="View.TButton",
                command=partial(self._set_view_mode, mode),
            )
            button.pack(side="left", padx=(0, 5))
            self.view_buttons[mode] = button
        self.word_label = tk.Label(
            toolbar,
            text="",
            bg=palette.surface,
            fg=palette.faint,
            font=self._theme.font(-2),
        )
        self.word_label.pack(side="right", padx=24)
        self.sync_scroll_check = ttk.Checkbutton(
            toolbar,
            text="Sync scroll",
            variable=self._sync_scroll_var,
            command=self._toggle_sync_scroll,
            style="Surface.TCheckbutton",
        )
        self.sync_scroll_check.pack(side="right", padx=(0, 16))
        Tooltip(
            self.sync_scroll_check,
            "Keep the preview aligned with the editor in split view",
            self._theme,
        )
        divider(toolbar, self._theme).pack(fill="x", side="bottom")

        self.body_panes = ttk.PanedWindow(frame, orient="horizontal")
        self.body_panes.grid(row=2, column=0, sticky="nsew")
        self.editor = MarkdownEditor(self.body_panes, self._theme, on_change=self._on_editor_change)
        self.preview = MarkdownPreview(self.body_panes, self._theme)
        self.editor.set_scroll_callback(self._on_editor_scroll)
        self.preview.set_scroll_callback(self._on_preview_scroll)
        return frame

    def _build_statusbar(self) -> None:
        palette = self._theme.palette
        height = max(STATUSBAR_HEIGHT, self._theme.base_size * 2 + 6)
        status = tk.Frame(self, bg=palette.surface, height=height)
        status.grid(row=2, column=0, sticky="ew")
        status.grid_propagate(False)
        status.columnconfigure(0, weight=1)
        divider(status, self._theme).pack(fill="x", side="top")
        inner = tk.Frame(status, bg=palette.surface)
        inner.pack(fill="both", expand=True, padx=16, pady=4)
        self.status_vault_label = tk.Label(
            inner,
            text=truncate(self._vault.display_path, 52),
            bg=palette.surface,
            fg=palette.faint,
            font=self._theme.font(-2),
        )
        self.status_vault_label.pack(side="left")
        Tooltip(self.status_vault_label, self._vault.display_path, self._theme)
        self.status_message = tk.Label(
            inner,
            text="",
            bg=palette.surface,
            fg=palette.muted,
            font=self._theme.font(-2),
            anchor="w",
        )
        self.status_message.pack(side="left", padx=(18, 0))
        self.save_label = tk.Label(
            inner,
            text="",
            bg=palette.surface,
            fg=palette.green,
            font=self._theme.font(-2, "bold"),
            width=14,
            anchor="e",
        )
        self.save_label.pack(side="right")
        self.cursor_label = tk.Label(
            inner,
            text="",
            bg=palette.surface,
            fg=palette.faint,
            font=self._theme.font(-2),
            width=14,
            anchor="e",
        )
        self.cursor_label.pack(side="right", padx=(0, 12))
        self._set_save_state("saved")

    def _bind_shortcuts(self) -> None:
        bindings: tuple[tuple[str, Callable[[], None]], ...] = (
            ("<Control-n>", self._new_note),
            ("<Control-Shift-N>", self._new_folder),
            ("<Control-s>", self._save_clicked),
            ("<Control-Shift-S>", self._open_snippets),
            ("<Control-f>", self._find_current),
            ("<Control-h>", self._replace_current),
            ("<Control-Shift-F>", self._open_search),
            ("<Control-e>", self._cycle_view),
            ("<Control-p>", self._open_quick_switch),
            ("<Control-Shift-D>", self._show_dashboard_menu),
            ("<Control-Shift-P>", self._toggle_pin_current),
            ("<Control-comma>", self._open_settings),
            ("<F1>", self._show_shortcuts),
            ("<F2>", self._edit_properties),
        )
        for sequence, callback in bindings:
            self._toplevel.bind(sequence, self._shortcut(callback))

    def _bind_widget_shortcuts(self, widget: tk.Text) -> None:
        bindings: tuple[tuple[str, Callable[[], None]], ...] = (
            ("<Control-n>", self._new_note),
            ("<Control-Shift-N>", self._new_folder),
            ("<Control-p>", self._open_quick_switch),
            ("<Control-e>", self._cycle_view),
            ("<Control-f>", self._find_current),
            ("<Control-h>", self._replace_current),
        )
        for sequence, callback in bindings:
            widget.bind(sequence, self._shortcut(callback), add="+")

    @staticmethod
    def _shortcut(callback: Callable[[], None]) -> Callable[[tk.Event], str]:
        def handler(_event: tk.Event) -> str:
            callback()
            return "break"

        return handler

    def _initialize_start_view(self) -> None:
        start_id = self._setting_int("ui.last_note", 0, minimum=0, maximum=2**31)
        if self._restore_last and start_id:
            node = self._vault.get_node(start_id)
            if node is not None and node.is_note and self.open_node(start_id):
                return
        self._show_dashboard(save=False)

    def _update_sidebar_stats(self) -> None:
        stats = self._vault.stats()
        self.tree_count_label.configure(text=f"{stats.notes}")
        self.vault_stats_label.configure(
            text=(
                f"{stats.notes} {pluralize(stats.notes, 'note')}  ·  "
                f"{stats.folders} {pluralize(stats.folders, 'folder')}"
            )
        )
        self.trash_button.configure(text=f"Trash {stats.trashed}" if stats.trashed else "Trash")

    def _schedule_tree_refresh(self) -> None:
        if self._tree_job is not None:
            self.after_cancel(self._tree_job)
        self._tree_job = self.after(110, self._refresh_tree)

    def _refresh_tree(self) -> None:
        self._tree_job = None
        if not self.winfo_exists():
            return
        query = self.tree_filter.get_value()
        self._syncing_tree = True
        try:
            for item in self.tree.get_children():
                self.tree.delete(item)
            nodes = self._vault.live_nodes()
            by_parent: dict[int | None, list[Node]] = {}
            parent_map: dict[int, int | None] = {}
            for node in nodes:
                by_parent.setdefault(node.parent_id, []).append(node)
                parent_map[node.id] = node.parent_id
            for children in by_parent.values():
                children.sort(key=lambda item: (item.sort_order, item.title.casefold()))

            visible: set[int] | None = None
            if query:
                visible = self._matching_node_ids(nodes, by_parent, parent_map, query)
            ancestors: set[str] = set()
            if self._note is not None:
                parent = parent_map.get(self._note.id)
                while parent is not None and str(parent) not in ancestors:
                    ancestors.add(str(parent))
                    parent = parent_map.get(parent)
            current = self._note.id if self._note is not None else None

            def insert_children(parent_id: int | None, parent_iid: str) -> None:
                for node in by_parent.get(parent_id, []):
                    if visible is not None and node.id not in visible:
                        continue
                    iid = str(node.id)
                    if node.is_folder:
                        is_open = bool(query) or iid not in self._collapsed
                        if iid in ancestors:
                            is_open = True
                        self.tree.insert(
                            parent_iid,
                            "end",
                            iid=iid,
                            text=f"▸ {node.title}",
                            open=is_open,
                            tags=("folder",),
                        )
                        insert_children(node.id, iid)
                        continue
                    if node.pinned:
                        icon = "★"
                        tags: tuple[str, ...] = ("pinned",)
                    else:
                        icon = "◆"
                        tags = (f"status_{node.status}",) if node.status != "todo" else ()
                    self.tree.insert(
                        parent_iid,
                        "end",
                        iid=iid,
                        text=f"{icon} {node.title}",
                        tags=tags,
                    )
                    if node.id == current:
                        self.tree.selection_set(iid)

            insert_children(None, "")
            if current is not None:
                iid = str(current)
                if self.tree.exists(iid):
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
            if query and not visible:
                self._set_status(f'No tree matches for "{query}"')
        finally:
            self._syncing_tree = False

    def _matching_node_ids(
        self,
        nodes: list[Node],
        by_parent: dict[int | None, list[Node]],
        parent_map: dict[int, int | None],
        query: str,
    ) -> set[int]:
        tag_only = query.startswith("#")
        needle = query.lstrip("#").casefold()
        matched: set[int] = set()
        matched_folders: list[int] = []
        for node in nodes:
            if tag_only:
                haystack = node.tags.casefold()
            else:
                haystack = " ".join(
                    (
                        node.title,
                        node.tags,
                        node.target,
                        node.content,
                    )
                ).casefold()
            if needle and needle in haystack:
                matched.add(node.id)
                if node.is_folder:
                    matched_folders.append(node.id)

        def add_descendants(node_id: int) -> None:
            for child in by_parent.get(node_id, []):
                if child.id in matched:
                    continue
                matched.add(child.id)
                if child.is_folder:
                    add_descendants(child.id)
                else:
                    add_descendants(child.id)

        for node in nodes:
            if node.is_folder and node.id in matched:
                add_descendants(node.id)
        for folder_id in matched_folders:
            parent = parent_map.get(folder_id)
            while parent is not None:
                matched.add(parent)
                parent = parent_map.get(parent)
        for node_id in list(matched):
            parent = parent_map.get(node_id)
            while parent is not None and parent not in matched:
                matched.add(parent)
                parent = parent_map.get(parent)
        return matched

    def _on_tree_select(self, _event: tk.Event | None = None) -> None:
        if self._syncing_tree:
            return
        selection = self.tree.selection()
        if not selection:
            return
        try:
            node_id = int(selection[0])
        except ValueError:
            return
        node = self._vault.get_node(node_id)
        if node is None:
            return
        if node.is_folder:
            self._selected_folder_id = node.id
            return
        if self._note is not None and self._note.id == node.id:
            return
        self._selected_folder_id = node.parent_id
        self.open_node(node.id)

    def _on_tree_open(self, _event: tk.Event | None = None) -> None:
        if self._syncing_tree:
            return
        iid = self.tree.focus()
        if iid:
            self._collapsed.discard(iid)

    def _on_tree_close(self, _event: tk.Event | None = None) -> None:
        if self._syncing_tree:
            return
        iid = self.tree.focus()
        if iid:
            self._collapsed.add(iid)

    def _on_tree_double_click(self, event: tk.Event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        node = self._vault.get_node(int(iid))
        if node is None:
            return
        if node.is_folder:
            is_open = bool(self.tree.item(iid, "open"))
            self.tree.item(iid, open=not is_open)
            if is_open:
                self._collapsed.add(iid)
            else:
                self._collapsed.discard(iid)
        else:
            self.open_node(node.id)

    def _on_tree_context(self, event: tk.Event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        node = self._vault.get_node(int(iid))
        if node is None:
            return
        if iid not in self.tree.selection():
            self._syncing_tree = True
            try:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
            finally:
                self._syncing_tree = False
        self._selected_folder_id = node.id if node.is_folder else node.parent_id
        menu = tk.Menu(self, tearoff=0)
        if node.is_folder:
            menu.add_command(
                label="New note here...",
                command=lambda: self._new_note(node.id),
            )
            menu.add_command(
                label="New folder here...",
                command=lambda: self._new_folder(node.id),
            )
            menu.add_separator()
        menu.add_command(label="Open", command=lambda: self.open_node(node.id))
        if not node.is_folder:
            menu.add_command(
                label="Pin or unpin",
                command=lambda: self._toggle_pin_node(node.id),
            )
        menu.add_command(
            label="Move up",
            accelerator="Ctrl+Up",
            command=lambda: self._reorder_selected_tree(-1),
        )
        menu.add_command(
            label="Move down",
            accelerator="Ctrl+Down",
            command=lambda: self._reorder_selected_tree(1),
        )
        menu.add_separator()
        menu.add_command(label="Rename...", command=lambda: self._rename_node(node))
        menu.add_command(label="Duplicate", command=lambda: self._duplicate_node(node))
        menu.add_command(label="Move to folder...", command=lambda: self._move_node(node))
        menu.add_separator()
        menu.add_command(label="Move to trash", command=lambda: self._delete_node(node))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_tree_drag_start(self, event: tk.Event) -> None:
        self._reset_tree_drag()
        if self.tree.identify_element(event.x, event.y) == "Treeitem.indicator":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        node = self._vault.get_node(int(iid))
        if node is None:
            return
        self._tree_drag = _TreeDrag(
            source=node,
            start_x=event.x,
            start_y=event.y,
            blocked=self._descendant_folder_ids(node),
        )

    def _on_tree_drag_motion(self, event: tk.Event) -> None:
        drag = self._tree_drag
        if drag is None:
            return
        if not drag.active:
            if (
                abs(event.x - drag.start_x) < _TREE_DRAG_THRESHOLD
                and abs(event.y - drag.start_y) < _TREE_DRAG_THRESHOLD
            ):
                return
            drag.active = True
            self.tree.configure(cursor="fleur")
        if not 0 <= event.y <= self.tree.winfo_height():
            self._clear_drop_highlight(drag)
            drag.plan = None
            drag.description = ""
            return
        target_iid = self.tree.identify_row(event.y)
        if not target_iid:
            self._clear_drop_highlight(drag)
            drag.plan = (None, None)
            drag.description = "Move to the vault root"
            self._set_status("Drop to move to the vault root")
            return
        target = self._vault.get_node(int(target_iid))
        if target is None:
            self._clear_drop_highlight(drag)
            drag.plan = None
            return
        bbox = self.tree.bbox(target_iid)
        ratio = ((event.y - bbox[1]) / bbox[3]) if bbox and bbox[3] else 0.5
        plan, description = self._tree_drop_plan(drag.source, drag.blocked, target, ratio)
        drag.plan = plan
        drag.description = description
        if plan is None:
            self._clear_drop_highlight(drag)
            if description:
                self._set_status(description)
            return
        self._highlight_drop_target(drag, target_iid)
        self._set_status(description)

    def _tree_drop_plan(
        self,
        source: Node,
        blocked: set[int],
        target: Node,
        ratio: float,
    ) -> tuple[tuple[int | None, int | None] | None, str]:
        if target.id == source.id:
            return None, ""
        if target.is_folder and 0.25 <= ratio <= 0.75:
            if target.id in blocked:
                return None, "A folder cannot move inside itself"
            return (target.id, None), f'Move into "{target.title}"'
        parent_id = target.parent_id
        if parent_id is not None and parent_id in blocked:
            return None, "A folder cannot move inside itself"
        siblings = self._vault.children(parent_id)
        identifiers = [child.id for child in siblings]
        if target.id not in identifiers:
            return None, ""
        if ratio < 0.5:
            return (parent_id, target.id), f'Place before "{target.title}"'
        index = identifiers.index(target.id)
        before_id = identifiers[index + 1] if index + 1 < len(identifiers) else None
        return (parent_id, before_id), f'Place after "{target.title}"'

    def _highlight_drop_target(self, drag: _TreeDrag, iid: str) -> None:
        if drag.hover_iid == iid:
            return
        self._clear_drop_highlight(drag)
        tags = tuple(self.tree.item(iid, "tags"))
        drag.hover_iid = iid
        drag.hover_tags = tags
        self.tree.item(iid, tags=("drop_target", *tags))

    def _clear_drop_highlight(self, drag: _TreeDrag) -> None:
        if drag.hover_iid is not None and self.tree.exists(drag.hover_iid):
            self.tree.item(drag.hover_iid, tags=drag.hover_tags)
        drag.hover_iid = None
        drag.hover_tags = ()

    def _reset_tree_drag(self) -> None:
        if self._tree_drag is not None:
            self._clear_drop_highlight(self._tree_drag)
        self._tree_drag = None
        with suppress(tk.TclError):
            self.tree.configure(cursor="")

    def _on_tree_drag_end(self, _event: tk.Event | None = None) -> str | None:
        drag = self._tree_drag
        if drag is None or not drag.active:
            self._reset_tree_drag()
            return None
        source_id = drag.source.id
        plan = drag.plan
        self._reset_tree_drag()
        if plan is not None:
            parent_id, before_id = plan
            self._apply_tree_move(source_id, parent_id, before_id)
        return "break"

    def _reorder_selected_tree(self, offset: int) -> str:
        node = self._selected_tree_node()
        if node is None or not self._save_if_needed():
            return "break"
        siblings = self._vault.children(node.parent_id)
        identifiers = [child.id for child in siblings]
        if node.id not in identifiers:
            return "break"
        index = identifiers.index(node.id)
        if not 0 <= index + offset < len(identifiers):
            self._set_status("Item is already at the edge of its folder")
            return "break"
        try:
            updated = self._vault.reorder_node(node.id, offset)
        except ValueError as exc:
            messagebox.showerror("Could not reorder item", str(exc), parent=self)
            return "break"
        if updated is not None:
            if self._note is not None and self._note.id == updated.id:
                self._note = updated
            self._refresh_tree()
            self._select_tree_item(updated.id)
            self._update_header_path()
            self._set_status(f'Moved "{updated.title}" {"up" if offset < 0 else "down"}')
        return "break"

    def _apply_tree_move(
        self,
        node_id: int,
        parent_id: int | None,
        before_id: int | None,
    ) -> bool:
        if not self._save_if_needed():
            return False
        try:
            updated = self._vault.move_node(node_id, parent_id, before_id=before_id)
        except ValueError as exc:
            messagebox.showerror("Could not move item", str(exc), parent=self)
            return False
        if self._note is not None and self._note.id == updated.id:
            self._note = updated
        self._refresh_tree()
        self._select_tree_item(updated.id)
        self._selected_folder_id = updated.parent_id
        self._update_header_path()
        self._set_status(f'Moved "{updated.title}" to its new position')
        return True

    def _select_tree_item(self, node_id: int) -> None:
        iid = str(node_id)
        if not self.tree.exists(iid):
            return
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)

    def _focus_tree(self, _event: tk.Event | None = None) -> str:
        items = self.tree.get_children()
        if items:
            self.tree.focus_set()
            self.tree.focus(items[0])
            self.tree.selection_set(items[0])
        return "break"

    def _clear_tree_filter(self, _event: tk.Event | None = None) -> str:
        self.tree_filter.set_value("")
        self.tree.focus_set()
        return "break"

    def _matching_folder_choices(self, *, exclude: set[int] | None = None) -> list[tuple[str, int]]:
        blocked = exclude or set()
        nodes = self._vault.live_nodes()
        by_parent: dict[int | None, list[Node]] = {}
        for node in nodes:
            by_parent.setdefault(node.parent_id, []).append(node)
        for children in by_parent.values():
            children.sort(key=lambda item: (item.sort_order, item.title.casefold()))
        choices: list[tuple[str, int]] = []

        def walk(parent_id: int | None, prefix: str) -> None:
            for node in by_parent.get(parent_id, []):
                if not node.is_folder or node.id in blocked:
                    continue
                label = f"{prefix} / {node.title}" if prefix else node.title
                choices.append((label, node.id))
                walk(node.id, label)

        walk(None, "")
        counts: dict[str, int] = {}
        for label, _identifier in choices:
            counts[label] = counts.get(label, 0) + 1
        return [
            (f"{label}  [{identifier}]" if counts[label] > 1 else label, identifier)
            for label, identifier in choices
        ]

    def _descendant_folder_ids(self, node: Node) -> set[int]:
        if not node.is_folder:
            return set()
        nodes = self._vault.live_nodes()
        by_parent: dict[int | None, list[Node]] = {}
        for child in nodes:
            by_parent.setdefault(child.parent_id, []).append(child)
        result = {node.id}
        stack = [node.id]
        while stack:
            current = stack.pop()
            for child in by_parent.get(current, []):
                if child.is_folder and child.id not in result:
                    result.add(child.id)
                    stack.append(child.id)
        return result

    def _default_parent(self) -> int | None:
        selection = self.tree.selection()
        if selection:
            node = self._vault.get_node(int(selection[0]))
            if node is not None:
                return node.id if node.is_folder else node.parent_id
        if self._selected_folder_id is not None:
            folder = self._vault.get_node(self._selected_folder_id)
            if folder is not None and folder.is_folder:
                return folder.id
        if self._note is not None:
            return self._note.parent_id
        return None

    def _new_note(self, folder_id: int | None = None) -> None:
        if not self._save_if_needed():
            return
        parent = self._default_parent() if folder_id is None else folder_id
        last_template = str(self._vault.get_setting("ui.last_template", "blank") or "blank")
        dialog = NewNoteDialog(
            self,
            self._theme,
            templates=TEMPLATES,
            folders=self._matching_folder_choices(),
            initial_template=last_template,
            initial_folder_id=parent,
        )
        result = dialog.show(590)
        if not isinstance(result, dict):
            return
        title = str(result.get("title", "")).strip()
        if not title:
            return
        target = str(result.get("target", "")).strip()
        template = result.get("template")
        template_key = str(getattr(template, "key", "blank"))
        selected = get_template(template_key)
        content = render_template(selected, title, target)
        destination = result.get("folder_id")
        parent_id = destination if isinstance(destination, int) else None
        try:
            node = self._vault.create_node(
                title,
                parent_id,
                kind="note",
                content=content,
                tags=selected.tags,
                target=target,
                status=selected.status,
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("Could not create note", str(exc), parent=self)
            return
        self._vault.set_setting("ui.last_template", selected.key)
        self._clear_filter_for_new_item()
        self._refresh_tree()
        self._update_sidebar_stats()
        self.open_node(node.id)
        self._set_status(f'Created "{node.title}"')

    def _new_folder(self, parent_id: int | None = None) -> None:
        if not self._save_if_needed():
            return
        parent = self._default_parent() if parent_id is None else parent_id
        dialog = PromptDialog(
            self,
            self._theme,
            title="New folder",
            label="Folder name",
            initial="New folder",
            confirm_text="Create folder",
        )
        result = dialog.show(280)
        if not isinstance(result, str) or not result.strip():
            return
        try:
            node = self._vault.create_node(result.strip(), parent, kind="folder")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Could not create folder", str(exc), parent=self)
            return
        self._clear_filter_for_new_item()
        self._refresh_tree()
        self._update_sidebar_stats()
        iid = str(node.id)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
        self._selected_folder_id = node.id
        self._set_status(f'Created folder "{node.title}"')

    def _clear_filter_for_new_item(self) -> None:
        if self.tree_filter.get_value():
            self.tree_filter.set_value("")
            if self._tree_job is not None:
                self.after_cancel(self._tree_job)
                self._tree_job = None

    def open_node(self, node_id: int, *, force: bool = False) -> bool:
        node = self._vault.get_node(node_id)
        if node is None or node.is_folder:
            return False
        if not force and self._note is not None and self._note.id == node_id:
            return True
        if not self._save_if_needed():
            self._sync_tree_selection()
            return False
        node = self._vault.get_node(node_id)
        if node is None:
            return False
        self._loading = True
        try:
            self._note = node
            self.title_var.set(node.title)
            self.editor.set_text(node.content)
            self.preview.set_markdown(node.content, preserve_scroll=False)
            self._dirty = False
            self._preview_stale = False
            self._render_note_meta()
            self.note_frame.grid()
            self.dashboard.grid_remove()
            self._apply_view_mode()
            self._sync_tree_selection()
            self._update_document_stats()
            self._set_save_state("saved")
            self._update_window_title()
            self._vault.set_setting("ui.last_note", str(node.id))
        finally:
            self._loading = False
        self._restore_sashes()
        return True

    def _dashboard_open(self, node_id: int) -> None:
        self.open_node(node_id)

    def _show_dashboard_menu(self) -> None:
        self._show_dashboard()

    def _show_dashboard(self, *, save: bool = True) -> bool:
        if save and not self._save_if_needed():
            return False
        if self._note is not None:
            self._note = None
        self._dirty = False
        self._syncing_tree = True
        try:
            selection = self.tree.selection()
            if selection:
                self.tree.selection_remove(*selection)
        finally:
            self._syncing_tree = False
        self.note_frame.grid_remove()
        self.dashboard.grid()
        self.dashboard.refresh()
        self._toplevel.title("RedScribe")
        self._set_save_state("saved")
        self._update_document_stats()
        return True

    def _sync_tree_selection(self) -> None:
        if self._note is None:
            return
        iid = str(self._note.id)
        if not self.tree.exists(iid):
            return
        parent = self._note.parent_id
        while parent is not None:
            parent_iid = str(parent)
            if not self.tree.exists(parent_iid):
                break
            self.tree.item(parent_iid, open=True)
            parent_node = self._vault.get_node(parent)
            parent = parent_node.parent_id if parent_node is not None else None
        self._syncing_tree = True
        try:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
        finally:
            self._syncing_tree = False

    def _render_note_meta(self) -> None:
        if self._note is None:
            return
        node = self._note
        palette = self._theme.palette
        for child in self.meta_row.winfo_children():
            child.destroy()
        path = self._vault.path_of(node.id, include_self=False)
        self.path_label.configure(text=path or "Vault root")
        properties = ttk.Button(
            self.meta_row,
            text="Properties",
            style="Subtle.TButton",
            command=self._edit_properties,
        )
        properties.pack(side="right", padx=(8, 0))
        pin = ttk.Button(
            self.meta_row,
            text="Unpin" if node.pinned else "Pin",
            style="Subtle.TButton",
            command=self._toggle_pin_current,
        )
        pin.pack(side="right", padx=(8, 0))
        Pill(
            self.meta_row,
            f"{node.status_label.upper()}",
            self._theme,
            foreground=status_color(self._theme, node.status),
            background=palette.surface,
        ).pack(side="left", padx=(0, 9))
        if node.difficulty:
            Pill(
                self.meta_row,
                node.difficulty_label.upper(),
                self._theme,
                foreground=difficulty_color(self._theme, node.difficulty),
                background=palette.surface,
            ).pack(side="left", padx=(0, 9))
        if node.target:
            tk.Label(
                self.meta_row,
                text=f"◎ {truncate(node.target, 42)}",
                bg=palette.surface,
                fg=palette.muted,
                font=self._theme.font(-1),
            ).pack(side="left", padx=(0, 10))
        tags = node.tag_list
        for tag in tags[:3]:
            TagChip(
                self.meta_row,
                tag,
                self._theme,
                command=partial(self._filter_by_tag, tag),
                background=palette.surface,
            ).pack(side="left", padx=(0, 5))
        if len(tags) > 3:
            tk.Label(
                self.meta_row,
                text=f"+{len(tags) - 3}",
                bg=palette.surface,
                fg=palette.faint,
                font=self._theme.font(-2),
            ).pack(side="left", padx=(0, 5))
        if node.flag:
            Pill(
                self.meta_row,
                "FLAG",
                self._theme,
                foreground=palette.amber,
                background=palette.surface,
            ).pack(side="left", padx=(4, 0))
        if node.updated_at:
            tk.Label(
                self.meta_row,
                text=f"edited {humanize_delta(node.updated_at)}",
                bg=palette.surface,
                fg=palette.faint,
                font=self._theme.font(-2),
            ).pack(side="right", padx=(0, 12))

    def _update_header_path(self) -> None:
        if self._note is None:
            return
        path = self._vault.path_of(self._note.id, include_self=False)
        self.path_label.configure(text=path or "Vault root")

    def _on_editor_change(self) -> None:
        if self._loading or self._note is None:
            return
        self._dirty = True
        self._preview_stale = True
        self._set_save_state("dirty")
        self._update_window_title()
        self._update_document_stats()
        if self._view_mode != "write":
            self._schedule_preview()
        self._schedule_autosave()

    def _on_title_changed(self, *_args: str) -> None:
        if self._loading or self._note is None:
            return
        self._dirty = True
        self._set_save_state("dirty")
        self._update_window_title()
        self._schedule_autosave()

    def _schedule_autosave(self) -> None:
        if self._autosave_job is not None:
            self.after_cancel(self._autosave_job)
        self._autosave_job = self.after(AUTOSAVE_DEBOUNCE_MS, self._autosave)

    def _autosave(self) -> None:
        self._autosave_job = None
        if not self._dirty or self._note is None:
            return
        self.save_now()

    def _save_clicked(self) -> None:
        if self.save_now(notify=True):
            self._set_status("Note saved")

    def save_now(self, *, notify: bool = False) -> bool:
        if self._note is None:
            return True
        if not self._dirty:
            return True
        node_id = self._note.id
        title = self.title_var.get().strip() or "Untitled"
        if not self.title_var.get().strip():
            self._loading = True
            try:
                self.title_var.set(title)
            finally:
                self._loading = False
        self._set_save_state("saving")
        try:
            node = self._vault.update_node(
                node_id,
                title=title,
                content=self.editor.get_text(),
            )
        except Exception as exc:
            LOGGER.exception("Failed to save note %s", node_id)
            self._set_save_state("error")
            if notify:
                messagebox.showerror("Could not save note", str(exc), parent=self)
            return False
        self._note = node
        self._dirty = False
        self._preview_stale = True
        self._set_save_state("saved")
        self._update_window_title()
        if self.tree.exists(str(node.id)):
            icon = "★" if node.pinned else "◆"
            self.tree.item(str(node.id), text=f"{icon} {node.title}")
        return True

    def _save_if_needed(self, *, notify: bool = False) -> bool:
        if not self._dirty:
            return True
        return self.save_now(notify=notify)

    def _set_save_state(self, state: str) -> None:
        palette = self._theme.palette
        labels = {
            "saved": ("Saved", palette.green),
            "dirty": ("Unsaved", palette.amber),
            "saving": ("Saving...", palette.muted),
            "error": ("Save failed", palette.red),
        }
        text, color = labels.get(state, labels["saved"])
        if hasattr(self, "save_label"):
            self.save_label.configure(text=f"● {text}", fg=color)

    def _update_window_title(self) -> None:
        if self._note is None:
            self._toplevel.title("RedScribe")
            return
        marker = " *" if self._dirty else ""
        self._toplevel.title(f"{self.title_var.get().strip() or 'Untitled'}{marker} — RedScribe")

    def _update_document_stats(self) -> None:
        if not hasattr(self, "word_label"):
            return
        if self._note is None:
            self.word_label.configure(text="")
            self.cursor_label.configure(text="")
            return
        words = word_count(self.editor.get_text())
        minutes = (words + 199) // 200
        summary = (
            f"{words:,} {pluralize(words, 'word')}  ·  {minutes or 1} min read"
            if words
            else "Empty note"
        )
        self.word_label.configure(text=summary)
        self._update_cursor()

    def _update_cursor(self, _event: tk.Event | None = None) -> None:
        if self._note is None or not hasattr(self, "cursor_label"):
            return
        line, column = self.editor.cursor_position()
        self.cursor_label.configure(text=f"Ln {line}, Col {column}")

    def _schedule_preview(self) -> None:
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(PREVIEW_DEBOUNCE_MS, self._render_preview)

    def _render_preview(self) -> None:
        self._preview_job = None
        if self._note is None or self._view_mode == "write":
            return
        self.preview.set_markdown(self.editor.get_text(), preserve_scroll=True)
        self._preview_stale = False

    def _on_editor_scroll(self, first: str, _last: str) -> None:
        if self._sync_scroll_ready():
            self._move_scroll(self.preview.text, first)

    def _on_preview_scroll(self, first: str, _last: str) -> None:
        if self._sync_scroll_ready():
            self._move_scroll(self.editor.text, first)

    def _sync_scroll_ready(self) -> bool:
        return self._sync_preview_scroll and not self._syncing_scroll and self._view_mode == "split"

    def _move_scroll(self, widget: tk.Text, first: str) -> None:
        self._syncing_scroll = True
        try:
            widget.yview_moveto(float(first))
        except (ValueError, tk.TclError):
            pass
        finally:
            self._syncing_scroll = False

    def _toggle_sync_scroll(self) -> None:
        self._sync_preview_scroll = bool(self._sync_scroll_var.get())
        self._vault.set_setting(
            "ui.sync_preview_scroll",
            "1" if self._sync_preview_scroll else "0",
        )
        self._set_status(
            "Preview scroll sync on" if self._sync_preview_scroll else "Preview scroll sync off"
        )

    def _apply_view_mode(self) -> None:
        for widget in (self.editor, self.preview):
            if str(widget) in self.body_panes.panes():
                self.body_panes.forget(widget)
        if self._view_mode == "write":
            self.body_panes.add(self.editor, weight=1)
        elif self._view_mode == "preview":
            self.body_panes.add(self.preview, weight=1)
        else:
            self.body_panes.add(self.editor, weight=3)
            self.body_panes.add(self.preview, weight=2)
        for mode, button in self.view_buttons.items():
            button.configure(
                style="ViewActive.TButton" if mode == self._view_mode else "View.TButton"
            )
        if self._view_mode != "write" and self._preview_stale and self._note is not None:
            self._render_preview()
        self._restore_sashes()

    def _set_view_mode(self, mode: str) -> None:
        if mode not in _VIEW_MODES or self._note is None:
            return
        self._view_mode = mode
        self._vault.set_setting("ui.view_mode", mode)
        self._apply_view_mode()

    def _cycle_view(self) -> None:
        if self._note is None:
            return
        index = _VIEW_MODES.index(self._view_mode)
        self._set_view_mode(_VIEW_MODES[(index + 1) % len(_VIEW_MODES)])

    def _find_current(self) -> None:
        if self._note is None:
            self._open_search()
            return
        if self._view_mode == "preview":
            self._set_view_mode("split")
        self.editor.show_find(replace=False)

    def _replace_current(self) -> None:
        if self._note is None:
            return
        if self._view_mode == "preview":
            self._set_view_mode("split")
        self.editor.show_find(replace=True)

    def _editor_event(self, sequence: str) -> None:
        if self._note is None:
            return
        self.editor.text.event_generate(sequence)

    def _select_all(self) -> None:
        if self._note is None:
            return
        self.editor.focus_editor()
        self.editor.text.tag_add("sel", "1.0", "end-1c")
        self.editor.text.mark_set("insert", "1.0")

    def _edit_properties(self) -> None:
        if self._note is None:
            return
        if not self._save_if_needed():
            return
        node = self._vault.get_node(self._note.id)
        if node is None:
            return
        dialog = PropertiesDialog(self, self._theme, node=node)
        result = dialog.show(580)
        if not isinstance(result, dict):
            return
        try:
            updated = self._vault.update_node(
                node.id,
                title=str(result.get("title", node.title)),
                target=str(result.get("target", "")),
                tags=str(result.get("tags", "")),
                flag=str(result.get("flag", "")),
                status=str(result.get("status", "todo")),
                difficulty=str(result.get("difficulty", "")),
                pinned=bool(result.get("pinned", False)),
            )
        except ValueError as exc:
            messagebox.showerror("Could not update note", str(exc), parent=self)
            return
        self._note = updated
        self._loading = True
        try:
            self.title_var.set(updated.title)
        finally:
            self._loading = False
        self._render_note_meta()
        self._refresh_tree()
        self._update_sidebar_stats()
        self._update_window_title()
        self._set_status("Note properties updated")

    def _toggle_pin_current(self) -> None:
        if self._note is None:
            return
        self._toggle_pin_node(self._note.id)

    def _toggle_pin_node(self, node_id: int) -> None:
        node = self._vault.get_node(node_id)
        if node is None or node.is_folder:
            return
        try:
            updated = self._vault.update_node(node.id, pinned=not node.pinned)
        except ValueError as exc:
            messagebox.showerror("Could not update note", str(exc), parent=self)
            return
        if self._note is not None and self._note.id == node_id:
            self._note = updated
            self._render_note_meta()
        self._refresh_tree()
        self._set_status("Note pinned" if updated.pinned else "Note unpinned")

    def _rename_current(self) -> None:
        if self._note is not None:
            self._rename_node(self._note)

    def _rename_selected_tree(self) -> None:
        node = self._selected_tree_node()
        if node is not None:
            self._rename_node(node)

    def _rename_node(self, node: Node) -> None:
        if not self._save_if_needed():
            return
        dialog = PromptDialog(
            self,
            self._theme,
            title="Rename",
            label="Title",
            initial=node.title,
            confirm_text="Rename",
        )
        result = dialog.show(280)
        if not isinstance(result, str) or not result.strip():
            return
        try:
            updated = self._vault.update_node(node.id, title=result.strip())
        except ValueError as exc:
            messagebox.showerror("Could not rename", str(exc), parent=self)
            return
        if self._note is not None and self._note.id == node.id:
            self._note = updated
            self._loading = True
            try:
                self.title_var.set(updated.title)
            finally:
                self._loading = False
            self._render_note_meta()
            self._update_window_title()
        self._refresh_tree()
        self._set_status(f'Renamed to "{updated.title}"')

    def _duplicate_current(self) -> None:
        if self._note is not None:
            self._duplicate_node(self._note)

    def _duplicate_node(self, node: Node) -> None:
        if not self._save_if_needed():
            return
        try:
            copy = self._vault.duplicate_node(node.id)
        except ValueError as exc:
            messagebox.showerror("Could not duplicate", str(exc), parent=self)
            return
        self._refresh_tree()
        self._update_sidebar_stats()
        if copy.is_note and self.open_node(copy.id):
            self._set_status(f'Duplicated as "{copy.title}"')

    def _move_current(self) -> None:
        if self._note is not None:
            self._move_node(self._note)

    def _move_node(self, node: Node) -> None:
        if not self._save_if_needed():
            return
        excluded = self._descendant_folder_ids(node)
        dialog = FolderPickerDialog(
            self,
            self._theme,
            folders=self._matching_folder_choices(exclude=excluded),
            current_folder_id=node.parent_id,
            title=f'Move "{truncate(node.title, 32)}"',
        )
        result = dialog.show(300)
        if not isinstance(result, dict):
            return
        destination = result.get("folder_id")
        parent_id = destination if isinstance(destination, int) else None
        try:
            updated = self._vault.move_node(node.id, parent_id)
        except ValueError as exc:
            messagebox.showerror("Could not move item", str(exc), parent=self)
            return
        if self._note is not None and self._note.id == node.id:
            self._note = updated
            self._update_header_path()
        self._refresh_tree()
        self._set_status(f'Moved "{updated.title}"')

    def _delete_current(self) -> None:
        if self._note is not None:
            self._delete_node(self._note)

    def _delete_selected_tree(self) -> None:
        node = self._selected_tree_node()
        if node is not None:
            self._delete_node(node)

    def _selected_tree_node(self) -> Node | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._vault.get_node(int(selection[0]))

    def _delete_node(self, node: Node) -> None:
        if not self._save_if_needed():
            return
        confirmed = messagebox.askyesno(
            "Move to trash",
            f'Move "{node.title}" to the trash?',
            parent=self,
        )
        if not confirmed:
            return
        current_id = self._note.id if self._note is not None else None
        try:
            affected = self._vault.delete_node(node.id)
        except ValueError as exc:
            messagebox.showerror("Could not delete item", str(exc), parent=self)
            return
        if current_id is not None and self._vault.get_node(current_id) is None:
            self._note = None
            self._dirty = False
            self.note_frame.grid_remove()
            self.dashboard.grid()
            self.dashboard.refresh()
            self._toplevel.title("RedScribe")
            self._set_save_state("saved")
        self._refresh_tree()
        self._update_sidebar_stats()
        if self._note is None:
            self.dashboard.refresh()
        self._set_status(f"Moved {affected} {pluralize(affected, 'item')} to trash")

    def _open_quick_switch(self) -> None:
        if not self._save_if_needed():
            return
        switcher = QuickSwitch(
            self,
            self._theme,
            vault=self._vault,
            on_open=self._dashboard_open,
        )
        switcher.show()

    def _open_search(self) -> None:
        dialog = SearchDialog(self, self._theme, vault=self._vault)
        node_id = dialog.show()
        if node_id is not None:
            self.open_node(node_id)

    def _open_snippets(self) -> None:
        target = self._note.target if self._note is not None else ""
        dialog = SnippetsWindow(
            self,
            self._theme,
            vault=self._vault,
            target=target,
        )
        result = dialog.show(700)
        if not isinstance(result, dict):
            return
        if result.get("action") != "insert":
            return
        command = str(result.get("command", ""))
        if self._note is None:
            messagebox.showinfo(
                "Snippet copied",
                "Open a note first, then insert a snippet from the library.",
                parent=self,
            )
            return
        self.editor.insert_command(command)
        self._set_status("Snippet inserted")

    def _open_flags(self) -> None:
        dialog = FlagsDialog(self, self._theme, vault=self._vault)
        node_id = dialog.show(640)
        if isinstance(node_id, int):
            self.open_node(node_id)

    def _open_trash(self) -> None:
        dialog = TrashDialog(
            self,
            self._theme,
            vault=self._vault,
            on_change=self._on_vault_changed,
        )
        dialog.show(640)
        self._on_vault_changed()

    def _on_vault_changed(self) -> None:
        self._refresh_tree()
        self._update_sidebar_stats()
        if self.dashboard.winfo_ismapped():
            self.dashboard.refresh()

    def _open_settings(self) -> None:
        settings = {
            "theme": self._theme_name,
            "font_size": self._font_size,
            "restore_last_note": self._restore_last,
        }
        dialog = SettingsDialog(
            self,
            self._theme,
            settings=settings,
            vault_path=self._vault.display_path,
        )
        result = dialog.show(470)
        if not isinstance(result, dict):
            return
        theme_name = str(result.get("theme", self._theme_name))
        font_size = result.get("font_size", self._font_size)
        try:
            new_size = max(9, min(18, int(font_size)))
        except (TypeError, ValueError):
            new_size = self._font_size
        restored = result.get("restore_last_note", self._restore_last)
        self._restore_last = bool(restored)
        self._vault.set_setting("ui.restore_last_note", "1" if self._restore_last else "0")
        if theme_name != self._theme_name or new_size != self._font_size:
            self._change_appearance(theme_name, new_size)

    def _change_appearance(self, theme_name: str, font_size: int) -> None:
        if theme_name not in {"dark", "light"}:
            return
        if not self._save_if_needed():
            return
        self._theme_name = theme_name
        self._font_size = max(9, min(18, font_size))
        self._vault.set_setting("ui.theme", self._theme_name)
        self._vault.set_setting("ui.font_size", str(self._font_size))
        self._rebuild_ui()
        self._set_status("Appearance updated")

    def _rebuild_ui(self) -> None:
        current_id = self._note.id if self._note is not None else None
        filter_value = self.tree_filter.get_value() if hasattr(self, "tree_filter") else ""
        self._capture_layout()
        self._cancel_jobs()
        self._note = None
        self._dirty = False
        self._theme = build_theme(self._toplevel, self._theme_name, self._font_size)
        configure_styles(self._toplevel, self._theme)
        for child in self.winfo_children():
            child.destroy()
        self._build_menus()
        self._build_ui()
        self._toplevel.bind("<Map>", self._on_toplevel_map, add="+")
        self._refresh_tree()
        self._update_sidebar_stats()
        if filter_value:
            self.tree_filter.set_value(filter_value)
            if self._tree_job is not None:
                self.after_cancel(self._tree_job)
                self._tree_job = None
            self._refresh_tree()
        if current_id is not None:
            node = self._vault.get_node(current_id)
            if node is not None and node.is_note:
                self.open_node(current_id, force=True)
            else:
                self._show_dashboard(save=False)
        else:
            self._show_dashboard(save=False)
        self._restore_sashes()

    def _capture_layout(self) -> None:
        try:
            width = self.panes.sashpos(0)
        except tk.TclError:
            return
        if width > 100:
            self._vault.set_setting("ui.sidebar_width", str(width))
        if len(self.body_panes.panes()) == 2:
            try:
                split = self.body_panes.sashpos(0)
            except tk.TclError:
                split = 0
            if split > 100:
                self._vault.set_setting("ui.split_sash", str(split))

    def _restore_sashes(self) -> None:
        if self._layout_job is not None:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(80, self._apply_sashes)

    def _on_toplevel_map(self, event: tk.Event) -> None:
        if event.widget is self._toplevel:
            self._restore_sashes()

    def _apply_sashes(self) -> None:
        self._layout_job = None
        if not self.winfo_exists() or not self.panes.winfo_ismapped():
            return
        try:
            total = self.panes.winfo_width()
            if total <= 1:
                return
            sidebar = self._setting_int(
                "ui.sidebar_width",
                SIDEBAR_WIDTH,
                minimum=240,
                maximum=max(240, total - 480),
            )
            self.panes.sashpos(0, sidebar)
            if (
                self._note is not None
                and self._view_mode == "split"
                and len(self.body_panes.panes()) == 2
                and self.body_panes.winfo_ismapped()
            ):
                body_total = self.body_panes.winfo_width()
                if body_total <= 1:
                    return
                split = self._setting_int(
                    "ui.split_sash",
                    max(300, body_total // 2),
                    minimum=200,
                    maximum=max(200, body_total - 220),
                )
                self.body_panes.sashpos(0, split)
        except tk.TclError:
            pass

    def _cancel_jobs(self) -> None:
        for attribute in (
            "_autosave_job",
            "_preview_job",
            "_tree_job",
            "_status_job",
            "_layout_job",
        ):
            job = getattr(self, attribute, None)
            if job is not None:
                with suppress(tk.TclError):
                    self.after_cancel(job)
                setattr(self, attribute, None)

    def _filter_by_tag(self, tag: str) -> None:
        self.tree_filter.set_value(f"#{tag}")
        self.tree.focus_set()

    def _toggle_theme(self) -> None:
        target = "light" if self._theme_name == "dark" else "dark"
        self._change_appearance(target, self._font_size)

    def _use_dark_theme(self) -> None:
        if self._theme_name != "dark":
            self._change_appearance("dark", self._font_size)

    def _use_light_theme(self) -> None:
        if self._theme_name != "light":
            self._change_appearance("light", self._font_size)

    def _change_font_size(self, delta: int) -> None:
        new_size = max(9, min(18, self._font_size + delta))
        if new_size != self._font_size:
            self._change_appearance(self._theme_name, new_size)

    def _show_shortcuts(self) -> None:
        ShortcutsDialog(self, self._theme).show(680)

    def _show_about(self) -> None:
        AboutDialog(self, self._theme).show(450)

    def _load_demo(self) -> None:
        if self._vault.stats().notes:
            messagebox.showinfo(
                "Demo data",
                "Demo notes can only be loaded into an empty vault.",
                parent=self,
            )
            return
        count = seed_demo(self._vault)
        self._refresh_tree()
        self._update_sidebar_stats()
        self.dashboard.refresh()
        self._set_status(f"Loaded {count} demo {pluralize(count, 'note')}")

    def _import_files(self) -> None:
        if not self._save_if_needed():
            return
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Import Markdown notes",
            filetypes=(("Markdown", "*.md *.markdown *.mdown"), ("All files", "*.*")),
        )
        if not paths:
            return
        try:
            imported = import_markdown_files(self._vault, list(paths), self._default_parent())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import failed", str(exc), parent=self)
            return
        self._clear_filter_for_new_item()
        self._refresh_tree()
        self._update_sidebar_stats()
        self.dashboard.refresh()
        count = len(imported)
        self._set_status(f"Imported {count} {pluralize(count, 'note')}")
        if imported:
            self.open_node(imported[0].id)

    def _import_folder(self) -> None:
        if not self._save_if_needed():
            return
        directory = filedialog.askdirectory(parent=self, title="Import folder")
        if not directory:
            return
        try:
            folder, count = import_directory(self._vault, directory, self._default_parent())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import failed", str(exc), parent=self)
            return
        self._clear_filter_for_new_item()
        self._refresh_tree()
        self._update_sidebar_stats()
        self.dashboard.refresh()
        self._set_status(f"Imported {count} {pluralize(count, 'note')} from folder")
        if folder is not None:
            iid = str(folder.id)
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self._selected_folder_id = folder.id

    def _export_note_markdown(self) -> None:
        if self._note is None:
            return
        if not self.save_now(notify=True):
            return
        node_id = self._note.id
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Export note as Markdown",
            initialdir=str(Path.home()),
            initialfile=self._vault.node_filename(node_id),
            defaultextension=".md",
            filetypes=(("Markdown", "*.md"),),
        )
        if not destination:
            return
        try:
            path = export_note_markdown(self._vault, node_id, destination)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        self._set_status(f"Exported {path.name}")

    def _export_note_html(self) -> None:
        if self._note is None:
            return
        if not self.save_now(notify=True):
            return
        node_id = self._note.id
        filename = Path(self._vault.node_filename(node_id)).with_suffix(".html").name
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Export note as HTML",
            initialdir=str(Path.home()),
            initialfile=filename,
            defaultextension=".html",
            filetypes=(("HTML", "*.html"),),
        )
        if not destination:
            return
        try:
            path = export_note_html(self._vault, node_id, destination)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        self._set_status(f"Exported {path.name}")

    def _export_vault_markdown(self) -> None:
        if not self._save_if_needed(notify=True):
            return
        directory = filedialog.askdirectory(parent=self, title="Export vault as Markdown folder")
        if not directory:
            return
        try:
            count = export_vault_markdown(self._vault, directory)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        self._set_status(f"Exported {count} {pluralize(count, 'note')}")

    def _export_vault_html(self) -> None:
        if not self._save_if_needed(notify=True):
            return
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Export vault as an HTML report",
            initialdir=str(Path.home()),
            initialfile="redscribe-vault.html",
            defaultextension=".html",
            filetypes=(("HTML", "*.html"),),
        )
        if not destination:
            return
        try:
            count = export_vault_html(self._vault, destination)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        self._set_status(f"Exported a report with {count} {pluralize(count, 'note')}")

    def _backup_vault(self) -> None:
        if not self._save_if_needed(notify=True):
            return
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Back up vault",
            initialdir=str(Path.home()),
            initialfile="redscribe-backup.sqlite",
            defaultextension=".sqlite",
            filetypes=(("SQLite database", "*.sqlite *.db"),),
        )
        if not destination:
            return
        try:
            path = self._vault.backup_to(destination)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Backup failed", str(exc), parent=self)
            return
        self._set_status(f"Backed up vault to {path.name}")

    def _set_status(self, message: str) -> None:
        if not hasattr(self, "status_message"):
            return
        self.status_message.configure(text=message)
        if self._status_job is not None:
            self.after_cancel(self._status_job)
        if message:
            self._status_job = self.after(8000, self._clear_status)

    def _clear_status(self) -> None:
        self._status_job = None
        if hasattr(self, "status_message") and self.status_message.winfo_exists():
            self.status_message.configure(text="")

    def close(self) -> None:
        if not self._save_if_needed(notify=True):
            return
        self._capture_layout()
        with suppress(tk.TclError):
            self._vault.set_setting("ui.window", self._toplevel.geometry())
        self._cancel_jobs()
        self._toplevel.destroy()
