"""Application entry point for RedScribe."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path

from redscribe import __version__
from redscribe.observability import LOG_LEVELS, configure_logging, log_event, timed_event
from redscribe.observability_commands import (
    emit_report,
    read_schema_version,
    run_backup,
    run_doctor,
    run_migrate,
    run_stats,
)
from redscribe.services.demo import DEMO_PROFILES, seed_demo
from redscribe.storage.db import Vault

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


def _add_shared_arguments(parser: argparse.ArgumentParser, *, subcommand: bool) -> None:
    missing = argparse.SUPPRESS if subcommand else None
    parser.add_argument(
        "--vault",
        type=Path,
        default=missing,
        help="Path to the SQLite vault file. Defaults to the user data directory.",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(LOG_LEVELS),
        default=missing if subcommand else "WARNING",
        metavar="LEVEL",
        help="Minimum log level: DEBUG, INFO, WARNING, ERROR, or CRITICAL.",
    )
    parser.add_argument(
        "--json-logs",
        action="store_true",
        default=missing if subcommand else False,
        help="Emit one JSON object per log record on stderr.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redscribe",
        description="A local-first notebook for CTFs, pentests, and security research.",
    )
    _add_shared_arguments(parser, subcommand=False)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Seed example notes when the vault is empty.",
    )
    parser.add_argument(
        "--demo-profile",
        choices=tuple(DEMO_PROFILES),
        default="full",
        help="Fixture set used by --demo (default: full).",
    )
    parser.add_argument(
        "--demo-seed",
        type=int,
        metavar="N",
        help="Add deterministic extra demo fixtures derived from an integer seed.",
    )
    parser.add_argument(
        "--ui",
        choices=("window", "browser"),
        default="window",
        help=(
            "Frontend to launch: a native web window (default, needs the "
            "'web' extra), or the system browser."
        ),
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
        "--port",
        type=int,
        default=0,
        metavar="PORT",
        help="Port for the local web server (0 chooses a free port).",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Start the web server without opening a browser window.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"RedScribe {__version__}",
    )

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    doctor = commands.add_parser("doctor", help="Check vault health without modifying data.")
    _add_shared_arguments(doctor, subcommand=True)
    doctor.add_argument("--json", action="store_true", help="Print the report as JSON.")

    stats = commands.add_parser("stats", help="Print scriptable vault statistics.")
    _add_shared_arguments(stats, subcommand=True)
    stats.add_argument("--json", action="store_true", help="Print the report as JSON.")

    backup = commands.add_parser("backup", help="Write and verify a portable vault snapshot.")
    _add_shared_arguments(backup, subcommand=True)
    backup.add_argument(
        "--destination",
        type=Path,
        metavar="PATH",
        help="Backup file path. Defaults to a timestamped file beside the vault.",
    )
    backup.add_argument("--json", action="store_true", help="Print the report as JSON.")

    migrate = commands.add_parser("migrate", help="Apply schema migrations and rebuild search.")
    _add_shared_arguments(migrate, subcommand=True)
    migrate.add_argument("--json", action="store_true", help="Print the report as JSON.")
    return parser


def _vault_path(value: Path | None) -> Path:
    path = (value or default_vault_path()).expanduser()
    if path.exists() and path.is_dir():
        return path / "redscribe.sqlite"
    return path


def _json_output(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def _run_web(args: argparse.Namespace) -> int:
    from redscribe.ui.web import run_web_ui

    vault_path = _vault_path(args.vault)
    demo = bool(args.demo)
    if demo and (args.demo_profile != "full" or args.demo_seed is not None):
        with Vault(vault_path) as vault:
            added = seed_demo(vault, profile=args.demo_profile, seed=args.demo_seed)
        log_event(
            LOGGER,
            "cli.demo_seed",
            profile=args.demo_profile,
            seed=args.demo_seed,
            notes=added,
        )
        demo = False
    return run_web_ui(
        vault_path,
        mode=args.ui,
        theme=args.theme,
        font_size=args.font_size,
        demo=demo,
        port=args.port,
        open_browser=not args.no_open,
    )


def _run_doctor(args: argparse.Namespace) -> int:
    path = _vault_path(args.vault)
    with Vault(path) as vault:
        result = run_doctor(vault, path)
    emit_report(result.report, json_output=_json_output(args))
    return result.exit_code


def _run_stats(args: argparse.Namespace) -> int:
    path = _vault_path(args.vault)
    with Vault(path) as vault:
        result = run_stats(vault, path)
    emit_report(result.report, json_output=_json_output(args))
    return result.exit_code


def _run_backup(args: argparse.Namespace) -> int:
    path = _vault_path(args.vault)
    destination = getattr(args, "destination", None)
    with Vault(path) as vault:
        result = run_backup(vault, path, destination=destination)
    emit_report(result.report, json_output=_json_output(args))
    return result.exit_code


def _run_migrate(args: argparse.Namespace) -> int:
    path = _vault_path(args.vault)
    before = read_schema_version(path)
    with Vault(path) as vault:
        result = run_migrate(vault, path, before=before)
    emit_report(result.report, json_output=_json_output(args))
    return result.exit_code


def _run(args: argparse.Namespace) -> int:
    command = getattr(args, "command", None)
    if command == "doctor":
        return _run_doctor(args)
    if command == "stats":
        return _run_stats(args)
    if command == "backup":
        return _run_backup(args)
    if command == "migrate":
        return _run_migrate(args)
    return _run_web(args)


def _report_startup_failure(
    details: str,
    *,
    json_logs: bool = False,
    error_type: str = "Error",
) -> None:
    if json_logs:
        payload = {"event": "startup_failure", "error_type": error_type, "error": details}
        sys.stderr.write(json.dumps(payload, sort_keys=True) + "\n")
        return
    sys.stderr.write(f"RedScribe could not start: {details}\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Start the desktop application or run a maintenance command."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    configure_logging(str(args.log_level), json_logs=bool(args.json_logs))
    command = str(getattr(args, "command", None) or "web")
    log_event(LOGGER, "cli.start", command=command, vault=str(_vault_path(args.vault)))
    try:
        with timed_event(LOGGER, "cli.finish", command=command):
            return _run(args)
    except Exception as exc:
        LOGGER.exception("RedScribe failed to start")
        details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        _report_startup_failure(
            details,
            json_logs=bool(args.json_logs),
            error_type=type(exc).__name__,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
