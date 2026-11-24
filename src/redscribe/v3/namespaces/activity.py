"""Activity namespace routes for the V3 API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redscribe.v3.activity import (
    DENSITY_MODES,
    DIGEST_PERIODS,
    ActivityFilter,
    ActivityService,
    parse_query,
    validate_query,
)
from redscribe.v3.activity.timezone import resolve_timezone
from redscribe.v3.api.envelope import success
from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.request_id import normalize_request_id, optional_str
from redscribe.v3.api.router import Handler, V3Router
from redscribe.v3.clock import SystemClock
from redscribe.v3.events.bus import EventBus

_DEFAULT_SERVICE: ActivityService | None = None


def get_service() -> ActivityService:
    """Return the shared activity service, creating it on first use."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        clock = SystemClock()
        service = ActivityService(bus=EventBus(clock=clock), clock=clock)
        service.install_subscriber()
        _DEFAULT_SERVICE = service
    return _DEFAULT_SERVICE


def set_service(service: ActivityService | None) -> None:
    """Replace the shared service (primarily for tests and embedding)."""
    global _DEFAULT_SERVICE
    _DEFAULT_SERVICE = service


def _string_list(body: Mapping[str, Any], key: str) -> tuple[str, ...]:
    """Read an optional list of strings."""
    value = body.get(key, ())
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a list", field=key)
    return tuple(str(item) for item in value if str(item).strip())


def _optional_float(body: Mapping[str, Any], key: str) -> float | None:
    """Read an optional numeric value."""
    value = body.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a number", field=key)
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a number", field=key) from error


def _optional_int(body: Mapping[str, Any], key: str) -> int | None:
    """Read an optional integer value."""
    value = _optional_float(body, key)
    return None if value is None else int(value)


def _choice(body: Mapping[str, Any], key: str, choices: tuple[str, ...], default: str) -> str:
    """Read an optional value constrained to a fixed choice set."""
    value = optional_str(body, key, default=default, limit=80).strip().casefold()
    if value and value not in choices:
        raise V3Error(
            V3ErrorCode.INVALID_CHOICE,
            f"'{key}' must be one of: {', '.join(choices)}",
            field=key,
        )
    return value or default


def _request_filter(body: Mapping[str, Any]) -> tuple[ActivityFilter, str, tuple[str, ...]]:
    """Build an activity filter from a request body."""
    query = optional_str(body, "query", limit=2000)
    event_filter, _chips, errors = parse_query(query)
    kinds = _string_list(body, "kinds")
    exclude_kinds = _string_list(body, "exclude_kinds")
    actors = _string_list(body, "actors")
    subjects = _string_list(body, "subjects")
    severities = _string_list(body, "severities")
    tags = _string_list(body, "tags")
    correlation = optional_str(body, "correlation_id", limit=200)
    merged = ActivityFilter(
        kinds=event_filter.kinds + kinds,
        exclude_kinds=event_filter.exclude_kinds + exclude_kinds,
        actors=event_filter.actors + actors,
        subjects=event_filter.subjects + subjects,
        severities=event_filter.severities + severities,
        minimum_severity=event_filter.minimum_severity,
        text=event_filter.text,
        since=event_filter.since
        if event_filter.since is not None
        else _optional_float(body, "since"),
        until=event_filter.until
        if event_filter.until is not None
        else _optional_float(body, "until"),
        correlation_id=event_filter.correlation_id or correlation,
        tags=event_filter.tags + tags,
        free_text=event_filter.free_text,
    )
    return merged, query, errors


