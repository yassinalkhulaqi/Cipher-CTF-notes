"""Fuzzy quick-switch palette for jumping between notes."""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from redscribe.db import Vault
from redscribe.fuzzy import rank_items
from redscribe.models import Node
from redscribe.ui.theme import Theme
from redscribe.ui.widgets import SearchBox


class QuickSwitch(tk.Toplevel):
    """A borderless command palette backed by fuzzy note ranking."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        vault: Vault,
        on_open: Callable[[int], None],
    ) -> None:
        super().__init__(master)
        self._theme = theme
        self._vault = vault
        self._on_open = on_open
        self._paths = {
            node.id: vault.path_of(node.id, include_self=False) for node in vault.iter_notes()
        }
        self._entries: list[tuple[Node, str]] = [
            (node, self._paths.get(node.id, "")) for node in vault.iter_notes()
        ]
        self._ranked: list[tuple[Node, str]] = []
        self.withdraw()
        self.overrideredirect(True)
        self.transient(master.winfo_toplevel())
        palette = theme.palette
        self.configure(bg=palette.border)
        shell = tk.Frame(self, bg=palette.surface)
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        shell.rowconfigure(2, weight=1)
        shell.columnconfigure(0, weight=1)

        header = tk.Frame(shell, bg=palette.surface)
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        header.columnconfigure(1, weight=1)
        tk.Label(
            header,
            text="⌕",
            bg=palette.surface,
            fg=palette.accent,
            font=theme.font(5, "bold"),
        ).grid(row=0, column=0, padx=(0, 10))
        self.search = SearchBox(
            header,
            theme,
            "Jump to a note by title, target, tag, or path…",
            background=palette.surface_alt,
            font_delta=1,
        )
        self.search.grid(row=0, column=1, sticky="ew")
        self.search.bind_change(self._filter)

        self.count = tk.Label(
            shell,
            text="",
            bg=palette.surface,
            fg=palette.faint,
            font=theme.font(-2),
            anchor="w",
        )
        self.count.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 6))

        body = tk.Frame(shell, bg=palette.surface)
        body.grid(row=2, column=0, sticky="nsew", padx=10)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            body,
            columns=("path",),
            show="tree",
            selectmode="browse",
            height=12,
        )
        self.tree.column("#0", width=330, stretch=False)
        self.tree.column("path", width=280, stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            body,
            orient="vertical",
            command=self.tree.yview,
            style="Vertical.TScrollbar",
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure("pinned", foreground=palette.accent)

        footer = tk.Frame(shell, bg=palette.surface, height=34)
        footer.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 12))
        tk.Label(
            footer,
            text="↑↓ navigate   ·   Enter open   ·   Esc close",
            bg=palette.surface,
            fg=palette.faint,
            font=theme.font(-2),
            anchor="w",
        ).pack(side="left")

        self.search.entry.bind("<Down>", self._next, add="+")
        self.search.entry.bind("<Up>", self._previous, add="+")
        self.search.entry.bind("<Return>", lambda _event: self._open(), add="+")
        self.search.entry.bind("<Escape>", lambda _event: self.close(), add="+")
        self.tree.bind("<Double-1>", lambda _event: self._open(), add="+")
        self.tree.bind("<Return>", lambda _event: self._open(), add="+")
        self.tree.bind("<Escape>", lambda _event: self.close(), add="+")
        self.bind("<Escape>", lambda _event: self.close())
        self._filter()

    def _filter(self) -> None:
        query = self.search.get_value()
        entries = rank_items(
            query,
            self._entries,
            key=lambda entry: f"{entry[0].title} {entry[1]} {entry[0].target} {entry[0].tags}",
            limit=100,
        )
        self._ranked = entries
        for item in self.tree.get_children():
            self.tree.delete(item)
        for node, path in entries:
            self.tree.insert(
                "",
                "end",
                iid=str(node.id),
                text=f"{'◆' if node.pinned else ' '}  {node.title}",
                values=(path or "Vault root",),
                tags=("pinned",) if node.pinned else (),
            )
        if entries:
            first = str(entries[0][0].id)
            self.tree.selection_set(first)
            self.tree.focus(first)
            self.tree.see(first)
        self.count.configure(text=f"{len(entries)} {'note' if len(entries) == 1 else 'notes'}")

    def _move(self, offset: int) -> str:
        items = self.tree.get_children()
        if not items:
            return "break"
        current = self.tree.selection()
        index = items.index(current[0]) if current else 0
        index = max(0, min(len(items) - 1, index + offset))
        self.tree.selection_set(items[index])
        self.tree.focus(items[index])
        self.tree.see(items[index])
        return "break"

    def _next(self, _event: tk.Event | None = None) -> str:
        return self._move(1)

    def _previous(self, _event: tk.Event | None = None) -> str:
        return self._move(-1)

    def _open(self) -> str:
        selection = self.tree.selection()
        if not selection:
            return "break"
        node_id = int(selection[0])
        self.destroy()
        self._on_open(node_id)
        return "break"

    def close(self) -> None:
        self.destroy()

    def show(self) -> None:
        width = 660
        height = 500
        parent = self.master
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + 110
        except tk.TclError:
            x = (self.winfo_screenwidth() - width) // 2
            y = 120
        x = max(20, min(x, self.winfo_screenwidth() - width - 20))
        y = max(20, min(y, self.winfo_screenheight() - height - 40))
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        with contextlib.suppress(tk.TclError):
            self.grab_set()
        self.search.focus_entry()
        self.lift()
        self.wait_window(self)
