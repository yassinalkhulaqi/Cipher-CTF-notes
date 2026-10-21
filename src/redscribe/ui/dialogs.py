"""Modal dialogs for creating, editing, and inspecting RedScribe data."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import messagebox, ttk
from typing import Literal

from redscribe import __version__
from redscribe.db import Vault
from redscribe.domain.models import (
    DIFFICULTIES,
    DIFFICULTY_LABELS,
    STATUS_LABELS,
    STATUSES,
    FlagHit,
    Node,
    Snippet,
    Template,
)
from redscribe.domain.utils import humanize_delta
from redscribe.ui.theme import Theme
from redscribe.ui.widgets import SearchBox, center_window


class BaseDialog(tk.Toplevel):
    """Common modal window shell with a heading and a footer."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        title: str,
        *,
        width: int = 560,
    ) -> None:
        super().__init__(master)
        self._theme = theme
        self._width = width
        self.result: object | None = None
        self.withdraw()
        self.title(title)
        self.configure(bg=theme.palette.bg)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _event: self.cancel())
        self.content = tk.Frame(self, bg=theme.palette.bg)
        self.content.pack(fill="both", expand=True, padx=28, pady=(24, 8))
        self.footer = tk.Frame(self, bg=theme.palette.bg)
        self.footer.pack(fill="x", padx=28, pady=(10, 22))
        self._error = tk.Label(
            self.footer,
            text="",
            bg=theme.palette.bg,
            fg=theme.palette.red,
            font=theme.font(-1),
            anchor="w",
        )
        self._error.pack(side="left")

    def heading(self, title: str, subtitle: str = "") -> None:
        palette = self._theme.palette
        tk.Label(
            self.content,
            text=title,
            bg=palette.bg,
            fg=palette.text,
            font=self._theme.font(8, "bold"),
            anchor="w",
        ).pack(fill="x")
        if subtitle:
            tk.Label(
                self.content,
                text=subtitle,
                bg=palette.bg,
                fg=palette.muted,
                font=self._theme.font(-1),
                anchor="w",
                justify="left",
                wraplength=self._width - 80,
            ).pack(fill="x", pady=(5, 0))

    def add_button(
        self,
        text: str,
        command: Callable[[], None],
        *,
        style: str = "Tool.TButton",
        side: Literal["left", "right", "top", "bottom"] = "right",
    ) -> ttk.Button:
        button = ttk.Button(self.footer, text=text, command=command, style=style)
        button.pack(side=side, padx=(8, 0))
        return button

    def add_close_buttons(
        self,
        primary_text: str,
        primary_command: Callable[[], None],
        *,
        secondary_text: str = "Cancel",
    ) -> None:
        self.add_button(primary_text, primary_command, style="Accent.TButton")
        if secondary_text:
            self.add_button(secondary_text, self.cancel)

    def show_error(self, message: str) -> None:
        self._error.configure(text=message)

    def show(self, height: int) -> object | None:
        self.update_idletasks()
        width = max(self._width, self.winfo_reqwidth())
        height = max(height, self.winfo_reqheight())
        width = min(width, max(360, self.winfo_screenwidth() - 60))
        height = min(height, max(260, self.winfo_screenheight() - 80))
        self.deiconify()
        center_window(self, self.master, width, height)
        self.grab_set()
        focused = self.focus_get()
        if focused is None or not str(focused).startswith(str(self)):
            self.focus_set()
        self.wait_window(self)
        return self.result

    def cancel(self) -> None:
        self.result = None
        self.destroy()


