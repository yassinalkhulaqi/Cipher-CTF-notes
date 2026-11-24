"""Application service for manifest validation, installation, and discovery."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.idempotency import etag_matches
from redscribe.v3.api.pagination import PageRequest
from redscribe.v3.api_sdk.capabilities import CapabilityNegotiator
from redscribe.v3.api_sdk.errors import ManifestError, SdkError
from redscribe.v3.api_sdk.manifest import (
    SCHEMA_ID,
    ManifestStore,
    example_manifest,
    manifest_schema,
    parse_manifest,
    validate_manifest,
)
from redscribe.v3.api_sdk.safety import assert_no_code_execution
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.config import V3Config, default_config

SDK_CONTRACTS: dict[str, Any] = {
    "base_path": "/api/v3",
    "envelopes": {
        "success": {"data": "any", "meta": "ResponseMeta"},
        "error": {"error": "ErrorDetail", "meta": "ResponseMeta"},
    },
    "headers": ["X-Request-ID", "If-None-Match", "Idempotency-Key", "X-Capability"],
    "write_requires_opt_in": True,
    "execution": "none",
    "schema": SCHEMA_ID,
}


def _as_v3(error: SdkError, code: V3ErrorCode = V3ErrorCode.FORBIDDEN) -> V3Error:
    return V3Error(
        code,
        error.message,
        field=error.field,
        status=error.status,
        retryable=error.retryable,
        context=error.context,
    )


@dataclass(slots=True, init=False)
class ExtensionService:
    """Stateful service shared by routes, SDK clients, and the CLI."""

    config: V3Config
    negotiator: CapabilityNegotiator
    store: ManifestStore
    clock: Clock

    def __init__(
        self,
        config: V3Config | None = None,
        *,
        store: ManifestStore | None = None,
        negotiator: CapabilityNegotiator | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.config = config or default_config
        self.negotiator = negotiator or CapabilityNegotiator(config=self.config)
        self.store = store or ManifestStore()
        self.clock = clock or SystemClock()

    def validate(self, document: Any) -> dict[str, Any]:
        """Validate a manifest document without changing state."""
        report = validate_manifest(document)
        return report.as_dict()

    def schema(self) -> dict[str, Any]:
        """Return the manifest schema descriptor."""
        return manifest_schema()

    def example(self) -> dict[str, Any]:
        """Return a valid example document."""
        return example_manifest()

    def list(
        self,
        *,
        offset: int = 0,
        size: int = 50,
        required: Iterable[str] = (),
    ) -> dict[str, Any]:
        """List installed manifests using B00 pagination."""
        request = PageRequest(offset=offset, size=size)
        items, meta, cursor = self.store.page(request.offset, request.size)
        wanted = frozenset(required)
        summaries = tuple(
            item
            for item in self.store.summaries(wanted)
            if item["id"] in {manifest.id for manifest in items}
        )
        return {
            "extensions": list(summaries),
            "next_cursor": cursor,
            "revision": self.store.revision,
            "page": meta.as_dict(),
        }

    def get(self, identifier: str, *, etag: str = "") -> dict[str, Any]:
        """Return one manifest, or a conditional-not-modified marker."""
        manifest = self.store.get(identifier)
        if etag and etag_matches(etag, manifest.fingerprint):
            return {
                "extension": None,
                "not_modified": True,
                "etag": manifest.fingerprint,
            }
        return {
            "extension": manifest.as_dict(),
            "not_modified": False,
            "etag": manifest.fingerprint,
        }

    def install(
        self,
        document: Mapping[str, Any] | None,
        *,
        allow_write: bool = False,
        expected_etag: str = "",
    ) -> dict[str, Any]:
        """Install a validated manifest after explicit write opt-in."""
        try:
            self.negotiator.allow_write(opt_in=allow_write)
            manifest = parse_manifest(document or {})
            for capability in manifest.requires:
                self.negotiator.require(capability, required_for=manifest.id)
        except SdkError as error:
            code = (
                V3ErrorCode.INVALID_REQUEST
                if isinstance(error, ManifestError)
                else V3ErrorCode.FORBIDDEN
            )
            raise _as_v3(error, code) from error
        installed, replaced = self.store.install(manifest, expected_etag=expected_etag)
        return {
            "extension": installed.as_dict(),
            "replaced": replaced,
            "etag": installed.fingerprint,
            "revision": self.store.revision,
        }

    def remove(
        self,
        identifier: str,
        *,
        allow_write: bool = False,
        expected_etag: str = "",
    ) -> dict[str, Any]:
        """Remove an installed manifest after explicit write opt-in."""
        try:
            self.negotiator.allow_write(opt_in=allow_write)
        except SdkError as error:
            raise _as_v3(error) from error
        removed = self.store.remove(identifier, expected_etag=expected_etag)
        return {
            "extension": removed.as_dict(),
            "removed": True,
            "revision": self.store.revision,
        }

    def negotiate(self, required: Iterable[str]) -> dict[str, Any]:
        """Negotiate required capabilities for a script or manifest."""
        decisions = self.negotiator.negotiate(required)
        denied = [item.name for item in decisions if not item.granted]
        return {
            "decisions": [item.as_dict() for item in decisions],
            "granted": not denied,
            "denied": denied,
        }

    def contracts(self) -> dict[str, Any]:
        """Return SDK wire contracts for the in-app explorer."""
        return {
            **SDK_CONTRACTS,
            "capabilities": self.negotiator.as_dict(),
            "error_codes": [
                "unknown_route",
                "not_found",
                "invalid_request",
                "invalid_type",
                "missing_field",
                "idempotency_conflict",
                "precondition_failed",
                "forbidden",
            ],
            "version": "1.0.0",
        }

    def safety(self) -> dict[str, Any]:
        """Run and report the static code-execution invariant."""
        report = assert_no_code_execution()
        return {**report.as_dict(), "checked_at": self.clock.now_iso()}

    def health(self) -> dict[str, Any]:
        """Return service health for diagnostics."""
        return {
            "status": "ok",
            "manifests": self.store.size(),
            "revision": self.store.revision,
            "offline_only": self.config.offline_only,
            "allow_extensions": self.config.allow_extensions,
        }

    def require_manifest(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        """Read the manifest document from a request body."""
        document = body.get("manifest")
        if not isinstance(document, Mapping):
            raise V3Error(
                V3ErrorCode.INVALID_TYPE, "'manifest' must be an object", field="manifest"
            )
        return document


_shared_service: ExtensionService | None = None


def get_service() -> ExtensionService:
    """Return the process-wide extension service."""
    global _shared_service
    if _shared_service is None:
        _shared_service = ExtensionService()
    return _shared_service


def set_service(service: ExtensionService) -> ExtensionService:
    """Replace the shared service, primarily for tests and local fixtures."""
    global _shared_service
    _shared_service = service
    return service


def reset_service() -> ExtensionService:
    """Reset the shared service to its default configuration."""
    global _shared_service
    _shared_service = ExtensionService()
    return _shared_service
