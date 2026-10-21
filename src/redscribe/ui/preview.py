"""Rendered Markdown preview built on a read-only Tk text widget."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from functools import partial
from tkinter import ttk

from redscribe.domain.utils import slugify
from redscribe.highlight import tokenize_code
from redscribe.markdown import (
    CodeBlock,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Rule,
    Span,
    TableBlock,
    parse_inline,
    parse_markdown,
    safe_url,
)
from redscribe.ui.theme import Theme


class MarkdownPreview(tk.Frame):
    """A read-only, themed view of a Markdown document."""

    def __init__(self, master: tk.Misc, theme: Theme) -> None:
        palette = theme.palette
        super().__init__(master, bg=palette.surface, bd=0, highlightthickness=0)
        self._theme = theme
        self._markdown = ""
        self._link_tags: list[str] = []
        self._urls: dict[str, str] = {}
        self._anchors: dict[str, str] = {}
        self._link_index = 0
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.text = tk.Text(
            self,
            wrap="word",
            bg=palette.surface,
            fg=palette.text,
            insertbackground=palette.accent,
            selectbackground=palette.selection,
            selectforeground=palette.text,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=28,
            pady=22,
            spacing1=1,
            spacing3=2,
            cursor="arrow",
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.text.yview, style="Vertical.TScrollbar"
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=self.scrollbar.set)
        self.text.bind("<Control-a>", self._select_all)
        self.text.bind("<Button-3>", self._show_context_menu)
        self.text.bind("<Motion>", self._on_motion, add="+")
        self.text.bind("<Leave>", lambda _event: self.text.configure(cursor="arrow"), add="+")
        self._menu: tk.Menu | None = None
        self._configure_tags()
        self.text.configure(state="disabled")

    def _configure_tags(self) -> None:
        theme = self._theme
        palette = theme.palette
        self.text.tag_configure("body", font=theme.font(), spacing3=7)
        self.text.tag_configure(
            "h1", font=theme.font(11, "bold"), spacing1=17, spacing3=9, foreground=palette.text
        )
        self.text.tag_configure(
            "h2", font=theme.font(7, "bold"), spacing1=14, spacing3=7, foreground=palette.accent
        )
        self.text.tag_configure(
            "h3", font=theme.font(4, "bold"), spacing1=11, spacing3=6, foreground=palette.amber
        )
        self.text.tag_configure(
            "h4", font=theme.font(2, "bold"), spacing1=9, spacing3=4, foreground=palette.muted
        )
        self.text.tag_configure(
            "h5", font=theme.font(1, "bold"), spacing1=8, spacing3=3, foreground=palette.muted
        )
        self.text.tag_configure(
            "h6", font=theme.font(0, "bold"), spacing1=8, spacing3=3, foreground=palette.faint
        )
        self.text.tag_configure("list", font=theme.font(), lmargin1=14, lmargin2=30)
        self.text.tag_configure("list_marker", foreground=palette.accent)
        self.text.tag_configure(
            "quote",
            font=theme.font(0, italic=True),
            foreground=palette.muted,
            lmargin1=18,
            lmargin2=18,
            spacing1=4,
            spacing3=6,
        )
        self.text.tag_configure("quote_bar", foreground=palette.accent)
        self.text.tag_configure(
            "code_lang",
            font=theme.font(-2, "bold", mono=True),
            foreground=palette.faint,
            spacing1=9,
            lmargin1=18,
        )
        self.text.tag_configure(
            "code",
            font=theme.font(-1, mono=True),
            background=palette.code_bg,
            foreground=palette.text,
            lmargin1=18,
            lmargin2=18,
        )
        self.text.tag_configure("tok_keyword", foreground=palette.accent)
        self.text.tag_configure("tok_builtin", foreground=palette.blue)
        self.text.tag_configure("tok_string", foreground=palette.green)
        self.text.tag_configure("tok_comment", foreground=palette.faint)
        self.text.tag_configure("tok_number", foreground=palette.amber)
        self.text.tag_configure("tok_variable", foreground=palette.amber)
        self.text.tag_configure("strong", font=theme.font(0, "bold"))
        self.text.tag_configure("em", font=theme.font(0, italic=True))
        self.text.tag_configure(
            "inline_code", font=theme.font(-1, mono=True), foreground=palette.green
        )
        self.text.tag_configure("strike", overstrike=True, foreground=palette.muted)
        self.text.tag_configure("rule", foreground=palette.border)
        self.text.tag_configure("table", font=theme.font(-1, mono=True), spacing1=1, spacing3=1)
        self.text.tag_configure(
            "table_header", font=theme.font(-1, "bold", mono=True), foreground=palette.text
        )
        self.text.tag_configure(
            "table_rule", font=theme.font(-1, mono=True), foreground=palette.border
        )

    def set_markdown(self, content: str, *, preserve_scroll: bool = True) -> None:
        self._markdown = content
        try:
            fraction = self.text.yview()[0] if preserve_scroll else 0.0
        except tk.TclError:
            fraction = 0.0
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for tag in self._link_tags:
            self.text.tag_delete(tag)
        self._link_tags = []
        self._urls = {}
        self._anchors = {}
        self._link_index = 0
        try:
            self._render(parse_markdown(content))
        except Exception:
            self.text.insert("1.0", content)
        self.text.configure(state="disabled")
        self.text.yview_moveto(fraction)

    def _render(
        self, blocks: list[Heading | Paragraph | ListBlock | CodeBlock | Quote | TableBlock | Rule]
    ) -> None:
        if not blocks:
            return
        for block in blocks:
            if isinstance(block, Heading):
                self._insert_heading(block)
            elif isinstance(block, Paragraph):
                self._insert_paragraph(block)
            elif isinstance(block, ListBlock):
                self._insert_list(block)
            elif isinstance(block, CodeBlock):
                self._insert_code(block)
            elif isinstance(block, Quote):
                self._insert_quote(block)
            elif isinstance(block, TableBlock):
                self._insert_table(block)
            elif isinstance(block, Rule):
                self.text.insert("end", "─" * 64 + "\n", ("rule",))
            self.text.insert("end", "\n", ("body",))

    def _insert_heading(self, block: Heading) -> None:
        level = min(6, max(1, block.level))
        start = self.text.index("insert")
        self.text.insert("insert", block.text, (f"h{level}",))
        if block.text:
            self._anchors.setdefault(slugify(block.text), start)

    def _insert_paragraph(self, block: Paragraph) -> None:
        self._insert_spans(parse_inline(block.text), "body")

    def _insert_list(self, block: ListBlock) -> None:
        for item in block.items:
            indent = "  " * max(0, item.indent // 2)
            if item.checked is not None:
                marker = "☑ " if item.checked else "☐ "
            elif item.ordered:
                marker = f"{item.number}. "
            else:
                marker = "• "
            self.text.insert("insert", indent, ("list",))
            self.text.insert("insert", marker, ("list", "list_marker"))
            self._insert_spans(parse_inline(item.text), "list")
            self.text.insert("insert", "\n", ("list",))

    def _insert_quote(self, block: Quote) -> None:
        self.text.insert("insert", "▍ ", ("quote", "quote_bar"))
        self._insert_spans(parse_inline(block.text.replace("\n", " ")), "quote")

    def _insert_code(self, block: CodeBlock) -> None:
        language = (block.language or "text").upper()
        self.text.insert("insert", f"{language}\n", ("code_lang",))
        for token in tokenize_code(block.code, block.language):
            tag = f"tok_{token.kind}" if token.kind != "text" else "code"
            self.text.insert("insert", token.text, ("code", tag))

    def _insert_table(self, block: TableBlock) -> None:
        columns = max(1, len(block.headers))
        rows = [list(block.headers), *[row[:columns] for row in block.rows]]
        widths = [3] * columns
        for row in rows:
            for index in range(columns):
                cell = self._plain(row[index] if index < len(row) else "")
                widths[index] = max(widths[index], min(30, len(cell)))
        header = self._format_row(block.headers, widths, columns)
        self.text.insert("insert", header + "\n", ("table", "table_header"))
        separator = "─┼─".join("─" * width for width in widths)
        self.text.insert("insert", separator + "\n", ("table", "table_rule"))
        for row in block.rows:
            line = self._format_row(row, widths, columns)
            self.text.insert("insert", line + "\n", ("table",))

    def _format_row(self, row: list[str], widths: list[int], columns: int) -> str:
        cells: list[str] = []
        for index in range(columns):
            value = self._plain(row[index] if index < len(row) else "")
            cells.append(value[: widths[index]].ljust(widths[index]))
        return " │ ".join(cells)

    def _plain(self, text: str) -> str:
        return "".join(span.text for span in parse_inline(text))

    def _insert_spans(self, spans: list[Span], base: str) -> None:
        for span in spans:
            if not span.text:
                continue
            start = self.text.index("insert")
            self.text.insert("insert", span.text, (base,))
            end = self.text.index("insert")
            if span.kind == "bold":
                self.text.tag_add("strong", start, end)
            elif span.kind == "italic":
                self.text.tag_add("em", start, end)
            elif span.kind == "code":
                self.text.tag_add("inline_code", start, end)
            elif span.kind == "strike":
                self.text.tag_add("strike", start, end)
            elif span.kind == "link":
                url = safe_url(span.url)
                if url is not None:
                    tag = self._link_tag(url)
                    self.text.tag_add(tag, start, end)

    def _link_tag(self, url: str) -> str:
        tag = f"link_{self._link_index}"
        self._link_index += 1
        self._urls[tag] = url
        palette = self._theme.palette
        self.text.tag_configure(tag, foreground=palette.blue, underline=True)
        self.text.tag_bind(tag, "<Button-1>", partial(self._open_link, url))
        self.text.tag_bind(tag, "<Enter>", partial(self._set_cursor, "hand2"))
        self.text.tag_bind(tag, "<Leave>", partial(self._set_cursor, "arrow"))
        self._link_tags.append(tag)
        return tag

    def _open_link(self, url: str, _event: tk.Event | None = None) -> None:
        self._open(url)

    def _set_cursor(self, cursor: str, _event: tk.Event | None = None) -> None:
        self.text.configure({"cursor": cursor})

    def _open(self, url: str) -> None:
        if url.startswith("#"):
            self._scroll_to_anchor(url[1:])
        else:
            webbrowser.open_new_tab(url)

    def _scroll_to_anchor(self, anchor: str) -> None:
        target = self._anchors.get(anchor)
        if target:
            self.text.see(target)

    def _on_motion(self, event: tk.Event) -> None:
        try:
            index = self.text.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        tags = self.text.tag_names(index)
        hovering = any(tag.startswith("link_") for tag in tags)
        self.text.configure(cursor="hand2" if hovering else "arrow")

    def _select_all(self, _event: tk.Event | None = None) -> str:
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")
        return "break"

    def _show_context_menu(self, event: tk.Event) -> None:
        palette = self._theme.palette
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=palette.surface_alt,
            fg=palette.text,
            activebackground=palette.accent,
            activeforeground="#ffffff",
            bd=0,
            font=self._theme.font(-1),
        )
        try:
            index = self.text.index(f"@{event.x},{event.y}")
        except tk.TclError:
            index = "1.0"
        link_tag = next(
            (tag for tag in self.text.tag_names(index) if tag.startswith("link_")),
            None,
        )
        if link_tag is not None:
            ranges = self.text.tag_ranges(link_tag)
            if ranges:
                label = self.text.get(ranges[0], ranges[1])
                menu.add_command(
                    label=f"Open {label[:42]}",
                    command=partial(self._open_index, link_tag),
                )
                menu.add_separator()
        has_selection = bool(self.text.tag_ranges("sel"))
        menu.add_command(
            label="Copy",
            command=self._copy_selection,
            state="normal" if has_selection else "disabled",
        )
        menu.add_command(label="Copy all", command=self.copy_all)
        menu.add_separator()
        menu.add_command(label="Select all", command=lambda: self._select_all())
        self._menu = menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_index(self, tag: str) -> None:
        url = self._urls.get(tag)
        if url:
            self._open(url)

    def _copy_selection(self) -> None:
        if not self.text.tag_ranges("sel"):
            return
        self.clipboard_clear()
        self.clipboard_append(self.text.get("sel.first", "sel.last"))

    def copy_all(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        palette = theme.palette
        self.configure(bg=palette.surface)
        self.text.configure(
            bg=palette.surface,
            fg=palette.text,
            insertbackground=palette.accent,
            selectbackground=palette.selection,
            selectforeground=palette.text,
        )
        self._configure_tags()
        self.set_markdown(self._markdown)
