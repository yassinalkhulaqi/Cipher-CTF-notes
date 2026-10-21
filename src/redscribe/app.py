"""Application entry point for RedScribe."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tkinter.messagebox as messagebox
import traceback
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

from redscribe import __version__
from redscribe.db import Vault
from redscribe.demo import seed_demo

LOGGER = logging.getLogger(__name__)


def default_vault_path() -> Path:
    """Return the platform-appropriate default vault database path."""
    platform_name: str = sys.platform
    if platform_name == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return base / "RedScribe" / "redscribe.sqlite"
    if platform_name == "darwin":
        return Path.home() / "Library" / "Application Support" / "RedScribe" / "redscribe.sqlite"
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "redscribe" / "redscribe.sqlite"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redscribe",
        description="A local-first notebook for CTFs, pentests, and security research.",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        help="Path to the SQLite vault file. Defaults to the user data directory.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Seed example notes when the vault is empty.",
    )
    parser.add_argument(
        "--theme",
        choices=("dark", "light"),
        help="Override the stored color theme for this session.",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        metavar="SIZE",
        help="Override the stored UI font size (9-18).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"RedScribe {__version__}",
    )
    return parser


def _vault_path(value: Path | None) -> Path:
    path = (value or default_vault_path()).expanduser()
    if path.exists() and path.is_dir():
        return path / "redscribe.sqlite"
    return path


def _run(args: argparse.Namespace) -> int:
    import tkinter as tk

    from redscribe.ui.mainwindow import MainWindow

    root = tk.Tk()
    root.withdraw()
    root.option_add("*tearOff", False)
    vault = Vault(_vault_path(args.vault))
    try:
        if args.demo and vault.stats().notes == 0:
            seed_demo(vault)
        window = MainWindow(
            root,
            vault,
            theme_name=args.theme,
            font_size=args.font_size,
        )
        window.pack(fill="both", expand=True)

        def report_error(
            exc_type: type[BaseException],
            exc: BaseException,
            tb: TracebackType | None,
        ) -> None:
            LOGGER.error(
                "Unhandled UI exception",
                exc_info=(exc_type, exc, tb),
            )
            messagebox.showerror(
                "Unexpected error",
                f"{exc_type.__name__}: {exc}",
                parent=root,
            )

        root.report_callback_exception = report_error
        root.deiconify()
        root.mainloop()
    finally:
        vault.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Start the desktop application."""
    logging.basicConfig(level=logging.WARNING)
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except Exception as exc:
        LOGGER.exception("RedScribe failed to start")
        details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        try:
            messagebox.showerror(
                "RedScribe could not start",
                details,
            )
        except Exception:
            sys.stderr.write(f"RedScribe could not start: {details}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
