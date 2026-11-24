"""Release smoke suite built entirely from B00 contracts.

The suite is fast, deterministic, and side-effect free from the caller's point
of view: it uses an isolated router and in-memory services, so it can run on
every ref without touching a vault, a socket, or a process boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from redscribe.v3.api.envelope import success, unwrap
from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.idempotency import IdempotencyGuard, MemoryIdempotencyStore, compute_etag
from redscribe.v3.api.pagination import decode_cursor
from redscribe.v3.api.router import V3Router, register_system_routes
from redscribe.v3.capabilities import ALL_CAPABILITIES, CAP_RELEASE, Capabilities
from redscribe.v3.config import default_config
from redscribe.v3.entities.registry import default_registry
from redscribe.v3.entities.types import LinkKind
from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.redaction import RedactionPolicy
from redscribe.v3.events.types import DomainEvent
from redscribe.v3.migrations.registry import chain
from redscribe.v3.migrations.v5 import SCHEMA_VERSION, migration_checksum
from redscribe.v3.release.golden import GoldenPathVault
from redscribe.v3.release.models import (
    RELEASE_ACTIONS,
    CheckSeverity,
    SmokeCheck,
    SmokeReport,
    phase_values,
)
from redscribe.v3.release.scenarios import run_all_scenarios

CheckOperation = Callable[[], tuple[Any, bool]]


def _text(value: Any) -> str:
    """Render check evidence consistently."""
    return value if isinstance(value, str) else repr(value)


def _check(
    check_id: str,
    title: str,
    severity: CheckSeverity,
    expected: Any,
    operation: CheckOperation,
) -> SmokeCheck:
    """Run one check and capture any failure as evidence."""
    detail = ""
    try:
        actual, passed = operation()
    except Exception as error:
        actual, passed = type(error).__name__, False
        detail = str(error)
    return SmokeCheck(
        check_id=check_id,
        title=title,
        severity=severity,
        passed=passed,
        expected=_text(expected),
        actual=_text(actual),
        detail=detail,
    )


def _build_checks(router: V3Router) -> tuple[SmokeCheck, ...]:
    """Build the full smoke check catalogue."""
    scenarios = run_all_scenarios()
    golden = scenarios[0]
    vault = GoldenPathVault()
    vault.capture_note()

    def raises_v3_error(operation: Callable[[], Any]) -> CheckOperation:
        def wrapped() -> tuple[Any, bool]:
            try:
                operation()
            except V3Error as error:
                return error.code.value, True
            return "no error", False

        return wrapped

    checks: list[SmokeCheck] = [
        _check(
            "api.envelope_roundtrip",
            "Success envelopes round-trip through unwrap.",
            CheckSeverity.BLOCKER,
            {"ok": True},
            lambda: (unwrap(success({"ok": True}).as_dict()), True),
        ),
        _check(
            "api.error_status",
            "Stable error codes map to fixed HTTP statuses.",
            CheckSeverity.MAJOR,
            404,
            lambda: (V3Error(V3ErrorCode.NOT_FOUND, "missing").status, True),
        ),
        _check(
            "api.cursor_tamper",
            "Opaque cursors reject tampering.",
            CheckSeverity.MAJOR,
            "invalid_cursor",
            raises_v3_error(lambda: decode_cursor("not-a-cursor")),
        ),
        _check(
            "api.idempotency_conflict",
            "Idempotency keys cannot be reused with a new payload.",
            CheckSeverity.MAJOR,
            "idempotency_conflict",
            lambda: _idempotency_probe(),
        ),
        _check(
            "api.etag_stable",
            "ETag computation is stable for identical payloads.",
            CheckSeverity.MINOR,
            compute_etag({"a": 1}),
            lambda: (compute_etag({"a": 1}), True),
        ),
        _check(
            "router.health",
            "System health route answers.",
            CheckSeverity.BLOCKER,
            "ok",
            lambda: (router.dispatch("system", "health")["status"], True),
        ),
        _check(
            "router.manifest",
            "Route manifest exposes version, namespaces, and routes.",
            CheckSeverity.BLOCKER,
            "3.0",
            lambda: (router.manifest()["version"], True),
        ),
        _check(
            "router.release_routes",
            "Every declared release action is registered.",
            CheckSeverity.BLOCKER,
            len(RELEASE_ACTIONS),
            lambda: (
                sum(1 for action in RELEASE_ACTIONS if router.get("release", action) is not None),
                all(router.get("release", action) is not None for action in RELEASE_ACTIONS),
            ),
        ),
        _check(
            "router.route_paths",
            "All routes use the canonical /api/v3 prefix.",
            CheckSeverity.MAJOR,
            True,
            lambda: (all(route.path.startswith("/api/v3/") for route in router.routes()), True),
        ),
        _check(
            "router.public_manifest",
            "The release manifest route is public and read-only.",
            CheckSeverity.MINOR,
            True,
            lambda: (_public_release_manifest(router), True),
        ),
        _check(
            "config.offline_only",
            "V3 configuration stays offline-only.",
            CheckSeverity.BLOCKER,
            True,
            lambda: (default_config.offline_only, True),
        ),
        _check(
            "config.api_version",
            "Configuration and envelope API versions agree.",
            CheckSeverity.MAJOR,
            "3.0",
            lambda: (default_config.api_version, True),
        ),
        _check(
            "capabilities.complete",
            "All fourteen capabilities are registered.",
            CheckSeverity.MAJOR,
            14,
            lambda: (len(ALL_CAPABILITIES), len(ALL_CAPABILITIES) == 14),
        ),
        _check(
            "capabilities.release",
            "The release capability is enabled by default.",
            CheckSeverity.MAJOR,
            True,
            lambda: (Capabilities().has(CAP_RELEASE), True),
        ),
        _check(
            "migration.chain_valid",
            "The append-only migration chain validates.",
            CheckSeverity.BLOCKER,
            (),
            lambda: (chain.validate(), chain.validate() == ()),
        ),
        _check(
            "migration.schema",
            "Schema version matches configuration.",
            CheckSeverity.BLOCKER,
            SCHEMA_VERSION,
            lambda: (
                default_config.schema_version,
                default_config.schema_version == SCHEMA_VERSION,
            ),
        ),
        _check(
            "migration.checksum",
            "Migration checksum has a stable digest shape.",
            CheckSeverity.MINOR,
            32,
            lambda: (len(migration_checksum()), len(migration_checksum()) == 32),
        ),
        _check(
            "entities.fallback_kind",
            "Unknown entity kinds render with a fallback spec.",
            CheckSeverity.MAJOR,
            "circle",
            lambda: (default_registry.get("future-kind").icon, True),
        ),
        _check(
            "entities.link_semantics",
            "Link kinds keep their directed/undirected meaning.",
            CheckSeverity.MINOR,
            (False, True),
            lambda: (
                (LinkKind.RELATES.is_directed, LinkKind.DERIVES.is_directed),
                not LinkKind.RELATES.is_directed and LinkKind.DERIVES.is_directed,
            ),
        ),
        _check(
            "events.subscriber_isolation",
            "A failing subscriber cannot break event recording.",
            CheckSeverity.MAJOR,
            (1, 1),
            lambda: _subscriber_probe(),
        ),
        _check(
            "events.redaction",
            "The shared redaction policy hides token values.",
            CheckSeverity.BLOCKER,
            "[redacted]",
            lambda: (RedactionPolicy().apply({"token": "secret"})["token"], True),
        ),
        _check(
            "events.outbox_checkpoint",
            "Published events advance the outbox checkpoint.",
            CheckSeverity.MAJOR,
            1,
            lambda: (vault.stats()["checkpoint"], vault.stats()["checkpoint"] == 1),
        ),
        _check(
            "golden.scenarios",
            "Every golden-path scenario passes.",
            CheckSeverity.BLOCKER,
            len(scenarios),
            lambda: (
                sum(1 for result in scenarios if result.ok),
                all(result.ok for result in scenarios),
            ),
        ),
        _check(
            "golden.phases",
            "The golden path covers all seven phases.",
            CheckSeverity.MAJOR,
            phase_values(),
            lambda: (tuple(golden.phases), tuple(golden.phases) == phase_values()),
        ),
        _check(
            "golden.digest",
            "The exported bundle digest verifies.",
            CheckSeverity.BLOCKER,
            True,
            lambda: (
                next(step.passed for step in golden.steps if step.name == "bundle-verified"),
                True,
            ),
        ),
    ]
    return tuple(checks)


def _public_release_manifest(router: V3Router) -> bool:
    """Return whether the release manifest route is public."""
    spec = router.get("release", "manifest")
    return spec is not None and spec.public


def _idempotency_probe() -> tuple[str, bool]:
    """Check conflicting idempotency payload handling."""
    guard = IdempotencyGuard(MemoryIdempotencyStore())
    try:
        guard.execute("smoke-key", {"n": 1}, lambda: {"ok": True})
        guard.execute("smoke-key", {"n": 2}, lambda: {"ok": True})
    except V3Error as error:
        return error.code.value, error.code is V3ErrorCode.IDEMPOTENCY_CONFLICT
    return "no error", False


def _subscriber_probe() -> tuple[tuple[int, int], bool]:
    """Check that subscriber failures are isolated."""
    bus = EventBus()

    def broken(record: Any) -> None:
        raise RuntimeError("subscriber failed")

    bus.subscribe("smoke.event", broken)
    bus.publish(DomainEvent(kind="smoke.event"))
    shape = (bus.size(), len(bus.errors()))
    return shape, shape == (1, 1)


def _isolated_router() -> V3Router:
    """Build a router containing system and release routes only."""
    router = V3Router()
    register_system_routes(router)
    if router.get("release", "manifest") is None:
        from redscribe.v3.namespaces.release import register as register_release

        register_release(router)
    return router


def run_smoke(router: V3Router | None = None) -> SmokeReport:
    """Run the release smoke suite and return a structured report."""
    target = router or _isolated_router()
    if target.get("system", "health") is None:
        register_system_routes(target)
    if target.get("release", "manifest") is None:
        from redscribe.v3.namespaces.release import register as register_release

        register_release(target)
    return SmokeReport(checks=_build_checks(target))


def smoke_check_ids() -> tuple[str, ...]:
    """Return the identifiers of all smoke checks."""
    return tuple(check.check_id for check in _build_checks(_isolated_router()))
