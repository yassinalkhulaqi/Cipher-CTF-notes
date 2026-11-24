"""Three-way merge for entity families with explained conflict reason codes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.entities.types import EntityLink as V3EntityLink
from redscribe.v3.portability.errors import BundleError, MergeError, ResolutionError
from redscribe.v3.portability.records import PortableEntity, link_as_dict
from redscribe.v3.portability.vectors import VersionVector

MERGE_FIELDS: tuple[str, ...] = ("title", "summary", "status", "tags", "body", "deleted")


class ConflictReason(str, Enum):
    """Stable reason codes explaining why a merge needs a decision."""

    FIELD_BOTH_EDITED = "field_both_edited"
    DELETE_MODIFY = "delete_modify"
    CONCURRENT_ADD = "concurrent_add"
    TAG_SET_DIVERGENCE = "tag_set_divergence"
    CONTENT_DIVERGENCE = "content_divergence"
    LINK_TARGET_MISSING = "link_target_missing"
    VECTOR_REGRESSION = "vector_regression"
    SCHEMA_MISMATCH = "schema_mismatch"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    UNKNOWN_FIELD = "unknown_field"

    @property
    def description(self) -> str:
        """Human-readable explanation for the conflict workbench."""
        return {
            ConflictReason.FIELD_BOTH_EDITED: "Both devices edited the same field.",
            ConflictReason.DELETE_MODIFY: "One device deleted a record the other edited.",
            ConflictReason.CONCURRENT_ADD: "Both devices created a record with the same id.",
            ConflictReason.TAG_SET_DIVERGENCE: "Both devices changed the tag set differently.",
            ConflictReason.CONTENT_DIVERGENCE: "Both devices edited the note body.",
            ConflictReason.LINK_TARGET_MISSING: "A link points at an entity not in the merge.",
            ConflictReason.VECTOR_REGRESSION: "An incoming vector does not include known history.",
            ConflictReason.SCHEMA_MISMATCH: "The bundle schema is not compatible.",
            ConflictReason.CHECKSUM_MISMATCH: "A record checksum does not match its manifest.",
            ConflictReason.UNKNOWN_FIELD: "A payload contains an unrecognized merge field.",
        }[self]

    @property
    def severity(self) -> str:
        """Suggested UI severity for the reason."""
        if self in (ConflictReason.DELETE_MODIFY, ConflictReason.CONCURRENT_ADD):
            return "critical"
        if self in (ConflictReason.CHECKSUM_MISMATCH, ConflictReason.SCHEMA_MISMATCH):
            return "warning"
        return "error"


class ResolutionStrategy(str, Enum):
    """Default strategy applied when an automatic merge cannot decide."""

    MANUAL = "manual"
    KEEP_LOCAL = "keep_local"
    KEEP_REMOTE = "keep_remote"
    MERGE_FIELDS = "merge_fields"
    SKIP = "skip"


class ResolutionChoice(str, Enum):
    """Concrete decision recorded for one conflict."""

    MANUAL = "manual"
    KEEP_LOCAL = "keep_local"
    KEEP_REMOTE = "keep_remote"
    MERGE_FIELDS = "merge_fields"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class FieldDiff:
    """A per-field comparison used by the side-by-side conflict diff."""

    field: str
    base: Any
    local: Any
    remote: Any
    local_changed: bool
    remote_changed: bool

    @property
    def overlap(self) -> bool:
        """Whether both sides changed the same field."""
        return self.local_changed and self.remote_changed

    @property
    def chosen(self) -> Any:
        """Return the automatically preferred value, if unambiguous."""
        if self.local_changed and not self.remote_changed:
            return self.local
        if self.remote_changed and not self.local_changed:
            return self.remote
        return self.base

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "field": self.field,
            "base": self.base,
            "local": self.local,
            "remote": self.remote,
            "local_changed": self.local_changed,
            "remote_changed": self.remote_changed,
            "overlap": self.overlap,
        }


@dataclass(frozen=True, slots=True)
class Conflict:
    """One unexplained difference that requires a recorded decision."""

    ref: str
    family: str
    reason: ConflictReason
    fields: tuple[FieldDiff, ...] = ()
    base: dict[str, Any] | None = None
    local: dict[str, Any] | None = None
    remote: dict[str, Any] | None = None
    suggestion: ResolutionChoice = ResolutionChoice.MANUAL
    detail: str = ""

    @property
    def severity(self) -> str:
        """Severity hint for conflict workbench rendering."""
        return self.reason.severity

    @property
    def message(self) -> str:
        """Reason description prefixed with the affected reference."""
        return f"{self.ref}: {self.reason.description}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for the API and conflict UI."""
        return {
            "ref": self.ref,
            "family": self.family,
            "reason": self.reason.value,
            "reason_description": self.reason.description,
            "severity": self.reason.severity,
            "message": self.message,
            "fields": [item.as_dict() for item in self.fields],
            "base": self.base,
            "local": self.local,
            "remote": self.remote,
            "suggestion": self.suggestion.value,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class MergeOutcome:
    """Result of merging one entity reference."""

    status: str
    entity: PortableEntity | None = None
    conflict: Conflict | None = None


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Result of merging two independently edited vaults."""

    entities: tuple[PortableEntity, ...] = ()
    links: tuple[V3EntityLink, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    applied: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    vector: VersionVector = field(default_factory=VersionVector.empty)
    families: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        """Whether the merge produced no conflicts."""
        return not self.conflicts

    def counts(self) -> dict[str, int]:
        """Return counts used by dry-run previews and receipts."""
        return {
            "entities": len(self.entities),
            "links": len(self.links),
            "applied": len(self.applied),
            "unchanged": len(self.unchanged),
            "conflicts": len(self.conflicts),
        }

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            **self.counts(),
            "families": list(self.families),
            "vector": self.vector.as_dict(),
            "applied": list(self.applied),
            "unchanged": list(self.unchanged),
            "conflicts": [conflict.as_dict() for conflict in self.conflicts],
            "entities": [entity.as_dict() for entity in self.entities],
            "links": [link_as_dict(link) for link in self.links],
        }


def _diffs_for(
    base_values: dict[str, Any],
    local_values: dict[str, Any],
    remote_values: dict[str, Any],
) -> tuple[FieldDiff, ...]:
    """Build field diffs for three comparable field maps."""
    return tuple(
        FieldDiff(
            field=name,
            base=base_values.get(name),
            local=local_values.get(name),
            remote=remote_values.get(name),
            local_changed=local_values.get(name) != base_values.get(name),
            remote_changed=remote_values.get(name) != base_values.get(name),
        )
        for name in MERGE_FIELDS
    )


def _reason_for(diffs: tuple[FieldDiff, ...]) -> ConflictReason:
    """Choose the most specific reason code for overlapping edits."""
    overlapping = [diff.field for diff in diffs if diff.overlap]
    if "body" in overlapping:
        return ConflictReason.CONTENT_DIVERGENCE
    if "tags" in overlapping:
        return ConflictReason.TAG_SET_DIVERGENCE
    return ConflictReason.FIELD_BOTH_EDITED


def three_way_merge(
    ref: str,
    base: PortableEntity | None,
    local: PortableEntity | None,
    remote: PortableEntity | None,
) -> MergeOutcome:
    """Merge one entity snapshot using its last common ancestor.

    Unchanged sides fast-forward, disjoint field edits auto-merge, and
    overlapping edits become an explained conflict with a suggestion.
    """
    if base is None:
        if local is None and remote is None:
            return MergeOutcome("unchanged")
        if local is None:
            assert remote is not None
            return MergeOutcome("applied", remote)
        if remote is None:
            return MergeOutcome("applied", local)
        if local.fingerprint() == remote.fingerprint():
            return MergeOutcome("applied", local)
        diffs = _diffs_for({}, local.field_values(), remote.field_values())
        conflict = Conflict(
            ref=ref,
            family=local.family,
            reason=ConflictReason.CONCURRENT_ADD,
            fields=tuple(diff for diff in diffs if diff.overlap),
            local=local.as_dict(),
            remote=remote.as_dict(),
            suggestion=ResolutionChoice.MANUAL,
        )
        return MergeOutcome("conflict", conflict=conflict)

    if local is None and remote is None:
        return MergeOutcome("unchanged")
    base_values = base.field_values()
    if local is None:
        assert remote is not None
        if remote.deleted:
            return MergeOutcome("unchanged")
        conflict = Conflict(
            ref=ref,
            family=base.family,
            reason=ConflictReason.DELETE_MODIFY,
            fields=_diffs_for(base_values, {**base_values, "deleted": True}, remote.field_values()),
            base=base.as_dict(),
            remote=remote.as_dict(),
            suggestion=ResolutionChoice.KEEP_REMOTE,
        )
        return MergeOutcome("conflict", conflict=conflict)
    if remote is None:
        if local.deleted:
            return MergeOutcome("unchanged")
        conflict = Conflict(
            ref=ref,
            family=base.family,
            reason=ConflictReason.DELETE_MODIFY,
            fields=_diffs_for(base_values, local.field_values(), {**base_values, "deleted": True}),
            base=base.as_dict(),
            local=local.as_dict(),
            suggestion=ResolutionChoice.KEEP_LOCAL,
        )
        return MergeOutcome("conflict", conflict=conflict)

    local_values = local.field_values()
    remote_values = remote.field_values()
    if local.deleted != remote.deleted:
        conflict = Conflict(
            ref=ref,
            family=base.family,
            reason=ConflictReason.DELETE_MODIFY,
            fields=_diffs_for(base_values, local_values, remote_values),
            base=base.as_dict(),
            local=local.as_dict(),
            remote=remote.as_dict(),
            suggestion=(
                ResolutionChoice.KEEP_REMOTE if local.deleted else ResolutionChoice.KEEP_LOCAL
            ),
        )
        return MergeOutcome("conflict", conflict=conflict)
    if local.fingerprint() == remote.fingerprint():
        if local.fingerprint() == base.fingerprint():
            return MergeOutcome("unchanged", base)
        return MergeOutcome("applied", local)
    diffs = _diffs_for(base_values, local_values, remote_values)
    if not any(diff.local_changed for diff in diffs):
        return MergeOutcome("applied", remote)
    if not any(diff.remote_changed for diff in diffs):
        return MergeOutcome("applied", local)

    overlaps = tuple(diff for diff in diffs if diff.overlap)
    vector = base.vector.merge(local.vector).merge(remote.vector)
    if not overlaps:
        merged_values = {diff.field: diff.chosen for diff in diffs}
        merged_values["deleted"] = local.deleted or remote.deleted
        return MergeOutcome("applied", local.apply_fields(merged_values, vector=vector))

    conflict = Conflict(
        ref=ref,
        family=base.family,
        reason=_reason_for(diffs),
        fields=overlaps,
        base=base.as_dict(),
        local=local.as_dict(),
        remote=remote.as_dict(),
        suggestion=ResolutionChoice.MANUAL,
    )
    return MergeOutcome("conflict", conflict=conflict)


def _link_index(links: tuple[V3EntityLink, ...]) -> dict[tuple[str, str, str], V3EntityLink]:
    """Index links by their universal identity key."""
    return {link.key: link for link in links}


def merge_links(
    base: tuple[V3EntityLink, ...],
    local: tuple[V3EntityLink, ...],
    remote: tuple[V3EntityLink, ...],
    *,
    valid_refs: frozenset[str],
) -> tuple[tuple[V3EntityLink, ...], tuple[Conflict, ...]]:
    """Merge link sets, reporting missing endpoints and divergent edits."""
    base_index = _link_index(base)
    local_index = _link_index(local)
    remote_index = _link_index(remote)
    merged: list[V3EntityLink] = []
    conflicts: list[Conflict] = []
    for key in sorted(set(base_index) | set(local_index) | set(remote_index)):
        ancestor = base_index.get(key)
        ours = local_index.get(key)
        theirs = remote_index.get(key)
        ours_changed = ours is not None and (
            ancestor is None or ours.as_dict() != ancestor.as_dict()
        )
        sides_equal = ours is not None and theirs is not None and ours.as_dict() == theirs.as_dict()
        if ours_changed or sides_equal:
            assert ours is not None
            chosen = ours
        elif theirs is not None:
            chosen = theirs
        elif ancestor is not None:
            continue
        else:
            continue
        missing = [
            endpoint
            for endpoint in (str(chosen.source), str(chosen.target))
            if endpoint not in valid_refs
        ]
        if missing:
            conflicts.append(
                Conflict(
                    ref="/".join(key),
                    family="link",
                    reason=ConflictReason.LINK_TARGET_MISSING,
                    local=link_as_dict(ours) if ours else None,
                    remote=link_as_dict(theirs) if theirs else None,
                    detail=f"Missing endpoints: {', '.join(sorted(missing))}",
                    suggestion=ResolutionChoice.SKIP,
                )
            )
            continue
        both_changed = (
            ours is not None
            and theirs is not None
            and (ancestor is None or ours.as_dict() != ancestor.as_dict())
            and (ancestor is None or theirs.as_dict() != ancestor.as_dict())
        )
        if both_changed:
            assert ours is not None
            assert theirs is not None
            ours_payload = ours.as_dict()
            theirs_payload = theirs.as_dict()
            ancestor_payload = ancestor.as_dict() if ancestor is not None else {}
            conflicts.append(
                Conflict(
                    ref="/".join(key),
                    family="link",
                    reason=ConflictReason.FIELD_BOTH_EDITED,
                    fields=tuple(
                        FieldDiff(
                            field=name,
                            base=ancestor_payload.get(name),
                            local=ours_payload.get(name),
                            remote=theirs_payload.get(name),
                            local_changed=ours_payload.get(name) != ancestor_payload.get(name),
                            remote_changed=theirs_payload.get(name) != ancestor_payload.get(name),
                        )
                        for name in ("label", "weight", "metadata")
                    ),
                    local=link_as_dict(ours),
                    remote=link_as_dict(theirs),
                    suggestion=ResolutionChoice.KEEP_LOCAL,
                )
            )
            continue
        merged.append(chosen)
    return tuple(merged), tuple(conflicts)


def merge_families(
    base: tuple[PortableEntity, ...],
    local: tuple[PortableEntity, ...],
    remote: tuple[PortableEntity, ...],
    *,
    base_links: tuple[V3EntityLink, ...] = (),
    local_links: tuple[V3EntityLink, ...] = (),
    remote_links: tuple[V3EntityLink, ...] = (),
    families: tuple[str, ...] = (),
) -> MergeResult:
    """Merge two independently edited vaults, grouped by entity family."""
    wanted = frozenset(families)
    base_map = {entity.ref: entity for entity in base}
    local_map = {entity.ref: entity for entity in local}
    remote_map = {entity.ref: entity for entity in remote}
    refs = set(base_map) | set(local_map) | set(remote_map)
    entities: list[PortableEntity] = []
    conflicts: list[Conflict] = []
    applied: list[str] = []
    unchanged: list[str] = []
    for ref in sorted(refs):
        base_entity = base_map.get(ref)
        local_entity = local_map.get(ref)
        remote_entity = remote_map.get(ref)
        head = local_entity or remote_entity or base_entity
        assert head is not None
        family = head.family
        if wanted and family not in wanted:
            continue
        outcome = three_way_merge(ref, base_entity, local_entity, remote_entity)
        if outcome.conflict is not None:
            conflicts.append(outcome.conflict)
        elif outcome.entity is not None:
            entities.append(outcome.entity)
            if outcome.status == "applied":
                applied.append(ref)
            else:
                unchanged.append(ref)
        else:
            unchanged.append(ref)
    valid_refs = frozenset(refs)
    links, link_conflicts = merge_links(
        base_links,
        local_links,
        remote_links,
        valid_refs=valid_refs,
    )
    conflicts.extend(link_conflicts)
    all_vectors = tuple(entity.vector for entity in (*base, *local, *remote))
    return MergeResult(
        entities=tuple(sorted(entities, key=lambda item: item.ref)),
        links=links,
        conflicts=tuple(conflicts),
        applied=tuple(applied),
        unchanged=tuple(unchanged),
        vector=_merge_all_vectors(all_vectors),
        families=tuple(sorted({entity.family for entity in entities})),
    )


def _merge_all_vectors(vectors: tuple[VersionVector, ...]) -> VersionVector:
    """Combine all vectors without importing the vector helper module late."""
    result = VersionVector.empty()
    for vector in vectors:
        result = result.merge(vector)
    return result


def group_conflicts_by_reason(
    conflicts: tuple[Conflict, ...],
) -> dict[ConflictReason, tuple[Conflict, ...]]:
    """Group conflicts by reason code in stable order."""
    groups: dict[ConflictReason, list[Conflict]] = {}
    for conflict in conflicts:
        groups.setdefault(conflict.reason, []).append(conflict)
    return {reason: tuple(items) for reason, items in groups.items()}


def suggest_for(
    conflict: Conflict,
    strategy: ResolutionStrategy = ResolutionStrategy.MANUAL,
) -> ResolutionChoice:
    """Return the decision implied by a default resolution strategy."""
    if strategy is ResolutionStrategy.KEEP_LOCAL:
        return ResolutionChoice.KEEP_LOCAL
    if strategy is ResolutionStrategy.KEEP_REMOTE:
        return ResolutionChoice.KEEP_REMOTE
    if strategy is ResolutionStrategy.SKIP:
        return ResolutionChoice.SKIP
    if strategy is ResolutionStrategy.MERGE_FIELDS:
        return ResolutionChoice.MERGE_FIELDS
    return conflict.suggestion


def require_choice(conflict: Conflict, choice: ResolutionChoice) -> None:
    """Validate that a choice is meaningful for a conflict."""
    if choice is ResolutionChoice.MANUAL:
        raise ResolutionError("Manual choices must be made in the conflict workbench")
    if conflict.local is None and choice is ResolutionChoice.KEEP_LOCAL:
        raise ResolutionError(f"Conflict {conflict.ref} has no local side")
    if conflict.remote is None and choice is ResolutionChoice.KEEP_REMOTE:
        raise ResolutionError(f"Conflict {conflict.ref} has no remote side")
    if choice is ResolutionChoice.MERGE_FIELDS and not conflict.fields:
        raise ResolutionError(f"Conflict {conflict.ref} has no mergeable field diffs")


def detect_vector_regressions(
    base: VersionVector,
    local: VersionVector,
    remote: VersionVector,
    *,
    ref: str = "vault",
) -> tuple[Conflict, ...]:
    """Report vectors that lost knowledge of a common ancestor."""
    conflicts: list[Conflict] = []
    for name, vector in (("local", local), ("remote", remote)):
        if not vector.dominates(base):
            conflicts.append(
                Conflict(
                    ref=f"{ref}/{name}",
                    family="vector",
                    reason=ConflictReason.VECTOR_REGRESSION,
                    base=base.as_dict(),
                    local=local.as_dict(),
                    remote=remote.as_dict(),
                    detail=f"{name} vector is missing known device counters",
                    suggestion=(
                        ResolutionChoice.KEEP_LOCAL
                        if name == "remote"
                        else ResolutionChoice.KEEP_REMOTE
                    ),
                )
            )
    return tuple(conflicts)


def apply_resolution(
    result: MergeResult,
    conflict: Conflict,
    choice: ResolutionChoice,
) -> MergeResult:
    """Apply one decision to a merge result, returning a new result."""
    require_choice(conflict, choice)
    if choice is ResolutionChoice.SKIP:
        remaining = tuple(item for item in result.conflicts if item.ref != conflict.ref)
        return MergeResult(
            entities=result.entities,
            links=result.links,
            conflicts=remaining,
            applied=result.applied,
            unchanged=(*result.unchanged, conflict.ref),
            vector=result.vector,
            families=result.families,
        )
    if choice is ResolutionChoice.MERGE_FIELDS:
        diffs = conflict.fields
        values = {diff.field: diff.local if diff.local_changed else diff.remote for diff in diffs}
        source_payload = conflict.local or conflict.remote
        if source_payload is None:
            raise MergeError(f"Cannot merge conflict without a source snapshot: {conflict.ref}")
        try:
            source = PortableEntity.from_dict(source_payload)
        except BundleError as error:
            raise MergeError(f"Conflict {conflict.ref} is not an entity conflict") from error
        merged = source.apply_fields(values, vector=result.vector.merge(source.vector))
        entities = tuple(item for item in result.entities if item.ref != conflict.ref)
        entities = tuple(sorted((*entities, merged), key=lambda item: item.ref))
        remaining = tuple(item for item in result.conflicts if item.ref != conflict.ref)
        return MergeResult(
            entities=entities,
            links=result.links,
            conflicts=remaining,
            applied=(*result.applied, conflict.ref),
            unchanged=result.unchanged,
            vector=result.vector,
            families=tuple(sorted({item.family for item in entities})),
        )
    selected = conflict.local if choice is ResolutionChoice.KEEP_LOCAL else conflict.remote
    if selected is None:
        raise MergeError(f"Conflict {conflict.ref} has no selected snapshot")
    try:
        entity = PortableEntity.from_dict(selected)
    except BundleError as error:
        raise MergeError(f"Conflict {conflict.ref} is not an entity conflict") from error
    entities = tuple(item for item in result.entities if item.ref != conflict.ref)
    entities = tuple(sorted((*entities, entity), key=lambda item: item.ref))
    remaining = tuple(item for item in result.conflicts if item.ref != conflict.ref)
    return MergeResult(
        entities=entities,
        links=result.links,
        conflicts=remaining,
        applied=(*result.applied, conflict.ref),
        unchanged=result.unchanged,
        vector=result.vector,
        families=tuple(sorted({item.family for item in entities})),
    )
