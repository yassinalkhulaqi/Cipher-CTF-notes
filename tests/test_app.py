from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import redscribe.app as app
import redscribe.observability_commands as commands
import redscribe.ui.web as web
from redscribe import __version__
from redscribe.app import (
    _build_parser,
    _report_startup_failure,
    _vault_path,
    default_vault_path,
    main,
)
from redscribe.observability import (
    JsonFormatter,
    configure_logging,
    log_event,
    reset_logging,
    timed_event,
)
from redscribe.observability_commands import emit_report, read_schema_version
from redscribe.services.demo import seed_demo
from redscribe.storage.db import SCHEMA_VERSION, Vault


@pytest.fixture(autouse=True)
def _isolate_logging() -> Iterator[None]:
    reset_logging()
    yield
    reset_logging()


def _seeded_vault(path: Path) -> None:
    with Vault(path) as vault:
        seed_demo(vault)


def _json_stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


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
    assert args.ui == "window"
    assert args.theme is None
    assert args.font_size is None
    assert args.log_level == "WARNING"
    assert args.json_logs is False
    assert args.demo_profile == "full"
    assert args.demo_seed is None
    assert args.command is None


def test_parser_rejects_legacy_tk_interface() -> None:
    """The classic Tkinter backend was removed; only web frontends remain."""
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["--ui", "tk"])


def test_main_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"RedScribe {__version__}"


def test_parser_rejects_unknown_log_level_and_command() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["--log-level", "TRACE"])
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["unknown-command"])


def test_parser_accepts_shared_options_on_both_sides_of_command(tmp_path: Path) -> None:
    vault = tmp_path / "vault.db"
    before = _build_parser().parse_args(["--vault", str(vault), "stats", "--json"])
    assert before.command == "stats"
    assert before.vault == vault
    assert before.json is True
    after = _build_parser().parse_args(
        ["doctor", "--vault", str(vault), "--log-level", "DEBUG", "--json-logs"]
    )
    assert after.command == "doctor"
    assert after.vault == vault
    assert after.log_level == "DEBUG"
    assert after.json_logs is True
    assert after.json is False


def test_main_launches_web_with_preserved_defaults(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[Path, dict[str, Any]]] = []

    def fake_run(path: Path, **kwargs: Any) -> int:
        calls.append((path, kwargs))
        return 0

    monkeypatch.setattr(web, "run_web_ui", fake_run)
    assert main([]) == 0
    assert len(calls) == 1
    options = calls[0][1]
    assert options["mode"] == "window"
    assert options["theme"] is None
    assert options["font_size"] is None
    assert options["demo"] is False
    assert options["port"] == 0
    assert options["open_browser"] is True
    assert capsys.readouterr().out == ""


def test_main_seeds_custom_demo_profile_before_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault_path = tmp_path / "vault.db"
    calls: list[dict[str, Any]] = []

    def fake_run(path: Path, **kwargs: Any) -> int:
        calls.append(kwargs)
        return 0

    monkeypatch.setattr(web, "run_web_ui", fake_run)
    argv = [
        "--vault",
        str(vault_path),
        "--demo",
        "--demo-profile",
        "ctf",
        "--demo-seed",
        "17",
    ]
    assert main(argv) == 0
    assert calls[0]["demo"] is False
    with Vault(vault_path) as vault:
        stats = vault.stats()
        assert stats.notes == 5
        assert stats.folders == 1


def test_main_doctor_reports_all_checks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vault_path = tmp_path / "vault.db"
    _seeded_vault(vault_path)
    assert main(["doctor", "--vault", str(vault_path), "--json"]) == 0
    report = _json_stdout(capsys)
    assert report["ok"] is True
    assert report["vault"] == str(vault_path)
    assert [check["name"] for check in report["checks"]] == [
        "open",
        "schema",
        "search_index",
        "nodes",
        "snippets",
        "integrity",
        "backup",
    ]
    assert all(check["ok"] for check in report["checks"])
    assert report["summary"] == {"passed": 7, "failed": 0}