class PromptDialog(BaseDialog):
    """Ask for a single line of text."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        title: str,
        label: str,
        initial: str = "",
        confirm_text: str = "Save",
        allow_empty: bool = False,
        placeholder: str = "",
    ) -> None:
        super().__init__(master, theme, title, width=460)
        self._allow_empty = allow_empty
        self.heading(title, "Enter a value and press Enter to confirm.")
        palette = theme.palette
        tk.Label(
            self.content,
            text=label,
            bg=palette.bg,
            fg=palette.muted,
            font=theme.font(-1, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(20, 6))
        self.var = tk.StringVar(value=initial)
        self.entry = ttk.Entry(self.content, textvariable=self.var)
        self.entry.pack(fill="x")
        if placeholder:
            tk.Label(
                self.content,
                text=placeholder,
                bg=palette.bg,
                fg=palette.faint,
                font=theme.font(-2),
                anchor="w",
            ).pack(fill="x", pady=(4, 0))
        self.add_close_buttons(confirm_text, self.confirm)
        self.entry.bind("<Return>", lambda _event: self.confirm())
        self.entry.focus_set()
        self.entry.selection_range(0, "end")

    def confirm(self) -> None:
        value = self.var.get().strip()
        if not value and not self._allow_empty:
            self.show_error("A value is required.")
            self.entry.focus_set()
            return
        self.result = value
        self.destroy()


class NewNoteDialog(BaseDialog):
    """Collect the title, template, target, and folder for a new note."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        templates: Sequence[Template],
        folders: Sequence[tuple[str, int]],
        initial_template: str = "blank",
        initial_folder_id: int | None = None,
    ) -> None:
        super().__init__(master, theme, "New note", width=680)
        self._templates = {template.key: template for template in templates}
        self._folders = [("Vault root", None), *folders]
        self._last_default = ""
        self.heading("Create a new note", "Start blank or use a structured workflow template.")
        palette = theme.palette
        form = tk.Frame(self.content, bg=palette.bg)
        form.pack(fill="x", pady=(18, 12))
        form.columnconfigure(1, weight=1)

        self.title_var = tk.StringVar()
        self.target_var = tk.StringVar()
        initial_folder = next(
            (label for label, identifier in self._folders if identifier == initial_folder_id),
            self._folders[0][0],
        )
        self.folder_var = tk.StringVar(value=initial_folder)

        self._form_row(form, 0, "Title")
        self.title_entry = ttk.Entry(form, textvariable=self.title_var)
        self.title_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self._form_row(form, 1, "Target")
        self.target_entry = ttk.Entry(form, textvariable=self.target_var)
        self.target_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self._form_row(form, 2, "Folder")
        self.folder_box = ttk.Combobox(
            form,
            textvariable=self.folder_var,
            values=[label for label, _identifier in self._folders],
            state="readonly",
        )
        self.folder_box.grid(row=2, column=1, sticky="ew", pady=4)

        tk.Label(
            self.content,
            text="Template",
            bg=palette.bg,
            fg=palette.muted,
            font=theme.font(-1, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(8, 6))
        self.tree = ttk.Treeview(
            self.content,
            columns=("name", "description"),
            show="headings",
            height=7,
            selectmode="browse",
        )
        self.tree.heading("name", text="Template")
        self.tree.heading("description", text="What it sets up")
        self.tree.column("name", width=210, stretch=False)
        self.tree.column("description", width=400, stretch=True)
        for template in templates:
            self.tree.insert(
                "",
                "end",
                iid=template.key,
                values=(f"{template.glyph}  {template.name}", template.description),
            )
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_template_selected, add="+")
        self.tree.bind("<Double-1>", lambda _event: self.confirm(), add="+")

        self.add_close_buttons("Create note", self.confirm)
        initial = initial_template if initial_template in self._templates else "blank"
        selection = initial if initial in self._templates else next(iter(self._templates))
        self.tree.selection_set(selection)
        self.tree.focus(selection)
        self._on_template_selected()
        self.title_entry.focus_set()

    def _form_row(self, parent: tk.Frame, row: int, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=self._theme.palette.bg,
            fg=self._theme.palette.muted,
            font=self._theme.font(-1, "bold"),
            width=8,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(0, 12))

    def _selected_template(self) -> Template:
        selection = self.tree.selection()
        key = selection[0] if selection else "blank"
        return self._templates.get(key, next(iter(self._templates.values())))

    def _on_template_selected(self, _event: tk.Event | None = None) -> None:
        template = self._selected_template()
        current = self.title_var.get().strip()
        if not current or current == self._last_default:
            self.title_var.set(template.default_title)
        self._last_default = template.default_title

    def confirm(self) -> None:
        template = self._selected_template()
        title = self.title_var.get().strip() or template.default_title
        folder_label = self.folder_var.get()
        folder_id = next(
            (identifier for label, identifier in self._folders if label == folder_label),
            None,
        )
        self.result = {
            "title": title,
            "target": self.target_var.get().strip(),
            "template": template,
            "folder_id": folder_id,
        }
        self.destroy()


