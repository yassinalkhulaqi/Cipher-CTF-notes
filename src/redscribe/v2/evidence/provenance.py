"""Acquisition provenance construction, review, and comparison."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v2.evidence.errors import ValidationError
from redscribe.v2.evidence.models import AcquisitionMethod, AcquisitionProvenance
from redscribe.v2.evidence.validation import (
    normalize_tags,
    normalize_timestamp,
    now_iso,
    validate_case_reference,
)

PROVENANCE_FIELDS: tuple[str, ...] = (
    "method",
    "tool",
    "tool_version",
    "operator",
    "source_path",
    "source_description",
    "acquired_at",
    "case_reference",
    "witness",
    "image_number",
    "notes",
)

UNSET: object = object()

FIELD_LABELS: dict[str, str] = {
    "method": "Acquisition method",
    "tool": "Tool",
    "tool_version": "Tool version",
    "operator": "Operator",
    "source_path": "Source path",
    "source_description": "Source description",
    "acquired_at": "Acquired at",
    "case_reference": "Case reference",
    "witness": "Witness",
    "image_number": "Image number",
    "notes": "Notes",
}


def empty_provenance(evidence_id: str) -> AcquisitionProvenance:
    """Return a provenance record with only its identity populated."""
    return AcquisitionProvenance(
        evidence_id=evidence_id,
        method=AcquisitionMethod.MANUAL_UPLOAD,
        tool="redscribe",
        tool_version="",
        operator="",
        source_path="",
        source_description="",
        acquired_at="",
        case_reference="",
        witness="",
        image_number=0,
        notes="",
    )


def from_acquisition(
    evidence_id: str,
    *,
    method: AcquisitionMethod = AcquisitionMethod.MANUAL_UPLOAD,
    tool: str = "redscribe",
    tool_version: str = "",
    operator: str = "",
    source_path: str = "",
    source_description: str = "",
    acquired_at: str = "",
    case_reference: str = "",
    witness: str = "",
    image_number: int = 0,
    notes: str = "",
) -> AcquisitionProvenance:
    """Build a validated provenance record from acquisition inputs."""
    return AcquisitionProvenance(
        evidence_id=evidence_id,
        method=method,
        tool=tool.strip()[:120] or "redscribe",
        tool_version=tool_version.strip()[:60],
        operator=operator.strip()[:120],
        source_path=source_path.strip()[:500],
        source_description=source_description.strip()[:1_000],
        acquired_at=normalize_timestamp(acquired_at, default=now_iso()),
        case_reference=validate_case_reference(case_reference),
        witness=witness.strip()[:120],
        image_number=max(0, min(image_number, 99_999)),
        notes=notes.strip()[:2_000],
    )


def update_provenance(
    provenance: AcquisitionProvenance,
    *,
    method: object = UNSET,
    tool: object = UNSET,
    tool_version: object = UNSET,
    operator: object = UNSET,
    source_path: object = UNSET,
    source_description: object = UNSET,
    acquired_at: object = UNSET,
    case_reference: object = UNSET,
    witness: object = UNSET,
    image_number: object = UNSET,
    notes: object = UNSET,
) -> AcquisitionProvenance:
    """Return a provenance record with bounded field updates applied."""
    payload = provenance.as_dict()
    if method is not UNSET:
        if not isinstance(method, AcquisitionMethod):
            raise ValidationError(
                "'method' must be an acquisition method", details={"field": "method"}
            )
        payload["method"] = method.value
    text_fields: dict[str, object] = {
        "tool": tool,
        "tool_version": tool_version,
        "operator": operator,
        "source_path": source_path,
        "source_description": source_description,
        "case_reference": case_reference,
        "witness": witness,
        "notes": notes,
    }
    for name, value in text_fields.items():
        if value is UNSET:
            continue
        if value is None:
            payload[name] = ""
            continue
        if not isinstance(value, str):
            raise ValidationError(f"'{name}' must be a string", details={"field": name})
        limit = 2_000 if name == "notes" else (1_000 if name == "source_description" else 500)
        payload[name] = value.strip()[:limit]
    if acquired_at is not UNSET:
        if acquired_at is None:
            payload["acquired_at"] = ""
        elif isinstance(acquired_at, str):
            payload["acquired_at"] = normalize_timestamp(acquired_at)
        else:
            raise ValidationError(
                "'acquired_at' must be a string", details={"field": "acquired_at"}
            )
    if image_number is not UNSET:
        if isinstance(image_number, bool) or not isinstance(image_number, int):
            raise ValidationError(
                "'image_number' must be an integer", details={"field": "image_number"}
            )
        payload["image_number"] = max(0, min(image_number, 99_999))
    return AcquisitionProvenance.from_dict(payload)


def merge_provenance(
    base: AcquisitionProvenance,
    override: AcquisitionProvenance,
) -> AcquisitionProvenance:
    """Fill blank fields in ``base`` from ``override`` without overwriting data."""
    payload = base.as_dict()
    incoming = override.as_dict()
    for name in PROVENANCE_FIELDS:
        current = payload.get(name)
        if current in ("", 0, None) and incoming.get(name) not in ("", 0, None):
            payload[name] = incoming[name]
    return AcquisitionProvenance.from_dict(payload)


def provenance_checklist(provenance: AcquisitionProvenance) -> list[dict[str, Any]]:
    """Return a field-by-field review checklist for the UI."""
    values = provenance.as_dict()
    checklist: list[dict[str, Any]] = []
    for name in PROVENANCE_FIELDS:
        value = values.get(name)
        filled = bool(value) and value != 0
        checklist.append(
            {
                "field": name,
                "label": FIELD_LABELS[name],
                "filled": filled,
                "value": "" if value is None else str(value),
            }
        )
    return checklist


def missing_provenance_fields(provenance: AcquisitionProvenance) -> tuple[str, ...]:
    """Return the names of provenance fields that still need input."""
    return tuple(item["field"] for item in provenance_checklist(provenance) if not item["filled"])


def validate_provenance(provenance: AcquisitionProvenance) -> None:
    """Raise when required provenance fields are structurally invalid."""
    if not provenance.evidence_id:
        raise ValidationError(
            "Provenance requires an evidence id", details={"field": "evidence_id"}
        )
    if provenance.image_number < 0:
        raise ValidationError("Image number cannot be negative", details={"field": "image_number"})
    if provenance.acquired_at and not normalize_timestamp(provenance.acquired_at):
        raise ValidationError("Invalid acquisition timestamp", details={"field": "acquired_at"})


def compare_provenance(
    left: AcquisitionProvenance,
    right: AcquisitionProvenance,
) -> dict[str, Any]:
    """Report provenance field differences between two records."""
    left_values = left.as_dict()
    right_values = right.as_dict()
    changed = [
        name for name in PROVENANCE_FIELDS if left_values.get(name) != right_values.get(name)
    ]
    return {
        "changed": changed,
        "count": len(changed),
        "identical": not changed,
    }


def provenance_tags(provenance: AcquisitionProvenance) -> tuple[str, ...]:
    """Build UI tags describing how an item was acquired."""
    tags = [provenance.method.value, provenance.tool]
    if provenance.witness:
        tags.append("witnessed")
    if provenance.case_reference:
        tags.append(provenance.case_reference)
    if provenance.image_number:
        tags.append(f"image-{provenance.image_number}")
    return normalize_tags(tags)


def provenance_summary(provenance: AcquisitionProvenance) -> dict[str, Any]:
    """Return a compact provenance view for list and detail responses."""
    return {
        "method": provenance.method.value,
        "tool": provenance.tool,
        "tool_version": provenance.tool_version,
        "operator": provenance.operator,
        "source_path": provenance.source_path,
        "acquired_at": provenance.acquired_at,
        "case_reference": provenance.case_reference,
        "witness": provenance.witness,
        "image_number": provenance.image_number,
        "completeness": provenance.completeness(),
        "missing_fields": list(missing_provenance_fields(provenance)),
    }


def acquisition_timeline(records: Sequence[AcquisitionProvenance]) -> list[dict[str, Any]]:
    """Return acquisition events ordered by timestamp."""
    entries = [
        {
            "evidence_id": item.evidence_id,
            "timestamp": item.acquired_at,
            "method": item.method.value,
            "operator": item.operator,
            "source_path": item.source_path,
        }
        for item in records
        if item.acquired_at
    ]
    return sorted(entries, key=lambda item: item["timestamp"])


def provenance_from_manifest(value: Mapping[str, Any]) -> AcquisitionProvenance:
    """Parse provenance from a manifest mapping."""
    return AcquisitionProvenance.from_dict(value)
