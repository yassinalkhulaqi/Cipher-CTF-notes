"""Sync/portability namespace routes for the V3 API.

The module is discovered dynamically by ``V3Router.install_namespaces``; it adds
routes with ``router.add("sync", action, handler)`` and never edits a central
dispatch table.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import wraps
from typing import Any

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.request_id import (
    optional_str,
    optional_tags,
    require_bool,
    require_choice,
    require_str,
)
from redscribe.v3.api.router import Handler, V3Router
from redscribe.v3.capabilities import CapabilityError
from redscribe.v3.portability.errors import PortabilityError
from redscribe.v3.portability.merge import ConflictReason, ResolutionStrategy
from redscribe.v3.portability.service import PortabilityService
from redscribe.v3.portability.vectors import VersionVector

_ACTIONS = (
    "health",
    "reasons",
    "devices",
    "device.register",
    "device.trust",
    "vectors.compare",
    "bundle.plan",
    "bundle.create",
    "bundle.inspect",
    "bundle.open",
    "bundle.verify",
    "conflicts.detect",
    "merge.preview",
    "conflicts.resolve",
    "receipt.get",
    "receipt.list",
    "audit.list",
    "transfer.start",
    "transfer.status",
    "transfer.checkpoint",
    "transfer.chunk",
    "transfer.pause",
    "transfer.resume",
    "transfer.cancel",
    "transfer.finish",
)


def actions() -> tuple[str, ...]:
    """Return every action registered by this namespace."""
    return _ACTIONS


def create_service() -> PortabilityService:
    """Build a fresh portability service for a namespace instance."""
    return PortabilityService()


def guarded(handler: Handler) -> Handler:
    """Translate portability failures into stable V3 error envelopes."""

    @wraps(handler)
    def wrapped(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        try:
            return handler(body, headers)
        except CapabilityError as error:
            raise V3Error(V3ErrorCode.FORBIDDEN, str(error)) from error
        except PortabilityError as error:
            code = _error_code(error.code)
            raise V3Error(code, error.message, context=error.context) from error
        except (KeyError, TypeError, ValueError) as error:
            raise V3Error(V3ErrorCode.INVALID_REQUEST, str(error)) from error

    return wrapped


def _error_code(code: str) -> V3ErrorCode:
    """Map a portability error code to a V3 API error code."""
    return {
        "bundle_error": V3ErrorCode.INVALID_REQUEST,
        "manifest_error": V3ErrorCode.INVALID_REQUEST,
        "verification_error": V3ErrorCode.PRECONDITION_FAILED,
        "decryption_error": V3ErrorCode.FORBIDDEN,
        "device_error": V3ErrorCode.FORBIDDEN,
        "merge_error": V3ErrorCode.CONFLICT,
        "resolution_error": V3ErrorCode.CONFLICT,
        "transfer_error": V3ErrorCode.PRECONDITION_FAILED,
    }.get(code, V3ErrorCode.INVALID_REQUEST)


def _passphrase(body: dict[str, Any]) -> str:
    """Read a passphrase without cleaning or echoing it."""
    value = body.get("passphrase")
    if not isinstance(value, str) or not value:
        raise V3Error(V3ErrorCode.MISSING_FIELD, "Missing required field 'passphrase'")
    return value


def _vectors(body: dict[str, Any], key: str) -> VersionVector:
    """Parse a version vector from a request field."""
    value = body.get(key, {})
    if not isinstance(value, dict):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a mapping", field=key)
    try:
        return VersionVector.from_dict(value)
    except PortabilityError as error:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, error.message, field=key) from error


def register(router: V3Router, service: PortabilityService | None = None) -> None:
    """Register all sync namespace routes on the supplied router."""
    api = service or create_service()

    @guarded
    def health(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.health()

    @guarded
    def reasons(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {
            "reasons": [
                {
                    "code": reason.value,
                    "description": reason.description,
                    "severity": reason.severity,
                }
                for reason in ConflictReason
            ],
            "strategies": [strategy.value for strategy in ResolutionStrategy],
        }

    @guarded
    def devices(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.devices()

    @guarded
    def device_register(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.register_device(
            require_str(body, "device_id"),
            require_str(body, "label"),
            platform=optional_str(body, "platform", default="desktop"),
            trusted=require_bool(body, "trusted"),
        )

    @guarded
    def device_trust(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.trust_device(require_str(body, "device_id"))

    @guarded
    def vectors_compare(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.compare_vectors(
            _vectors(body, "local").as_dict(),
            _vectors(body, "remote").as_dict(),
        )

    @guarded
    def bundle_plan(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.plan_bundle(
            api._entities(body.get("entities", ())),
            api._links(body.get("links", ())),
        )

    @guarded
    def bundle_create(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.create_bundle(
            api._entities(body.get("entities", ())),
            api._links(body.get("links", ())),
            passphrase=_passphrase(body),
            device_id=optional_str(body, "device_id", default="local"),
            metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else None,
        )

    @guarded
    def bundle_inspect(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.inspect_bundle(require_str(body, "bundle_id"))

    @guarded
    def bundle_open(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.open_bundle(require_str(body, "bundle_id"), _passphrase(body))

    @guarded
    def bundle_verify(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.verify_bundle(require_str(body, "bundle_id"), _passphrase(body))

    @guarded
    def conflicts_detect(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.detect_conflicts(
            api._entities(body.get("base", ())),
            api._entities(body.get("local", ())),
            api._entities(body.get("remote", ())),
            base_links=api._links(body.get("base_links", ())),
            local_links=api._links(body.get("local_links", ())),
            remote_links=api._links(body.get("remote_links", ())),
        )

    @guarded
    def merge_preview(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.preview_import(
            require_str(body, "bundle_id"),
            _passphrase(body),
            api._entities(body.get("base", ())),
            api._entities(body.get("local", ())),
            base_links=api._links(body.get("base_links", ())),
            local_links=api._links(body.get("local_links", ())),
            families=optional_tags(body, "families"),
            base_vector=_vectors(body, "base_vector"),
            local_vector=_vectors(body, "local_vector"),
        )

    @guarded
    def conflicts_resolve(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        decisions = body.get("decisions", {})
        if not isinstance(decisions, dict):
            raise V3Error(
                V3ErrorCode.INVALID_TYPE, "'decisions' must be a mapping", field="decisions"
            )
        default = (
            require_choice(
                body,
                "default",
                tuple(strategy.value for strategy in ResolutionStrategy),
            )
            if "default" in body
            else ResolutionStrategy.MANUAL.value
        )
        return api.resolve_preview(
            require_str(body, "preview_id"),
            {str(key): str(value) for key, value in decisions.items()},
            actor=optional_str(body, "actor", default="local"),
            device=optional_str(body, "device", default="local"),
            default=ResolutionStrategy(default),
        )

    @guarded
    def receipt_get(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.receipt(require_str(body, "receipt_id"))

    @guarded
    def receipt_list(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.receipts()

    @guarded
    def audit_list(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.audit()

    @guarded
    def transfer_start(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        chunk_size = body.get("chunk_size", 64 * 1024)
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
            raise V3Error(V3ErrorCode.INVALID_TYPE, "'chunk_size' must be an integer")
        return api.begin_transfer(require_str(body, "bundle_id"), chunk_size=chunk_size)

    @guarded
    def transfer_status(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.transfer_status(require_str(body, "transfer_id"))

    @guarded
    def transfer_checkpoint(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.transfer_checkpoint(require_str(body, "transfer_id"))

    @guarded
    def transfer_chunk(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        index = body.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise V3Error(V3ErrorCode.INVALID_REQUEST, "'index' must be a non-negative integer")
        return api.push_chunk(
            require_str(body, "transfer_id"),
            index,
            require_str(body, "chunk", limit=8 * 1024 * 1024),
        )

    @guarded
    def transfer_pause(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.pause_transfer(require_str(body, "transfer_id"))

    @guarded
    def transfer_resume(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.resume_transfer(require_str(body, "transfer_id"))

    @guarded
    def transfer_cancel(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.cancel_transfer(require_str(body, "transfer_id"))

    @guarded
    def transfer_finish(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return api.finish_transfer(require_str(body, "transfer_id"))

    handlers = (
        health,
        reasons,
        devices,
        device_register,
        device_trust,
        vectors_compare,
        bundle_plan,
        bundle_create,
        bundle_inspect,
        bundle_open,
        bundle_verify,
        conflicts_detect,
        merge_preview,
        conflicts_resolve,
        receipt_get,
        receipt_list,
        audit_list,
        transfer_start,
        transfer_status,
        transfer_checkpoint,
        transfer_chunk,
        transfer_pause,
        transfer_resume,
        transfer_cancel,
        transfer_finish,
    )
    for action, handler in zip(_ACTIONS, handlers, strict=True):
        router.add("sync", action, handler)


__all__ = ["actions", "create_service", "guarded", "register"]