class PropertiesDialog(BaseDialog):
    """Edit a note's metadata without leaving the editor."""

    def __init__(self, master: tk.Misc, theme: Theme, *, node: Node) -> None:
        super().__init__(master, theme, "Note properties", width=540)
        self._node = node
        self._status_labels = {STATUS_LABELS[value]: value for value in STATUSES}
        self._difficulty_labels = {DIFFICULTY_LABELS[value]: value for value in DIFFICULTIES}
        self.heading("Note properties", "Metadata powers filters, dashboards, and exports.")
        palette = theme.palette
        form = tk.Frame(self.content, bg=palette.bg)
        form.pack(fill="both", expand=True, pady=(18, 0))
        form.columnconfigure(1, weight=1)

        self.title_var = tk.StringVar(value=node.title)
        self.target_var = tk.StringVar(value=node.target)
        self.tags_var = tk.StringVar(value=node.tags)
        self.flag_var = tk.StringVar(value=node.flag)
        self.status_var = tk.StringVar(value=STATUS_LABELS.get(node.status, "Open"))
        self.difficulty_var = tk.StringVar(value=DIFFICULTY_LABELS.get(node.difficulty, "Unrated"))
        self.pinned_var = tk.BooleanVar(value=node.pinned)

        rows = [
            ("Title", ttk.Entry(form, textvariable=self.title_var)),
            ("Target", ttk.Entry(form, textvariable=self.target_var)),
            ("Tags", ttk.Entry(form, textvariable=self.tags_var)),
            ("Flag", ttk.Entry(form, textvariable=self.flag_var)),
        ]
        for index, (label, widget) in enumerate(rows):
            self._row(form, index, label)
            widget.grid(row=index, column=1, sticky="ew", pady=4)
        self._row(form, 4, "Status")
        status = ttk.Combobox(
            form,
            textvariable=self.status_var,
            values=list(self._status_labels),
            state="readonly",
        )
        status.grid(row=4, column=1, sticky="ew", pady=4)
        self._row(form, 5, "Difficulty")
        difficulty = ttk.Combobox(
            form,
            textvariable=self.difficulty_var,
            values=list(self._difficulty_labels),
            state="readonly",
        )
        difficulty.grid(row=5, column=1, sticky="ew", pady=4)
        self._row(form, 6, "Pinned")
        pinned = ttk.Checkbutton(
            form,
            text="Pin this note to the dashboard",
            variable=self.pinned_var,
            style="TCheckbutton",
        )
        pinned.grid(row=6, column=1, sticky="w", pady=4)

        tk.Label(
            form,
            text=(
                "Tags are comma-separated. Flags can be entered manually "
                "or detected in the note body."
            ),
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-2),
            anchor="w",
            wraplength=380,
            justify="left",
        ).grid(row=7, column=1, sticky="w", pady=(10, 0))

        self.add_close_buttons("Save changes", self.confirm)
        self.bind("<Return>", lambda _event: self.confirm())

    def _row(self, parent: tk.Frame, row: int, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=self._theme.palette.bg,
            fg=self._theme.palette.muted,
            font=self._theme.font(-1, "bold"),
            width=10,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(0, 12))

    def confirm(self) -> None:
        self.result = {
            "title": self.title_var.get().strip() or self._node.title,
            "target": self.target_var.get().strip(),
            "tags": self.tags_var.get().strip(),
            "flag": self.flag_var.get().strip(),
            "status": self._status_labels.get(self.status_var.get(), "todo"),
            "difficulty": self._difficulty_labels.get(self.difficulty_var.get(), ""),
            "pinned": self.pinned_var.get(),
        }
        self.destroy()


