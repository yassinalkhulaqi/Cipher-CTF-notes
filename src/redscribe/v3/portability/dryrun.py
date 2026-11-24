"""Dry-run planning for bundle creation, import, and three-way merges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v3.entities.types import EntityLink as V3EntityLink
from redscribe.v3.portability.merge import Conflict, MergeResult, merge_families
from redscribe.v3.portability.records import PortableEntity
from redscribe.v3.portability.vectors import VectorRelation, VersionVector

CHANGE_ACTIONS: tuple[str, ...] = ("create", "update", "delete", "unchanged")


@dataclass(frozen=True, slots=True)
class ChangePreview:
    """One prospective change shown in the dry-run preview."""

    ref: str
    action: str
    family: str
    title: str
    fields: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ref": self.ref,
            "action": self.action,
            "family": self.family,
            "title": self.title,
            "fields": list(self.fields),
        }


@dataclass(frozen=True, slots=True)
class DryRunReport:
    """A complete, non-mutating preview of a portability operation."""

    operation: str
    valid: bool
    headline: str
    changes: tuple[ChangePreview, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    warnings: tuple[str, ...] = ()
    counts: dict[str, int] | None = None

    def summary(self) -> dict[str, int]:
        """Return aggregate counters for the report."""
        counts: dict[str, int] = dict.fromkeys(CHANGE_ACTIONS, 0)
        for change in self.changes:
            counts[change.action] = counts.get(change.action, 0) + 1
        counts["conflicts"] = len(self.conflicts)
        counts["warnings"] = len(self.warnings)
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "operation": self.operation,
            "valid": self.valid,
            "headline": self.headline,
            "changes": [change.as_dict() for change in self.changes],
            "conflicts": [conflict.as_dict() for conflict in self.conflicts],
            "warnings": list(self.warnings),
            "counts": self.counts or self.summary(),
        }


def _changed_fields(base: PortableEntity | None, entity: PortableEntity) -> tuple[str, ...]:
    """Return field names that differ from a base snapshot."""
    if base is None:
        return ("entity",)
    fields = (
        "title",
        "summary",
        "status",
        "tags",
        "body",
        "deleted",
    )
    before = base.field_values()
    after = entity.field_values()
    return tuple(name for name in fields if before.get(name) != after.get(name))


def preview_merge(
    result: MergeResult,
    *,
    operation: str = "merge",
    warnings: tuple[str, ...] = (),
) -> DryRunReport:
    """Turn a merge result into a human-readable dry-run report."""
    changes: list[ChangePreview] = []
    for ref in result.applied:
        entity = next((item for item in result.entities if item.ref == ref), None)
        if entity is None:
            continue
        changes.append(
            ChangePreview(
                ref=ref,
                action="update",
                family=entity.family,
                title=entity.title,
                fields=_changed_fields(None, entity),
            )
        )
    for ref in result.unchanged:
        changes.append(
            ChangePreview(ref=ref, action="unchanged", family="entity", title=ref.split(":")[-1])
        )
    for conflict in result.conflicts:
        changes.append(
            ChangePreview(
                ref=conflict.ref,
                action="update",
                family=conflict.family,
                title=conflict.ref.split(":")[-1],
                fields=tuple(diff.field for diff in conflict.fields),
            )
        )
    counts = result.counts()
    counts["changes"] = len(changes)
    valid = result.clean and not any("MISMATCH" in warning for warning in warnings)
    headline = (
        f"{counts['entities']} entities ready, {counts['conflicts']} conflicts"
        if counts["conflicts"]
        else f"{counts['entities']} entities ready to import"
    )
    return DryRunReport(
        operation=operation,
        valid=valid,
        headline=headline,
        changes=tuple(changes),
        conflicts=result.conflicts,
        warnings=warnings,
        counts=counts,
    )


def plan_import(
    base: tuple[PortableEntity, ...],
    local: tuple[PortableEntity, ...],
    remote: tuple[PortableEntity, ...],
    *,
    base_links: tuple[V3EntityLink, ...] = (),
    local_links: tuple[V3EntityLink, ...] = (),
    remote_links: tuple[V3EntityLink, ...] = (),
    base_vector: VersionVector | None = None,
    local_vector: VersionVector | None = None,
    remote_vector: VersionVector | None = None,
    families: tuple[str, ...] = (),
) -> tuple[DryRunReport, MergeResult]:
    """Preview an imported bundle against the local vault without mutating it."""
    warnings: list[str] = []
    ancestor = base_vector or VersionVector.empty()
    ours = local_vector or VersionVector.empty()
    theirs = remote_vector or VersionVector.empty()
    relation = theirs.compare(ours)
    if relation is VectorRelation.CONCURRENT:
        warnings.append("Both vaults contain independent edits")
    if not theirs.dominates(ancestor):
        warnings.append("Incoming vector does not include the common ancestor")
    if not ours.dominates(ancestor):
        warnings.append("Local vector does not include the common ancestor")
    result = merge_families(
        base,
        local,
        remote,
        base_links=base_links,
        local_links=local_links,
        remote_links=remote_links,
        families=families,
    )
    report = preview_merge(result, operation="import", warnings=tuple(warnings))
    return report, result


def plan_bundle_create(
    entities: tuple[PortableEntity, ...],
    links: tuple[V3EntityLink, ...] = (),
) -> DryRunReport:
    """Preview what a bundle export would contain."""
    families: dict[str, int] = {}
    for entity in entities:
        families[entity.family] = families.get(entity.family, 0) + 1
    changes = tuple(
        ChangePreview(ref=entity.ref, action="unchanged", family=entity.family, title=entity.title)
        for entity in entities
    )
    counts = {
        "entities": len(entities),
        "links": len(links),
        "families": len(families),
        "changes": len(changes),
        "conflicts": 0,
    }
    headline = f"Bundle will contain {len(entities)} entities across {len(families)} families"
    return DryRunReport(
        operation="bundle.create",
        valid=True,
        headline=headline,
        changes=changes,
        counts=counts,
    )


def filter_changes(report: DryRunReport, *, action: str = "") -> tuple[ChangePreview, ...]:
    """Filter preview changes by action."""
    if not action:
        return report.changes
    return tuple(change for change in report.changes if change.action == action)
