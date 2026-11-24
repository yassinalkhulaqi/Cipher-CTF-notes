"""Security namespace routes for the V3 API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.vault_security.policy import PolicyError
from redscribe.v3.vault_security.recovery import RecoveryCodeError
from redscribe.v3.vault_security.service import (
    InvalidPassphraseError,
    VaultAlreadyInitializedError,
    VaultLockedError,
    VaultNotInitializedError,
    VaultSecurityError,
    VaultSecurityService,
    parse_scope,
)

_service = VaultSecurityService()


def get_service() -> VaultSecurityService:
    """Return the namespace service instance."""
    return _service


def set_service(service: VaultSecurityService) -> None:
    """Replace the service instance, primarily for isolated tests."""
    global _service
    _service = service


def _text(body: Mapping[str, Any], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value:
        raise V3Error.missing(name)
    return value


def _optional_text(body: Mapping[str, Any], name: str, default: str = "") -> str:
    value = body.get(name, default)
    if not isinstance(value, str):
        raise V3Error.invalid(name, "must be a string")
    return value


def _request_id(headers: Mapping[str, str]) -> str:
    return _optional_text(headers, "X-Request-ID")


def _translate(error: Exception) -> V3Error:
    if isinstance(error, (InvalidPassphraseError, RecoveryCodeError)):
        return V3Error(V3ErrorCode.FORBIDDEN, str(error))
    if isinstance(error, VaultNotInitializedError):
        return V3Error(V3ErrorCode.PRECONDITION_FAILED, str(error))
    if isinstance(error, VaultLockedError):
        return V3Error(V3ErrorCode.PRECONDITION_FAILED, str(error))
    if isinstance(error, VaultAlreadyInitializedError):
        return V3Error(V3ErrorCode.CONFLICT, str(error))
    if isinstance(error, PolicyError):
        return V3Error(V3ErrorCode.INVALID_REQUEST, str(error))
    if isinstance(error, VaultSecurityError):
        return V3Error(V3ErrorCode.INTERNAL, str(error))
    if isinstance(error, ValueError):
        return V3Error(V3ErrorCode.INVALID_REQUEST, str(error))
    if isinstance(error, TypeError):
        return V3Error(V3ErrorCode.INVALID_TYPE, str(error))
    return V3Error(V3ErrorCode.INTERNAL, "Security request could not be completed")


def register(router: V3Router) -> None:
    """Register every vault security route on the supplied router."""

    def status(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _service.status()

    def posture(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _service.posture().as_dict()

    def setup(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        content = body.get("content", {})
        if content is not None and not isinstance(content, dict):
            raise V3Error.invalid("content", "must be an object")
        count = body.get("recovery_count", 6)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 8:
            raise V3Error.invalid("recovery_count", "must be between 1 and 8")
        try:
            result = _service.setup(
                _text(body, "passphrase"),
                content=content or {},
                recovery_count=count,
                request_id=_request_id(headers),
            )
        except (VaultSecurityError, ValueError, TypeError) as error:
            raise _translate(error) from None
        return result.as_dict()

    def unlock(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        try:
            return _service.unlock(
                _text(body, "passphrase"), request_id=_request_id(headers)
            ).as_dict()
        except (VaultSecurityError, ValueError, TypeError) as error:
            raise _translate(error) from None

    def lock(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _service.lock(request_id=_request_id(headers)).as_dict()

    def rotate(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        try:
            return _service.rotate(
                _text(body, "new_passphrase"), request_id=_request_id(headers)
            ).as_dict()
        except (VaultSecurityError, ValueError, TypeError) as error:
            raise _translate(error) from None

    def recovery_issue(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        count = body.get("count", 6)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 8:
            raise V3Error.invalid("count", "must be between 1 and 8")
        try:
            codes = _service.issue_recovery_codes(
                _text(body, "passphrase"), count=count, request_id=_request_id(headers)
            )
        except (VaultSecurityError, ValueError, TypeError) as error:
            raise _translate(error) from None
        return {"recovery_codes": list(codes), "count": len(codes)}

    def recover(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        try:
            return _service.recover(
                _text(body, "code"),
                _text(body, "new_passphrase"),
                request_id=_request_id(headers),
            ).as_dict()
        except (VaultSecurityError, RecoveryCodeError, ValueError, TypeError) as error:
            raise _translate(error) from None

    def policy_get(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _service.policy_snapshot()

    def policy_update(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        rules = body.get("rules", ())
        if not isinstance(rules, (list, tuple)) or not all(
            isinstance(rule, dict) for rule in rules
        ):
            raise V3Error.invalid("rules", "must be a list of rule objects")
        rule_payloads: tuple[dict[str, Any], ...] = tuple(
            rule for rule in rules if isinstance(rule, dict)
        )
        try:
            grants = tuple(parse_scope(str(value)) for value in body.get("grants", ()))
            revocations = tuple(parse_scope(str(value)) for value in body.get("revocations", ()))
        except PolicyError as error:
            raise _translate(error) from None
        try:
            return _service.update_policy(
                rules=rule_payloads,
                grants=grants,
                revocations=revocations,
                request_id=_request_id(headers),
            )
        except (VaultSecurityError, ValueError, TypeError) as error:
            raise _translate(error) from None

    def policy_preview(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        try:
            scope = parse_scope(_text(body, "scope"))
        except PolicyError as error:
            raise _translate(error) from None
        return _service.preview_policy(_optional_text(body, "text"), scope)

    def audit_list(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        try:
            return _service.audit_list(body)
        except (ValueError, TypeError) as error:
            raise _translate(error) from None

    def audit_export(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        fmt = _optional_text(body, "format", "json")
        if fmt not in ("json", "jsonl"):
            raise V3Error.invalid("format", "must be 'json' or 'jsonl'")
        try:
            rendered = _service.audit_export(
                fmt=fmt, criteria=body, request_id=_request_id(headers)
            )
        except (VaultSecurityError, ValueError, TypeError) as error:
            raise _translate(error) from None
        return {"format": fmt, "document": rendered}

    def events(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {"events": list(_service.events())}

    router.add("security", "status", status, public=True)
    router.add("security", "posture", posture, public=True)
    router.add("security", "setup", setup)
    router.add("security", "unlock", unlock)
    router.add("security", "lock", lock)
    router.add("security", "rotate", rotate)
    router.add("security", "recovery_issue", recovery_issue)
    router.add("security", "recover", recover)
    router.add("security", "policy_get", policy_get)
    router.add("security", "policy_update", policy_update)
    router.add("security", "policy_preview", policy_preview)
    router.add("security", "audit_list", audit_list)
    router.add("security", "audit_export", audit_export)
    router.add("security", "events", events)