class SnippetDialog(BaseDialog):
    """Create or edit a custom command snippet."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        snippet: Snippet | None = None,
    ) -> None:
        super().__init__(master, theme, "Edit snippet" if snippet else "New snippet", width=660)
        self._snippet = snippet
        self.heading(
            "Edit command snippet" if snippet else "Create a command snippet",
            "Placeholders use double braces, for example {{target}} or {{lhost}}.",
        )
        palette = theme.palette
        form = tk.Frame(self.content, bg=palette.bg)
        form.pack(fill="both", expand=True, pady=(16, 0))
        form.columnconfigure(1, weight=1)
        form.rowconfigure(3, weight=1)
        self.title_var = tk.StringVar(value=snippet.title if snippet else "")
        self.tags_var = tk.StringVar(value=snippet.tags if snippet else "")
        self.description_var = tk.StringVar(value=snippet.description if snippet else "")
        for index, (label, variable) in enumerate(
            (
                ("Title", self.title_var),
                ("Tags", self.tags_var),
                ("Description", self.description_var),
            )
        ):
            tk.Label(
                form,
                text=label,
                bg=palette.bg,
                fg=palette.muted,
                font=theme.font(-1, "bold"),
                width=12,
                anchor="w",
            ).grid(row=index, column=0, sticky="w", padx=(0, 12), pady=4)
            ttk.Entry(form, textvariable=variable).grid(row=index, column=1, sticky="ew", pady=4)

        tk.Label(
            form,
            text="Command",
            bg=palette.bg,
            fg=palette.muted,
            font=theme.font(-1, "bold"),
            anchor="nw",
        ).grid(row=3, column=0, sticky="nw", padx=(0, 12), pady=(10, 4))
        command_frame = tk.Frame(
            form,
            bg=palette.surface_alt,
            highlightthickness=1,
            highlightbackground=palette.border,
        )
        command_frame.grid(row=3, column=1, sticky="nsew", pady=(10, 4))
        command_frame.rowconfigure(0, weight=1)
        command_frame.columnconfigure(0, weight=1)
        self.command_text = tk.Text(
            command_frame,
            height=7,
            wrap="none",
            bg=palette.surface_alt,
            fg=palette.text,
            insertbackground=palette.accent,
            selectbackground=palette.selection,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            font=theme.font(-1, mono=True),
        )
        self.command_text.grid(row=0, column=0, sticky="nsew")
        command_scroll = ttk.Scrollbar(
            command_frame,
            orient="vertical",
            command=self.command_text.yview,
            style="Vertical.TScrollbar",
        )
        command_scroll.grid(row=0, column=1, sticky="ns")
        self.command_text.configure(yscrollcommand=command_scroll.set)
        self.command_text.insert("1.0", snippet.command if snippet else "")

        self.add_close_buttons("Save snippet", self.confirm)
        self.command_text.focus_set()

    def confirm(self) -> None:
        command = self.command_text.get("1.0", "end-1c").strip()
        if not command:
            self.show_error("A command is required.")
            self.command_text.focus_set()
            return
        self.result = {
            "title": self.title_var.get().strip() or "Untitled snippet",
            "tags": self.tags_var.get().strip(),
            "description": self.description_var.get().strip(),
            "command": command,
        }
        self.destroy()


class SettingsDialog(BaseDialog):
    """Edit application preferences stored in the vault."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        settings: dict[str, object],
        vault_path: str,
    ) -> None:
        super().__init__(master, theme, "Settings", width=500)
        self.heading("Settings", "Preferences are stored inside the vault.")
        palette = theme.palette
        form = tk.Frame(self.content, bg=palette.bg)
        form.pack(fill="x", pady=(18, 0))
        form.columnconfigure(1, weight=1)
        self.theme_var = tk.StringVar(value=str(settings.get("theme", "dark")))
        self.font_var = tk.IntVar(value=int(str(settings.get("font_size", 11))))
        self.restore_var = tk.BooleanVar(value=bool(settings.get("restore_last_note", True)))

        self._row(form, 0, "Theme")
        theme_box = ttk.Combobox(
            form, textvariable=self.theme_var, values=("dark", "light"), state="readonly"
        )
        theme_box.grid(row=0, column=1, sticky="ew", pady=4)
        self._row(form, 1, "Font size")
        font_box = ttk.Spinbox(form, from_=9, to=18, textvariable=self.font_var, width=8)
        font_box.grid(row=1, column=1, sticky="w", pady=4)
        self._row(form, 2, "Startup")
        ttk.Checkbutton(
            form,
            text="Reopen the last note on launch",
            variable=self.restore_var,
        ).grid(row=2, column=1, sticky="w", pady=4)

        tk.Label(
            self.content,
            text="Vault location",
            bg=palette.bg,
            fg=palette.muted,
            font=theme.font(-1, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(22, 6))
        path = tk.Text(
            self.content,
            height=2,
            wrap="char",
            bg=palette.surface_alt,
            fg=palette.muted,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=palette.border,
            font=theme.font(-2, mono=True),
            padx=8,
            pady=6,
        )
        path.insert("1.0", vault_path)
        path.configure(state="disabled")
        path.pack(fill="x")

        self.add_close_buttons("Save settings", self.confirm)
        self.bind("<Return>", lambda _event: self.confirm())

    def _row(self, parent: tk.Frame, row: int, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=self._theme.palette.bg,
            fg=self._theme.palette.muted,
            font=self._theme.font(-1, "bold"),
            width=10,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(0, 12))

    def confirm(self) -> None:
        try:
            size = max(9, min(18, int(self.font_var.get())))
        except (tk.TclError, ValueError):
            size = 11
        self.result = {
            "theme": self.theme_var.get(),
            "font_size": size,
            "restore_last_note": self.restore_var.get(),
        }
        self.destroy()


class FolderPickerDialog(BaseDialog):
    """Choose a destination folder for a node."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        folders: Sequence[tuple[str, int]],
        current_folder_id: int | None,
        title: str = "Move to folder",
    ) -> None:
        super().__init__(master, theme, title, width=480)
        self._folders = [("Vault root", None), *folders]
        self.heading(title, "Choose the destination for this item.")
        palette = theme.palette
        current = next(
            (label for label, identifier in self._folders if identifier == current_folder_id),
            "Vault root",
        )
        self.folder_var = tk.StringVar(value=current)
        box = ttk.Combobox(
            self.content,
            textvariable=self.folder_var,
            values=[label for label, _identifier in self._folders],
            state="readonly",
        )
        box.pack(fill="x", pady=(24, 0))
        note = tk.Label(
            self.content,
            text=(
                "Notes can only live in folders. Choosing the vault root "
                "moves the item to the top level."
            ),
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-2),
            anchor="w",
            justify="left",
            wraplength=390,
        )
        note.pack(fill="x", pady=(8, 0))
        self.add_close_buttons("Move", self.confirm)
        self.bind("<Return>", lambda _event: self.confirm())

    def confirm(self) -> None:
        label = self.folder_var.get()
        folder_id = next(
            (identifier for name, identifier in self._folders if name == label),
            None,
        )
        self.result = {"folder_id": folder_id}
        self.destroy()


class AboutDialog(BaseDialog):
    """A compact about window."""

    def __init__(self, master: tk.Misc, theme: Theme) -> None:
        super().__init__(master, theme, "About RedScribe", width=540)
        palette = theme.palette
        tk.Label(
            self.content,
            text="REDSCRIBE",
            bg=palette.bg,
            fg=palette.accent,
            font=theme.font(-2, "bold"),
        ).pack(anchor="w")
        tk.Label(
            self.content,
            text="Local-first security notes.",
            bg=palette.bg,
            fg=palette.text,
            font=theme.font(12, "bold"),
        ).pack(anchor="w", pady=(6, 2))
        tk.Label(
            self.content,
            text=f"Version {__version__}",
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-1),
        ).pack(anchor="w")
        copy = (
            "A focused notebook for CTF challenges, host and web assessments, and "
            "engagement journals. Notes live in a single portable SQLite vault. "
            "No account, no cloud, no telemetry."
        )
        tk.Label(
            self.content,
            text=copy,
            bg=palette.bg,
            fg=palette.muted,
            font=theme.font(),
            wraplength=470,
            justify="left",
        ).pack(anchor="w", pady=(20, 10))
        tk.Label(
            self.content,
            text="Built with Python and Tkinter. Use only on systems you are authorized to test.",
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-2),
            wraplength=470,
            justify="left",
        ).pack(anchor="w")
        self.add_close_buttons("Close", self.destroy, secondary_text="")


class ShortcutsDialog(BaseDialog):
    """Keyboard reference for the main window and editor."""

    _GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
        (
            "Notes",
            (
                ("Ctrl+N", "New note from template"),
                ("Ctrl+Shift+N", "New folder"),
                ("Ctrl+S", "Save now"),
                ("Ctrl+E", "Cycle editor / split / preview"),
                ("Ctrl+Shift+D", "Open the dashboard"),
                ("Ctrl+Shift+P", "Pin or unpin the current note"),
                ("Ctrl+,", "Open settings"),
                ("F2", "Edit note properties"),
                ("Delete", "Move selected tree item to trash"),
            ),
        ),
        (
            "Find and navigate",
            (
                ("Ctrl+P", "Quick switch notes"),
                ("Ctrl+Shift+F", "Search the whole vault"),
                ("Ctrl+F", "Find in the current note"),
                ("Ctrl+H", "Find and replace"),
                ("Ctrl+Shift+S", "Open the snippet library"),
                ("F1", "Show this reference"),
            ),
        ),
        (
            "Editing",
            (
                ("Ctrl+B", "Bold selection"),
                ("Ctrl+I", "Italic selection"),
                ("Ctrl+K", "Inline code selection"),
                ("Ctrl+Shift+X", "Strikethrough selection"),
                ("Tab / Shift+Tab", "Indent or outdent"),
                ("Ctrl+Z / Ctrl+Y", "Undo / redo"),
            ),
        ),
    )

    def __init__(self, master: tk.Misc, theme: Theme) -> None:
        super().__init__(master, theme, "Keyboard shortcuts", width=640)
        self.heading("Keyboard shortcuts", "Everything important is one keystroke away.")
        palette = theme.palette
        body = tk.Frame(self.content, bg=palette.bg)
        body.pack(fill="both", expand=True, pady=(18, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        for column, (title, rows) in enumerate(self._GROUPS[:2]):
            self._group(body, column, title, rows)
        self._group(body, 0, self._GROUPS[2][0], self._GROUPS[2][1], row=1)
        self.add_close_buttons("Close", self.destroy, secondary_text="")

    def _group(
        self,
        parent: tk.Frame,
        column: int,
        title: str,
        rows: Sequence[tuple[str, str]],
        *,
        row: int = 0,
    ) -> None:
        palette = self._theme.palette
        frame = tk.Frame(parent, bg=palette.bg)
        frame.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(0, 22) if column == 0 else (10, 0),
            pady=(0, 16),
        )
        tk.Label(
            frame,
            text=title.upper(),
            bg=palette.bg,
            fg=palette.faint,
            font=self._theme.font(-2, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))
        for shortcut, description in rows:
            row_frame = tk.Frame(frame, bg=palette.bg)
            row_frame.pack(fill="x", pady=2)
            tk.Label(
                row_frame,
                text=shortcut,
                bg=palette.surface_alt,
                fg=palette.text,
                font=self._theme.font(-2, mono=True),
                padx=6,
                pady=2,
            ).pack(side="left")
            tk.Label(
                row_frame,
                text=description,
                bg=palette.bg,
                fg=palette.muted,
                font=self._theme.font(-1),
                anchor="w",
            ).pack(side="left", padx=(9, 0))


class TrashDialog(BaseDialog):
    """Review, restore, or permanently delete trashed items."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        vault: Vault,
        on_change: Callable[[], None],
    ) -> None:
        super().__init__(master, theme, "Trash", width=760)
        self._vault = vault
        self._on_change = on_change
        self._items: dict[str, Node] = {}
        self.heading("Trash", "Trashed notes keep their content until you empty the trash.")
        palette = theme.palette
        self.tree = ttk.Treeview(
            self.content,
            columns=("title", "location", "deleted"),
            show="headings",
            height=13,
            selectmode="browse",
        )
        self.tree.heading("title", text="Item")
        self.tree.heading("location", text="Location")
        self.tree.heading("deleted", text="Deleted")
        self.tree.column("title", width=260)
        self.tree.column("location", width=300)
        self.tree.column("deleted", width=110, anchor="e")
        self.tree.pack(fill="both", expand=True, pady=(16, 0))
        self.tree.bind("<Double-1>", lambda _event: self.restore(), add="+")
        self.empty_label = tk.Label(
            self.content,
            text="",
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-1),
        )

        self.add_button("Restore", self.restore, style="Accent.TButton")
        self.add_button("Delete forever", self.delete_permanent, style="Danger.TButton")
        self.add_button("Empty trash", self.empty_all, style="Danger.TButton")
        self.add_button("Close", self.destroy)
        self._refresh()

    def _refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._items = {}
        roots = self._vault.trashed_roots()
        for node in roots:
            iid = str(node.id)
            self._items[iid] = node
            location = self._vault.path_of(node.id, include_self=False, sep=" / ")
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    f"{'▸' if node.is_folder else '◆'}  {node.title}",
                    location or "Vault root",
                    humanize_delta(node.deleted_at or ""),
                ),
            )
        if roots:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.empty_label.pack_forget()
        else:
            self.empty_label.configure(text="Trash is empty.")
            self.empty_label.pack(fill="x", pady=(12, 0))

    def _selected(self) -> Node | None:
        selection = self.tree.selection()
        return self._items.get(selection[0]) if selection else None

    def _changed(self) -> None:
        self._on_change()
        self._refresh()

    def restore(self) -> None:
        node = self._selected()
        if node is None:
            return
        try:
            self._vault.restore_node(node.id)
        except ValueError as exc:
            messagebox.showerror("Restore failed", str(exc), parent=self)
            return
        self._changed()

    def delete_permanent(self) -> None:
        node = self._selected()
        if node is None:
            return
        confirmed = messagebox.askyesno(
            "Delete forever",
            f"Permanently delete “{node.title}” and everything inside it? This cannot be undone.",
            parent=self,
        )
        if not confirmed:
            return
        try:
            self._vault.delete_node(node.id, permanent=True)
        except ValueError as exc:
            messagebox.showerror("Delete failed", str(exc), parent=self)
            return
        self._changed()

    def empty_all(self) -> None:
        confirmed = messagebox.askyesno(
            "Empty trash",
            "Permanently delete every trashed item? This cannot be undone.",
            parent=self,
        )
        if not confirmed:
            return
        self._vault.empty_trash()
        self._changed()


