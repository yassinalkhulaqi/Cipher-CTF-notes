"""Evidence manifest export, validation, comparison, and import planning."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from redscribe.v2.evidence.errors import ManifestError
from redscribe.v2.evidence.hashing import canonical_digest, canonical_json
from redscribe.v2.evidence.models import (
    CustodyEvent,
    EvidenceManifest,
    EvidenceRecord,
    FindingLink,
    ImportPlan,
    ManifestEntry,
    ManifestFormat,
    RetentionPolicy,
)
from redscribe.v2.evidence.validation import normalize_timestamp, now_iso

MANIFEST_VERSION = 1
SUPPORTED_STRATEGIES = ("skip", "overwrite", "rename")
GENERATOR = "redscribe-evidence-vault"


def entry_from_record(record: EvidenceRecord) -> ManifestEntry:
    """Build a manifest entry from an evidence record."""
    return ManifestEntry(
        evidence_id=record.id,
        filename=record.original_filename,
        sha256=record.sha256,
        md5=record.md5,
        size_bytes=record.size_bytes,
        stored_path=record.stored_path,
        kind=record.kind.value,
        status=record.status.value,
    )


def entries_from_records(records: Iterable[EvidenceRecord]) -> tuple[ManifestEntry, ...]:
    """Build manifest entries for a collection of records."""
    return tuple(entry_from_record(record) for record in sorted(records, key=lambda item: item.id))


def build_manifest(
    records: Iterable[EvidenceRecord],
    *,
    custody: Iterable[CustodyEvent] = (),
    links: Iterable[FindingLink] = (),
    retention: Iterable[RetentionPolicy] = (),
    case_reference: str = "",
    generated_at: str = "",
    generator: str = GENERATOR,
) -> EvidenceManifest:
    """Build a checksummed manifest from repository state."""
    ordered_records = sorted(records, key=lambda item: item.id)
    body: dict[str, Any] = {
        "format": ManifestFormat.JSON.value,
        "version": MANIFEST_VERSION,
        "generated_at": normalize_timestamp(generated_at, default=now_iso()),
        "generator": generator,
        "case_reference": case_reference.strip()[:120],
        "records": [record.as_dict() for record in ordered_records],
        "entries": [entry.as_dict() for entry in entries_from_records(ordered_records)],
        "custody": [event.as_dict() for event in sorted(custody, key=lambda item: item.id)],
        "links": [link.as_dict() for link in sorted(links, key=lambda item: item.id)],
        "retention": [
            policy.as_dict() for policy in sorted(retention, key=lambda item: item.evidence_id)
        ],
    }
    return EvidenceManifest(
        version=MANIFEST_VERSION,
        generated_at=body["generated_at"],
        generator=generator,
        case_reference=body["case_reference"],
        records=tuple(body["records"]),
        entries=tuple(ManifestEntry.from_dict(item) for item in body["entries"]),
        custody=tuple(body["custody"]),
        links=tuple(body["links"]),
        retention=tuple(body["retention"]),
        checksum=canonical_digest(body),
    )


def manifest_body(manifest: EvidenceManifest) -> dict[str, Any]:
    """Return the checksummed body of a manifest."""
    payload = manifest.as_dict()
    payload.pop("checksum", None)
    return payload


def verify_manifest_checksum(manifest: EvidenceManifest) -> bool:
    """Return whether a manifest checksum matches its body."""
    return canonical_digest(manifest_body(manifest)) == manifest.checksum


def parse_manifest(value: Mapping[str, Any] | str) -> EvidenceManifest:
    """Parse and validate a manifest from a mapping or JSON string."""
    if isinstance(value, str):
        try:
            payload: object = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ManifestError("Manifest is not valid JSON") from exc
    else:
        payload = value
    if not isinstance(payload, Mapping):
        raise ManifestError("Manifest must be an object")
    manifest = EvidenceManifest.from_dict(payload)
    if manifest.version != MANIFEST_VERSION:
        raise ManifestError(
            f"Unsupported manifest version: {manifest.version}",
            details={"version": manifest.version},
        )
    if not verify_manifest_checksum(manifest):
        raise ManifestError("Manifest checksum does not match its contents")
    return manifest


def manifest_to_json(manifest: EvidenceManifest, *, indent: int = 2) -> str:
    """Serialize a manifest as canonical JSON."""
    return json.dumps(manifest.as_dict(), indent=indent, ensure_ascii=False, sort_keys=True)


def manifest_from_json(text: str) -> EvidenceManifest:
    """Parse a manifest from a JSON string."""
    return parse_manifest(text)


def manifest_to_jsonl(manifest: EvidenceManifest) -> str:
    """Serialize a manifest as newline-delimited sections."""
    sections = [
        {"section": "header", "payload": manifest_body(manifest)},
        {"section": "checksum", "payload": {"checksum": manifest.checksum}},
    ]
    return "\n".join(canonical_json(section) for section in sections) + "\n"


def validate_manifest(manifest: EvidenceManifest) -> tuple[bool, list[str]]:
    """Run structural validation checks on a manifest."""
    problems: list[str] = []
    if manifest.version != MANIFEST_VERSION:
        problems.append(f"Unsupported version {manifest.version}")
    if not verify_manifest_checksum(manifest):
        problems.append("Checksum mismatch")
    ids = {entry.evidence_id for entry in manifest.entries}
    if len(ids) != len(manifest.entries):
        problems.append("Duplicate evidence ids in manifest entries")
    record_ids = {str(item.get("id", "")) for item in manifest.records}
    if ids != record_ids:
        problems.append("Manifest entries and records describe different evidence ids")
    for entry in manifest.entries:
        if len(entry.sha256) != 64:
            problems.append(f"Invalid SHA-256 for {entry.evidence_id}")
        if len(entry.md5) != 32:
            problems.append(f"Invalid MD5 for {entry.evidence_id}")
        if entry.size_bytes < 0:
            problems.append(f"Negative size for {entry.evidence_id}")
    return not problems, problems


def compare_manifests(
    current: EvidenceManifest,
    incoming: EvidenceManifest,
) -> dict[str, Any]:
    """Compare two manifests by evidence id and digest."""
    current_entries = {entry.evidence_id: entry for entry in current.entries}
    incoming_entries = {entry.evidence_id: entry for entry in incoming.entries}
    added = sorted(set(incoming_entries) - set(current_entries))
    removed = sorted(set(current_entries) - set(incoming_entries))
    changed: list[str] = []
    for evidence_id in sorted(set(current_entries) & set(incoming_entries)):
        left = current_entries[evidence_id]
        right = incoming_entries[evidence_id]
        if (
            left.sha256 != right.sha256
            or left.md5 != right.md5
            or left.size_bytes != right.size_bytes
            or left.status != right.status
        ):
            changed.append(evidence_id)
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "identical": not (added or removed or changed),
        "current_count": len(current_entries),
        "incoming_count": len(incoming_entries),
    }


def plan_import(
    manifest: EvidenceManifest,
    existing_ids: Iterable[str],
    *,
    strategy: str = "skip",
) -> ImportPlan:
    """Decide which manifest records should be created, updated, or skipped."""
    if strategy not in SUPPORTED_STRATEGIES:
        raise ManifestError(
            f"Unsupported import strategy: {strategy}",
            details={"strategy": strategy},
        )
    existing = set(existing_ids)
    incoming = {entry.evidence_id for entry in manifest.entries}
    create = sorted(incoming - existing)
    overlap = sorted(incoming & existing)
    conflicts: list[str] = []
    warnings: list[str] = []
    if strategy == "skip":
        skip = overlap
        update: list[str] = []
    elif strategy == "overwrite":
        skip = []
        update = overlap
    else:
        skip = []
        update = []
        conflicts = list(overlap)
        warnings.append("Rename strategy requires explicit id mapping for each conflict")
    if not manifest.generator:
        warnings.append("Manifest has no generator metadata")
    if not manifest.case_reference:
        warnings.append("Manifest has no case reference")
    return ImportPlan(
        strategy=strategy,
        create=tuple(create),
        update=tuple(update),
        skip=tuple(skip),
        conflicts=tuple(conflicts),
        warnings=tuple(warnings),
    )


def manifest_stats(manifest: EvidenceManifest) -> dict[str, Any]:
    """Return aggregate counters for a manifest."""
    total_bytes = sum(entry.size_bytes for entry in manifest.entries)
    kinds: dict[str, int] = {}
    for entry in manifest.entries:
        kinds[entry.kind] = kinds.get(entry.kind, 0) + 1
    return {
        "records": len(manifest.records),
        "entries": len(manifest.entries),
        "custody_events": len(manifest.custody),
        "links": len(manifest.links),
        "retention_policies": len(manifest.retention),
        "total_bytes": total_bytes,
        "kinds": dict(sorted(kinds.items())),
        "checksum": manifest.checksum,
    }


def entries_by_hash(manifest: EvidenceManifest) -> dict[str, str]:
    """Index manifest entries by both supported digest algorithms."""
    index: dict[str, str] = {}
    for entry in manifest.entries:
        index[entry.sha256] = entry.evidence_id
        index[entry.md5] = entry.evidence_id
    return index


def custody_by_evidence(manifest: EvidenceManifest) -> dict[str, list[dict[str, Any]]]:
    """Group manifest custody events by evidence id."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in manifest.custody:
        evidence_id = str(event.get("evidence_id", ""))
        if evidence_id:
            groups.setdefault(evidence_id, []).append(dict(event))
    return groups


