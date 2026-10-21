"""Color palettes, fonts, and ttk style configuration."""

from __future__ import annotations

import contextlib
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk


@dataclass(frozen=True, slots=True)
class Palette:
    name: str
    dark: bool
    bg: str
    surface: str
    surface_alt: str
    raised: str
    border: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_hover: str
    accent_soft: str
    green: str
    amber: str
    blue: str
    red: str
    purple: str
    code_bg: str
    selection: str


DARK = Palette(
    name="dark",
    dark=True,
    bg="#0b0d12",
    surface="#10131a",
    surface_alt="#161a24",
    raised="#1e2430",
    border="#252c39",
    text="#e9edf5",
    muted="#9aa5b8",
    faint="#677287",
    accent="#ff4d6d",
    accent_hover="#ff6b85",
    accent_soft="#3a1a24",
    green="#22c55e",
    amber="#f59e0b",
    blue="#3b82f6",
    red="#ef4444",
    purple="#a855f7",
    code_bg="#0d1017",
    selection="#3b2430",
)

LIGHT = Palette(
    name="light",
    dark=False,
    bg="#f4f6fa",
    surface="#ffffff",
    surface_alt="#eef1f7",
    raised="#e2e7f0",
    border="#d5dbe6",
    text="#141923",
    muted="#5a6476",
    faint="#8993a5",
    accent="#d61f4c",
    accent_hover="#b81740",
    accent_soft="#fbe4ea",
    green="#15803d",
    amber="#a16207",
    blue="#1d4ed8",
    red="#b91c1c",
    purple="#7e22ce",
    code_bg="#f2f4f9",
    selection="#f6cbd5",
)

PALETTES: dict[str, Palette] = {"dark": DARK, "light": LIGHT}

HEADER_HEIGHT = 64
SIDEBAR_WIDTH = 300
STATUSBAR_HEIGHT = 28

UI_FONTS = (
    "Inter",
    "Segoe UI",
    "SF Pro Text",
    "Helvetica Neue",
    "DejaVu Sans",
    "Arial",
)
MONO_FONTS = (
    "Cascadia Code",
    "Cascadia Mono",
    "JetBrains Mono",
    "Fira Code",
    "Consolas",
    "SF Mono",
    "Menlo",
    "DejaVu Sans Mono",
    "Courier New",
)


def _pick_family(root: tk.Misc, candidates: tuple[str, ...], fallback: str) -> str:
    available = {name.casefold(): name for name in tkfont.families(root)}
    for candidate in candidates:
        found = available.get(candidate.casefold())
        if found:
            return found
    return fallback


@dataclass(slots=True)
class Theme:
    palette: Palette
    ui_family: str
    mono_family: str
    base_size: int

    def font(
        self,
        size_delta: int = 0,
        weight: str = "normal",
        *,
        mono: bool = False,
        italic: bool = False,
    ) -> tuple[str, int, str]:
        family = self.mono_family if mono else self.ui_family
        size = max(7, self.base_size + size_delta)
        style = weight
        if italic:
            style = f"{style} italic" if weight != "normal" else "italic"
        return (family, size, style)


def build_theme(root: tk.Misc, name: str, font_size: int = 11) -> Theme:
    palette = PALETTES.get(name, DARK)
    return Theme(
        palette=palette,
        ui_family=_pick_family(root, UI_FONTS, "Arial"),
        mono_family=_pick_family(root, MONO_FONTS, "Courier New"),
        base_size=max(9, min(18, int(font_size))),
    )


def status_color(theme: Theme, status: str) -> str:
    palette = theme.palette
    return {
        "todo": palette.muted,
        "active": palette.blue,
        "done": palette.green,
        "blocked": palette.red,
    }.get(status, palette.text)


def difficulty_color(theme: Theme, difficulty: str) -> str:
    palette = theme.palette
    return {
        "": palette.muted,
        "easy": palette.green,
        "medium": palette.amber,
        "hard": palette.red,
        "insane": palette.purple,
    }.get(difficulty, palette.text)