class FlagsDialog(BaseDialog):
    """Browse and copy every flag collected across the vault."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        vault: Vault,
    ) -> None:
        super().__init__(master, theme, "Flag collection", width=780)
        self._vault = vault
        self._flags = vault.collected_flags()
        self.heading("Flag collection", "Manually saved flags and values detected in note bodies.")
        palette = theme.palette
        toolbar = tk.Frame(self.content, bg=palette.bg)
        toolbar.pack(fill="x", pady=(16, 8))
        self.search = SearchBox(toolbar, theme, "Filter flags, notes, or paths…")
        self.search.pack(side="left", fill="x", expand=True)
        self.search.bind_change(self._filter)
        self.count_label = tk.Label(
            toolbar,
            text="",
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-2),
        )
        self.count_label.pack(side="right", padx=(12, 0))
        self.tree = ttk.Treeview(
            self.content,
            columns=("flag", "note", "path"),
            show="headings",
            height=14,
            selectmode="browse",
        )
        self.tree.heading("flag", text="Flag")
        self.tree.heading("note", text="Note")
        self.tree.heading("path", text="Path")
        self.tree.column("flag", width=330)
        self.tree.column("note", width=200)
        self.tree.column("path", width=200)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _event: self.open_selected(), add="+")

        self.add_button("Open note", self.open_selected, style="Accent.TButton")
        self.add_button("Copy", self.copy_selected)
        self.add_button("Copy all", self.copy_all)
        self.add_button("Close", self.cancel)
        self._populate(self._flags)

    def _populate(self, flags: Sequence[FlagHit]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for hit in flags:
            self.tree.insert(
                "",
                "end",
                iid=str(hit.node_id) + "|" + hit.flag,
                values=(hit.flag, hit.title, hit.path or "Vault root"),
            )
        if flags:
            self.tree.selection_set(self.tree.get_children()[0])
            self.tree.see(self.tree.get_children()[0])
        self.count_label.configure(text=f"{len(flags)} {('flag' if len(flags) == 1 else 'flags')}")

    def _filter(self) -> None:
        query = self.search.get_value().casefold()
        if not query:
            self._populate(self._flags)
            return
        filtered = [
            hit
            for hit in self._flags
            if query in hit.flag.casefold()
            or query in hit.title.casefold()
            or query in hit.path.casefold()
        ]
        self._populate(filtered)

    def _selected(self) -> str:
        selection = self.tree.selection()
        if not selection:
            return ""
        values = self.tree.item(selection[0], "values")
        return str(values[0]) if values else ""

    def copy_selected(self) -> None:
        flag = self._selected()
        if flag:
            self.clipboard_clear()
            self.clipboard_append(flag)

    def copy_all(self) -> None:
        self.clipboard_clear()
        self.clipboard_append("\n".join(hit.flag for hit in self._flags))

    def open_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        node_id = int(selection[0].split("|", 1)[0])
        self.result = node_id
        self.destroy()