def test_main_doctor_returns_failure_on_broken_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault_path = tmp_path / "vault.db"
    _seeded_vault(vault_path)

    def broken_pragma(vault: Vault, pragma: str) -> str:
        raise RuntimeError("corrupt")

    monkeypatch.setattr(commands, "_pragma_check", broken_pragma)
    assert main(["doctor", "--vault", str(vault_path)]) == 1
    output = capsys.readouterr().out
    assert "[FAIL] integrity: RuntimeError: corrupt" in output
    assert "Result: failed" in output


def test_main_stats_supports_json_and_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault_path = tmp_path / "vault.db"
    _seeded_vault(vault_path)
    assert main(["stats", "--vault", str(vault_path), "--json"]) == 0
    report = _json_stdout(capsys)
    assert report["command"] == "stats"
    assert report["counts"]["notes"] == 6
    assert report["counts"]["folders"] == 3
    assert report["counts"]["flags"] == 2
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["top_tags"][0]["tag"]
    assert len(report["recent_notes"]) == 5

    assert main(["stats", "--vault", str(vault_path)]) == 0
    text = capsys.readouterr().out
    assert "Stats:" in text
    assert "  notes: 6" in text
    assert "Top tags:" in text


def test_main_backup_writes_explicit_destination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault_path = tmp_path / "vault.db"
    destination = tmp_path / "snapshots" / "vault.db"
    _seeded_vault(vault_path)
    assert (
        main(
            [
                "backup",
                "--vault",
                str(vault_path),
                "--destination",
                str(destination),
                "--json",
            ]
        )
        == 0
    )
    report = _json_stdout(capsys)
    assert report["destination"] == str(destination)
    assert report["notes"] == 6
    assert report["folders"] == 3
    assert report["bytes"] > 0
    assert destination.exists()


def test_main_backup_defaults_to_timestamped_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault_path = tmp_path / "vault.db"
    _seeded_vault(vault_path)
    assert main(["backup", "--vault", str(vault_path), "--json"]) == 0
    report = _json_stdout(capsys)
    target = Path(report["destination"])
    assert target.parent.name == "backups"
    assert target.name.startswith("vault-")
    assert target.exists()


def test_migrate_reports_existing_and_new_vaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault_path = tmp_path / "vault.db"
    assert read_schema_version(vault_path) is None
    _seeded_vault(vault_path)
    assert read_schema_version(vault_path) == SCHEMA_VERSION
    assert main(["migrate", "--vault", str(vault_path), "--json"]) == 0
    report = _json_stdout(capsys)
    assert report["before"] == SCHEMA_VERSION
    assert report["after"] == SCHEMA_VERSION
    assert report["applied"] is False
    assert report["created"] is False

    fresh = tmp_path / "fresh.db"
    assert main(["migrate", "--vault", str(fresh), "--json"]) == 0
    created = _json_stdout(capsys)
    assert created["before"] is None
    assert created["after"] == SCHEMA_VERSION
    assert created["created"] is True
    assert created["applied"] is True


def test_read_schema_version_ignores_corrupt_files(tmp_path: Path) -> None:
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"not a database")
    assert read_schema_version(broken) is None


def test_main_reports_failures_in_plain_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(args: argparse.Namespace) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(app, "_run", boom)
    assert main([]) == 1
    assert "RedScribe could not start: RuntimeError: boom" in capsys.readouterr().err


def test_main_reports_failures_as_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(args: argparse.Namespace) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(app, "_run", boom)
    assert main(["--json-logs", "--log-level", "DEBUG"]) == 1
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    events = {record.get("event"): record for record in lines}
    assert events["cli.start"]["command"] == "web"
    assert events["cli.finish"]["command"] == "web"
    assert events["startup_failure"]["error_type"] == "RuntimeError"
    assert any("exception" in record for record in lines)


def test_report_startup_failure_plain_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    _report_startup_failure("bad", error_type="OSError")
    assert "RedScribe could not start: bad" in capsys.readouterr().err
    _report_startup_failure("bad", json_logs=True, error_type="OSError")
    payload = json.loads(capsys.readouterr().err)
    assert payload == {
        "event": "startup_failure",
        "error": "bad",
        "error_type": "OSError",
    }


