"""Small reusable Tk widgets used across the RedScribe interface."""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from redscribe.ui.theme import Theme


class Tooltip:
    """Show a small delayed hint for a widget."""

    def __init__(self, widget: tk.Misc, text: str, theme: Theme, *, delay: int = 550) -> None:
        self.widget = widget
        self.text = text
        self.theme = theme
        self.delay = delay
        self._job: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        self._job = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._job is not None:
            with contextlib.suppress(tk.TclError):
                self.widget.after_cancel(self._job)
            self._job = None

    def _show(self) -> None:
        self._job = None
        if self._window is not None or not self.widget.winfo_exists():
            return
        palette = self.theme.palette
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.configure(bg=palette.border)
        label = tk.Label(
            window,
            text=self.text,
            bg=palette.surface_alt,
            fg=palette.text,
            font=self.theme.font(-1),
            padx=9,
            pady=5,
        )
        label.pack(padx=1, pady=1)
        window.update_idletasks()
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        width = window.winfo_reqwidth()
        if x + width > window.winfo_screenwidth() - 10:
            x = window.winfo_screenwidth() - width - 10
        window.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
        self._window = window

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self._window is not None:
            with contextlib.suppress(tk.TclError):
                self._window.destroy()
            self._window = None


class ScrollableFrame(tk.Frame):
    """A vertically scrollable frame with a themed scrollbar."""

    def __init__(self, master: tk.Misc, theme: Theme, *, bg: str | None = None) -> None:
        palette = theme.palette
        background = bg or palette.bg
        super().__init__(master, bg=background)
        self._theme = theme
        self._background = background
        self.canvas = tk.Canvas(
            self,
            bg=background,
            bd=0,
            highlightthickness=0,
            yscrollincrement=12,
        )
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview, style="Vertical.TScrollbar"
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner = tk.Frame(self.canvas, bg=background)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner.bind("<Configure>", self._update_scrollregion, add="+")
        self.canvas.bind("<Configure>", self._resize_window, add="+")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_linux_wheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_linux_wheel, add="+")

    def _update_scrollregion(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_window(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=max(1, event.width))

    def _contains_pointer(self, widget: tk.Misc) -> bool:
        try:
            path = str(widget)
            own = str(self)
        except tk.TclError:
            return False
        return path == own or path.startswith(f"{own}.")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if not self.winfo_exists() or not self._contains_pointer(event.widget):
            return
        delta = event.delta
        if delta == 0:
            return
        steps = -1 if delta > 0 else 1
        if abs(delta) >= 120:
            steps = int(-delta / 120)
        self.canvas.yview_scroll(steps * 3, "units")

    def _on_linux_wheel(self, event: tk.Event) -> None:
        if not self.winfo_exists() or not self._contains_pointer(event.widget):
            return
        self.canvas.yview_scroll(-3 if event.num == 4 else 3, "units")

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0.0)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._background = theme.palette.bg
        self.configure(bg=self._background)
        self.canvas.configure(bg=self._background)
        self.inner.configure(bg=self._background)


class Card(tk.Frame):
    """A bordered surface panel with an inner body frame."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        padding: tuple[int, int] = (16, 14),
        bg: str | None = None,
    ) -> None:
        palette = theme.palette
        background = bg or palette.surface_alt
        super().__init__(
            master,
            bg=background,
            bd=0,
            highlightthickness=1,
            highlightbackground=palette.border,
            highlightcolor=palette.border,
        )
        self.body = tk.Frame(self, bg=background)
        self.body.pack(fill="both", expand=True, padx=padding[0], pady=padding[1])


class Pill(tk.Label):
    """A compact status badge."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        theme: Theme,
        *,
        foreground: str | None = None,
        background: str | None = None,
    ) -> None:
        palette = theme.palette
        super().__init__(
            master,
            text=text,
            bg=background or palette.surface,
            fg=foreground or palette.muted,
            font=theme.font(-2, "bold"),
            padx=7,
            pady=2,
            bd=0,
        )

    def update_look(
        self,
        text: str,
        *,
        foreground: str | None = None,
        background: str | None = None,
    ) -> None:
        self.configure(text=text)
        if foreground is not None:
            self.configure(fg=foreground)
        if background is not None:
            self.configure(bg=background)


