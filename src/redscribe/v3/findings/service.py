"""Application service for the finding studio."""

from __future__ import annotations

from collections import Counter
from typing import Any

from redscribe.v3.capabilities import (
    CAP_FINDINGS,
    Capabilities,
    CapabilityError,
    default_capabilities,
)
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities.ids import new_id
from redscribe.v3.entities.service import EntityService
from redscribe.v3.entities.types import (
    EntityId,
    EntityKind,
    EntityRef,
    LinkKind,
)
from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.types import DomainEvent, EventSeverity
from redscribe.v3.findings.cvss_v4 import (
    SeverityBand,
    cvss_v4_breakdown,
    parse_cvss_v4_vector,
)
from redscribe.v3.findings.duplicates import (
    DEFAULT_THRESHOLD,
    DuplicateSuggestion,
    duplicate_summary,
    suggest_duplicates,
)
from redscribe.v3.findings.lifecycle import (
    TransitionError,
    TransitionRule,
    apply_transition,
    available_actions,
    rules_for,
    state_summary,
)
from redscribe.v3.findings.mappings import MappingError, mapping_report, validate_mappings
from redscribe.v3.findings.models import (
    Finding,
    FindingMappings,
    FindingState,
    ProofBlock,
    ProofRole,
    RemediationTask,
    RetestRecord,
    RetestVerdict,
    TransitionRecord,
    parse_finding_ref,
)
from redscribe.v3.findings.proof import (
    ProofError,
    add_proof_block,
    make_proof,
    proof_link,
    proof_summary,
    verify_chain,
)
from redscribe.v3.findings.remediation import (
    RemediationError,
    add_task,
    new_task,
    plan_for,
    task_from_lines,
    update_task,
)

FINDING_CREATED = "finding.created"
FINDING_UPDATED = "finding.updated"
FINDING_SCORED = "finding.scored"
FINDING_REMEDIATION = "finding.remediation_updated"
FINDING_RETEST = "finding.retest_recorded"
FINDING_TRANSITION = "finding.transitioned"
FINDING_PROOF = "finding.proof_added"
FINDING_DUPLICATE = "finding.duplicate_linked"


class FindingServiceError(KeyError):
    """Raised when a finding reference is unknown."""


class FindingConflictError(ValueError):
    """Raised when a mutation conflicts with current finding state."""


