"""Orchestration service for the evidence vault."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from redscribe.v2.evidence.custody import (
    CustodyChain,
    custody_summary,
    custody_timeline,
)
from redscribe.v2.evidence.errors import (
    ConflictError,
    IngestError,
    ManifestError,
    NotFoundError,
    ValidationError,
)
from redscribe.v2.evidence.files import (
    BlobStore,
    DirectoryBlobStore,
    InMemoryBlobStore,
    validate_blob_size,
)
from redscribe.v2.evidence.hashing import canonical_json, hash_bytes
from redscribe.v2.evidence.integrity import (
    UNSET,
    IntegrityVerifier,
    integrity_badge,
    report_summary,
)
from redscribe.v2.evidence.links import FindingLinkIndex, group_by_type, link_summary
from redscribe.v2.evidence.manifests import (
    build_manifest,
    custody_by_evidence,
    entries_by_hash,
    links_by_evidence,
    parse_manifest,
    plan_import,
    retention_by_evidence,
    validate_manifest,
)
from redscribe.v2.evidence.mime import detect_mime, mime_from_path
from redscribe.v2.evidence.models import (
    AcquisitionMethod,
    CustodyAction,
    DispositionAction,
    EvidenceKind,
    EvidenceManifest,
    EvidenceRecord,
    EvidenceStats,
    EvidenceStatus,
    FindingLink,
    IntegrityReport,
    IntegrityState,
    LinkType,
    RetentionBasis,
    RetentionPolicy,
    ThumbnailMetadata,
)
from redscribe.v2.evidence.provenance import (
    from_acquisition,
    missing_provenance_fields,
    provenance_checklist,
    provenance_summary,
    update_provenance,
)
from redscribe.v2.evidence.records import (
    apply_update,
    build_record,
    filter_records,
    generate_evidence_id,
    paginate_records,
    transition_status,
)

BLANK_DIGEST_LENGTH = 64


class EvidenceVaultService:
    """Application service combining repositories, blobs, and domain rules."""

    def __init__(
        self,
        repository: Any | None = None,
        blobs: BlobStore | None = None,
        *,
        max_bytes: int = 64 * 1024 * 1024,
        case_reference: str = "",
        generator: str = "redscribe-evidence-vault",
    ) -> None:
        if repository is None:
            from redscribe.v2.evidence.repositories import InMemoryEvidenceRepository

            repository = InMemoryEvidenceRepository()
        self._repository = repository
        self._blobs = blobs if blobs is not None else InMemoryBlobStore()
        self._max_bytes = max_bytes
        self._case_reference = case_reference
        self._generator = generator
        self._verifier = IntegrityVerifier()

    @property
    def repository(self) -> Any:
        return self._repository

    @property
    def blobs(self) -> BlobStore:
        return self._blobs

    @property
    def case_reference(self) -> str:
        return self._case_reference

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    # ------------------------------------------------------------------
    # Ingestion and records
    # ------------------------------------------------------------------

    def ingest_bytes(
        self,
        data: bytes,
        *,
        filename: str = "evidence.bin",
        title: str = "",
        description: str = "",
        mime_type: str = "",
        tags: Sequence[str] | str = (),
        note_id: int | None = None,
        kind: EvidenceKind | None = None,
        method: AcquisitionMethod = AcquisitionMethod.MANUAL_UPLOAD,
        actor: str = "",
        operator: str = "",
        source_path: str = "",
        source_description: str = "",
        case_reference: str = "",
        witness: str = "",
        image_number: int = 0,
        custom_fields: Mapping[str, Any] | None = None,
        dedupe: bool = True,
    ) -> EvidenceRecord:
        """Ingest in-memory bytes as a new evidence record."""
        validate_blob_size(data, max_bytes=self._max_bytes)
        digests = hash_bytes(data)
        if dedupe:
            existing = self.find_by_sha256(digests.sha256)
            if existing is not None:
                return existing
        from redscribe.v2.evidence.records import mime_kind
        from redscribe.v2.evidence.thumbnails import thumbnail_metadata
        from redscribe.v2.evidence.validation import now_iso, sanitize_filename

        clean_name = sanitize_filename(filename)
        seed = f"{digests.sha256}:{clean_name}:{now_iso()}"
        evidence_id = generate_evidence_id(seed, existing=self.record_ids())
        mime = detect_mime(data, filename=clean_name, declared=mime_type)
        stored_path = self._blobs.put(evidence_id, clean_name, data)
        thumbnail = thumbnail_metadata(
            data,
            mime_type=mime.mime_type,
            source_sha256=digests.sha256,
            filename=clean_name,
        )
        provenance = from_acquisition(
            evidence_id,
            method=method,
            operator=operator or actor,
            source_path=source_path or clean_name,
            source_description=source_description,
            case_reference=case_reference or self._case_reference,
            witness=witness,
            image_number=image_number,
        )
        record = build_record(
            evidence_id=evidence_id,
            title=title or clean_name,
            description=description,
            digests=digests,
            mime=mime,
            kind=kind or mime_kind(mime, clean_name),
            status=EvidenceStatus.ACQUIRED,
            original_filename=clean_name,
            stored_path=stored_path,
            thumbnail=thumbnail,
            provenance=provenance,
            tags=tags,
            note_id=note_id,
            custom_fields=custom_fields,
        )
        self._repository.save_record(record)
        self.add_custody(
            record.id,
            CustodyAction.ACQUIRED,
            actor=actor or operator or "system",
            description=f"Acquired {clean_name}",
            location=source_path or clean_name,
            reference=digests.sha256[:16],
        )
        self.set_retention(record.id, basis=RetentionBasis.CASE)
        return record

    def ingest_path(
        self,
        path: str | Path,
        **options: Any,
    ) -> EvidenceRecord:
        """Read a file from disk and ingest it as evidence."""
        source = Path(path).expanduser()
        if not source.is_file():
            raise IngestError(f"Evidence file does not exist: {source}")
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise IngestError(f"Unable to read evidence file: {source}") from exc
        options.setdefault("filename", source.name)
        options.setdefault("source_path", str(source))
        return self.ingest_bytes(data, **options)

    def record_external(
        self,
        *,
        title: str,
        description: str = "",
        source_path: str = "",
        kind: EvidenceKind = EvidenceKind.OTHER,
        tags: Sequence[str] | str = (),
        note_id: int | None = None,
        operator: str = "",
        case_reference: str = "",
    ) -> EvidenceRecord:
        """Create a metadata-only record for evidence held outside the vault."""
        from redscribe.v2.evidence.records import mime_kind
        from redscribe.v2.evidence.validation import now_iso

        marker = {"title": title, "source_path": source_path, "kind": kind.value}
        digests = hash_bytes(canonical_json(marker).encode("utf-8"))
        evidence_id = generate_evidence_id(
            f"external:{digests.sha256}:{now_iso()}", existing=self.record_ids()
        )
        mime = mime_from_path(source_path or title)
        provenance = from_acquisition(
            evidence_id,
            method=AcquisitionMethod.EXTERNAL_TOOL,
            operator=operator,
            source_path=source_path,
            case_reference=case_reference or self._case_reference,
        )
        record = build_record(
            evidence_id=evidence_id,
            title=title,
            description=description,
            digests=digests,
            mime=mime,
            kind=mime_kind(mime, source_path),
            status=EvidenceStatus.DISCOVERED,
            original_filename=Path(source_path).name if source_path else "",
            stored_path="",
            thumbnail=ThumbnailMetadata(
                available=False, preview_kind="external", note="External evidence"
            ),
            provenance=provenance,
            tags=tags,
            note_id=note_id,
        )
        self._repository.save_record(record)
        self.add_custody(
            record.id,
            CustodyAction.CREATED,
            actor=operator or "system",
            description=f"Registered external evidence: {title}",
            location=source_path,
        )
        self.set_retention(record.id, basis=RetentionBasis.CASE)
        return record

    def get_record(self, evidence_id: str) -> EvidenceRecord:
        """Return one record or raise a not-found error."""
        record = self._repository.get_record(evidence_id)
        if record is None:
            raise NotFoundError(
                f"Evidence {evidence_id} does not exist",
                details={"evidence_id": evidence_id},
            )
        return record

    def find_by_sha256(self, digest: str) -> EvidenceRecord | None:
        """Find a record by its SHA-256 digest."""
        needle = digest.casefold()
        return next(
            (
                record
                for record in self._repository.all_records()
                if record.sha256.casefold() == needle
            ),
            None,
        )

    def record_ids(self) -> tuple[str, ...]:
        """Return all stored evidence ids."""
        return tuple(record.id for record in self._repository.all_records())

    def list_records(
        self,
        *,
        query: str = "",
        kind: EvidenceKind | None = None,
        status: EvidenceStatus | None = None,
        tag: str = "",
        mime_type: str = "",
        note_id: int | None = None,
        hash_prefix: str = "",
        sort: str = "created_at",
        direction: str = "desc",
    ) -> list[EvidenceRecord]:
        """Return filtered records in deterministic order."""
        return filter_records(
            self._repository.all_records(),
            query=query,
            kind=kind,
            status=status,
            tag=tag,
            mime_type=mime_type,
            note_id=note_id,
            hash_prefix=hash_prefix,
            sort=sort,
            direction=direction,
        )

    def list_page(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        **filters: Any,
    ) -> tuple[list[EvidenceRecord], dict[str, Any]]:
        """Return one page of filtered records and pagination metadata."""
        records = self.list_records(**filters)
        return paginate_records(records, offset=offset, limit=limit)

    def update_record(self, evidence_id: str, **changes: Any) -> EvidenceRecord:
        """Apply validated field updates to one record."""
        record = self.get_record(evidence_id)
        updated = apply_update(record, **changes)
        self._repository.save_record(updated)
        return updated

    def set_status(
        self,
        evidence_id: str,
        target: EvidenceStatus,
        *,
        actor: str = "system",
        description: str = "",
        force: bool = False,
    ) -> EvidenceRecord:
        """Move a record through its lifecycle and journal the transition."""
        record = self.get_record(evidence_id)
        updated = transition_status(record, target, force=force)
        if updated is record:
            return record
        self._repository.save_record(updated)
        action = {
            EvidenceStatus.VERIFIED: CustodyAction.VERIFIED,
            EvidenceStatus.SEALED: CustodyAction.SEALED,
            EvidenceStatus.ARCHIVED: CustodyAction.RELEASED,
            EvidenceStatus.DISPOSED: CustodyAction.DESTROYED,
        }.get(target, CustodyAction.ANALYZED)
        self.add_custody(
            evidence_id,
            action,
            actor=actor,
            description=description or f"Status changed to {target.value}",
        )
        return updated

    def delete_record(self, evidence_id: str, *, remove_blob: bool = True) -> bool:
        """Delete one record and all of its dependent metadata."""
        record = self._repository.get_record(evidence_id)
        if record is None:
            return False
        if remove_blob and record.stored_path:
            self._blobs.delete(record.stored_path)
        self._repository.delete_record(evidence_id)
        self._repository.delete_custody(evidence_id)
        self._repository.delete_links(evidence_id)
        self._repository.delete_policy(evidence_id)
        return True

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------

    def verify_record(
        self, evidence_id: str, *, manifest: EvidenceManifest | None = None
    ) -> IntegrityReport:
        """Verify one record against stored bytes, custody, and a manifest."""
        record = self.get_record(evidence_id)
        data: object = UNSET
        if record.stored_path:
            data = self._blobs.get(record.stored_path)
        entry = None
        if manifest is not None:
            entry = next(
                (item for item in manifest.entries if item.evidence_id == evidence_id),
                None,
            )
        report = self._verifier.verify_record(
            record,
            data=data,
            custody=self._repository.custody_events(evidence_id),
            manifest=entry,
        )
        if report.state is IntegrityState.VERIFIED:
            self.add_custody(
                evidence_id,
                CustodyAction.VERIFIED,
                actor="integrity-verifier",
                description="Digest and custody verification passed",
                reference=report.checked_at,
            )
        return report

    def verify_all(
        self,
        *,
        manifest: EvidenceManifest | None = None,
        include_unavailable: bool = True,
    ) -> dict[str, Any]:
        """Verify all records and return reports plus aggregate counters."""
        reports: list[IntegrityReport] = []
        for record in self._repository.all_records():
            unavailable = bool(record.stored_path) and not self._blobs.exists(record.stored_path)
            if unavailable and not include_unavailable:
                continue
            reports.append(self.verify_record(record.id, manifest=manifest))
        return {
            "reports": [report.as_dict() for report in reports],
            "summary": report_summary(reports),
        }

    def verify_digest(self, data: bytes, *, expected_sha256: str = "") -> dict[str, Any]:
        """Compute and compare digests for raw bytes."""
        from redscribe.v2.evidence.hashing import digest_matches

        digests = hash_bytes(data)
        return {
            **digests.as_dict(),
            "expected_match": digest_matches(expected_sha256, digests.sha256)
            if expected_sha256
            else None,
        }

    # ------------------------------------------------------------------
    # Custody
    # ------------------------------------------------------------------

    def add_custody(
        self,
        evidence_id: str,
        action: CustodyAction,
        *,
        actor: str = "system",
        timestamp: str = "",
        description: str = "",
        location: str = "",
        reference: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> Any:
        """Append a custody event to an item's chain."""
        self.get_record(evidence_id)
        chain = CustodyChain(self._repository.custody_events())
        event = chain.append(
            evidence_id,
            action,
            actor=actor,
            timestamp=timestamp,
            description=description,
            location=location,
            reference=reference,
            metadata=metadata,
        )
        self._repository.save_custody_event(event)
        return event

    def list_custody(self, evidence_id: str = "") -> list[Any]:
        """Return custody events, optionally scoped to one item."""
        if evidence_id:
            self.get_record(evidence_id)
        return self._repository.custody_events(evidence_id)

    def custody_view(self, evidence_id: str) -> dict[str, Any]:
        """Return a UI-ready custody timeline and summary."""
        events = self.list_custody(evidence_id)
        valid, problems = CustodyChain(events).verify(evidence_id)
        return {
            "events": [event.as_dict() for event in events],
            "timeline": custody_timeline(events),
            "summary": custody_summary(events),
            "valid": valid,
            "problems": problems,
        }

    def verify_custody(self, evidence_id: str) -> tuple[bool, list[str]]:
        """Verify one item's custody chain."""
        return CustodyChain(self.list_custody(evidence_id)).verify(evidence_id)

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------

    def get_provenance(self, evidence_id: str) -> dict[str, Any]:
        """Return a UI-ready provenance view for one item."""
        record = self.get_record(evidence_id)
        payload = record.provenance.as_dict()
        payload["checklist"] = provenance_checklist(record.provenance)
        payload["summary"] = provenance_summary(record.provenance)
        payload["missing_fields"] = list(missing_provenance_fields(record.provenance))
        return payload

    def set_provenance(self, evidence_id: str, **changes: Any) -> dict[str, Any]:
        """Update provenance fields and return the normalized view."""
        from redscribe.v2.evidence.validation import now_iso

        record = self.get_record(evidence_id)
        updated_provenance = update_provenance(record.provenance, **changes)
        updated = replace(record, provenance=updated_provenance, updated_at=now_iso())
        self._repository.save_record(updated)
        return self.get_provenance(evidence_id)

    # ------------------------------------------------------------------
    # Finding links
    # ------------------------------------------------------------------

    def add_link(
        self,
        evidence_id: str,
        finding_id: str,
        **options: Any,
    ) -> FindingLink:
        """Create a typed link between evidence and a finding."""
        self.get_record(evidence_id)
        index = FindingLinkIndex(self._repository.all_links())
        link = index.add(evidence_id=evidence_id, finding_id=finding_id, **options)
        self._repository.save_link(link)
        return link

    def remove_link(self, link_id: int) -> bool:
        """Remove one finding link by id."""
        return self._repository.delete_link(link_id)

    def list_links(self, evidence_id: str = "", finding_id: str = "") -> list[FindingLink]:
        """Return finding links, optionally filtered."""
        links = self._repository.all_links()
        if evidence_id:
            links = [item for item in links if item.evidence_id == evidence_id]
        if finding_id:
            needle = finding_id.casefold()
            links = [item for item in links if item.finding_id.casefold() == needle]
        return links

    def links_view(self, evidence_id: str = "", finding_id: str = "") -> dict[str, Any]:
        """Return grouped and summarized finding links."""
        links = self.list_links(evidence_id, finding_id)
        return {
            "links": [item.as_dict() for item in links],
            "groups": group_by_type(links),
            "summary": link_summary(links),
        }

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    def get_retention(self, evidence_id: str, *, now: str = "") -> dict[str, Any]:
        """Return a detailed retention view for one item."""
        from redscribe.v2.evidence.retention import describe_policy

        self.get_record(evidence_id)
        policy = next(
            (item for item in self._repository.all_policies() if item.evidence_id == evidence_id),
            None,
        )
        if policy is None:
            return {"evidence_id": evidence_id, "policy": None, "decision": None}
        return {
            "evidence_id": evidence_id,
            "policy": policy.as_dict(),
            "decision": describe_policy(policy, now=now)["decision"],
        }

    def set_retention(self, evidence_id: str, **changes: Any) -> RetentionPolicy:
        """Create or update a retention policy."""
        from redscribe.v2.evidence.retention import build_policy, update_policy

        self.get_record(evidence_id)
        current = next(
            (item for item in self._repository.all_policies() if item.evidence_id == evidence_id),
            None,
        )
        if current is None:
            policy = build_policy(evidence_id, **changes)
        else:
            policy = update_policy(current, **changes)
        self._repository.save_policy(policy)
        return policy

    def set_hold(self, evidence_id: str, *, held: bool, reason: str = "") -> RetentionPolicy:
        """Apply or release a legal hold."""
        from redscribe.v2.evidence.retention import set_legal_hold

        current = self.get_retention(evidence_id)["policy"]
        if current is None:
            policy = self.set_retention(
                evidence_id,
                basis=RetentionBasis.LEGAL_HOLD if held else RetentionBasis.CASE,
                legal_hold=held,
                reason=reason,
            )
            return policy
        updated = set_legal_hold(RetentionPolicy.from_dict(current), held=held, reason=reason)
        self._repository.save_policy(updated)
        return updated

    def retention_plan(self, *, now: str = "") -> list[dict[str, Any]]:
        """Return disposition decisions for every policy."""
        from redscribe.v2.evidence.retention import evaluate_policy

        return [
            evaluate_policy(policy, now=now).as_dict() for policy in self._repository.all_policies()
        ]

    def apply_retention(
        self,
        *,
        now: str = "",
        destroy: bool = False,
        actor: str = "retention-manager",
    ) -> dict[str, Any]:
        """Apply due retention decisions, optionally disposing of evidence."""
        from redscribe.v2.evidence.retention import evaluate_policy

        decisions: list[dict[str, Any]] = []
        disposed: list[str] = []
        for policy in self._repository.all_policies():
            decision = evaluate_policy(policy, now=now)
            payload = decision.as_dict()
            if decision.action is DispositionAction.DESTROY and destroy:
                record = self._repository.get_record(policy.evidence_id)
                if record is not None:
                    self.set_status(
                        record.id,
                        EvidenceStatus.DISPOSED,
                        actor=actor,
                        description="Retention period expired",
                        force=True,
                    )
                    disposed.append(record.id)
            decisions.append(payload)
        return {"decisions": decisions, "disposed": disposed}

    # ------------------------------------------------------------------
    # Manifests
    # ------------------------------------------------------------------

    def export_manifest(self, *, case_reference: str = "") -> EvidenceManifest:
        """Build and persist a manifest of the current vault state."""
        manifest = build_manifest(
            self._repository.all_records(),
            custody=self._repository.custody_events(),
            links=self._repository.all_links(),
            retention=self._repository.all_policies(),
            case_reference=case_reference or self._case_reference,
            generator=self._generator,
        )
        self._repository.save_manifest(manifest)
        return manifest

    def manifest_json(self, *, case_reference: str = "") -> str:
        """Return the current manifest as pretty-printed JSON."""
        from redscribe.v2.evidence.manifests import manifest_to_json

        return manifest_to_json(self.export_manifest(case_reference=case_reference))

    def preview_import(
        self,
        payload: Mapping[str, Any] | str,
        *,
        strategy: str = "skip",
    ) -> dict[str, Any]:
        """Parse a manifest and preview its import without changing state."""
        manifest = parse_manifest(payload)
        valid, problems = validate_manifest(manifest)
        plan = plan_import(manifest, self.record_ids(), strategy=strategy)
        return {
            "manifest": manifest.as_dict(),
            "valid": valid,
            "problems": problems,
            "plan": plan.as_dict(),
        }

    def import_manifest(
        self,
        payload: Mapping[str, Any] | str,
        *,
        strategy: str = "skip",
        actor: str = "manifest-import",
    ) -> dict[str, Any]:
        """Import records and metadata from a validated manifest."""
        manifest = parse_manifest(payload)
        valid, problems = validate_manifest(manifest)
        if not valid:
            raise ManifestError("Manifest failed validation", details={"problems": problems})
        plan = plan_import(manifest, self.record_ids(), strategy=strategy)
        if plan.conflicts:
            raise ConflictError(
                "Manifest contains ids that require explicit renaming",
                details={"conflicts": list(plan.conflicts)},
            )
        from redscribe.v2.evidence.validation import now_iso

        id_map: dict[str, str] = {}
        created: list[str] = []
        updated: list[str] = []
        for evidence_id in list(plan.create) + list(plan.update):
            source = next(
                (item for item in manifest.records if str(item.get("id")) == evidence_id),
                None,
            )
            if source is None:
                continue
            payload_record = dict(source)
            self._repository.save_record(EvidenceRecord.from_dict(payload_record))
            if evidence_id in plan.create:
                created.append(evidence_id)
                id_map[evidence_id] = evidence_id
            else:
                updated.append(evidence_id)
                id_map[evidence_id] = evidence_id
        for event in custody_by_evidence(manifest).values():
            for raw in event:
                evidence_id = str(raw.get("evidence_id", ""))
                if evidence_id not in id_map:
                    continue
                from redscribe.v2.evidence.models import CustodyEvent

                original = CustodyEvent.from_dict(raw)
                self.add_custody(
                    id_map[evidence_id],
                    original.action,
                    actor=original.actor or actor,
                    timestamp=original.timestamp,
                    description=original.description,
                    location=original.location,
                    reference=original.reference,
                    metadata=original.metadata,
                )
        for raw_list in links_by_evidence(manifest).values():
            for raw in raw_list:
                source_id = str(raw.get("evidence_id", ""))
                if source_id not in id_map:
                    continue
                try:
                    self.add_link(
                        id_map[source_id],
                        str(raw.get("finding_id", "")),
                        finding_title=str(raw.get("finding_title", "")),
                        link_type=LinkType(str(raw.get("link_type", "related_to"))),
                        strength=float(raw.get("strength", 0.5)),
                        created_by=str(raw.get("created_by", actor)),
                        created_at=str(raw.get("created_at", "")),
                        note=str(raw.get("note", "")),
                        allow_duplicate=True,
                    )
                except ValidationError:
                    continue
        for evidence_id, raw in retention_by_evidence(manifest).items():
            if evidence_id not in id_map:
                continue
            policy_data = dict(raw)
            policy_data.pop("evidence_id", None)
            self.set_retention(id_map[evidence_id], **policy_data)
        if created:
            for evidence_id in created:
                self.add_custody(
                    evidence_id,
                    CustodyAction.IMPORTED,
                    actor=actor,
                    description="Evidence imported from manifest",
                    reference=manifest.checksum[:16],
                )
        self._repository.save_manifest(manifest)
        return {
            "plan": plan.as_dict(),
            "created": created,
            "updated": updated,
            "skipped": list(plan.skip),
            "warnings": list(plan.warnings),
            "checksum": manifest.checksum,
            "imported_at": now_iso(),
        }

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def stats(self) -> EvidenceStats:
        """Return aggregate counters for the evidence vault."""
        records = self._repository.all_records()
        by_status: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        verified = 0
        alerts = 0
        for record in records:
            by_status[record.status.value] = by_status.get(record.status.value, 0) + 1
            by_kind[record.kind.value] = by_kind.get(record.kind.value, 0) + 1
            if record.status is EvidenceStatus.VERIFIED:
                verified += 1
        for report in self.verify_all()["reports"]:
            if IntegrityReport.from_dict(report).state in {
                IntegrityState.MISMATCH,
                IntegrityState.ERROR,
            }:
                alerts += 1
        policies = self._repository.all_policies()
        return EvidenceStats(
            total=len(records),
            by_status=dict(sorted(by_status.items())),
            by_kind=dict(sorted(by_kind.items())),
            total_bytes=sum(record.size_bytes for record in records),
            verified=verified,
            alerts=alerts,
            custody_events=len(self._repository.custody_events()),
            links=len(self._repository.all_links()),
            legal_holds=sum(1 for policy in policies if policy.legal_hold),
        )

    def detail(self, evidence_id: str) -> dict[str, Any]:
        """Return a composite detail payload for the UI."""
        record = self.get_record(evidence_id)
        return {
            "record": record.detail(),
            "integrity": self.verify_record(evidence_id).as_dict(),
            "custody": self.custody_view(evidence_id),
            "provenance": self.get_provenance(evidence_id),
            "links": self.links_view(evidence_id=evidence_id),
            "retention": self.get_retention(evidence_id),
            "badge": integrity_badge(self.verify_record(evidence_id)),
        }

    def list_view(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        **filters: Any,
    ) -> dict[str, Any]:
        """Return a composite list payload with integrity badges."""
        records, page = self.list_page(offset=offset, limit=limit, **filters)
        manifest = self._repository.all_manifests()
        entries = entries_by_hash(manifest[-1]) if manifest else {}
        items: list[dict[str, Any]] = []
        for record in records:
            summary = record.summary()
            data: object = UNSET
            if record.stored_path:
                data = self._blobs.get(record.stored_path)
            report = self._verifier.verify_record(
                record,
                data=data,
                custody=self._repository.custody_events(record.id),
                manifest=next(
                    (
                        entry
                        for entry in (manifest[-1].entries if manifest else ())
                        if entry.evidence_id == record.id
                    ),
                    None,
                ),
            )
            summary["integrity"] = integrity_badge(report)
            summary["digest_index"] = entries.get(record.sha256, "")
            items.append(summary)
        return {"items": items, "page": page}


def create_service(
    source: Any | None = None,
    *,
    storage_root: str | Path | None = None,
    **options: Any,
) -> EvidenceVaultService:
    """Create a service with repository and blob storage wired together."""
    from redscribe.v2.evidence.repositories import build_repository

    repository = build_repository(source)
    blobs: BlobStore | None = DirectoryBlobStore(storage_root) if storage_root is not None else None
    return EvidenceVaultService(repository, blobs, **options)