class TagChip(tk.Label):
    """A clickable tag bubble."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        theme: Theme,
        *,
        command: Callable[[], None] | None = None,
        background: str | None = None,
    ) -> None:
        palette = theme.palette
        self._theme = theme
        self._base = background or palette.surface
        super().__init__(
            master,
            text=f"#{text}",
            bg=self._base,
            fg=palette.muted,
            font=theme.font(-2),
            padx=8,
            pady=3,
            cursor="hand2" if command else "",
            bd=0,
            highlightthickness=1,
            highlightbackground=palette.border,
        )
        self._command = command
        if command is not None:
            self.bind("<Button-1>", lambda _event: command())
            self.bind("<Enter>", self._hover, add="+")
            self.bind("<Leave>", self._leave, add="+")

    def _hover(self, _event: tk.Event | None = None) -> None:
        palette = self._theme.palette
        self.configure(bg=palette.raised, fg=palette.text)

    def _leave(self, _event: tk.Event | None = None) -> None:
        palette = self._theme.palette
        self.configure(bg=self._base, fg=palette.muted)


class SearchBox(tk.Frame):
    """A themed entry with a real placeholder and change callback."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        placeholder: str,
        *,
        background: str | None = None,
        width: int = 24,
        font_delta: int = -1,
    ) -> None:
        palette = theme.palette
        base = background or palette.surface_alt
        super().__init__(
            master,
            bg=base,
            highlightthickness=1,
            highlightbackground=palette.border,
            highlightcolor=palette.accent,
            bd=0,
        )
        self._theme = theme
        self._base = base
        self.var = tk.StringVar()
        self.entry = tk.Entry(
            self,
            textvariable=self.var,
            bg=base,
            fg=palette.text,
            insertbackground=palette.accent,
            selectbackground=palette.selection,
            selectforeground=palette.text,
            relief="flat",
            bd=0,
            highlightthickness=0,
            width=width,
            font=theme.font(font_delta),
        )
        self.entry.pack(fill="both", expand=True, padx=9, pady=6)
        self._placeholder = tk.Label(
            self,
            text=placeholder,
            bg=base,
            fg=palette.faint,
            font=theme.font(font_delta),
            cursor="xterm",
        )
        self._placeholder.bind("<Button-1>", lambda _event: self.entry.focus_set())
        self._placeholder.place(x=10, rely=0.5, anchor="w")
        self._change: Callable[[], None] | None = None
        self.var.trace_add("write", self._on_change)
        self.entry.bind("<FocusIn>", self._update_placeholder, add="+")
        self.entry.bind("<FocusOut>", self._update_placeholder, add="+")
        self.bind("<Button-1>", lambda _event: self.entry.focus_set())

    def _on_change(self, *_args: str) -> None:
        self._update_placeholder()
        if self._change is not None:
            self._change()

    def _update_placeholder(self, _event: tk.Event | None = None) -> None:
        if self.var.get():
            self._placeholder.place_forget()
        else:
            self._placeholder.place(x=10, rely=0.5, anchor="w")
        self.configure(highlightbackground=self._theme.palette.border)

    def bind_change(self, callback: Callable[[], None]) -> None:
        self._change = callback

    def get_value(self) -> str:
        return self.var.get().strip()

    def set_value(self, value: str) -> None:
        self.var.set(value)
        self.entry.icursor("end")

    def focus_entry(self) -> None:
        self.entry.focus_set()
        self.entry.selection_range(0, "end")

    def select_all(self) -> None:
        self.entry.selection_range(0, "end")
        self.entry.icursor("end")


class EmptyState(tk.Frame):
    """A centered empty-state panel with an optional action."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        *,
        glyph: str,
        title: str,
        message: str,
        action_text: str | None = None,
        action: Callable[[], None] | None = None,
        background: str | None = None,
    ) -> None:
        palette = theme.palette
        bg = background or palette.bg
        super().__init__(master, bg=bg)
        inner = tk.Frame(self, bg=bg)
        inner.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(
            inner,
            text=glyph,
            bg=bg,
            fg=palette.accent,
            font=theme.font(24, "bold"),
        ).pack(pady=(0, 10))
        tk.Label(
            inner,
            text=title,
            bg=bg,
            fg=palette.text,
            font=theme.font(8, "bold"),
        ).pack(pady=(0, 6))
        tk.Label(
            inner,
            text=message,
            bg=bg,
            fg=palette.muted,
            font=theme.font(),
            wraplength=460,
            justify="center",
        ).pack(pady=(0, 16))
        if action_text and action is not None:
            ttk.Button(inner, text=action_text, style="Accent.TButton", command=action).pack()


def divider(master: tk.Misc, theme: Theme) -> tk.Frame:
    return tk.Frame(master, bg=theme.palette.border, height=1, bd=0, highlightthickness=0)


def bind_click(widget: tk.Misc, callback: Callable[[], None]) -> None:
    """Bind a click on a widget and its non-button descendants."""
    if isinstance(widget, (tk.Button, ttk.Button, ttk.Entry, ttk.Combobox, tk.Entry)):
        return
    widget.bind("<Button-1>", lambda _event: callback(), add="+")
    with contextlib.suppress(tk.TclError):
        widget.configure({"cursor": "hand2"})
    for child in widget.winfo_children():
        bind_click(child, callback)


def center_window(
    window: tk.Toplevel,
    parent: tk.Misc,
    width: int,
    height: int,
    *,
    offset_y: int = 0,
) -> None:
    window.update_idletasks()
    try:
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
    except tk.TclError:
        parent_x, parent_y, parent_width, parent_height = 0, 0, 0, 0
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    if parent_width < 100 or parent_height < 100:
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
    else:
        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2
    x = max(12, min(x, screen_width - width - 12))
    y = max(12, min(y + offset_y, screen_height - height - 12))
    window.geometry(f"{width}x{height}+{x}+{y}")
