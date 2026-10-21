"""Snippet library with built-in playbooks and custom commands."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from redscribe.content.snippets import BUILTIN_SNIPPETS, resolve_command, snippet_placeholders
from redscribe.domain.models import Snippet
from redscribe.storage.db import Vault
from redscribe.ui.dialogs import BaseDialog, SnippetDialog
from redscribe.ui.theme import Theme
from redscribe.ui.widgets import SearchBox


class SnippetsWindow(BaseDialog):
    """Browse, resolve, copy, insert, and edit command snippets."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        vault: Vault,
        target: str = "",
    ) -> None:
        super().__init__(master, theme, "Snippet library", width=900)
        self._vault = vault
        self._builtin = list(BUILTIN_SNIPPETS)
        self._custom: list[Snippet] = []
        self._visible: list[Snippet] = []
        self._by_iid: dict[str, Snippet] = {}
        self.heading(
            "Snippet library",
            "Resolve placeholders with the current target, then insert or copy a command.",
        )
        palette = theme.palette
        toolbar = tk.Frame(self.content, bg=palette.bg)
        toolbar.pack(fill="x", pady=(16, 10))
        toolbar.columnconfigure(0, weight=1)
        self.search = SearchBox(toolbar, theme, "Search commands, tags, or descriptions…")
        self.search.grid(row=0, column=0, sticky="ew")
        self.search.bind_change(self._refresh_list)
        self.category_var = tk.StringVar(value="All categories")
        self.category = ttk.Combobox(
            toolbar,
            textvariable=self.category_var,
            state="readonly",
            width=22,
        )
        self.category.grid(row=0, column=1, padx=(10, 0))
        self.category.bind("<<ComboboxSelected>>", lambda _event: self._refresh_list())

        panes = tk.PanedWindow(
            self.content,
            orient="horizontal",
            bg=palette.border,
            sashwidth=5,
            bd=0,
            relief="flat",
        )
        panes.pack(fill="both", expand=True)
        left = tk.Frame(panes, bg=palette.surface)
        right = tk.Frame(panes, bg=palette.bg)
        panes.add(left, minsize=280, width=330)
        panes.add(right, minsize=420)

        self.tree = ttk.Treeview(
            left,
            columns=("category",),
            show="tree",
            selectmode="browse",
        )
        self.tree.column("#0", width=242, stretch=True)
        self.tree.column("category", width=72, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        scrollbar = ttk.Scrollbar(
            left, orient="vertical", command=self.tree.yview, style="Vertical.TScrollbar"
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure("custom", foreground=palette.accent)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_detail())
        self.tree.bind("<Double-1>", lambda _event: self._insert(), add="+")

        detail = tk.Frame(right, bg=palette.bg)
        detail.pack(fill="both", expand=True, padx=(18, 4), pady=(4, 0))
        detail.columnconfigure(0, weight=1)
        self.title_label = tk.Label(
            detail,
            text="",
            bg=palette.bg,
            fg=palette.text,
            font=theme.font(4, "bold"),
            anchor="w",
            justify="left",
            wraplength=460,
        )
        self.title_label.grid(row=0, column=0, sticky="ew")
        self.meta_label = tk.Label(
            detail,
            text="",
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-2),
            anchor="w",
        )
        self.meta_label.grid(row=1, column=0, sticky="ew", pady=(3, 8))
        self.description_label = tk.Label(
            detail,
            text="",
            bg=palette.bg,
            fg=palette.muted,
            font=theme.font(-1),
            anchor="w",
            justify="left",
            wraplength=470,
        )
        self.description_label.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        target_row = tk.Frame(detail, bg=palette.bg)
        target_row.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        tk.Label(
            target_row,
            text="Target",
            bg=palette.bg,
            fg=palette.muted,
            font=theme.font(-1, "bold"),
        ).pack(side="left")
        self.target_var = tk.StringVar(value=target)
        self.target_entry = ttk.Entry(target_row, textvariable=self.target_var)
        self.target_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.target_entry.bind("<KeyRelease>", lambda _event: self._refresh_detail())

        self.command_text = tk.Text(
            detail,
            height=9,
            wrap="none",
            bg=palette.code_bg,
            fg=palette.text,
            insertbackground=palette.accent,
            selectbackground=palette.selection,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=palette.border,
            padx=12,
            pady=10,
            font=theme.font(-1, mono=True),
        )
        self.command_text.grid(row=4, column=0, sticky="nsew")
        detail.rowconfigure(4, weight=1)
        command_scroll = ttk.Scrollbar(
            detail,
            orient="vertical",
            command=self.command_text.yview,
            style="Vertical.TScrollbar",
        )
        command_scroll.grid(row=4, column=1, sticky="ns")
        self.command_text.configure(yscrollcommand=command_scroll.set)
        self.placeholder_label = tk.Label(
            detail,
            text="",
            bg=palette.bg,
            fg=palette.faint,
            font=theme.font(-2),
            anchor="w",
            justify="left",
            wraplength=470,
        )
        self.placeholder_label.grid(row=5, column=0, sticky="ew", pady=(6, 0))

        self.add_button("Insert", self._insert, style="Accent.TButton")
        self.add_button("Copy", self._copy)
        self.add_button("New", self._new)
        self.add_button("Edit", self._edit)
        self.add_button("Delete", self._delete, style="Danger.TButton")
        self.add_button("Close", self.cancel)
        self._load_custom()
        self._refresh_categories()
        self._refresh_list()
        self.tree.focus_set()

    def _load_custom(self) -> None:
        self._custom = self._vault.list_custom_snippets()

    def _refresh_categories(self) -> None:
        categories = sorted(
            {snippet.category for snippet in [*self._builtin, *self._custom] if snippet.category},
            key=str.casefold,
        )
        values = ["All categories", *categories]
        self.category.configure(values=values)
        if self.category_var.get() not in values:
            self.category_var.set("All categories")

    def _refresh_list(self, select: Snippet | None = None) -> None:
        query = self.search.get_value().casefold()
        category = self.category_var.get()
        items = [*self._custom, *self._builtin]
        filtered: list[Snippet] = []
        for snippet in items:
            if category != "All categories" and snippet.category != category:
                continue
            haystack = " ".join(
                (snippet.title, snippet.command, snippet.description, snippet.tags)
            ).casefold()
            if query and query not in haystack:
                continue
            filtered.append(snippet)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._by_iid = {}
        for snippet in filtered:
            iid = f"c:{snippet.id}" if snippet.id is not None else f"b:{snippet.builtin_key}"
            self._by_iid[iid] = snippet
            tags = () if snippet.builtin else ("custom",)
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=f"{'▸' if snippet.builtin else '✦'}  {snippet.title}",
                values=(snippet.category,),
                tags=tags,
            )
        self._visible = filtered
        target = select or (filtered[0] if filtered else None)
        if target is not None:
            iid = f"c:{target.id}" if target.id is not None else f"b:{target.builtin_key}"
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                self.tree.see(iid)
        self._refresh_detail()

    def _selected(self) -> Snippet | None:
        selection = self.tree.selection()
        return self._by_iid.get(selection[0]) if selection else None

    def _resolved_command(self, snippet: Snippet) -> str:
        return resolve_command(snippet.command, target=self.target_var.get().strip())

    def _refresh_detail(self, _event: tk.Event | None = None) -> None:
        snippet = self._selected()
        if snippet is None:
            self.title_label.configure(text="No snippet selected")
            self.meta_label.configure(text="")
            self.description_label.configure(text="")
            self._set_command("")
            self.placeholder_label.configure(text="")
            return
        self.title_label.configure(text=snippet.title)
        source = "Built-in playbook" if snippet.builtin else "Custom snippet"
        self.meta_label.configure(
            text=f"{source}  ·  {snippet.category}  ·  #{snippet.tags.replace(',', ' #')}"
        )
        self.description_label.configure(text=snippet.description or "No description.")
        command = self._resolved_command(snippet)
        self._set_command(command)
        placeholders = snippet_placeholders(command)
        if placeholders:
            self.placeholder_label.configure(
                text="Unresolved placeholders: " + ", ".join(placeholders)
            )
        elif snippet_placeholders(snippet.command):
            self.placeholder_label.configure(text="All placeholders resolved for this target.")
        else:
            self.placeholder_label.configure(text="No placeholders in this command.")

    def _set_command(self, command: str) -> None:
        self.command_text.configure(state="normal")
        self.command_text.delete("1.0", "end")
        self.command_text.insert("1.0", command)
        self.command_text.configure(state="disabled")

    def _insert(self) -> None:
        snippet = self._selected()
        if snippet is None:
            return
        self.result = {"action": "insert", "command": self._resolved_command(snippet)}
        self.destroy()

    def _copy(self) -> None:
        snippet = self._selected()
        if snippet is None:
            return
        self.clipboard_clear()
        self.clipboard_append(self._resolved_command(snippet))
        self.placeholder_label.configure(text="Copied to clipboard.")

    def _new(self) -> None:
        dialog = SnippetDialog(self, self._theme)
        result = dialog.show(590)
        if not isinstance(result, dict):
            return
        try:
            created = self._vault.create_snippet(
                str(result["title"]),
                str(result["command"]),
                str(result["description"]),
                str(result["tags"]),
            )
        except ValueError as exc:
            messagebox.showerror("Snippet not saved", str(exc), parent=self)
            return
        self.grab_set()
        self._load_custom()
        self._refresh_categories()
        self._refresh_list(created)

    def _edit(self) -> None:
        snippet = self._selected()
        if snippet is None or snippet.builtin or snippet.id is None:
            return
        dialog = SnippetDialog(self, self._theme, snippet=snippet)
        result = dialog.show(590)
        if not isinstance(result, dict):
            return
        try:
            updated = self._vault.update_snippet(
                snippet.id,
                title=str(result["title"]),
                command=str(result["command"]),
                description=str(result["description"]),
                tags=str(result["tags"]),
            )
        except ValueError as exc:
            messagebox.showerror("Snippet not saved", str(exc), parent=self)
            return
        self.grab_set()
        self._load_custom()
        self._refresh_categories()
        self._refresh_list(updated)

    def _delete(self) -> None:
        snippet = self._selected()
        if snippet is None or snippet.builtin or snippet.id is None:
            return
        confirmed = messagebox.askyesno(
            "Delete snippet",
            f"Delete “{snippet.title}”? This cannot be undone.",
            parent=self,
        )
        if not confirmed:
            return
        self._vault.delete_snippet(snippet.id)
        self._load_custom()
        self._refresh_categories()
        self._refresh_list()

    def show(self, height: int = 660) -> object | None:
        return super().show(height)