class FindingService:
    """Own immutable finding snapshots and emit domain events for changes."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        bus: EventBus | None = None,
        entities: EntityService | None = None,
        capabilities: Capabilities | None = None,
    ) -> None:
        self._clock: Clock = clock or SystemClock()
        self._bus = bus or EventBus()
        self._entities = entities or EntityService(clock=self._clock)
        self._capabilities = capabilities or default_capabilities
        self._findings: dict[str, Finding] = {}

    @property
    def bus(self) -> EventBus:
        """The shared event bus."""
        return self._bus

    @property
    def entities(self) -> EntityService:
        """The shared entity service."""
        return self._entities

    def _require_capability(self) -> None:
        try:
            self._capabilities.require(CAP_FINDINGS)
        except CapabilityError as error:
            raise FindingConflictError(str(error)) from error

    def _now(self) -> float:
        return self._clock.now_timestamp()

    def _get(self, ref: str | EntityId) -> Finding:
        raw = str(ref)
        finding = self._findings.get(raw)
        if finding is None:
            raise FindingServiceError(f"Unknown finding: {raw}")
        return finding

    def _store(self, finding: Finding) -> Finding:
        self._findings[finding.ref_string] = finding
        return finding

    def _emit(
        self,
        kind: str,
        finding: Finding,
        *,
        severity: EventSeverity = EventSeverity.INFO,
        actor: str = "local",
        **payload: Any,
    ) -> DomainEvent:
        event = DomainEvent(
            kind=kind,
            subject=finding.entity_id,
            actor=actor,
            severity=severity,
            payload={**payload, "version": finding.version, "state": finding.state.value},
            correlation_id=finding.ref_string,
        )
        self._bus.publish(event)
        return event

    def create(
        self,
        *,
        title: str,
        summary: str = "",
        vector: str = "",
        owner: str = "",
        target_ref: EntityRef | None = None,
        cwes: tuple[str, ...] = (),
        cves: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
        actor: str = "local",
    ) -> Finding:
        """Create a draft finding and its universal entity record."""
        self._require_capability()
        if vector:
            parse_cvss_v4_vector(vector)
        record = self._entities.create(
            EntityKind.FINDING,
            title=title,
            summary=summary,
            tags=tags,
            owner=owner,
            metadata={"state": FindingState.DRAFT.value},
        )
        timestamp = record.created_at or self._now()
        finding = Finding(
            entity_id=record.entity_id,
            title=title,
            summary=summary,
            state=FindingState.DRAFT,
            vector=vector,
            owner=owner,
            target_ref=target_ref,
            mappings=FindingMappings(cwes=cwes, cves=cves),
            tags=tags,
            created_at=timestamp,
            updated_at=timestamp,
            metadata=dict(metadata or {}),
        )
        self._store(finding)
        self._emit(FINDING_CREATED, finding, actor=actor, title=title, vector=vector)
        return finding

    def get(self, ref: str | EntityId) -> Finding:
        """Return a finding snapshot or raise."""
        return self._get(ref)

    def find(self, raw: str) -> Finding | None:
        """Look up a finding by canonical reference, returning None when absent."""
        return self._findings.get(raw)

    def all(self) -> tuple[Finding, ...]:
        """Return every finding in stable reference order."""
        return tuple(self._findings[key] for key in sorted(self._findings))

    def list(
        self,
        *,
        query: str = "",
        state: str = "",
        severity: str = "",
        owner: str = "",
        tag: str = "",
        vector_has_threat: bool | None = None,
    ) -> tuple[Finding, ...]:
        """Filter findings by the studio's list facets."""
        needle = query.strip().casefold()
        state_filter = state.strip().casefold()
        severity_filter = severity.strip().casefold()
        owner_filter = owner.strip().casefold()
        tag_filter = tag.strip().casefold()
        results: list[Finding] = []
        for finding in self.all():
            if state_filter and finding.state.value != state_filter:
                continue
            if severity_filter and finding.severity.value != severity_filter:
                continue
            if owner_filter and owner_filter not in finding.owner.casefold():
                continue
            if tag_filter and not any(tag_filter in item.casefold() for item in finding.tags):
                continue
            if vector_has_threat is not None:
                has_threat = "/E:" in finding.vector and not finding.vector.endswith("/E:X")
                if has_threat != vector_has_threat:
                    continue
            if needle:
                haystack = " ".join(
                    (
                        finding.title,
                        finding.summary,
                        finding.owner,
                        " ".join(finding.tags),
                        " ".join(finding.mappings.cwes),
                        " ".join(finding.mappings.cves),
                    )
                ).casefold()
                if needle not in haystack:
                    continue
            results.append(finding)
        return tuple(results)

    def update(
        self,
        ref: str | EntityId,
        *,
        actor: str = "local",
        **changes: Any,
    ) -> Finding:
        """Update mutable finding fields, returning the new immutable version."""
        self._require_capability()
        existing = self._get(ref)
        allowed = {"title", "summary", "owner", "target_ref", "tags", "metadata"}
        unknown = set(changes) - allowed
        if unknown:
            raise FindingConflictError(f"Unknown finding fields: {', '.join(sorted(unknown))}")
        if "title" in changes and not str(changes["title"]).strip():
            raise FindingConflictError("Finding title cannot be blank")
        if "tags" in changes:
            changes["tags"] = tuple(str(item) for item in changes["tags"])
        updated = existing.evolve(**changes, updated_at=self._now())
        self._store(updated)
        self._entities.update(
            existing.entity_id,
            title=changes.get("title"),
            summary=changes.get("summary"),
            tags=changes.get("tags"),
        )
        self._emit(FINDING_UPDATED, updated, actor=actor, fields=sorted(changes))
        return updated

    def set_score(
        self,
        ref: str | EntityId,
        vector: str,
        *,
        actor: str = "local",
    ) -> Finding:
        """Set or replace the CVSS v4 vector of a finding."""
        self._require_capability()
        parsed = parse_cvss_v4_vector(vector)
        existing = self._get(ref)
        result = cvss_v4_breakdown(parsed)
        updated = existing.evolve(vector=parsed.render(), updated_at=self._now())
        self._store(updated)
        self._emit(
            FINDING_SCORED,
            updated,
            actor=actor,
            vector=parsed.render(),
            score=result["final"],
            severity=result["severity"],
        )
        return updated

    def set_severity_override(
        self,
        ref: str | EntityId,
        band: str | SeverityBand,
        *,
        actor: str = "local",
    ) -> Finding:
        """Apply or clear a manual severity override."""
        self._require_capability()
        existing = self._get(ref)
        metadata = dict(existing.metadata)
        if isinstance(band, SeverityBand):
            band = band.value
        normalized = band.strip().casefold()
        if normalized and normalized not in {item.value for item in SeverityBand}:
            raise FindingConflictError(f"Unknown severity band: {band}")
        if normalized and normalized != SeverityBand.NONE.value:
            metadata["severity_override"] = normalized
        else:
            metadata.pop("severity_override", None)
        updated = existing.evolve(metadata=metadata, updated_at=self._now())
        self._store(updated)
        self._emit(FINDING_SCORED, updated, actor=actor, override=normalized)
        return updated

    def set_mappings(
        self,
        ref: str | EntityId,
        *,
        cwes: tuple[str, ...] | None = None,
        cves: tuple[str, ...] | None = None,
        owasp: tuple[str, ...] | None = None,
        capec: tuple[str, ...] | None = None,
        mitre_attack: tuple[str, ...] | None = None,
        notes: str | None = None,
        actor: str = "local",
    ) -> Finding:
        """Replace weakness and framework mapping metadata."""
        self._require_capability()
        existing = self._get(ref)
        previous = existing.mappings
        mappings = FindingMappings(
            cwes=previous.cwes if cwes is None else cwes,
            cves=previous.cves if cves is None else cves,
            owasp=previous.owasp if owasp is None else owasp,
            capec=previous.capec if capec is None else capec,
            mitre_attack=previous.mitre_attack if mitre_attack is None else mitre_attack,
            notes=previous.notes if notes is None else notes,
        )
        issues = validate_mappings(mappings)
        if issues:
            raise MappingError("; ".join(issues))
        updated = existing.evolve(mappings=mappings, updated_at=self._now())
        self._store(updated)
        self._emit(FINDING_UPDATED, updated, actor=actor, mappings=mappings.as_dict())
        return updated

    def add_remediation(
        self,
        ref: str | EntityId,
        *,
        task_id: str = "",
        title: str = "",
        detail: str = "",
        owner: str = "",
        lines: str = "",
        actor: str = "local",
    ) -> Finding:
        """Add one task or a checklist parsed from newline-separated guidance."""
        self._require_capability()
        existing = self._get(ref)
        additions: tuple[RemediationTask, ...]
        if lines:
            additions = task_from_lines(lines, owner=owner)
        elif title:
            additions = (
                new_task(
                    task_id or f"task-{len(existing.remediation) + 1}",
                    title,
                    detail=detail,
                    owner=owner,
                ),
            )
        else:
            raise RemediationError("Provide either a task title or remediation lines")
        tasks = existing.remediation
        for task in additions:
            tasks = add_task(tasks, task)
        updated = existing.evolve(remediation=tasks, updated_at=self._now())
        self._store(updated)
        self._emit(
            FINDING_REMEDIATION, updated, actor=actor, added=[task.task_id for task in additions]
        )
        return updated

    def update_remediation_task(
        self,
        ref: str | EntityId,
        task_id: str,
        status: str,
        *,
        proof_ref: str = "",
        actor: str = "local",
    ) -> Finding:
        """Change the status of one remediation checklist item."""
        self._require_capability()
        from redscribe.v3.findings.models import TaskStatus

        try:
            parsed_status = TaskStatus.parse(status)
        except ValueError as error:
            raise RemediationError(str(error)) from error
        existing = self._get(ref)
        tasks = update_task(
            existing.remediation,
            task_id,
            status=parsed_status,
            timestamp=self._now(),
            proof_ref=proof_ref,
        )
        updated = existing.evolve(remediation=tasks, updated_at=self._now())
        self._store(updated)
        self._emit(
            FINDING_REMEDIATION,
            updated,
            actor=actor,
            task_id=task_id,
            status=parsed_status.value,
        )
        return updated

    def remediation(self, ref: str | EntityId) -> dict[str, Any]:
        """Return a remediation plan report."""
        finding = self._get(ref)
        return plan_for(
            finding.remediation,
            owner=finding.owner,
            notes=finding.metadata.get("remediation_notes", ""),
        ).as_dict()

    def record_retest(
        self,
        ref: str | EntityId,
        *,
        verdict: str | RetestVerdict,
        tested_by: str,
        notes: str = "",
        proof_refs: tuple[str, ...] = (),
        follow_up: str = "",
        actor: str = "local",
    ) -> RetestRecord:
        """Record an evidence-backed retest result on a finding."""
        self._require_capability()
        existing = self._get(ref)
        parsed = RetestVerdict.parse(verdict) if isinstance(verdict, str) else verdict
        record = RetestRecord(
            retest_id=new_id(EntityKind.RUN, prefix="retest").value,
            verdict=parsed,
            tested_by=tested_by,
            timestamp=self._now(),
            notes=notes,
            proof_refs=proof_refs,
            follow_up=follow_up,
        )
        updated = existing.evolve(retests=(*existing.retests, record), updated_at=self._now())
        self._store(updated)
        self._emit(
            FINDING_RETEST,
            updated,
            actor=actor,
            retest_id=record.retest_id,
            verdict=parsed.value,
        )
        return record

    def available_actions(self, ref: str | EntityId) -> tuple[str, ...]:
        """List lifecycle actions currently available on a finding."""
        return available_actions(self._get(ref))

    def transition_rules(self, ref: str | EntityId) -> tuple[TransitionRule, ...]:
        """List state rules for a finding's current state."""
        return rules_for(self._get(ref).state)

    def transition(
        self,
        ref: str | EntityId,
        action: str,
        *,
        actor: str = "local",
        note: str = "",
    ) -> tuple[Finding, TransitionRecord]:
        """Apply a guarded lifecycle transition."""
        self._require_capability()
        existing = self._get(ref)
        updated, record = apply_transition(
            existing, action, actor=actor, timestamp=self._now(), note=note
        )
        self._store(updated)
        self._emit(
            FINDING_TRANSITION,
            updated,
            actor=actor,
            severity=EventSeverity.WARNING
            if action in {"fail", "reopen", "regress"}
            else EventSeverity.NOTICE,
            action=action,
            source=record.source.value,
            target=record.target.value,
            note=note,
        )
        return updated, record

    def add_proof(
        self,
        ref: str | EntityId,
        *,
        block_id: str,
        target: EntityRef | str,
        excerpt: str = "",
        role: str | ProofRole = ProofRole.SUPPORTING,
        label: str = "",
        actor: str = "local",
    ) -> ProofBlock:
        """Attach an evidence-backed proof block and its EntityRef link."""
        self._require_capability()
        existing = self._get(ref)
        entity_ref = target if isinstance(target, EntityRef) else self._parse_ref(target)
        parsed_role = ProofRole.parse(role) if isinstance(role, str) else role
        block = make_proof(
            block_id,
            entity_ref,
            excerpt=excerpt,
            role=parsed_role,
            captured_at=self._now(),
            label=label,
        )
        updated = add_proof_block(existing, block, timestamp=self._now())
        self._store(updated)
        link = proof_link(updated, block)
        self._entities.graph().add(link)
        self._emit(
            FINDING_PROOF,
            updated,
            actor=actor,
            block_id=block.block_id,
            target=str(entity_ref),
            role=parsed_role.value,
        )
        return block

    @staticmethod
    def _parse_ref(raw: str) -> EntityRef:
        parsed = parse_finding_ref(raw) if raw.startswith("finding:") else None
        if parsed is not None:
            raise ProofError("A finding cannot be its own proof target")
        from redscribe.v3.entities.types import EntityId as _EntityId

        entity_id = _EntityId.parse(raw)
        if entity_id.kind is EntityKind.FINDING:
            raise ProofError("A finding cannot be its own proof target")
        return EntityRef(entity_id)

    def proof_report(self, ref: str | EntityId) -> dict[str, Any]:
        """Return a proof-block integrity report."""
        return proof_summary(self._get(ref))

    def mark_duplicate(
        self,
        ref: str | EntityId,
        canonical: str | EntityId,
        *,
        actor: str = "local",
        note: str = "",
    ) -> Finding:
        """Mark a finding as a duplicate of a canonical finding."""
        self._require_capability()
        existing = self._get(ref)
        canonical_id = parse_finding_ref(str(canonical))
        canonical_finding = self._get(canonical_id)
        if canonical_finding.ref_string == existing.ref_string:
            raise FindingConflictError("A finding cannot duplicate itself")
        if canonical_finding.duplicate_of is not None:
            raise FindingConflictError("The canonical finding is itself a duplicate")
        updated = existing.evolve(
            duplicate_of=canonical_id,
            metadata={**existing.metadata, "duplicate_note": note},
            updated_at=self._now(),
        )
        self._store(updated)
        self._entities.link(
            existing.entity_id,
            canonical_id,
            kind=LinkKind.DUPLICATES,
            label=note,
        )
        self._emit(
            FINDING_DUPLICATE,
            updated,
            actor=actor,
            canonical=canonical_finding.ref_string,
            note=note,
        )
        return updated

    def suggestions(
        self,
        ref: str | EntityId,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        candidates: tuple[Finding, ...] | None = None,
    ) -> tuple[DuplicateSuggestion, ...]:
        """Suggest duplicates for one finding."""
        source = self._get(ref)
        pool = (
            list(candidates)
            if candidates is not None
            else [item for item in self.all() if item.ref_string != source.ref_string]
        )
        return suggest_duplicates(source, pool, threshold=threshold)

    def duplicate_report(
        self,
        ref: str | EntityId,
        *,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> dict[str, Any]:
        """Return a duplicate-detection report for a finding."""
        return duplicate_summary(self._get(ref), list(self.all()), threshold=threshold)

    def summary(self) -> dict[str, Any]:
        """Return dashboard counts across all findings."""
        states: Counter[str] = Counter(item.state.value for item in self.all())
        severities: Counter[str] = Counter(item.severity.value for item in self.all())
        proof_issues = sum(len(verify_chain(item)) for item in self.all())
        incomplete_checklists = sum(
            1 for item in self.all() if item.remediation and not plan_for(item.remediation).complete
        )
        return {
            "total": len(self._findings),
            "by_state": dict(sorted(states.items())),
            "by_severity": dict(sorted(severities.items())),
            "open": sum(1 for item in self.all() if item.is_open),
            "duplicates": sum(1 for item in self.all() if item.duplicate_of is not None),
            "proof_issues": proof_issues,
            "incomplete_checklists": incomplete_checklists,
            "events": self._bus.size(),
        }

    def detail(self, ref: str | EntityId) -> dict[str, Any]:
        """Return a full finding detail payload for the editor."""
        finding = self._get(ref)
        return {
            "finding": finding.as_dict(),
            "lifecycle": state_summary(finding),
            "remediation": self.remediation(finding.ref_string),
            "proof": proof_summary(finding),
            "mappings": mapping_report(finding.mappings),
            "duplicates": self.duplicate_report(finding.ref_string),
            "score": cvss_v4_breakdown(finding.vector) if finding.vector else None,
        }

    def remove(self, ref: str | EntityId, *, actor: str = "local") -> None:
        """Delete a draft finding from the studio index."""
        self._require_capability()
        finding = self._get(ref)
        if finding.state is not FindingState.DRAFT:
            raise FindingConflictError("Only draft findings can be removed")
        del self._findings[finding.ref_string]
        self._entities.remove(finding.entity_id)
        self._emit(FINDING_UPDATED, finding, actor=actor, removed=True)


__all__ = [
    "FINDING_CREATED",
    "FINDING_DUPLICATE",
    "FINDING_PROOF",
    "FINDING_REMEDIATION",
    "FINDING_RETEST",
    "FINDING_SCORED",
    "FINDING_TRANSITION",
    "FINDING_UPDATED",
    "FindingConflictError",
    "FindingService",
    "FindingServiceError",
    "TransitionError",
]
