from __future__ import annotations

import sys
from pathlib import Path

import pytest

from redscribe import __version__, app
from redscribe.app import _build_parser, _vault_path, default_vault_path, main


def test_default_vault_path_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert default_vault_path() == tmp_path / "RedScribe" / "redscribe.sqlite"


def test_default_vault_path_on_macos(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert (
        default_vault_path()
        == tmp_path / "Library" / "Application Support" / "RedScribe" / "redscribe.sqlite"
    )


def test_default_vault_path_on_linux(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_vault_path() == tmp_path / "redscribe" / "redscribe.sqlite"


def test_vault_path_accepts_a_directory(tmp_path: Path) -> None:
    assert _vault_path(tmp_path) == tmp_path / "redscribe.sqlite"
    target = tmp_path / "custom.sqlite"
    assert _vault_path(target) == target


def test_parser_has_expected_defaults() -> None:
    args = _build_parser().parse_args([])
    assert args.vault is None
    assert args.demo is False
    assert args.theme is None
    assert args.font_size is None


def test_main_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"RedScribe {__version__}"


def test_run_returns_zero_when_mainloop_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeRoot:
        def withdraw(self) -> None:
            pass

        def option_add(self, *_args: object) -> None:
            pass

        def deiconify(self) -> None:
            pass

        def mainloop(self) -> None:
            pass

        def report_callback_exception(self, _handler: object) -> None:
            pass

    class FakeWindow:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def pack(self, **_kwargs: object) -> None:
            pass

    class FakeVault:
        def __init__(self, _path: Path) -> None:
            self.closed = False

        def stats(self) -> object:
            return type("Stats", (), {"notes": 0})()

        def close(self) -> None:
            self.closed = True

    import tkinter as tk

    monkeypatch.setattr(tk, "Tk", FakeRoot)
    monkeypatch.setattr("redscribe.ui.mainwindow.MainWindow", FakeWindow)
    monkeypatch.setattr(app, "Vault", FakeVault)
    args = _build_parser().parse_args(["--vault", str(tmp_path / "vault.sqlite")])
    assert app._run(args) == 0
