"""Structured logging helpers for the RedScribe CLI."""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TextIO

LOG_LEVELS: dict[str, int] = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}

_STANDARD_RECORD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def _utc_timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JsonFormatter(logging.Formatter):
    """Render each log record as a single deterministic JSON object."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": _utc_timestamp(self._clock()),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def configure_logging(
    level: str = "WARNING",
    *,
    json_logs: bool = False,
    stream: TextIO | None = None,
) -> None:
    """Configure the ``redscribe`` logger without touching the root logger."""
    reset_logging()
    logger = logging.getLogger("redscribe")
    handler = logging.StreamHandler(stream or sys.stderr)
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(LOG_LEVELS[level.upper()])
    logger.propagate = False


def reset_logging() -> None:
    """Remove CLI handlers and restore default propagation."""
    logger = logging.getLogger("redscribe")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


def _event_extra(event: str, fields: Mapping[str, object]) -> dict[str, object]:
    extra: dict[str, object] = {"event": event}
    for key, value in fields.items():
        if key in _STANDARD_RECORD_FIELDS:
            continue
        extra[key] = value
    return extra


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    **fields: object,
) -> None:
    """Log a named event with optional structured fields."""
    logger.log(level, event, extra=_event_extra(event, fields))


@contextmanager
def timed_event(
    logger: logging.Logger,
    event: str,
    **fields: object,
) -> Iterator[None]:
    """Log ``event`` on exit with the elapsed time in milliseconds."""
    started = time.perf_counter()
    try:
        yield
    finally:
        payload = dict(fields)
        payload["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
        logger.log(logging.INFO, event, extra=_event_extra(event, payload))