def links_by_evidence(manifest: EvidenceManifest) -> dict[str, list[dict[str, Any]]]:
    """Group manifest finding links by evidence id."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for link in manifest.links:
        evidence_id = str(link.get("evidence_id", ""))
        if evidence_id:
            groups.setdefault(evidence_id, []).append(dict(link))
    return groups


def retention_by_evidence(manifest: EvidenceManifest) -> dict[str, dict[str, Any]]:
    """Index manifest retention policies by evidence id."""
    return {
        str(policy.get("evidence_id", "")): dict(policy)
        for policy in manifest.retention
        if policy.get("evidence_id")
    }


def merge_manifests(manifests: Sequence[EvidenceManifest]) -> EvidenceManifest:
    """Merge manifests into one snapshot, preferring later generated data."""
    if not manifests:
        return build_manifest([])
    ordered = sorted(manifests, key=lambda item: item.generated_at)
    records: dict[str, dict[str, Any]] = {}
    entries: dict[str, ManifestEntry] = {}
    custody: dict[int, dict[str, Any]] = {}
    links: dict[int, dict[str, Any]] = {}
    policies: dict[str, dict[str, Any]] = {}
    for manifest in ordered:
        for record in manifest.records:
            records[str(record.get("id", ""))] = dict(record)
        for entry in manifest.entries:
            entries[entry.evidence_id] = entry
        for event in manifest.custody:
            custody[int(event.get("id", 0))] = dict(event)
        for link in manifest.links:
            links[int(link.get("id", 0))] = dict(link)
        for policy in manifest.retention:
            policies[str(policy.get("evidence_id", ""))] = dict(policy)
    latest = ordered[-1]
    return build_manifest(
        [EvidenceRecord.from_dict(item) for item in records.values() if item.get("id")],
        custody=[CustodyEvent.from_dict(item) for item in custody.values()],
        links=[FindingLink.from_dict(item) for item in links.values()],
        retention=[RetentionPolicy.from_dict(item) for item in policies.values()],
        case_reference=latest.case_reference,
        generated_at=latest.generated_at,
        generator=latest.generator,
    )
