"""Rollback through compensating events, never through destructive rewrites."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from redscribe.v3.automation.encoding import chain_digest, copy_value
from redscribe.v3.automation.errors import RollbackError
from redscribe.v3.automation.executor import InMemoryMutationSink, MutationSink
from redscribe.v3.automation.parsing import issue
from redscribe.v3.automation.types import (
    DryRunTrace,
    MutationIntent,
    RunRecord,
    RunStatus,
    StepStatus,
    TraceEntry,
    ValidationIssue,
)
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities.ids import try_parse
from redscribe.v3.events import DomainEvent, EventBus, EventSeverity


@dataclass(frozen=True, slots=True)
class RollbackReport:
    """Outcome of a compensating rollback."""

    record: RunRecord
    original_id: str
    baseline_digest: str
    result_digest: str
    equivalent: bool
    compensations: tuple[MutationIntent, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def ok(self) -> bool:
        """Whether the rollback restored document-state equivalence."""
        return self.equivalent and not any(item.is_error for item in self.issues)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "run": self.record.as_dict(),
            "original_id": self.original_id,
            "baseline_digest": self.baseline_digest,
            "result_digest": self.result_digest,
            "equivalent": self.equivalent,
            "compensations": len(self.compensations),
            "issues": [item.as_dict() for item in self.issues],
            "ok": self.ok,
        }


def compensation_plan(trace: DryRunTrace) -> tuple[MutationIntent, ...]:
    """Return compensations in reverse mutation order."""
    return tuple(
        replace(intent, inverse={"action": "compensate", "original": intent.key})
        for intent in reversed(trace.mutations)
    )


class RollbackManager:
    """Undo a recorded run by applying compensating operations and events."""

    def __init__(
        self,
        sink: MutationSink,
        *,
        bus: EventBus | None = None,
        clock: Clock | None = None,
        sink_factory: Callable[[], InMemoryMutationSink] | None = None,
    ) -> None:
        self.sink = sink
        self.bus = bus
        self.clock: Clock = clock or SystemClock()
        self.sink_factory = sink_factory or InMemoryMutationSink

    def rollback(
        self,
        record: RunRecord,
        trace: DryRunTrace | None = None,
    ) -> RollbackReport:
        """Compensate every mutation of a run and verify state equivalence."""
        if record.status is RunStatus.ROLLED_BACK:
            raise RollbackError("Run is already rolled back", path="run_id")
        source = trace or DryRunTrace(
            playbook_ref=record.playbook_ref,
            mode=record.mode,
            entries=record.trace,
            variables=record.variables,
            digest=record.trace_digest,
            input_fingerprint=record.input_fingerprint,
            state_digest=record.state_digest,
        )
        plan = compensation_plan(source)
        baseline_digest = self.sink_factory().entity_digest()
        replayed = self.sink_factory()
        for intent in source.mutations:
            replayed.commit(intent)
        replay_digest = replayed.entity_digest()

        self._publish("automation.rollback.requested", record, {"mutations": len(plan)})
        entries = list(record.trace)
        chain = record.trace_digest
        applied = 0
        for intent in plan:
            result = self.sink.compensate(intent)
            if not result.applied:
                continue
            applied += 1
            entry = TraceEntry(
                index=len(entries),
                step_id=intent.step_id,
                status=StepStatus.EXECUTED,
                kind=intent.kind,
                message=f"Compensated {intent.kind.value} on {intent.target}",
                variables={"compensation_of": intent.key},
                result=result,
            )
            chain = chain_digest(chain, _unsigned(entry))
            entries.append(replace(entry, chain=chain))
            self._publish(
                "automation.step.compensated",
                record,
                {"step_id": intent.step_id, "target": intent.target, "key": intent.key},
            )
        result_digest = self.sink.entity_digest()
        uncovered: tuple[str, ...] = ()
        if isinstance(self.sink, InMemoryMutationSink):
            uncovered = self.sink.compensation_coverage(source.mutations)
        equivalent = result_digest == baseline_digest
        issues: list[ValidationIssue] = []
        if record.state_digest and replay_digest != record.state_digest:
            issues.append(
                issue(
                    "trace_mismatch",
                    "Recorded trace does not reproduce the run state",
                    path="rollback.trace",
                )
            )
        if not equivalent:
            issues.append(
                issue(
                    "state_mismatch",
                    "Document state differs from the pre-run baseline",
                    path="rollback",
                )
            )
        if uncovered:
            issues.append(
                issue(
                    "uncovered_events",
                    f"Emitted events without compensating events: {', '.join(uncovered)}",
                    path="rollback.events",
                )
            )
        finished_at = self.clock.now_timestamp()
        rollback_record = RunRecord(
            id=f"run_{chain_digest(record.id, {'rollback': applied})}",
            playbook_ref=record.playbook_ref,
            status=RunStatus.ROLLED_BACK,
            mode=record.mode,
            started_at=finished_at,
            finished_at=finished_at,
            trace=tuple(entries),
            variables=copy_value(record.variables),
            input_fingerprint=record.input_fingerprint,
            trace_digest=chain,
            state_digest=result_digest,
            rollback_of=record.id,
        )
        self._publish(
            "automation.rollback.completed",
            record,
            {"equivalent": equivalent, "compensations": applied},
        )
        report = RollbackReport(
            record=rollback_record,
            original_id=record.id,
            baseline_digest=baseline_digest,
            result_digest=result_digest,
            equivalent=equivalent,
            compensations=plan,
            issues=tuple(issues),
        )
        if not report.ok:
            raise RollbackError("Rollback verification failed", path="rollback")
        return report

    def _publish(self, kind: str, record: RunRecord, payload: dict[str, Any]) -> None:
        """Emit compensating activity events when a bus is attached."""
        if self.bus is None:
            return
        subject = try_parse(record.playbook_ref)
        event = DomainEvent(
            kind=kind,
            subject=subject,
            severity=EventSeverity.NOTICE,
            payload={"run_id": record.id, **payload},
            correlation_id=record.id,
        )
        self.bus.publish(event, request_id=record.id)


def _unsigned(entry: TraceEntry) -> dict[str, Any]:
    """Return the hashable portion of a compensation trace entry."""
    return {
        "index": entry.index,
        "step_id": entry.step_id,
        "status": entry.status.value,
        "kind": entry.kind.value,
        "message": entry.message,
        "variables": entry.variables,
        "result": entry.result.as_dict() if entry.result else None,
    }
