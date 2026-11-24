"""Facade service coordinating bundles, merges, transfers, and audit trails."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from redscribe.v3.capabilities import CAP_ENCRYPTION, CAP_PORTABILITY, Capabilities
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.config import V3Config
from redscribe.v3.entities.types import EntityLink as V3EntityLink
from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.redaction import RedactionPolicy
from redscribe.v3.events.types import DomainEvent, EventSeverity
from redscribe.v3.portability.bundle import (
    PortableBundle,
    create_bundle,
    open_bundle,
)
from redscribe.v3.portability.conflicts import ConflictResolver, ResolutionLedger
from redscribe.v3.portability.crypto import DEFAULT_KDF_ITERATIONS, is_strong_passphrase
from redscribe.v3.portability.device import DeviceIdentity, DeviceRegistry
from redscribe.v3.portability.dryrun import DryRunReport, plan_bundle_create, plan_import
from redscribe.v3.portability.errors import (
    BundleError,
    PortabilityError,
    TransferError,
    VerificationError,
)
from redscribe.v3.portability.manifest import BundleManifest, VerificationReport
from redscribe.v3.portability.merge import (
    ConflictReason,
    MergeResult,
    ResolutionStrategy,
    group_conflicts_by_reason,
    merge_families,
)
from redscribe.v3.portability.receipt import VerificationReceipt, build_receipt
from redscribe.v3.portability.records import PortableEntity, link_from_dict
from redscribe.v3.portability.transfer import TransferManager, TransferSession
from redscribe.v3.portability.vectors import VectorRelation, VersionVector


@dataclass(frozen=True, slots=True)
class PreviewRecord:
    """A stored dry-run preview awaiting conflict decisions."""

    preview_id: str
    report: DryRunReport
    result: MergeResult
    manifest: BundleManifest | None = None


class PortabilityService:
    """Application service for safe, verifiable vault movement."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        capabilities: Capabilities | None = None,
        bus: EventBus | None = None,
        config: V3Config | None = None,
        kdf_iterations: int = DEFAULT_KDF_ITERATIONS,
        enforce_strong_passphrase: bool = True,
    ) -> None:
        self._clock: Clock = clock or SystemClock()
        self._capabilities = capabilities or (config or V3Config()).capabilities()
        self._bus = bus or EventBus()
        self._redaction = RedactionPolicy()
        self._kdf_iterations = kdf_iterations
        self._enforce_passphrase = enforce_strong_passphrase
        self._devices = DeviceRegistry()
        self._transfers = TransferManager()
        self._ledger = ResolutionLedger()
        self._resolver = ConflictResolver(self._ledger, self._bus)
        self._bundles: dict[str, PortableBundle] = {}
        self._previews: dict[str, PreviewRecord] = {}
        self._receipts: dict[str, VerificationReceipt] = {}
        self._audit: list[dict[str, Any]] = []
        self._sequence = 0
        self._local = DeviceIdentity(
            device_id="local",
            label="This device",
            platform="desktop",
            created_at=self._clock.now_timestamp(),
        )
        self._devices.add(self._local, trusted=True)

    def _require(self) -> None:
        """Gate portability operations behind their capability flags."""
        self._capabilities.require(CAP_PORTABILITY)
        self._capabilities.require(CAP_ENCRYPTION)

    def _emit(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        severity: EventSeverity = EventSeverity.INFO,
        correlation_id: str = "",
    ) -> None:
        """Record a redacted domain event and an audit entry."""
        cleaned = self._redaction.apply(payload)
        self._bus.publish(
            DomainEvent(
                kind=kind,
                severity=severity,
                payload=cleaned,
                correlation_id=correlation_id,
            )
        )
        self._sequence += 1
        self._audit.append({"sequence": self._sequence, "kind": kind, **cleaned})

    def _check_passphrase(self, passphrase: str) -> None:
        """Enforce the local passphrase policy without ever storing the value."""
        if not isinstance(passphrase, str) or not passphrase:
            raise PortabilityError("A bundle passphrase is required")
        if self._enforce_passphrase and not is_strong_passphrase(passphrase, minimum_length=8):
            raise PortabilityError("Passphrase is too weak for an encrypted bundle")

    def _bundle(self, bundle_id: str) -> PortableBundle:
        """Return a stored bundle or raise a not-found error."""
        bundle = self._bundles.get(bundle_id)
        if bundle is None:
            raise BundleError(f"Unknown bundle: {bundle_id}")
        return bundle

    def _entities(self, payloads: Any) -> tuple[PortableEntity, ...]:
        """Parse serialized entity snapshots."""
        if not isinstance(payloads, (list, tuple)):
            raise BundleError("Entities must be a list")
        return tuple(PortableEntity.from_dict(item) for item in payloads)

    def _links(self, payloads: Any) -> tuple[V3EntityLink, ...]:
        """Parse serialized entity links."""
        if not isinstance(payloads, (list, tuple)):
            raise BundleError("Links must be a list")
        return tuple(link_from_dict(item) for item in payloads)

    def register_device(
        self,
        device_id: str,
        label: str,
        *,
        platform: str = "desktop",
        trusted: bool = False,
    ) -> dict[str, Any]:
        """Register a device that may author or receive bundles."""
        self._require()
        identity = DeviceIdentity(
            device_id=device_id,
            label=label,
            platform=platform,
            created_at=self._clock.now_timestamp(),
        )
        record = self._devices.add(identity, trusted=trusted)
        self._emit(
            "portability.device.registered",
            {"device": device_id, "trusted": trusted, "label": label},
        )
        return record.as_dict()

    def trust_device(self, device_id: str) -> dict[str, Any]:
        """Trust a previously registered device."""
        self._require()
        record = self._devices.trust(device_id, seen_at=self._clock.now_timestamp())
        self._emit("portability.device.trusted", {"device": device_id})
        return record.as_dict()

    def devices(self) -> dict[str, Any]:
        """Return the device registry summary."""
        return self._devices.as_dict()

    def health(self) -> dict[str, Any]:
        """Return capability and workload status for the portability UI."""
        return {
            "available": self._capabilities.has(CAP_PORTABILITY)
            and self._capabilities.has(CAP_ENCRYPTION),
            "capabilities": {
                "portability": self._capabilities.has(CAP_PORTABILITY),
                "encryption": self._capabilities.has(CAP_ENCRYPTION),
            },
            "algorithm": "blake2b-xor-hmac-sha256-v1",
            "manifest_version": "v3.1",
            "reason_codes": [reason.value for reason in ConflictReason],
            "strategies": [strategy.value for strategy in ResolutionStrategy],
            "bundles": len(self._bundles),
            "devices": len(self._devices.all()),
            "transfers": len(self._transfers.all()),
            "receipts": len(self._receipts),
            "ledger_intact": self._ledger.verify_chain(),
        }

    def plan_bundle(
        self,
        entities: tuple[PortableEntity, ...],
        links: tuple[V3EntityLink, ...] = (),
    ) -> dict[str, Any]:
        """Return a non-mutating preview of a candidate bundle."""
        self._require()
        return plan_bundle_create(entities, links).as_dict()

    def create_bundle(
        self,
        entities: tuple[PortableEntity, ...],
        links: tuple[V3EntityLink, ...] = (),
        *,
        passphrase: str,
        device_id: str = "local",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Seal an encrypted bundle and store it for inspection or transfer."""
        self._require()
        self._check_passphrase(passphrase)
        device = self._devices.require_trusted(device_id).identity
        bundle = create_bundle(
            entities,
            links,
            device=device,
            passphrase=passphrase,
            clock=self._clock,
            metadata=metadata,
            iterations=self._kdf_iterations,
        )
        self._bundles[bundle.header.bundle_id] = bundle
        self._devices.see(device_id, at=self._clock.now_timestamp())
        self._emit(
            "portability.bundle.created",
            {
                "bundle": bundle.header.bundle_id,
                "device": device_id,
                "entities": len(entities),
                "links": len(links),
            },
            correlation_id=bundle.header.bundle_id,
        )
        return {**bundle.inspect(), "sealed": True}

    def inspect_bundle(self, bundle_id: str) -> dict[str, Any]:
        """Inspect bundle metadata without needing the passphrase."""
        self._require()
        return self._bundle(bundle_id).inspect()

    def verify_bundle(self, bundle_id: str, passphrase: str) -> dict[str, Any]:
        """Open, verify, and issue a receipt for a stored bundle."""
        self._require()
        bundle = self._bundle(bundle_id)
        payload = open_bundle(bundle, passphrase)
        origin_valid = self._devices.is_trusted(payload.origin_device)
        receipt = build_receipt(
            payload.manifest,
            payload.report,
            device=payload.origin_device,
            clock=self._clock,
            origin_valid=origin_valid,
            resolution_count=0,
        )
        self._receipts[receipt.receipt_id] = receipt
        self._emit(
            "portability.bundle.verified",
            {"bundle": bundle_id, "receipt": receipt.receipt_id, "ok": receipt.ok},
            severity=EventSeverity.NOTICE,
            correlation_id=bundle_id,
        )
        return {
            **payload.as_dict(),
            "receipt": receipt.as_dict(),
            "origin_trusted": origin_valid,
        }

    def open_bundle(self, bundle_id: str, passphrase: str) -> dict[str, Any]:
        """Return a verified plaintext summary for import planning."""
        self._require()
        payload = open_bundle(self._bundle(bundle_id), passphrase)
        return {
            **payload.as_dict(),
            "entity_payloads": [entity.as_dict() for entity in payload.entities],
            "link_payloads": [link.as_dict() for link in payload.links],
        }

    def compare_vectors(
        self,
        local: dict[str, int],
        remote: dict[str, int],
    ) -> dict[str, Any]:
        """Compare two version vectors using the shared causal ordering."""
        left = VersionVector.from_dict(local)
        right = VersionVector.from_dict(remote)
        relation = left.compare(right)
        return {
            "local": left.as_dict(),
            "remote": right.as_dict(),
            "relation": relation.value,
            "relation_label": relation.label,
            "merged": left.merge(right).as_dict(),
            "distance": left.distance_from(right),
            "changed_devices": list(left.changed_devices(right)),
            "concurrent": relation is VectorRelation.CONCURRENT,
        }

    def detect_conflicts(
        self,
        base: tuple[PortableEntity, ...],
        local: tuple[PortableEntity, ...],
        remote: tuple[PortableEntity, ...],
        *,
        base_links: tuple[V3EntityLink, ...] = (),
        local_links: tuple[V3EntityLink, ...] = (),
        remote_links: tuple[V3EntityLink, ...] = (),
    ) -> dict[str, Any]:
        """Detect and group merge conflicts without changing any data."""
        self._require()
        result = merge_families(
            base,
            local,
            remote,
            base_links=base_links,
            local_links=local_links,
            remote_links=remote_links,
        )
        groups = group_conflicts_by_reason(result.conflicts)
        return {
            "count": len(result.conflicts),
            "conflicts": [conflict.as_dict() for conflict in result.conflicts],
            "reasons": [reason.value for reason in groups],
            "groups": {
                reason.value: [item.as_dict() for item in items] for reason, items in groups.items()
            },
        }

    def preview_import(
        self,
        bundle_id: str,
        passphrase: str,
        base: tuple[PortableEntity, ...],
        local: tuple[PortableEntity, ...],
        *,
        base_links: tuple[V3EntityLink, ...] = (),
        local_links: tuple[V3EntityLink, ...] = (),
        families: tuple[str, ...] = (),
        base_vector: VersionVector | None = None,
        local_vector: VersionVector | None = None,
    ) -> dict[str, Any]:
        """Run a dry-run import and store it for later conflict resolution."""
        self._require()
        payload = open_bundle(self._bundle(bundle_id), passphrase)
        report, result = plan_import(
            base,
            local,
            payload.entities,
            base_links=base_links,
            local_links=local_links,
            remote_links=payload.links,
            base_vector=base_vector,
            local_vector=local_vector,
            remote_vector=payload.manifest.vector,
            families=families,
        )
        preview_id = f"preview_{len(self._previews) + 1:04d}"
        self._previews[preview_id] = PreviewRecord(preview_id, report, result, payload.manifest)
        self._emit(
            "portability.preview.created",
            {
                "preview": preview_id,
                "bundle": bundle_id,
                "conflicts": len(result.conflicts),
            },
            correlation_id=preview_id,
        )
        return {
            "preview_id": preview_id,
            **report.as_dict(),
            "merge": result.as_dict(),
        }

    def resolve_preview(
        self,
        preview_id: str,
        decisions: dict[str, str] | None = None,
        *,
        actor: str = "local",
        device: str = "local",
        default: ResolutionStrategy = ResolutionStrategy.MANUAL,
    ) -> dict[str, Any]:
        """Apply auditable decisions to a stored dry-run preview."""
        self._require()
        record = self._previews.get(preview_id)
        if record is None:
            raise PortabilityError(f"Unknown preview: {preview_id}")
        updated, entries = self._resolver.resolve_bulk(
            record.result,
            decisions or {},
            actor=actor,
            device=device,
            decided_at=self._clock.now_timestamp(),
            default=default,
        )
        receipt = build_receipt(
            record.manifest or _preview_manifest(preview_id),
            VerificationReport(),
            device=device,
            clock=self._clock,
            origin_valid=True,
            resolution_count=len(entries),
        )
        self._receipts[receipt.receipt_id] = receipt
        self._emit(
            "portability.merge.completed",
            {
                "preview": preview_id,
                "decisions": len(entries),
                "receipt": receipt.receipt_id,
                "clean": updated.clean,
            },
            severity=EventSeverity.NOTICE,
            correlation_id=preview_id,
        )
        return {
            "preview_id": preview_id,
            "merge": updated.as_dict(),
            "decisions": [entry.as_dict() for entry in entries],
            "ledger_intact": self._ledger.verify_chain(),
            "receipt": receipt.as_dict(),
        }

    def begin_transfer(
        self,
        bundle_id: str,
        *,
        chunk_size: int = 64 * 1024,
    ) -> dict[str, Any]:
        """Start a chunked transfer for a stored bundle."""
        self._require()
        if chunk_size < 1:
            raise TransferError("Chunk size must be positive")
        bundle = self._bundle(bundle_id)
        session = self._transfers.start(
            bundle_id,
            bundle.to_bytes(),
            chunk_size=chunk_size,
            created_at=self._clock.now_timestamp(),
        )
        self._emit(
            "portability.transfer.started",
            {"transfer": session.transfer_id, "bundle": bundle_id},
            correlation_id=session.transfer_id,
        )
        return session.as_dict()

    def transfer_status(self, transfer_id: str) -> dict[str, Any]:
        """Return progress and missing chunks for a transfer."""
        return self._transfers.get(transfer_id).as_dict()

    def transfer_checkpoint(self, transfer_id: str) -> dict[str, Any]:
        """Return a resumable checkpoint for an interrupted transfer."""
        return self._transfers.checkpoint(transfer_id)

    def push_chunk(
        self,
        transfer_id: str,
        index: int,
        chunk_b64: str,
    ) -> dict[str, Any]:
        """Receive one base64-encoded chunk and return the updated status."""
        self._require()
        try:
            data = base64.b64decode(chunk_b64, validate=True)
        except (ValueError, TypeError) as error:
            raise TransferError("Chunk data must be valid base64") from error
        receipt = self._transfers.push(
            transfer_id,
            index,
            data,
            updated_at=self._clock.now_timestamp(),
        )
        return {
            **self._transfers.get(transfer_id).as_dict(),
            "receipt": receipt.as_dict(),
        }

    def pause_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Pause a transfer while preserving received chunks."""
        return self._transfers.pause(transfer_id).as_dict()

    def resume_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Resume a paused or failed transfer."""
        session: TransferSession = self._transfers.resume(transfer_id)
        self._emit(
            "portability.transfer.resumed",
            {"transfer": transfer_id, "percent": session.percent},
            correlation_id=transfer_id,
        )
        return session.as_dict()

    def cancel_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Cancel a transfer with an auditable status change."""
        session = self._transfers.cancel(transfer_id)
        self._emit(
            "portability.transfer.cancelled",
            {"transfer": transfer_id, "received": session.received_chunks},
            severity=EventSeverity.WARNING,
            correlation_id=transfer_id,
        )
        return session.as_dict()

    def finish_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Assemble a complete transfer and verify the final digest."""
        self._require()
        data = self._transfers.finish(transfer_id)
        bundle = PortableBundle.from_bytes(data)
        self._emit(
            "portability.transfer.completed",
            {"transfer": transfer_id, "bundle": bundle.header.bundle_id},
            correlation_id=transfer_id,
        )
        return {
            "transfer": transfer_id,
            "bundle": bundle.header.bundle_id,
            "bytes": len(data),
            "status": "complete",
        }

    def receipt(self, receipt_id: str) -> dict[str, Any]:
        """Return one stored verification receipt."""
        found = self._receipts.get(receipt_id)
        if found is None:
            raise VerificationError(f"Unknown receipt: {receipt_id}")
        return found.as_dict()

    def receipts(self) -> dict[str, Any]:
        """Return all verification receipts."""
        return {
            "count": len(self._receipts),
            "receipts": [item.as_dict() for item in self._receipts.values()],
        }

    def audit(self) -> dict[str, Any]:
        """Return the redacted portability audit trail."""
        return {
            "count": len(self._audit),
            "events": [dict(item) for item in self._audit],
            "resolutions": self._resolver.as_dict(),
        }

    def bus_snapshot(self) -> dict[str, Any]:
        """Return the shared event bus snapshot for integration checks."""
        return self._bus.snapshot()


def _preview_manifest(preview_id: str) -> Any:
    """Return a minimal manifest stub used for merge receipts."""
    from redscribe.v3.portability.manifest import BundleManifest

    return BundleManifest(
        bundle_id=preview_id,
        created_at=0.0,
        source_device="local",
        entity_count=0,
        link_count=0,
        checksums={},
        payload_digest="",
    )