def configure_styles(root: tk.Misc, theme: Theme) -> None:
    palette = theme.palette
    root.configure({"background": palette.bg})
    style = ttk.Style(root)
    with contextlib.suppress(tk.TclError):
        style.theme_use("clam")

    base = theme.font()
    style.configure(".", background=palette.bg, foreground=palette.text, font=base)
    style.configure("TFrame", background=palette.bg)
    style.configure("Surface.TFrame", background=palette.surface)
    style.configure("Alt.TFrame", background=palette.surface_alt)
    style.configure("Header.TFrame", background=palette.surface)
    style.configure("Status.TFrame", background=palette.surface)
    style.configure("TLabel", background=palette.bg, foreground=palette.text)
    style.configure("Surface.TLabel", background=palette.surface, foreground=palette.text)
    style.configure("Alt.TLabel", background=palette.surface_alt, foreground=palette.text)
    style.configure("Muted.TLabel", background=palette.bg, foreground=palette.muted)
    style.configure("SurfaceMuted.TLabel", background=palette.surface, foreground=palette.muted)
    style.configure(
        "Brand.TLabel",
        background=palette.surface,
        foreground=palette.accent,
        font=theme.font(1, "bold"),
    )
    style.configure(
        "Heading.TLabel",
        background=palette.bg,
        foreground=palette.text,
        font=theme.font(9, "bold"),
    )
    style.configure(
        "CardTitle.TLabel",
        background=palette.surface_alt,
        foreground=palette.text,
        font=theme.font(1, "bold"),
    )
    style.configure(
        "Subtle.TLabel",
        background=palette.bg,
        foreground=palette.faint,
        font=theme.font(-1),
    )
    style.configure(
        "Eyebrow.TLabel",
        background=palette.bg,
        foreground=palette.faint,
        font=theme.font(-2, "bold"),
    )
    style.configure("TSeparator", background=palette.border)

    style.configure(
        "TButton",
        background=palette.surface_alt,
        foreground=palette.text,
        bordercolor=palette.border,
        lightcolor=palette.surface_alt,
        darkcolor=palette.surface_alt,
        focuscolor=palette.accent,
        borderwidth=0,
        padding=(12, 7),
        font=theme.font(),
    )
    style.map(
        "TButton",
        background=[
            ("disabled", palette.surface),
            ("pressed", palette.raised),
            ("active", palette.raised),
        ],
        foreground=[("disabled", palette.faint)],
    )
    style.configure(
        "Accent.TButton",
        background=palette.accent,
        foreground="#ffffff",
        bordercolor=palette.accent,
        lightcolor=palette.accent,
        darkcolor=palette.accent,
        focuscolor=palette.accent_hover,
        padding=(14, 8),
        font=theme.font(0, "bold"),
    )
    style.map(
        "Accent.TButton",
        background=[
            ("disabled", palette.faint),
            ("pressed", palette.accent_hover),
            ("active", palette.accent_hover),
        ],
        foreground=[("disabled", palette.surface)],
    )
    style.configure(
        "Subtle.TButton",
        background=palette.bg,
        foreground=palette.muted,
        bordercolor=palette.bg,
        lightcolor=palette.bg,
        darkcolor=palette.bg,
        padding=(8, 6),
    )
    style.map(
        "Subtle.TButton",
        background=[("pressed", palette.surface_alt), ("active", palette.surface_alt)],
        foreground=[("active", palette.text)],
    )
    style.configure(
        "Tool.TButton",
        background=palette.surface_alt,
        foreground=palette.text,
        padding=(8, 6),
        font=theme.font(-1),
    )
    style.map(
        "Tool.TButton",
        background=[("pressed", palette.raised), ("active", palette.raised)],
    )
    style.configure(
        "View.TButton",
        background=palette.surface_alt,
        foreground=palette.muted,
        bordercolor=palette.surface_alt,
        lightcolor=palette.surface_alt,
        darkcolor=palette.surface_alt,
        padding=(12, 6),
        font=theme.font(-1),
    )
    style.map(
        "View.TButton",
        background=[("pressed", palette.raised), ("active", palette.raised)],
        foreground=[("active", palette.text)],
    )
    style.configure(
        "ViewActive.TButton",
        background=palette.accent_soft,
        foreground=palette.accent,
        bordercolor=palette.accent_soft,
        lightcolor=palette.accent_soft,
        darkcolor=palette.accent_soft,
        padding=(12, 6),
        font=theme.font(-1, "bold"),
    )
    style.map(
        "ViewActive.TButton",
        background=[("pressed", palette.accent_soft), ("active", palette.accent_soft)],
        foreground=[("active", palette.accent)],
    )
    style.configure(
        "Danger.TButton",
        background=palette.surface_alt,
        foreground=palette.red,
        padding=(10, 6),
    )
    style.map("Danger.TButton", background=[("active", palette.raised)])
    style.configure(
        "Jump.TButton",
        background=palette.surface_alt,
        foreground=palette.muted,
        bordercolor=palette.border,
        lightcolor=palette.surface_alt,
        darkcolor=palette.surface_alt,
        padding=(14, 7),
        anchor="w",
        font=theme.font(-1),
    )
    style.map(
        "Jump.TButton",
        background=[("active", palette.raised), ("pressed", palette.raised)],
        foreground=[("active", palette.text)],
    )

    for widget_style in ("TEntry", "TSpinbox"):
        style.configure(
            widget_style,
            fieldbackground=palette.surface_alt,
            foreground=palette.text,
            insertcolor=palette.accent,
            bordercolor=palette.border,
            lightcolor=palette.border,
            darkcolor=palette.border,
            padding=(8, 6),
        )
        style.map(
            widget_style,
            fieldbackground=[("disabled", palette.surface), ("readonly", palette.surface_alt)],
            foreground=[("disabled", palette.faint)],
            bordercolor=[("focus", palette.accent)],
            lightcolor=[("focus", palette.accent)],
            darkcolor=[("focus", palette.accent)],
        )
    style.configure(
        "TCombobox",
        fieldbackground=palette.surface_alt,
        background=palette.surface_alt,
        foreground=palette.text,
        arrowcolor=palette.muted,
        bordercolor=palette.border,
        lightcolor=palette.border,
        darkcolor=palette.border,
        padding=(7, 5),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", palette.surface_alt), ("disabled", palette.surface)],
        foreground=[("disabled", palette.faint), ("readonly", palette.text)],
        selectbackground=[("readonly", palette.surface_alt)],
        selectforeground=[("readonly", palette.text)],
        bordercolor=[("focus", palette.accent)],
        arrowcolor=[("active", palette.text)],
    )
    root.option_add("*TCombobox*Listbox.background", palette.surface_alt)
    root.option_add("*TCombobox*Listbox.foreground", palette.text)
    root.option_add("*TCombobox*Listbox.selectBackground", palette.accent)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.font", base)

    style.configure(
        "Treeview",
        background=palette.surface,
        fieldbackground=palette.surface,
        foreground=palette.text,
        bordercolor=palette.border,
        lightcolor=palette.surface,
        darkcolor=palette.surface,
        borderwidth=0,
        rowheight=max(24, theme.base_size * 2 + 8),
        font=theme.font(-1),
    )
    style.map(
        "Treeview",
        background=[("selected", palette.accent_soft)],
        foreground=[("selected", palette.text)],
    )
    style.configure(
        "Treeview.Heading",
        background=palette.surface_alt,
        foreground=palette.muted,
        relief="flat",
        borderwidth=0,
        padding=(8, 6),
        font=theme.font(-1, "bold"),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette.raised)],
        foreground=[("active", palette.text)],
    )

    style.configure(
        "TNotebook",
        background=palette.bg,
        bordercolor=palette.border,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=palette.bg,
        foreground=palette.muted,
        padding=(14, 7),
        font=theme.font(-1),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", palette.surface)],
        foreground=[("selected", palette.text)],
    )

    style.configure(
        "TPanedwindow",
        background=palette.border,
        sashwidth=5,
        sashrelief="flat",
    )
    style.configure(
        "Sash",
        background=palette.border,
        gripcount=0,
    )

    for scrollbar_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            scrollbar_style,
            background=palette.raised,
            troughcolor=palette.surface,
            bordercolor=palette.surface,
            arrowcolor=palette.muted,
            gripcount=0,
            width=10,
        )
        style.map(
            scrollbar_style,
            background=[("active", palette.faint), ("pressed", palette.accent)],
        )

    style.configure(
        "TCheckbutton",
        background=palette.bg,
        foreground=palette.text,
        indicatorcolor=palette.surface_alt,
        bordercolor=palette.border,
        focuscolor=palette.accent,
    )
    style.map(
        "TCheckbutton",
        background=[("active", palette.bg)],
        indicatorcolor=[("selected", palette.accent), ("active", palette.raised)],
    )
    style.configure(
        "TRadiobutton",
        background=palette.bg,
        foreground=palette.text,
        indicatorcolor=palette.surface_alt,
        bordercolor=palette.border,
        focuscolor=palette.accent,
    )
    style.map(
        "TRadiobutton",
        background=[("active", palette.bg)],
        indicatorcolor=[("selected", palette.accent)],
    )
    style.configure("TScale", background=palette.bg, troughcolor=palette.surface_alt)

    root.option_add("*Menu.background", palette.surface_alt)
    root.option_add("*Menu.foreground", palette.text)
    root.option_add("*Menu.activeBackground", palette.accent)
    root.option_add("*Menu.activeForeground", "#ffffff")
    root.option_add("*Menu.selectColor", palette.accent)
    root.option_add("*Menu.font", base)
