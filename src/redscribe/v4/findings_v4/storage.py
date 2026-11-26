"""Persistence adapters for findings and their retest audit trail.

:class:`FindingStore` is an in-memory adapter that keeps secondary indexes by
severity and lifecycle state. It implements the :class:`FindingStorage`
protocol, so a SQLite-backed adapter can be dropped in without changing the
service or API layers. Snapshots are plain dictionaries suitable for JSON
serialisation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from .types import Finding, LifecycleState, RetestRecord, Severity

SNAPSHOT_VERSION = 1


class FindingStorage(Protocol):
    """The storage contract consumed by the finding service and API."""

    def add(self, finding: Finding) -> None: ...

    def get(self, finding_id: str) -> Finding | None: ...

    def update(self, finding: Finding) -> None: ...

    def delete(self, finding_id: str) -> None: ...

    def all(self) -> list[Finding]: ...

    def by_severity(self, severity: Severity) -> tuple[Finding, ...]: ...

    def by_state(self, state: LifecycleState) -> tuple[Finding, ...]: ...

    def add_retest(self, record: RetestRecord) -> None: ...

    def retests(self, finding_id: str) -> tuple[RetestRecord, ...]: ...


class FindingStore:
    """A deterministic in-memory store with severity and state indexes."""

    def __init__(self, findings: Iterable[Finding] = ()) -> None:
        self._findings: dict[str, Finding] = {}
        self._by_severity: dict[Severity, set[str]] = {item: set() for item in Severity}
        self._by_state: dict[LifecycleState, set[str]] = {item: set() for item in LifecycleState}
        self._retests: dict[str, list[RetestRecord]] = {}
        self._index_state: dict[str, tuple[Severity, LifecycleState]] = {}
        for finding in findings:
            self.add(finding)

    def _index(self, finding: Finding) -> None:
        self._by_severity[finding.severity].add(finding.id)
        self._by_state[finding.lifecycle_state].add(finding.id)
        self._index_state[finding.id] = (finding.severity, finding.lifecycle_state)

    def _unindex(self, finding_id: str) -> None:
        """Remove the index entries recorded when the id was last indexed.

        Findings are mutable records and callers may edit them in place before
        calling :meth:`update`, so the previous index values cannot be read back
        from the object itself.
        """
        previous = self._index_state.pop(finding_id, None)
        if previous is None:
            return
        severity, state = previous
        self._by_severity[severity].discard(finding_id)
        self._by_state[state].discard(finding_id)

    def add(self, finding: Finding) -> None:
        """Insert a finding, rejecting duplicate identifiers."""
        if finding.id in self._findings:
            raise ValueError(f"duplicate finding id: {finding.id}")
        self._findings[finding.id] = finding
        self._index(finding)

    def get(self, finding_id: str) -> Finding | None:
        """Return a finding by id, or ``None`` when absent."""
        return self._findings.get(finding_id)

    def update(self, finding: Finding) -> None:
        """Replace a stored finding and refresh its index entries."""
        existing = self._findings.get(finding.id)
        if existing is None:
            raise KeyError(f"unknown finding id: {finding.id}")
        self._unindex(finding.id)
        self._findings[finding.id] = finding
        self._index(finding)

    def delete(self, finding_id: str) -> Finding:
        """Remove a finding and its retest history, returning the removed item."""
        finding = self._findings.pop(finding_id, None)
        if finding is None:
            raise KeyError(f"unknown finding id: {finding_id}")
        self._unindex(finding_id)
        self._retests.pop(finding_id, None)
        return finding

    def all(self) -> list[Finding]:
        """Return all findings in deterministic creation order."""
        return sorted(self._findings.values(), key=lambda item: (item.created_at, item.id))

    def ids(self) -> tuple[str, ...]:
        """Return stored identifiers in deterministic order."""
        return tuple(sorted(self._findings))

    def by_severity(self, severity: Severity) -> tuple[Finding, ...]:
        """Return findings in a severity bucket."""
        return tuple(
            self._findings[item]
            for item in sorted(self._by_severity[severity])
            if item in self._findings
        )

    def by_state(self, state: LifecycleState) -> tuple[Finding, ...]:
        """Return findings in a lifecycle-state bucket."""
        return tuple(
            self._findings[item] for item in sorted(self._by_state[state]) if item in self._findings
        )

    def by_severity_at_least(self, minimum: Severity) -> tuple[Finding, ...]:
        """Return findings whose severity rank meets or exceeds ``minimum``."""
        return tuple(finding for finding in self.all() if finding.severity.rank >= minimum.rank)

    def add_retest(self, record: RetestRecord) -> None:
        """Append a retest record to a finding's audit trail."""
        if record.finding_id not in self._findings:
            raise KeyError(f"unknown finding id: {record.finding_id}")
        history = self._retests.setdefault(record.finding_id, [])
        if any(item.sequence == record.sequence for item in history):
            raise ValueError(f"duplicate retest sequence: {record.sequence}")
        history.append(record)

    def retests(self, finding_id: str) -> tuple[RetestRecord, ...]:
        """Return a finding's retest records ordered by sequence."""
        return tuple(sorted(self._retests.get(finding_id, ()), key=lambda item: item.sequence))

    def retest_count(self) -> int:
        """Return the total number of retest records across all findings."""
        return sum(len(items) for items in self._retests.values())

    def count(self) -> int:
        """Return the number of stored findings."""
        return len(self._findings)

    def __len__(self) -> int:
        return len(self._findings)

    def __contains__(self, finding_id: object) -> bool:
        return finding_id in self._findings

    def severity_counts(self) -> dict[str, int]:
        """Return a severity-to-count summary for every severity band."""
        return {item.value: len(self._by_severity[item]) for item in Severity}

    def state_counts(self) -> dict[str, int]:
        """Return a state-to-count summary for every lifecycle state."""
        return {item.value: len(self._by_state[item]) for item in LifecycleState}

    def clear(self) -> None:
        """Remove all findings, retests and index entries."""
        self._findings.clear()
        self._retests.clear()
        for severity in self._by_severity:
            self._by_severity[severity].clear()
        for state in self._by_state:
            self._by_state[state].clear()

    def snapshot(self) -> dict[str, Any]:
        """Export a JSON-safe snapshot including derived indexes."""
        return {
            "version": SNAPSHOT_VERSION,
            "findings": [finding.to_dict() for finding in self.all()],
            "retests": [
                record.to_dict() for finding in self.all() for record in self.retests(finding.id)
            ],
            "indexes": {
                "severity": self.severity_counts(),
                "state": self.state_counts(),
            },
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore a store from a snapshot, validating index consistency."""
        version = snapshot.get("version")
        if version != SNAPSHOT_VERSION:
            raise ValueError(f"unsupported snapshot version: {version!r}")
        raw_findings = snapshot.get("findings")
        raw_retests = snapshot.get("retests")
        if not isinstance(raw_findings, list) or not isinstance(raw_retests, list):
            raise ValueError("snapshot must contain findings and retests lists")
        replacement = FindingStore()
        for raw in raw_findings:
            if not isinstance(raw, dict):
                raise ValueError("finding entries must be mappings")
            replacement.add(Finding.from_dict(raw))
        for raw in raw_retests:
            if not isinstance(raw, dict):
                raise ValueError("retest entries must be mappings")
            replacement.add_retest(RetestRecord.from_dict(raw))
        indexes = snapshot.get("indexes")
        if isinstance(indexes, dict):
            severity = indexes.get("severity")
            state = indexes.get("state")
            if isinstance(severity, dict) and severity != replacement.severity_counts():
                raise ValueError("snapshot severity index is inconsistent")
            if isinstance(state, dict) and state != replacement.state_counts():
                raise ValueError("snapshot state index is inconsistent")
        self.clear()
        self._findings = replacement._findings
        self._by_severity = replacement._by_severity
        self._by_state = replacement._by_state
        self._retests = replacement._retests
        self._index_state = replacement._index_state
