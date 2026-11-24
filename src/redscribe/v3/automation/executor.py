"""Data-only step executor and mutation sinks.

The executor resolves step inputs through the typed variable resolver, builds a
:class:`MutationIntent`, and hands it to a sink. Two sinks exist: an in-memory
sink that actually changes document state, and a trace-only sink that refuses
every write. That separation is what makes ``writes == 0`` a structural property
of a dry run rather than a convention.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from redscribe.v3.automation.encoding import copy_value, digest
from redscribe.v3.automation.errors import (
    DryRunWriteAttemptedError,
    UnsupportedStepError,
    VariableResolutionError,
)
from redscribe.v3.automation.types import (
    STEP_KINDS,
    MutationIntent,
    MutationResult,
    PlaybookDefinition,
    StepDefinition,
    StepKind,
    StepStatus,
    Value,
)
from redscribe.v3.automation.variables import VariableResolution, resolve_inputs
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities.ids import slugify, try_parse
from redscribe.v3.entities.types import EntityId
from redscribe.v3.events import DomainEvent, EventBus, EventSeverity, make_event

CREATE_COLLECTIONS: dict[StepKind, str] = {
    StepKind.CREATE_NOTE: "notes",
    StepKind.CREATE_FINDING: "findings",
    StepKind.RENDER_SECTION: "sections",
}


class MutationSink(Protocol):
    """Contract for anything that can apply, preview and compensate a mutation."""

    def preview(self, intent: MutationIntent) -> MutationResult:
        """Predict the outcome of an intent without changing state."""
        ...

    def commit(self, intent: MutationIntent) -> MutationResult:
        """Apply an intent to durable state."""
        ...

    def compensate(self, intent: MutationIntent) -> MutationResult:
        """Undo an applied intent with a compensating operation."""
        ...

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot of current state."""
        ...

    def entity_digest(self) -> str:
        """Return a digest of document state, excluding the append-only event log."""
        ...