def test_json_formatter_produces_deterministic_records() -> None:
    record = logging.LogRecord(
        "redscribe.test",
        logging.INFO,
        __file__,
        10,
        "hello %s",
        ("world",),
        None,
    )
    record.__dict__["request_id"] = "abc"
    formatter = JsonFormatter(clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert json.loads(formatter.format(record)) == {
        "timestamp": "2026-01-01T00:00:00.000Z",
        "level": "INFO",
        "logger": "redscribe.test",
        "message": "hello world",
        "request_id": "abc",
    }


def test_json_formatter_includes_exceptions() -> None:
    try:
        raise ValueError("bad")
    except ValueError:
        record = logging.LogRecord(
            "redscribe.test",
            logging.ERROR,
            __file__,
            10,
            "failed",
            (),
            sys.exc_info(),
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: bad" in payload["exception"]


def test_configure_logging_text_and_json() -> None:
    text_stream = io.StringIO()
    configure_logging("INFO", stream=text_stream)
    logging.getLogger("redscribe.tests").info("plain")
    assert "INFO redscribe.tests: plain" in text_stream.getvalue()

    json_stream = io.StringIO()
    configure_logging("INFO", json_logs=True, stream=json_stream)
    log_event(logging.getLogger("redscribe.tests"), "custom", answer=42)
    payload = json.loads(json_stream.getvalue().strip())
    assert payload["event"] == "custom"
    assert payload["answer"] == 42
    assert payload["level"] == "INFO"


def test_log_event_drops_reserved_fields() -> None:
    stream = io.StringIO()
    configure_logging("WARNING", json_logs=True, stream=stream)
    log_event(
        logging.getLogger("redscribe.tests"),
        "reserved",
        level=logging.WARNING,
        message="ignored",
        pathname="ignored",
        ok=True,
    )
    payload = json.loads(stream.getvalue().strip())
    assert payload["event"] == "reserved"
    assert payload["ok"] is True
    assert payload["message"] == "reserved"
    assert "pathname" not in payload


def test_timed_event_emits_duration() -> None:
    stream = io.StringIO()
    configure_logging("INFO", json_logs=True, stream=stream)
    with timed_event(logging.getLogger("redscribe.tests"), "timed", phase="setup"):
        pass
    payload = json.loads(stream.getvalue().strip())
    assert payload["event"] == "timed"
    assert payload["phase"] == "setup"
    assert payload["duration_ms"] >= 0


def test_reset_logging_restores_defaults() -> None:
    configure_logging("DEBUG", json_logs=True, stream=io.StringIO())
    logger = logging.getLogger("redscribe")
    assert logger.handlers
    assert logger.propagate is False
    reset_logging()
    assert logger.handlers == []
    assert logger.propagate is True
    assert logger.level == logging.NOTSET


def test_emit_report_renders_text_and_json() -> None:
    report = {
        "command": "doctor",
        "vault": "vault.db",
        "ok": False,
        "checks": [{"name": "open", "ok": False, "detail": "bad"}],
    }
    text = io.StringIO()
    emit_report(report, stream=text)
    assert "Doctor: vault.db" in text.getvalue()
    assert "[FAIL] open: bad" in text.getvalue()
    assert "Result: failed" in text.getvalue()

    serialized = io.StringIO()
    emit_report(report, json_output=True, stream=serialized)
    assert json.loads(serialized.getvalue()) == report


def test_emit_report_renders_generic_commands() -> None:
    stream = io.StringIO()
    emit_report(
        {"command": "backup", "destination": "copy.db", "bytes": 12},
        stream=stream,
    )
    output = stream.getvalue()
    assert output.startswith("Backup:")
    assert "  destination: copy.db" in output
    assert "  bytes: 12" in output


def test_command_result_defaults_to_success() -> None:
    result = commands.CommandResult({"command": "stats"})
    assert result.exit_code == 0
