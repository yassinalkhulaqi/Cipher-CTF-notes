"""Workspace dashboard with stats, recent notes, flags, and tags."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from functools import partial
from tkinter import ttk

from redscribe.domain.models import FlagHit, Node, TagCount
from redscribe.domain.utils import humanize_delta, truncate
from redscribe.storage.db import Vault
from redscribe.ui.theme import Theme, difficulty_color, status_color
from redscribe.ui.widgets import Card, ScrollableFrame, TagChip, bind_click, divider


class Dashboard(tk.Frame):
    """A read-only overview of the current vault."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        vault: Vault,
        on_open: Callable[[int], None],
        on_new_note: Callable[[], None],
        on_search: Callable[[], None],
        on_snippets: Callable[[], None],
        on_tag: Callable[[str], None],
        on_view_flags: Callable[[], None],
        on_load_demo: Callable[[], None],
    ) -> None:
        palette = theme.palette
        super().__init__(master, bg=palette.bg)
        self._theme = theme
        self._vault = vault
        self._on_open = on_open
        self._on_new_note = on_new_note
        self._on_search = on_search
        self._on_snippets = on_snippets
        self._on_tag = on_tag
        self._on_view_flags = on_view_flags
        self._on_load_demo = on_load_demo
        self._stats = vault.stats()
        self.scroll = ScrollableFrame(self, theme)
        self.scroll.pack(fill="both", expand=True)
        self._build()

    def _build(self) -> None:
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        host = tk.Frame(self.scroll.inner, bg=self._theme.palette.bg)
        host.pack(fill="both", expand=True, padx=30, pady=(26, 32))
        self._build_header(host)
        if self._stats.notes == 0:
            self._build_empty(host)
            return
        self._build_stats(host)
        self._build_quick_actions(host)
        self._build_columns(host)

    def _build_header(self, host: tk.Frame) -> None:
        palette = self._theme.palette
        header = tk.Frame(host, bg=palette.bg)
        header.pack(fill="x", pady=(0, 20))
        text = tk.Frame(header, bg=palette.bg)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(
            text,
            text="OPERATIONS DASHBOARD",
            bg=palette.bg,
            fg=palette.accent,
            font=self._theme.font(-2, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            text,
            text="Your notebook at a glance",
            bg=palette.bg,
            fg=palette.text,
            font=self._theme.font(13, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(5, 3))
        recent = self._vault.recent_notes(1)
        updated = f" · last edit {humanize_delta(recent[0].updated_at)}" if recent else ""
        summary = (
            f"{self._stats.notes} notes in {self._stats.folders} folders · "
            f"{self._stats.flags} flags · {self._stats.targets} targets{updated}"
        )
        tk.Label(
            text,
            text=summary,
            bg=palette.bg,
            fg=palette.muted,
            font=self._theme.font(-1),
            anchor="w",
        ).pack(fill="x")

    def _build_empty(self, host: tk.Frame) -> None:
        palette = self._theme.palette
        card = Card(host, self._theme, padding=(40, 42))
        card.pack(fill="x", pady=(20, 0))
        tk.Label(
            card.body,
            text="◆",
            bg=palette.surface_alt,
            fg=palette.accent,
            font=self._theme.font(28, "bold"),
        ).pack(pady=(4, 14))
        tk.Label(
            card.body,
            text="Your vault is ready",
            bg=palette.surface_alt,
            fg=palette.text,
            font=self._theme.font(9, "bold"),
        ).pack()
        tk.Label(
            card.body,
            text=(
                "Capture a CTF challenge, a host assessment, or an engagement log. "
                "Everything stays in one portable SQLite file."
            ),
            bg=palette.surface_alt,
            fg=palette.muted,
            font=self._theme.font(),
            wraplength=520,
            justify="center",
        ).pack(pady=(8, 20))
        actions = tk.Frame(card.body, bg=palette.surface_alt)
        actions.pack()
        ttk.Button(
            actions,
            text="Create your first note",
            style="Accent.TButton",
            command=self._on_new_note,
        ).pack(side="left", padx=4)
        ttk.Button(
            actions, text="Load demo vault", style="Tool.TButton", command=self._on_load_demo
        ).pack(side="left", padx=4)

    def _build_stats(self, host: tk.Frame) -> None:
        palette = self._theme.palette
        stats = [
            ("NOTES", self._stats.notes, "captured", palette.accent),
            ("FLAGS", self._stats.flags, "collected", palette.amber),
            ("TARGETS", self._stats.targets, "in scope", palette.blue),
            ("TAGS", self._stats.tags, "labels", palette.green),
        ]
        row = tk.Frame(host, bg=palette.bg)
        row.pack(fill="x")
        for column, (label, value, caption, color) in enumerate(stats):
            row.columnconfigure(column, weight=1, uniform="stat")
            card = Card(row, self._theme, padding=(16, 14))
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 6, 0 if column == 3 else 6),
            )
            tk.Label(
                card.body,
                text=label,
                bg=palette.surface_alt,
                fg=palette.faint,
                font=self._theme.font(-2, "bold"),
                anchor="w",
            ).pack(fill="x")
            value_row = tk.Frame(card.body, bg=palette.surface_alt)
            value_row.pack(fill="x", pady=(4, 0))
            tk.Label(
                value_row,
                text=str(value),
                bg=palette.surface_alt,
                fg=color,
                font=self._theme.font(16, "bold"),
                anchor="w",
            ).pack(side="left")
            tk.Label(
                value_row,
                text=caption,
                bg=palette.surface_alt,
                fg=palette.faint,
                font=self._theme.font(-2),
                anchor="w",
            ).pack(side="left", padx=(7, 0), pady=(8, 0))

    def _build_quick_actions(self, host: tk.Frame) -> None:
        palette = self._theme.palette
        bar = tk.Frame(host, bg=palette.bg)
        bar.pack(fill="x", pady=(16, 20))
        ttk.Button(bar, text="+  New note", style="Accent.TButton", command=self._on_new_note).pack(
            side="left"
        )
        ttk.Button(bar, text="Search vault", style="Tool.TButton", command=self._on_search).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(
            bar, text="Snippet library", style="Tool.TButton", command=self._on_snippets
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            bar, text="Flag collection", style="Tool.TButton", command=self._on_view_flags
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            bar, text="Load demo vault", style="Subtle.TButton", command=self._on_load_demo
        ).pack(side="left", padx=(8, 0))

    def _build_columns(self, host: tk.Frame) -> None:
        palette = self._theme.palette
        columns = tk.Frame(host, bg=palette.bg)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=3, uniform="dash")
        columns.columnconfigure(1, weight=2, uniform="dash")
        left = tk.Frame(columns, bg=palette.bg)
        right = tk.Frame(columns, bg=palette.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        recent_card = Card(left, self._theme)
        recent_card.pack(fill="x")
        self._section_header(recent_card.body, "Recent notes", "Search", self._on_search)
        recent = self._vault.recent_notes(6)
        if not recent:
            self._empty_note(recent_card.body, "No notes yet.")
        for node in recent:
            self._note_row(recent_card.body, node, show_path=True)

        tags_card = Card(left, self._theme)
        tags_card.pack(fill="x", pady=(14, 0))
        tags = self._vault.tag_counts()[:18]
        self._section_header(tags_card.body, "Tags", "Search", self._on_search)
        if tags:
            self._tag_grid(tags_card.body, tags)
        else:
            self._empty_note(tags_card.body, "Add tags to notes to build a quick filter list.")

        pinned_card = Card(right, self._theme)
        pinned_card.pack(fill="x")
        self._section_header(pinned_card.body, "Pinned", "", None)
        pinned = self._vault.pinned_notes(5)
        if not pinned:
            self._empty_note(pinned_card.body, "Pin important notes to keep them in reach.")
        for node in pinned:
            self._note_row(pinned_card.body, node, show_path=False)

        flags_card = Card(right, self._theme)
        flags_card.pack(fill="x", pady=(14, 0))
        self._section_header(flags_card.body, "Flag collection", "View all", self._on_view_flags)
        flags = self._vault.collected_flags(5)
        if not flags:
            self._empty_note(flags_card.body, "Flags found in note bodies appear here.")
        for hit in flags:
            self._flag_row(flags_card.body, hit)

    def _section_header(
        self,
        parent: tk.Frame,
        title: str,
        action_text: str,
        action: Callable[[], None] | None,
    ) -> None:
        palette = self._theme.palette
        header = tk.Frame(parent, bg=palette.surface_alt)
        header.pack(fill="x", pady=(0, 8))
        tk.Label(
            header,
            text=title,
            bg=palette.surface_alt,
            fg=palette.text,
            font=self._theme.font(1, "bold"),
            anchor="w",
        ).pack(side="left")
        if action_text and action is not None:
            link = tk.Label(
                header,
                text=action_text,
                bg=palette.surface_alt,
                fg=palette.accent,
                font=self._theme.font(-2, "bold"),
                cursor="hand2",
            )
            link.pack(side="right")
            link.bind("<Button-1>", lambda _event: action())

    def _empty_note(self, parent: tk.Frame, message: str) -> None:
        palette = self._theme.palette
        tk.Label(
            parent,
            text=message,
            bg=palette.surface_alt,
            fg=palette.faint,
            font=self._theme.font(-1),
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(2, 6))

    def _note_row(self, parent: tk.Frame, node: Node, *, show_path: bool) -> None:
        palette = self._theme.palette
        base = palette.surface_alt
        row = tk.Frame(parent, bg=base, cursor="hand2")
        row.pack(fill="x", pady=1)
        glyph = tk.Label(
            row,
            text="◆",
            bg=base,
            fg=status_color(self._theme, node.status),
            font=self._theme.font(0, "bold"),
            width=2,
        )
        glyph.pack(side="left", padx=(2, 4), pady=5)
        text = tk.Frame(row, bg=base)
        text.pack(side="left", fill="x", expand=True)
        title = truncate(node.title, 58)
        tk.Label(
            text,
            text=title,
            bg=base,
            fg=palette.text,
            font=self._theme.font(0, "bold"),
            anchor="w",
        ).pack(fill="x")
        subtitle = ""
        if show_path:
            path = self._vault.path_of(node.id, include_self=False)
            subtitle = path or "Vault root"
        elif node.target:
            subtitle = node.target
        if subtitle:
            tk.Label(
                text,
                text=subtitle,
                bg=base,
                fg=palette.faint,
                font=self._theme.font(-2),
                anchor="w",
            ).pack(fill="x")
        meta = tk.Label(
            row,
            text=humanize_delta(node.updated_at),
            bg=base,
            fg=palette.faint,
            font=self._theme.font(-2),
            anchor="e",
        )
        meta.pack(side="right", padx=(8, 4))
        if node.difficulty:
            tk.Label(
                row,
                text=node.difficulty_label,
                bg=base,
                fg=difficulty_color(self._theme, node.difficulty),
                font=self._theme.font(-2, "bold"),
                anchor="e",
            ).pack(side="right", padx=(4, 0))
        bind_click(row, partial(self._on_open, node.id))
        self._bind_hover(row, base, palette.raised)
        divider(parent, self._theme).pack(fill="x", pady=(2, 2))

    def _flag_row(self, parent: tk.Frame, hit: FlagHit) -> None:
        palette = self._theme.palette
        base = palette.surface_alt
        row = tk.Frame(parent, bg=base, cursor="hand2")
        row.pack(fill="x", pady=1)
        tk.Label(
            row,
            text="⚑",
            bg=base,
            fg=palette.amber,
            font=self._theme.font(0, "bold"),
            width=2,
        ).pack(side="left", padx=(2, 4))
        text = tk.Frame(row, bg=base)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(
            text,
            text=truncate(hit.flag, 38),
            bg=base,
            fg=palette.amber,
            font=self._theme.font(-1, mono=True),
            anchor="w",
        ).pack(fill="x")
        path = hit.path or "Vault root"
        tk.Label(
            text,
            text=f"{truncate(hit.title, 34)}  ·  {truncate(path, 42)}",
            bg=base,
            fg=palette.faint,
            font=self._theme.font(-2),
            anchor="w",
        ).pack(fill="x")
        bind_click(row, partial(self._on_open, hit.node_id))
        self._bind_hover(row, base, palette.raised)
        divider(parent, self._theme).pack(fill="x", pady=(2, 2))

    def _tag_grid(self, parent: tk.Frame, tags: list[TagCount]) -> None:
        palette = self._theme.palette
        grid = tk.Frame(parent, bg=palette.surface_alt)
        grid.pack(fill="x")
        for column in range(3):
            grid.columnconfigure(column, weight=1)
        for index, tag in enumerate(tags):
            chip = TagChip(
                grid,
                f"{tag.tag}  {tag.count}",
                self._theme,
                command=partial(self._on_tag, tag.tag),
                background=palette.surface,
            )
            chip.grid(
                row=index // 3,
                column=index % 3,
                sticky="w",
                padx=(0, 6),
                pady=3,
            )

    def _bind_hover(self, widget: tk.Misc, base: str, hover: str) -> None:
        def paint(color: str, target: tk.Misc = widget) -> None:
            try:
                target.configure({"bg": color})
            except tk.TclError:
                return
            for child in target.winfo_children():
                paint(color, child)

        def bind_all_children(target: tk.Misc) -> None:
            target.bind("<Enter>", lambda _event: paint(hover), add="+")
            target.bind("<Leave>", lambda _event: paint(base), add="+")
            for child in target.winfo_children():
                bind_all_children(child)

        bind_all_children(widget)

    def refresh(self) -> None:
        self._stats = self._vault.stats()
        self.scroll.scroll_to_top()
        self._build()