class InMemoryMutationSink:
    """Deterministic in-memory document store used by live runs and replay."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, dict[str, Any]]] = {
            collection: {} for collection in CREATE_COLLECTIONS.values()
        }
        self._links: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._applied: set[str] = set()
        self._compensated: set[str] = set()

    def preview(self, intent: MutationIntent) -> MutationResult:
        """Predict the write without touching state."""
        self._check_kind(intent)
        existing = self._lookup(intent)
        after = self._render(intent)
        return MutationResult(
            intent=intent, ref=intent.target, applied=False, before=existing, after=after
        )

    def commit(self, intent: MutationIntent) -> MutationResult:
        """Apply a mutation once, keyed by its deterministic idempotency key."""
        self._check_kind(intent)
        existing = self._lookup(intent)
        if intent.key in self._applied:
            return MutationResult(
                intent=intent, ref=intent.target, applied=False, before=existing, after=existing
            )
        after = self._render(intent)
        self._write(intent, after)
        self._applied.add(intent.key)
        return MutationResult(
            intent=intent, ref=intent.target, applied=True, before=None, after=after
        )

    def compensate(self, intent: MutationIntent) -> MutationResult:
        """Undo a mutation, or record a compensating event for emitted events."""
        self._check_kind(intent)
        if intent.key not in self._applied or intent.key in self._compensated:
            return MutationResult(
                intent=intent,
                ref=intent.target,
                applied=False,
                before=self._lookup(intent),
                after=None,
            )
        before = self._lookup(intent)
        if intent.kind is StepKind.EMIT_EVENT:
            self._events.append(
                {
                    "key": f"undo:{intent.key}",
                    "kind": "automation.compensating_event",
                    "compensates": intent.key,
                    "subject": intent.target,
                    "severity": "notice",
                    "message": intent.payload.get("message", ""),
                }
            )
        elif intent.kind is StepKind.ATTACH_EVIDENCE:
            self._links.pop(intent.target, None)
        else:
            collection = CREATE_COLLECTIONS[intent.kind]
            self._collections[collection].pop(intent.target, None)
        self._compensated.add(intent.key)
        return MutationResult(
            intent=intent, ref=intent.target, applied=True, before=before, after=None
        )

    def snapshot(self) -> dict[str, Any]:
        """Return a deep, deterministic snapshot."""
        return {
            "collections": copy_value(self._collections),
            "links": copy_value(self._links),
            "events": copy_value(self._events),
            "applied": sorted(self._applied),
            "compensated": sorted(self._compensated),
        }

    def entity_digest(self) -> str:
        """Hash document state only; events are append-only and compensated separately."""
        return digest(
            {
                "collections": self._collections,
                "links": self._links,
            }
        )

    def compensation_coverage(self, intents: tuple[MutationIntent, ...]) -> tuple[str, ...]:
        """Return intent keys whose event emission has no compensating event."""
        emitted = {intent.key for intent in intents if intent.kind is StepKind.EMIT_EVENT}
        compensated = {
            event.get("compensates")
            for event in self._events
            if event.get("kind") == "automation.compensating_event"
        }
        return tuple(sorted(emitted - compensated))

    def _check_kind(self, intent: MutationIntent) -> None:
        """Refuse unknown or command-like mutation kinds."""
        kind_value = intent.kind.value if isinstance(intent.kind, StepKind) else str(intent.kind)
        if kind_value not in STEP_KINDS:
            raise UnsupportedStepError(
                f"Unsupported mutation kind: {kind_value}", path="steps.kind"
            )

    def _lookup(self, intent: MutationIntent) -> dict[str, Any] | None:
        """Return the current record targeted by an intent."""
        if intent.kind is StepKind.ATTACH_EVIDENCE:
            return self._links.get(intent.target)
        if intent.kind is StepKind.EMIT_EVENT:
            return None
        return self._collections[CREATE_COLLECTIONS[intent.kind]].get(intent.target)

    def _render(self, intent: MutationIntent) -> dict[str, Any]:
        """Render the record that would be stored for an intent."""
        payload = copy_value(intent.payload)
        if intent.kind is StepKind.EMIT_EVENT:
            return {
                "key": intent.key,
                "kind": payload.get("event_kind", "automation.event"),
                "subject": intent.target,
                "severity": payload.get("severity", "info"),
                "message": payload.get("message", ""),
            }
        return {"ref": intent.target, **payload}

    def _write(self, intent: MutationIntent, record: dict[str, Any]) -> None:
        """Write a rendered record to the appropriate collection."""
        if intent.kind is StepKind.ATTACH_EVIDENCE:
            self._links[intent.target] = record
        elif intent.kind is StepKind.EMIT_EVENT:
            self._events.append(record)
        else:
            self._collections[CREATE_COLLECTIONS[intent.kind]][intent.target] = record


class TraceOnlySink:
    """A sink that predicts writes but physically refuses every mutation."""

    def __init__(self) -> None:
        self._previews = 0

    def preview(self, intent: MutationIntent) -> MutationResult:
        """Predict a result, recording only an in-memory preview counter."""
        self._previews += 1
        return MutationResult(
            intent=intent,
            ref=intent.target,
            applied=False,
            before=None,
            after=intent.payload,
        )

    def commit(self, intent: MutationIntent) -> MutationResult:
        """Always fail: dry runs must never reach a mutating sink."""
        raise DryRunWriteAttemptedError(
            f"Dry run attempted to write mutation for step {intent.step_id}", path=intent.step_id
        )

    def compensate(self, intent: MutationIntent) -> MutationResult:
        """Always fail: dry runs must never compensate durable state."""
        raise DryRunWriteAttemptedError(
            f"Dry run attempted to compensate step {intent.step_id}", path=intent.step_id
        )

    def snapshot(self) -> dict[str, Any]:
        """Return proof that no state was written."""
        return {"writes": 0, "previews": self._previews}

    def entity_digest(self) -> str:
        """Return a constant digest representing an untouched empty store."""
        return digest({"trace_only": True})

    @property
    def previews(self) -> int:
        """Number of non-mutating previews performed."""
        return self._previews


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """The result of executing or planning one step."""

    step: StepDefinition
    status: StepStatus
    message: str
    result: MutationResult | None = None

    @property
    def ref(self) -> str:
        """Reference produced by this step, if any."""
        return self.result.ref if self.result else ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "step_id": self.step.id,
            "status": self.status.value,
            "message": self.message,
            "result": self.result.as_dict() if self.result else None,
        }


class StepExecutor:
    """Resolve a single step and dispatch its data-only mutation."""

    def __init__(
        self,
        sink: MutationSink,
        *,
        bus: EventBus | None = None,
        clock: Clock | None = None,
        actor: str = "automation",
    ) -> None:
        self.sink = sink
        self.bus = bus
        self.clock: Clock = clock or SystemClock()
        self.actor = actor

    def execute(
        self,
        step: StepDefinition,
        *,
        playbook_ref: str,
        resolution: VariableResolution,
        outputs: Mapping[str, Any],
        run_id: str,
        commit: bool,
    ) -> StepOutcome:
        """Execute one step, returning a traceable outcome."""
        context = resolution.context(outputs)
        if step.condition is not None and not step.condition.matches(context):
            return StepOutcome(
                step=step,
                status=StepStatus.SKIPPED,
                message=f"Skipped: {step.condition.describe()}",
            )
        try:
            inputs = resolve_inputs(step.inputs, context)
        except VariableResolutionError as error:
            return StepOutcome(step=step, status=StepStatus.FAILED, message=error.message)
        intent = build_intent(step, inputs, playbook_ref=playbook_ref, run_id=run_id)
        if commit:
            result = self.sink.commit(intent)
            status = StepStatus.EXECUTED if result.applied else StepStatus.SKIPPED
            message = "Applied" if result.applied else "Already applied (idempotent)"
            self._publish(step, intent, result, run_id, outputs)
        else:
            result = self.sink.preview(intent)
            status = StepStatus.PLANNED
            message = "Planned (no write)"
        return StepOutcome(step=step, status=status, message=message, result=result)

    def _publish(
        self,
        step: StepDefinition,
        intent: MutationIntent,
        result: MutationResult,
        run_id: str,
        outputs: Mapping[str, Any],
    ) -> None:
        """Publish activity events only for committed runs."""
        if self.bus is None:
            return
        subject = try_parse(intent.target) if intent.target else None
        self.bus.publish(
            make_event(
                "automation.step.executed",
                subject,
                run_id=run_id,
                step_id=step.id,
                step_kind=step.kind.value,
                ref=result.ref,
            ),
            request_id=run_id,
        )
        if step.kind is StepKind.EMIT_EVENT:
            payload = intent.payload
            explicit = try_parse(str(payload.get("subject", "")))
            try:
                severity = EventSeverity(str(payload.get("severity", "info")))
            except ValueError:
                severity = EventSeverity.INFO
            self.bus.publish(
                DomainEvent(
                    kind=str(payload.get("event_kind", "automation.event")),
                    subject=explicit or subject,
                    actor=self.actor,
                    severity=severity,
                    payload={
                        "message": str(payload.get("message", "")),
                        "run_id": run_id,
                        "step_id": step.id,
                    },
                    correlation_id=run_id,
                ),
                request_id=run_id,
            )


def build_intent(
    step: StepDefinition,
    inputs: Mapping[str, Any],
    *,
    playbook_ref: str,
    run_id: str = "",
) -> MutationIntent:
    """Build a deterministic intent from a resolved step."""
    title = str(inputs.get("title", step.title))
    key_source = {
        "playbook": playbook_ref,
        "step": step.id,
        "inputs": inputs,
    }
    key = digest(key_source)
    prefix = f"auto_{slugify(step.id, max_length=32)}_{slugify(title, max_length=32)}"
    if step.kind in CREATE_COLLECTIONS:
        collection = CREATE_COLLECTIONS[step.kind]
        target = f"{collection[:-1]}:{prefix}"
        payload = dict(inputs)
        payload.setdefault("title", title)
        payload.setdefault("created_by", "automation")
        payload.setdefault("playbook_ref", playbook_ref)
        payload.setdefault("run_id", run_id)
        inverse = {"action": "delete", "collection": collection, "ref": target}
    elif step.kind is StepKind.ATTACH_EVIDENCE:
        evidence_ref = str(inputs.get("evidence_ref", ""))
        target_ref = str(inputs.get("target_ref", ""))
        link_kind = str(inputs.get("link_kind", "evidences"))
        target = digest([evidence_ref, target_ref, link_kind], size=12)
        payload = {
            "evidence_ref": _validate_ref(evidence_ref, "evidence_ref"),
            "target_ref": _validate_ref(target_ref, "target_ref"),
            "link_kind": link_kind,
            "label": str(inputs.get("label", "")),
        }
        inverse = {"action": "unlink", "link": target}
    else:
        event_kind = str(inputs.get("event_kind", "automation.event"))
        subject = inputs.get("subject")
        target = _validate_ref(str(subject), "subject") if subject else event_kind
        payload = {
            "event_kind": event_kind,
            "message": str(inputs.get("message", title)),
            "severity": str(inputs.get("severity", "info")),
            "subject": target,
            "run_id": run_id,
        }
        inverse = {"action": "compensating_event", "key": key}
    return MutationIntent(
        step_id=step.id,
        kind=step.kind,
        target=target,
        payload=payload,
        key=key,
        inverse=inverse,
    )


def _validate_ref(value: str, field: str) -> str:
    """Validate an entity reference input without executing anything."""
    parsed: EntityId | None = try_parse(value)
    if parsed is None:
        raise VariableResolutionError(f"Invalid entity reference for {field}: {value}", path=field)
    return str(parsed)


def new_run_id(playbook: PlaybookDefinition, values: Mapping[str, Value], clock: Clock) -> str:
    """Build a deterministic run id from playbook, values and clock instant."""
    return f"run_{digest([playbook.ref, dict(values), clock.now_timestamp()], size=12)}"
