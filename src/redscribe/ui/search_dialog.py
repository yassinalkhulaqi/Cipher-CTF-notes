"""Full-text vault search dialog."""

from __future__ import annotations

import contextlib
import tkinter as tk
from tkinter import ttk

from redscribe.db import Vault
from redscribe.ui.theme import Theme
from redscribe.ui.widgets import SearchBox, center_window


class SearchDialog(tk.Toplevel):
    """Search note titles, bodies, and tags across the vault."""

    def __init__(self, master: tk.Misc, theme: Theme, *, vault: Vault) -> None:
        super().__init__(master)
        self._theme = theme
        self._vault = vault
        self._job: str | None = None
        self.result: int | None = None
        self.withdraw()
        self.title("Search vault")
        self.configure(bg=theme.palette.bg)
        self.transient(master.winfo_toplevel())
        self.resizable(True, True)
        self.minsize(640, 420)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())

        palette = theme.palette
        shell = tk.Frame(self, bg=palette.bg)
        shell.pack(fill="both", expand=True, padx=24, pady=20)
        shell.rowconfigure(3, weight=1)
        shell.columnconfigure(0, weight=1)

        tk.Label(
            shell,
            text="Search the vault",
            bg=palette.bg,
            fg=palette.text,
            font=theme.font(7, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            shell,
            text="Full-text search across note content, titles, and tags.",
            bg=palette.bg,
            fg=palette.muted,
            font=theme.font(-1),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 14))

        top = tk.Frame(shell, bg=palette.bg)
        top.grid(row=2, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        self.search = SearchBox(top, theme, "Search notes…", font_delta=1)
        self.search.grid(row=0, column=0, sticky="ew")
        self.search.bind_change(self._schedule)
        self.count = tk.Label(
            top,
            text="",
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-2),
            anchor="e",
            width=14,
        )
        self.count.grid(row=0, column=1, padx=(12, 0))

        body = tk.Frame(shell, bg=palette.bg)
        body.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            body,
            columns=("note", "path", "match"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("note", text="Note")
        self.tree.heading("path", text="Location")
        self.tree.heading("match", text="Match")
        self.tree.column("note", width=220)
        self.tree.column("path", width=180)
        self.tree.column("match", width=360)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            body, orient="vertical", command=self.tree.yview, style="Vertical.TScrollbar"
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Double-1>", lambda _event: self.open_selected(), add="+")
        self.tree.bind("<Return>", lambda _event: self.open_selected(), add="+")
        self.tree.bind("<Escape>", lambda _event: self.close(), add="+")

        self.hint = tk.Label(
            shell,
            text="Type at least one character. Enter opens the selected note.",
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-2),
            anchor="w",
        )
        self.hint.grid(row=4, column=0, sticky="ew", pady=(8, 0))

        self.search.entry.bind("<Down>", self._focus_results, add="+")
        self.search.entry.bind("<Return>", lambda _event: self.open_selected(), add="+")
        self.search.entry.bind("<Escape>", lambda _event: self.close(), add="+")
        self.search.focus_entry()

    def _schedule(self) -> None:
        if self._job is not None:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(self._job)
        self._job = self.after(180, self._run_search)

    def _run_search(self) -> None:
        self._job = None
        query = self.search.get_value()
        for item in self.tree.get_children():
            self.tree.delete(item)
        if not query:
            self.count.configure(text="")
            self.hint.configure(text="Type at least one character. Enter opens the selected note.")
            return
        hits = self._vault.search(query, limit=250)
        for hit in hits:
            self.tree.insert(
                "",
                "end",
                iid=str(hit.node_id),
                values=(hit.title, hit.path or "Vault root", hit.snippet),
            )
        self.count.configure(text=f"{len(hits)} {'match' if len(hits) == 1 else 'matches'}")
        if hits:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self.hint.configure(text="Enter opens the selected note. Esc closes search.")
        else:
            self.hint.configure(text="No notes matched that search.")

    def _focus_results(self, _event: tk.Event | None = None) -> str:
        items = self.tree.get_children()
        if items:
            current = self.tree.selection()
            if not current:
                self.tree.selection_set(items[0])
            self.tree.focus_set()
        return "break"

    def open_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.result = int(selection[0])
        self.destroy()

    def close(self) -> None:
        self.destroy()

    def show(self) -> int | None:
        self.deiconify()
        center_window(self, self.master, 840, 580)
        with contextlib.suppress(tk.TclError):
            self.grab_set()
        self.search.focus_entry()
        self.wait_window(self)
        return self.result
