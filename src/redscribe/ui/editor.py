"""A Markdown editor with syntax highlighting, line numbers, and find/replace."""

from __future__ import annotations

import contextlib
import re
import tkinter as tk
from collections.abc import Callable
from functools import partial
from tkinter import font as tkfont
from tkinter import ttk

from redscribe.ui.theme import Theme

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*([\w.+#-]*)[ \t]*$")
_HEADING_RE = re.compile(r"^( {0,3})(#{1,6})([ \t]+)(.*)$")
_QUOTE_RE = re.compile(r"^( {0,3})(>)([ \t]?)(.*)$")
_LIST_RE = re.compile(r"^([ \t]*)([-+*]|\d{1,9}[.)])([ \t]+)(.*)$")
_TASK_RE = re.compile(r"^\[([ xX])\][ \t]+(.*)$")
_HR_RE = re.compile(r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_LIST_CONTINUE_RE = re.compile(r"^([ \t]*)([-+*]|\d+[.)])[ \t]+(\[[ xX]\][ \t]+)?(.*)$")
_QUOTE_CONTINUE_RE = re.compile(r"^([ \t]*)((?:>[ \t]?)+)(.*)$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_INLINE_RE = re.compile(
    r"(?P<code>`[^`\n]+`)"
    r"|(?P<link>\[(?P<link_label>[^\]\n]+)\]\((?P<link_url>[^)\s]+)\))"
    r"|(?P<bold>\*\*(?P<bold_text>.+?)\*\*|__(?P<bold_text2>.+?)__)"
    r"|(?P<strike>~~(?P<strike_text>.+?)~~)"
    r"|(?P<italic>(?<!\*)\*(?!\*)(?P<italic_text>[^*\n]+)\*(?!\*))"
    r"|(?P<url>https?://[^\s<>()]+)"
)
_FLAG_RE = re.compile(
    r"\b(?:flag|HTB|CTF|picoCTF|THM|DUCTF|NCL|UofTCTF|ictf)\{[^}\n]{1,160}\}",
    re.IGNORECASE,
)

_SYNTAX_TAGS = (
    "h1",
    "h2",
    "h3",
    "h4",
    "quote",
    "list_marker",
    "fence",
    "codeblock",
    "hr",
    "table",
    "inline_marker",
    "inline_code",
    "bold",
    "italic",
    "strike",
    "link",
    "url",
    "flag",
)


class MarkdownEditor(tk.Frame):
    """A focused editor surface for one Markdown note."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        palette = theme.palette
        super().__init__(master, bg=palette.surface, bd=0, highlightthickness=0)
        self._theme = theme
        self._on_change = on_change
        self._highlight_job: str | None = None
        self._search_job: str | None = None
        self._loading = False
        self._find_ranges: list[tuple[str, str]] = []
        self._find_position = -1
        self._scroll_callback: Callable[[str, str], None] | None = None
        self._mono_font = theme.font(-1, mono=True)
        self._font_object = tkfont.Font(root=self, font=self._mono_font)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.gutter = tk.Canvas(
            self,
            width=46,
            bg=palette.bg,
            bd=0,
            highlightthickness=0,
        )
        self.gutter.grid(row=0, column=0, sticky="ns")
        self.gutter.bind("<Button-1>", self._on_gutter_click)
        self.gutter.bind("<Configure>", lambda _event: self._redraw_gutter())

        self.text = tk.Text(
            self,
            wrap="word",
            undo=True,
            autoseparators=True,
            maxundo=-1,
            bg=palette.surface,
            fg=palette.text,
            insertbackground=palette.accent,
            insertwidth=2,
            selectbackground=palette.selection,
            selectforeground=palette.text,
            inactiveselectbackground=palette.selection,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=22,
            pady=16,
            spacing1=1,
            spacing3=2,
            exportselection=False,
        )
        self.text.grid(row=0, column=1, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.text.yview, style="Vertical.TScrollbar"
        )
        self.scrollbar.grid(row=0, column=2, sticky="ns")
        self.text.configure(yscrollcommand=self._on_yscroll)  # type: ignore[arg-type]

        self._findbar = self._build_findbar()
        self._findbar.grid(row=1, column=0, columnspan=3, sticky="ew")
        self._findbar.grid_remove()

        self._configure_tags()
        self._bind_events()
        self._update_font_metrics()
        self._update_current_line()

    def _build_findbar(self) -> tk.Frame:
        palette = self._theme.palette
        bar = tk.Frame(
            self,
            bg=palette.surface_alt,
            bd=0,
            highlightthickness=1,
            highlightbackground=palette.border,
        )
        bar.columnconfigure(1, weight=1)
        self._find_var = tk.StringVar()
        self._replace_var = tk.StringVar()
        self._match_label = tk.Label(
            bar,
            text="",
            bg=palette.surface_alt,
            fg=palette.faint,
            font=self._theme.font(-2),
            width=10,
            anchor="w",
        )
        find_label = tk.Label(
            bar,
            text="Find",
            bg=palette.surface_alt,
            fg=palette.muted,
            font=self._theme.font(-1, "bold"),
        )
        find_label.grid(row=0, column=0, padx=(10, 8), pady=(7, 3), sticky="w")
        self._find_entry = ttk.Entry(bar, textvariable=self._find_var, width=28)
        self._find_entry.grid(row=0, column=1, padx=(0, 8), pady=(7, 3), sticky="ew")
        self._match_label.grid(row=0, column=2, padx=(0, 6), pady=(7, 3), sticky="w")
        previous = ttk.Button(
            bar, text="Prev", style="Tool.TButton", width=5, command=self.find_previous
        )
        previous.grid(row=0, column=3, padx=(0, 4), pady=(7, 3))
        following = ttk.Button(
            bar, text="Next", style="Tool.TButton", width=5, command=self.find_next
        )
        following.grid(row=0, column=4, padx=(0, 4), pady=(7, 3))
        close = ttk.Button(bar, text="×", style="Tool.TButton", width=3, command=self.hide_find)
        close.grid(row=0, column=5, rowspan=2, padx=(4, 8), pady=6, sticky="ns")

        replace_label = tk.Label(
            bar,
            text="Replace",
            bg=palette.surface_alt,
            fg=palette.muted,
            font=self._theme.font(-1, "bold"),
        )
        replace_label.grid(row=1, column=0, padx=(10, 8), pady=(3, 7), sticky="w")
        self._replace_entry = ttk.Entry(bar, textvariable=self._replace_var, width=28)
        self._replace_entry.grid(row=1, column=1, padx=(0, 8), pady=(3, 7), sticky="ew")
        replace_one = ttk.Button(
            bar, text="Replace", style="Tool.TButton", width=8, command=self.replace_current
        )
        replace_one.grid(row=1, column=3, padx=(0, 4), pady=(3, 7))
        replace_all = ttk.Button(
            bar, text="All", style="Tool.TButton", width=5, command=self.replace_all
        )
        replace_all.grid(row=1, column=4, padx=(0, 4), pady=(3, 7))
        self._replace_label = replace_label
        self._replace_one = replace_one
        self._replace_all = replace_all

        self._find_entry.bind("<Return>", lambda _event: self.find_next())
        self._find_entry.bind("<Shift-Return>", lambda _event: self.find_previous())
        self._replace_entry.bind("<Return>", lambda _event: self.replace_current())
        for widget in (self._find_entry, self._replace_entry):
            widget.bind("<Escape>", lambda _event: self.hide_find())
        self._find_var.trace_add("write", lambda *_args: self._schedule_search())
        bar.bind("<Escape>", lambda _event: self.hide_find())
        return bar

    def _bind_events(self) -> None:
        text = self.text
        text.bind("<KeyRelease>", self._on_key_release, add="+")
        text.bind("<ButtonRelease-1>", self._on_cursor_activity, add="+")
        text.bind("<Return>", self._on_return, add="+")
        text.bind("<Tab>", self._on_tab, add="+")
        text.bind("<Shift-Tab>", self._on_shift_tab, add="+")
        text.bind("<Control-b>", lambda _event: self._wrap_selection("**", "**", "bold"))
        text.bind("<Control-i>", lambda _event: self._wrap_selection("*", "*", "italic"))
        text.bind("<Control-k>", lambda _event: self._wrap_selection("`", "`", "code"))
        text.bind("<Control-Shift-X>", lambda _event: self._wrap_selection("~~", "~~", "text"))
        text.bind("<Control-a>", self._select_all)
        text.bind("<<Paste>>", self._on_external_change, add="+")
        text.bind("<<Cut>>", self._on_external_change, add="+")
        text.bind("<<Undo>>", self._on_external_change, add="+")
        text.bind("<<Redo>>", self._on_external_change, add="+")
        text.bind("<Control-f>", partial(self._find_shortcut, replace=False))
        text.bind("<Control-h>", partial(self._find_shortcut, replace=True))
        text.bind("<Escape>", lambda _event: self.hide_find())

    def _configure_tags(self) -> None:
        palette = self._theme.palette
        theme = self._theme
        self.text.configure(tabs=(self._font_object.measure("    "),))

        self.text.tag_configure("current_line", background=palette.surface_alt)
        self.text.tag_configure(
            "h1", font=theme.font(10, "bold"), foreground=palette.text, spacing1=16, spacing3=8
        )
        self.text.tag_configure(
            "h2", font=theme.font(6, "bold"), foreground=palette.accent, spacing1=13, spacing3=6
        )
        self.text.tag_configure(
            "h3", font=theme.font(3, "bold"), foreground=palette.amber, spacing1=10, spacing3=5
        )
        self.text.tag_configure(
            "h4", font=theme.font(1, "bold"), foreground=palette.muted, spacing1=8, spacing3=4
        )
        self.text.tag_configure(
            "quote",
            font=theme.font(0, italic=True),
            foreground=palette.muted,
            lmargin1=20,
            lmargin2=20,
        )
        self.text.tag_configure(
            "list_marker", foreground=palette.accent, font=theme.font(0, "bold")
        )
        self.text.tag_configure("fence", foreground=palette.faint, font=self._mono_font)
        self.text.tag_configure(
            "codeblock",
            foreground=palette.text,
            background=palette.code_bg,
            font=self._mono_font,
            lmargin1=16,
            lmargin2=16,
            spacing1=1,
            spacing3=1,
        )
        self.text.tag_configure("hr", foreground=palette.faint)
        self.text.tag_configure("table", foreground=palette.muted, font=self._mono_font)
        self.text.tag_configure("inline_marker", foreground=palette.faint)
        self.text.tag_configure("inline_code", foreground=palette.green, font=self._mono_font)
        self.text.tag_configure("bold", font=theme.font(0, "bold"))
        self.text.tag_configure("italic", font=theme.font(0, italic=True))
        self.text.tag_configure("strike", overstrike=True, foreground=palette.muted)
        self.text.tag_configure("link", foreground=palette.blue, underline=True)
        self.text.tag_configure("url", foreground=palette.blue)
        self.text.tag_configure("flag", foreground=palette.amber, font=theme.font(0, "bold"))
        self.text.tag_configure("find_all", background=palette.accent_soft)
        self.text.tag_configure("find_current", background=palette.accent, foreground="#ffffff")

    def _update_font_metrics(self) -> None:
        self.text.configure(font=self._theme.font(1, mono=False))
        padding = 24
        digits = max(3, len(str(self._line_count())))
        self._gutter_width = digits * max(7, self._font_object.measure("0")) + padding
        self.gutter.configure(width=self._gutter_width)

    def bind_change(self, callback: Callable[[], None]) -> None:
        self._on_change = callback

    def _on_yscroll(self, first: str, last: str) -> None:
        self.scrollbar.set(first, last)
        self._redraw_gutter()
        if self._scroll_callback is not None:
            self._scroll_callback(first, last)

    def set_scroll_callback(self, callback: Callable[[str, str], None] | None) -> None:
        self._scroll_callback = callback

    def _on_key_release(self, event: tk.Event) -> None:
        self._update_current_line()
        content_keys = {"BackSpace", "Delete", "Return", "Tab"}
        if event.char or event.keysym in content_keys:
            self._notify_change()
        self._redraw_gutter()

    def _on_cursor_activity(self, _event: tk.Event | None = None) -> None:
        self._update_current_line()
        self._redraw_gutter()

    def _on_external_change(self, _event: tk.Event | None = None) -> None:
        self.after_idle(self._notify_change)

    def _notify_change(self) -> None:
        if self._loading:
            return
        self.schedule_highlight()
        self._update_font_metrics()
        self._redraw_gutter()
        if self._on_change is not None:
            self._on_change()
        if self._findbar.winfo_ismapped() and self._find_var.get():
            self._schedule_search()

    def _select_all(self, _event: tk.Event | None = None) -> str:
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")
        self.text.see("insert")
        return "break"

    def _update_current_line(self) -> None:
        self.text.tag_remove("current_line", "1.0", "end")
        self.text.tag_add("current_line", "insert linestart", "insert lineend+1c")
        self._redraw_gutter()

    def _line_count(self) -> int:
        try:
            return int(self.text.index("end-1c").split(".")[0])
        except (tk.TclError, ValueError):
            return 1

    def _redraw_gutter(self) -> None:
        if not self.gutter.winfo_exists():
            return
        width = max(1, self.gutter.winfo_width())
        height = max(1, self.gutter.winfo_height())
        if width <= 1:
            width = getattr(self, "_gutter_width", 46)
        self.gutter.delete("all")
        palette = self._theme.palette
        self.gutter.create_line(width - 1, 0, width - 1, height, fill=palette.border, width=1)
        try:
            top = int(self.text.index("@0,0").split(".")[0])
            current = int(self.text.index("insert").split(".")[0])
        except (tk.TclError, ValueError):
            return
        line_total = self._line_count()
        digits = max(3, len(str(line_total)))
        for offset in range(0, 200):
            line_number = top + offset
            if line_number > line_total:
                break
            try:
                info = self.text.dlineinfo(f"{line_number}.0")
            except tk.TclError:
                break
            if info is None:
                continue
            _x, y, _line_width, line_height, _baseline = info
            if y > height:
                break
            color = palette.accent if line_number == current else palette.faint
            self.gutter.create_text(
                width - 12,
                y + line_height / 2,
                text=str(line_number).rjust(digits),
                fill=color,
                font=self._theme.font(-2, mono=True),
                anchor="e",
            )

    def _on_gutter_click(self, event: tk.Event) -> None:
        try:
            index = self.text.index(f"@0,{event.y}")
        except tk.TclError:
            return
        self.text.mark_set("insert", index)
        self.text.see("insert")
        self.text.focus_set()
        self._update_current_line()

    def schedule_highlight(self) -> None:
        if self._highlight_job is not None:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(120, self._run_highlight)

    def _run_highlight(self) -> None:
        self._highlight_job = None
        self._highlight()

    def _highlight(self) -> None:
        for tag in _SYNTAX_TAGS:
            self.text.tag_remove(tag, "1.0", "end")
        content = self.text.get("1.0", "end-1c")
        lines = content.split("\n")
        in_fence = False
        for number, line in enumerate(lines, start=1):
            start = f"{number}.0"
            end = f"{number}.end"
            fence = _FENCE_RE.match(line)
            if fence:
                self.text.tag_add("fence", start, end)
                in_fence = not in_fence
                continue
            if in_fence:
                self.text.tag_add("codeblock", start, f"{number}.end+1c")
                continue
            heading = _HEADING_RE.match(line)
            if heading:
                level = min(4, len(heading.group(2)))
                self._tag_span(number, heading.start(4), len(line), f"h{level}")
                continue
            quote = _QUOTE_RE.match(line)
            if quote:
                self.text.tag_add("quote", start, end)
                self._apply_inline(number, line)
                continue
            if _HR_RE.match(line):
                self.text.tag_add("hr", start, end)
                continue
            listing = _LIST_RE.match(line)
            if listing:
                self.text.tag_add(
                    "list_marker",
                    f"{number}.{listing.start(2)}",
                    f"{number}.{listing.end(2)}",
                )
                self._apply_inline(number, line)
                continue
            if _TABLE_SEPARATOR_RE.match(line) and "|" in line:
                self.text.tag_add("table", start, end)
                continue
            self._apply_inline(number, line)
        self._update_current_line()

    def _tag_span(self, line: int, start: int, end: int, tag: str) -> None:
        if end > start:
            self.text.tag_add(tag, f"{line}.{start}", f"{line}.{end}")

    def _apply_inline(self, number: int, line: str) -> None:
        for match in _INLINE_RE.finditer(line):
            if match.group("code"):
                self._tag_span(number, match.start(), match.end(), "inline_marker")
                self._tag_span(number, match.start() + 1, match.end() - 1, "inline_code")
            elif match.group("link"):
                label_start, label_end = match.start("link_label"), match.end("link_label")
                url_start, url_end = match.start("link_url"), match.end("link_url")
                self._tag_span(number, label_start, label_end, "link")
                self._tag_span(number, url_start, url_end, "url")
            elif match.group("bold"):
                self._tag_span(number, match.start(), match.start() + 2, "inline_marker")
                self._tag_span(number, match.start() + 2, match.end() - 2, "bold")
                self._tag_span(number, match.end() - 2, match.end(), "inline_marker")
            elif match.group("strike"):
                self._tag_span(number, match.start(), match.start() + 2, "inline_marker")
                self._tag_span(number, match.start() + 2, match.end() - 2, "strike")
                self._tag_span(number, match.end() - 2, match.end(), "inline_marker")
            elif match.group("italic"):
                self._tag_span(number, match.start(), match.start() + 1, "inline_marker")
                self._tag_span(number, match.start() + 1, match.end() - 1, "italic")
                self._tag_span(number, match.end() - 1, match.end(), "inline_marker")
            elif match.group("url"):
                self._tag_span(number, match.start(), match.end(), "url")
        for flag in _FLAG_RE.finditer(line):
            self._tag_span(number, flag.start(), flag.end(), "flag")

    def _on_return(self, _event: tk.Event | None = None) -> str | None:
        line = self.text.get("insert linestart", "insert lineend")
        cursor_column = int(self.text.index("insert").split(".")[1])
        before_cursor = line[:cursor_column]
        quote = _QUOTE_CONTINUE_RE.match(before_cursor)
        if quote is not None:
            indent, marker, quoted_text = quote.groups()
            if not quoted_text.strip():
                self.text.delete("insert linestart", "insert lineend")
                return "break"
            separator = "" if marker.endswith((" ", "\t")) else " "
            self.text.insert("insert", f"\n{indent}{marker}{separator}")
            self.text.see("insert")
            self._notify_change()
            return "break"
        match = _LIST_CONTINUE_RE.match(before_cursor)
        if match is None:
            return None
        indent, marker, task, rest = match.groups()
        if not rest.strip():
            self.text.delete("insert linestart", "insert lineend")
            return "break"
        if marker[0].isdigit():
            number = int(marker[:-1])
            new_marker = f"{number + 1}{marker[-1]}"
        else:
            new_marker = marker
        continuation = f"\n{indent}{new_marker} "
        if task is not None:
            continuation += "[ ] "
        self.text.insert("insert", continuation)
        self.text.see("insert")
        self._notify_change()
        return "break"

    def _on_tab(self, _event: tk.Event | None = None) -> str:
        if self._indent_selection(add=True):
            return "break"
        self.text.insert("insert", "    ")
        self._notify_change()
        return "break"

    def _on_shift_tab(self, _event: tk.Event | None = None) -> str:
        self._indent_selection(add=False)
        return "break"

    def _selected_lines(self) -> tuple[int, int] | None:
        ranges = self.text.tag_ranges("sel")
        if len(ranges) != 2:
            return None
        start_line = int(str(ranges[0]).split(".")[0])
        end_index = str(ranges[1])
        end_line = int(end_index.split(".")[0])
        end_column = int(end_index.split(".")[1])
        if end_column == 0 and end_line > start_line:
            end_line -= 1
        return start_line, end_line

    def _indent_selection(self, *, add: bool) -> bool:
        selected = self._selected_lines()
        if selected is None:
            if add:
                return False
            line_start = self.text.index("insert linestart")
            line_text = self.text.get(line_start, "insert")
            remove = len(line_text) - len(line_text.lstrip(" "))
            if remove:
                self.text.delete(line_start, f"{line_start}+{min(4, remove)}c")
                self._notify_change()
            return True
        start_line, end_line = selected
        for line in range(end_line, start_line - 1, -1):
            line_start = f"{line}.0"
            if add:
                self.text.insert(line_start, "    ")
            else:
                line_text = self.text.get(line_start, f"{line}.end")
                remove = len(line_text) - len(line_text.lstrip(" "))
                if remove:
                    self.text.delete(line_start, f"{line_start}+{min(4, remove)}c")
        self.text.tag_add("sel", f"{start_line}.0", f"{end_line}.end")
        self._notify_change()
        return True

    def _wrap_selection(self, prefix: str, suffix: str, placeholder: str) -> str:
        ranges = self.text.tag_ranges("sel")
        if len(ranges) == 2:
            selected = self.text.get(ranges[0], ranges[1])
            self.text.delete(ranges[0], ranges[1])
            self.text.insert(ranges[0], f"{prefix}{selected}{suffix}")
            self.text.tag_add("sel", ranges[0], f"{ranges[1]}+{len(prefix) + len(suffix)}c")
        else:
            start = self.text.index("insert")
            self.text.insert(start, f"{prefix}{placeholder}{suffix}")
            self.text.tag_add(
                "sel", f"{start}+{len(prefix)}c", f"{start}+{len(prefix)}c+{len(placeholder)}c"
            )
            self.text.mark_set("insert", f"{start}+{len(prefix) + len(placeholder)}c")
        self.text.focus_set()
        self._notify_change()
        return "break"

    def show_find(self, *, replace: bool = False) -> None:
        self._findbar.grid()
        if replace:
            self._replace_label.grid()
            self._replace_entry.grid()
            self._replace_one.grid()
            self._replace_all.grid()
        else:
            self._replace_label.grid_remove()
            self._replace_entry.grid_remove()
            self._replace_one.grid_remove()
            self._replace_all.grid_remove()
        selected = self.text.get("sel.first", "sel.last") if self.text.tag_ranges("sel") else ""
        if selected and "\n" not in selected:
            self._find_var.set(selected)
        self._find_entry.focus_set()
        if self._find_var.get():
            self._find_entry.selection_range(0, "end")
            self._run_search()
        else:
            self._find_entry.selection_range(0, "end")

    def _find_shortcut(self, _event: tk.Event, *, replace: bool) -> str:
        self.show_find(replace=replace)
        return "break"

    def hide_find(self) -> None:
        self._findbar.grid_remove()
        self._clear_find_tags()
        self.text.focus_set()

    def _clear_find_tags(self) -> None:
        self.text.tag_remove("find_all", "1.0", "end")
        self.text.tag_remove("find_current", "1.0", "end")
        self._find_ranges = []
        self._find_position = -1
        self._match_label.configure(text="")

    def _schedule_search(self) -> None:
        if self._search_job is not None:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(self._search_job)
        self._search_job = self.after(160, self._run_search)

    def _run_search(self) -> None:
        self._search_job = None
        self._clear_find_tags()
        query = self._find_var.get()
        if not query:
            return
        count = tk.IntVar()
        position = "1.0"
        while True:
            try:
                found = self.text.search(query, position, stopindex="end", nocase=True, count=count)
            except tk.TclError:
                break
            if not found:
                break
            length = max(1, count.get())
            end = f"{found}+{length}c"
            self._find_ranges.append((found, end))
            self.text.tag_add("find_all", found, end)
            position = end
        if not self._find_ranges:
            self._match_label.configure(text="No matches")
            return
        self._find_position = 0
        self._focus_match()

    def _focus_match(self) -> None:
        if not self._find_ranges:
            return
        self.text.tag_remove("find_current", "1.0", "end")
        start, end = self._find_ranges[self._find_position]
        self.text.tag_add("find_current", start, end)
        self.text.see(start)
        total = len(self._find_ranges)
        self._match_label.configure(text=f"{self._find_position + 1} / {total}")

    def find_next(self) -> None:
        if not self._find_ranges:
            self._run_search()
            return
        self._find_position = (self._find_position + 1) % len(self._find_ranges)
        self._focus_match()

    def find_previous(self) -> None:
        if not self._find_ranges:
            self._run_search()
            return
        self._find_position = (self._find_position - 1) % len(self._find_ranges)
        self._focus_match()

    def replace_current(self) -> None:
        if not self._find_ranges or self._find_position < 0:
            self._run_search()
            return
        start, end = self._find_ranges[self._find_position]
        replacement = self._replace_var.get()
        self.text.delete(start, end)
        self.text.insert(start, replacement)
        self._notify_change()
        self._run_search()

    def replace_all(self) -> None:
        if not self._find_ranges:
            self._run_search()
            return
        replacement = self._replace_var.get()
        for start, end in reversed(self._find_ranges):
            self.text.delete(start, end)
            self.text.insert(start, replacement)
        self._notify_change()
        self._run_search()

    def set_text(self, content: str, *, reset_undo: bool = True) -> None:
        self._loading = True
        try:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", content)
            if reset_undo:
                self.text.edit_reset()
            self.text.mark_set("insert", "1.0")
            self.text.see("1.0")
            self._update_font_metrics()
            self._highlight()
            self._update_current_line()
        finally:
            self._loading = False
        self._clear_find_tags()

    def get_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def clear(self) -> None:
        self.set_text("")

    def insert_command(self, command: str) -> None:
        text = command.strip("\n")
        if not text:
            return
        start = self.text.index("insert")
        if start != "1.0" and self.text.get(f"{start}-1c", start) != "\n":
            self.text.insert(start, "\n")
            start = self.text.index("insert")
        self.text.insert(start, text)
        self.text.mark_set("insert", f"{start}+{len(text)}c")
        self.text.see("insert")
        self.text.focus_set()
        self._notify_change()

    def insert_text(self, text: str) -> None:
        self.text.insert("insert", text)
        self.text.see("insert")
        self.text.focus_set()
        self._notify_change()

    def selected_text(self) -> str:
        if not self.text.tag_ranges("sel"):
            return ""
        return self.text.get("sel.first", "sel.last")

    def focus_editor(self) -> None:
        self.text.focus_set()

    def cursor_position(self) -> tuple[int, int]:
        line, column = self.text.index("insert").split(".")
        return int(line), int(column) + 1

    def apply_theme(self, theme: Theme) -> None:
        palette = theme.palette
        self._theme = theme
        self.configure(bg=palette.surface)
        self.text.configure(
            bg=palette.surface,
            fg=palette.text,
            insertbackground=palette.accent,
            selectbackground=palette.selection,
            selectforeground=palette.text,
            inactiveselectbackground=palette.selection,
        )
        self.gutter.configure(bg=palette.bg)
        self._findbar.configure(bg=palette.surface_alt, highlightbackground=palette.border)
        for child in self._findbar.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(bg=palette.surface_alt)
        self._mono_font = theme.font(-1, mono=True)
        self._font_object = tkfont.Font(root=self, font=self._mono_font)
        self._configure_tags()
        self._update_font_metrics()
        self._highlight()
        self._update_current_line()