def build_handlers(service: ActivityService) -> dict[str, Handler]:
    """Build every activity route handler around a service instance."""

    def stream(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        event_filter, query, errors = _request_filter(body)
        density = _choice(body, "density", DENSITY_MODES, "comfortable")
        offset = _optional_int(body, "offset")
        size = _optional_int(body, "size")
        requested_zone = optional_str(body, "timezone", limit=80)
        warnings = list(errors)
        if requested_zone:
            try:
                resolve_timezone(requested_zone)
            except ValueError:
                warnings.append(f"Ignoring unknown timezone: {requested_zone}")
            if requested_zone.casefold() not in {service.timezone.casefold(), "utc", "z"}:
                warnings.append(f"Stream timezone fixed to {service.timezone}")
        result = service.stream(
            event_filter,
            query=query,
            offset=0 if offset is None else offset,
            size=size,
            density=density,
            warnings=tuple(warnings),
        )
        return success(
            result.as_dict(), request_id=normalize_request_id(headers.get("x-request-id"))
        ).as_dict()

    def filters(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return success(
            service.filters(), request_id=normalize_request_id(headers.get("x-request-id"))
        ).as_dict()

    def validate(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        query = optional_str(body, "query", limit=2000)
        return success(
            validate_query(query).as_dict(),
            request_id=normalize_request_id(headers.get("x-request-id")),
        ).as_dict()

    def digest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        period = _choice(body, "period", DIGEST_PERIODS, "daily")
        anchor = _optional_float(body, "anchor")
        generated_at = _optional_float(body, "generated_at")
        highlight_limit = _optional_int(body, "highlight_limit")
        if anchor is not None:
            single = service.digest_at(
                anchor,
                period=period,
                generated_at=generated_at,
            )
            data: dict[str, Any] = {
                "period": period,
                "timezone": service.timezone,
                "generated_at": generated_at if generated_at is not None else 0.0,
                "total_events": 0 if single is None else single.entry_count,
                "digests": [] if single is None else [single.as_dict()],
            }
        else:
            collection = service.digest(
                period,
                generated_at=generated_at,
                highlight_limit=highlight_limit,
            )
            data = collection.as_dict()
        return success(data, request_id=normalize_request_id(headers.get("x-request-id"))).as_dict()

    def since(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        identity = optional_str(body, "identity", default="local", limit=120)
        limit = _optional_int(body, "limit")
        result = service.since(identity, limit=limit)
        return success(
            result.as_dict(), request_id=normalize_request_id(headers.get("x-request-id"))
        ).as_dict()

    def mark(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        identity = optional_str(body, "identity", default="local", limit=120)
        timestamp = _optional_float(body, "timestamp")
        sequence = _optional_int(body, "sequence")
        note = optional_str(body, "note", limit=240)
        marker = service.mark_visit(identity, timestamp=timestamp, sequence=sequence, note=note)
        return success(
            marker.as_dict(), request_id=normalize_request_id(headers.get("x-request-id"))
        ).as_dict()

    def retrospective(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        start = _optional_float(body, "start")
        end = _optional_float(body, "end")
        if start is None or end is None:
            raise V3Error(V3ErrorCode.MISSING_FIELD, "Retrospective requires start and end")
        if end <= start:
            raise V3Error(V3ErrorCode.INVALID_REQUEST, "Retrospective end must follow start")
        summary = service.retrospective(
            start=start,
            end=end,
            top_limit=_optional_int(body, "top_limit") or 5,
            highlight_limit=_optional_int(body, "highlight_limit"),
        )
        return success(
            summary.as_dict(), request_id=normalize_request_id(headers.get("x-request-id"))
        ).as_dict()

    def redact(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        payload = body.get("payload", {})
        if not isinstance(payload, Mapping):
            raise V3Error(V3ErrorCode.INVALID_TYPE, "'payload' must be an object", field="payload")
        cleaned = service.redact(payload)
        report = service.last_redaction_report()
        return success(
            {"payload": cleaned, "report": report},
            request_id=normalize_request_id(headers.get("x-request-id")),
        ).as_dict()

    def entry(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        sequence = body.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            raise V3Error(
                V3ErrorCode.INVALID_TYPE, "'sequence' must be an integer", field="sequence"
            )
        found = service.entry(sequence)
        if found is None:
            raise V3Error.not_found("activity entry")
        return success(
            found.as_dict(), request_id=normalize_request_id(headers.get("x-request-id"))
        ).as_dict()

    def stats(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return success(
            service.stats(), request_id=normalize_request_id(headers.get("x-request-id"))
        ).as_dict()

    def health(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return success(
            {
                "status": "ok",
                "namespace": "activity",
                "entries": len(service.entries()),
                "timezone": service.timezone,
            },
            request_id=normalize_request_id(headers.get("x-request-id")),
        ).as_dict()

    def modes(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return success(
            {
                "densities": list(DENSITY_MODES),
                "periods": list(DIGEST_PERIODS),
            },
            request_id=normalize_request_id(headers.get("x-request-id")),
        ).as_dict()

    return {
        "stream": stream,
        "filters": filters,
        "validate": validate,
        "digest": digest,
        "since": since,
        "mark": mark,
        "retrospective": retrospective,
        "redact": redact,
        "entry": entry,
        "stats": stats,
        "health": health,
        "modes": modes,
    }


def register(router: V3Router) -> None:
    """Register all activity routes on ``router``."""
    handlers = build_handlers(get_service())
    for action, handler in handlers.items():
        router.add("activity", action, handler)
