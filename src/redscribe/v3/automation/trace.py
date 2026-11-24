"""Hash-chained traces, timelines and field-level diffs."""

from __future__ import annotations

from typing import Any

from redscribe.v3.automation.encoding import chain_digest, copy_value, flatten
from redscribe.v3.automation.executor import StepOutcome
from redscribe.v3.automation.types import (
    DiffEntry,
    DryRunTrace,
    RunMode,
    RunRecord,
    StepDefinition,
    TraceEntry,
)


class TraceRecorder:
    """Accumulate trace entries with a tamper-evident hash chain."""

    def __init__(self) -> None:
        self._chain = ""
        self._entries: list[TraceEntry] = []

    def record(
        self,
        step: StepDefinition,
        outcome: StepOutcome,
        *,
        variables: dict[str, Any] | None = None,
    ) -> TraceEntry:
        """Append one entry and extend the chain."""
        safe_variables = copy_value(variables or {})
        provisional = TraceEntry(
            index=len(self._entries),
            step_id=step.id,
            status=outcome.status,
            kind=step.kind,
            message=outcome.message,
            variables=safe_variables,
            result=outcome.result,
        )
        self._chain = chain_digest(self._chain, _entry_unsigned(provisional))
        entry = TraceEntry(
            index=provisional.index,
            step_id=provisional.step_id,
            status=provisional.status,
            kind=provisional.kind,
            message=provisional.message,
            variables=provisional.variables,
            result=provisional.result,
            chain=self._chain,
        )
        self._entries.append(entry)
        return entry

    def finish(
        self,
        *,
        playbook_ref: str,
        mode: RunMode,
        variables: dict[str, Any],
        input_fingerprint: str,
        state_digest: str,
    ) -> DryRunTrace:
        """Freeze the recorded entries into an immutable trace."""
        writes = sum(
            1 for entry in self._entries if entry.result is not None and entry.result.applied
        )
        return DryRunTrace(
            playbook_ref=playbook_ref,
            mode=mode,
            entries=tuple(self._entries),
            variables=copy_value(variables),
            digest=self._chain,
            writes=writes,
            input_fingerprint=input_fingerprint,
            state_digest=state_digest,
        )

    @property
    def entries(self) -> tuple[TraceEntry, ...]:
        """Return entries recorded so far."""
        return tuple(self._entries)


def _entry_unsigned(entry: TraceEntry) -> dict[str, Any]:
    """Return the hashable portion of a trace entry."""
    return {
        "index": entry.index,
        "step_id": entry.step_id,
        "status": entry.status.value,
        "kind": entry.kind.value,
        "message": entry.message,
        "variables": entry.variables,
        "result": entry.result.as_dict() if entry.result else None,
    }


def timeline(trace: DryRunTrace) -> tuple[dict[str, Any], ...]:
    """Render a trace as an ordered timeline for the UI."""
    result: list[dict[str, Any]] = []
    for entry in trace.entries:
        intent = entry.result.intent if entry.result else None
        result.append(
            {
                "index": entry.index,
                "step_id": entry.step_id,
                "title": entry.step_id,
                "status": entry.status.value,
                "kind": entry.kind.value,
                "message": entry.message,
                "target": intent.target if intent else "",
                "mutation": intent.as_dict() if intent else None,
                "tone": _tone(entry.status.value),
                "chain": entry.chain,
            }
        )
    return tuple(result)


def _tone(status: str) -> str:
    """Map a step status to a semantic color tone."""
    return {
        "executed": "good",
        "planned": "info",
        "skipped": "warn",
        "failed": "bad",
    }.get(status, "neutral")


def _trace_rows(trace: DryRunTrace) -> dict[str, dict[str, Any]]:
    """Normalize a trace into comparable rows keyed by step and occurrence."""
    counts: dict[str, int] = {}
    rows: dict[str, dict[str, Any]] = {}
    for entry in trace.entries:
        occurrence = counts.get(entry.step_id, 0)
        counts[entry.step_id] = occurrence + 1
        key = f"{entry.step_id}[{occurrence}]"
        rows[key] = {
            "status": entry.status.value,
            "kind": entry.kind.value,
            "message": entry.message,
            "target": entry.result.ref if entry.result else "",
            "intent": entry.result.intent.as_dict() if entry.result else None,
        }
    return rows


def diff_traces(first: DryRunTrace, second: DryRunTrace) -> tuple[DiffEntry, ...]:
    """Return field-level differences between two traces."""
    left = _trace_rows(first)
    right = _trace_rows(second)
    differences: list[DiffEntry] = []
    for key in sorted(set(left) | set(right)):
        before = left.get(key)
        after = right.get(key)
        if before is None or after is None:
            differences.append(DiffEntry(f"steps.{key}", before, after))
            continue
        for path, value in flatten(before).items():
            other = flatten(after).get(path)
            if value != other:
                differences.append(DiffEntry(f"steps.{key}.{path}", value, other))
    if first.input_fingerprint != second.input_fingerprint:
        differences.append(
            DiffEntry("input_fingerprint", first.input_fingerprint, second.input_fingerprint)
        )
    return tuple(differences)


def diff_runs(first: RunRecord, second: RunRecord) -> tuple[DiffEntry, ...]:
    """Compare run metadata and traces for the run history view."""
    differences: list[DiffEntry] = []
    for field_name in ("status", "mode", "trace_digest", "state_digest", "rollback_of"):
        left = getattr(first, field_name)
        right = getattr(second, field_name)
        left_value = left.value if hasattr(left, "value") else left
        right_value = right.value if hasattr(right, "value") else right
        if left_value != right_value:
            differences.append(DiffEntry(field_name, left_value, right_value))
    differences.extend(diff_traces(_as_trace(first), _as_trace(second)))
    return tuple(differences)


def _as_trace(record: RunRecord) -> DryRunTrace:
    """Adapt a persisted run record to a trace for diffing."""
    return DryRunTrace(
        playbook_ref=record.playbook_ref,
        mode=record.mode,
        entries=record.trace,
        variables=record.variables,
        digest=record.trace_digest,
        input_fingerprint=record.input_fingerprint,
        state_digest=record.state_digest,
    )
