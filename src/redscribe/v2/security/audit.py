"""Audit log analysis helpers for security-relevant events."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """A single observation derived from audit event analysis."""

    code: str
    severity: str
    message: str
    count: int = 1
    event_ids: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "count": self.count,
            "event_ids": list(self.event_ids),
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Aggregate audit analysis output."""

    total_events: int
    findings: tuple[AuditFinding, ...]
    counts_by_type: Mapping[str, int]
    counts_by_outcome: Mapping[str, int]
    timeline: tuple[dict[str, Any], ...]

    @property
    def highest_severity(self) -> str:
        rank = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        best = "none"
        best_rank = -1
        for finding in self.findings:
            current = rank.get(finding.severity, 0)
            if current > best_rank:
                best = finding.severity
                best_rank = current
        return best

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "highest_severity": self.highest_severity,
            "counts_by_type": dict(self.counts_by_type),
            "counts_by_outcome": dict(self.counts_by_outcome),
            "timeline": list(self.timeline),
            "findings": [finding.as_dict() for finding in self.findings],
        }


class AuditAnalyzer:
    """Analyze event streams for suspicious or risky patterns."""

    def __init__(self, *, failure_threshold: int = 5, window_minutes: int = 10) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if window_minutes < 1:
            raise ValueError("window_minutes must be positive")
        self.failure_threshold = failure_threshold
        self.window_minutes = window_minutes

    def analyze(self, events: Sequence[Mapping[str, Any]]) -> AuditReport:
        normalized = [normalize_event(event) for event in events]
        type_counts = Counter(event["type"] for event in normalized)
        outcome_counts = Counter(event["outcome"] for event in normalized)
        findings: list[AuditFinding] = []
        findings.extend(self._auth_failures(normalized))
        findings.extend(self._rate_limits(normalized))
        findings.extend(self._denied_actions(normalized))
        findings.extend(self._sensitive_exports(normalized))
        findings.extend(self._anomalous_clients(normalized))
        timeline = build_timeline(normalized)
        return AuditReport(
            total_events=len(normalized),
            findings=tuple(sorted(findings, key=_finding_sort_key)),
            counts_by_type=dict(sorted(type_counts.items())),
            counts_by_outcome=dict(sorted(outcome_counts.items())),
            timeline=timeline,
        )

    def _auth_failures(self, events: Sequence[Mapping[str, Any]]) -> list[AuditFinding]:
        failures = [
            event
            for event in events
            if event["type"] in {"auth", "login"} and event["outcome"] == "failure"
        ]
        if len(failures) < self.failure_threshold:
            return []
        by_actor: dict[str, list[Mapping[str, Any]]] = {}
        for event in failures:
            by_actor.setdefault(event["actor"] or "unknown", []).append(event)
        findings: list[AuditFinding] = []
        for actor, actor_events in sorted(by_actor.items()):
            if len(actor_events) < self.failure_threshold:
                continue
            findings.append(
                AuditFinding(
                    code="auth_failure_burst",
                    severity="high"
                    if len(actor_events) >= self.failure_threshold * 2
                    else "medium",
                    message=f"Repeated authentication failures for actor '{actor}'.",
                    count=len(actor_events),
                    event_ids=tuple(event["id"] for event in actor_events[:10]),
                    details={"actor": actor},
                )
            )
        if not findings and len(failures) >= self.failure_threshold:
            findings.append(
                AuditFinding(
                    code="auth_failures",
                    severity="medium",
                    message="Multiple authentication failures observed.",
                    count=len(failures),
                    event_ids=tuple(event["id"] for event in failures[:10]),
                )
            )
        return findings

    def _rate_limits(self, events: Sequence[Mapping[str, Any]]) -> list[AuditFinding]:
        limited = [
            event
            for event in events
            if event["type"] in {"rate_limit", "throttle"} or event["outcome"] == "rate_limited"
        ]
        if not limited:
            return []
        severity = "high" if len(limited) >= 10 else "medium"
        return [
            AuditFinding(
                code="rate_limit_pressure",
                severity=severity,
                message="Rate limiting events indicate abusive or repeated access attempts.",
                count=len(limited),
                event_ids=tuple(event["id"] for event in limited[:10]),
            )
        ]

    def _denied_actions(self, events: Sequence[Mapping[str, Any]]) -> list[AuditFinding]:
        denied = [
            event for event in events if event["outcome"] in {"denied", "blocked", "forbidden"}
        ]
        if not denied:
            return []
        action_counts = Counter(event["action"] for event in denied if event["action"])
        details = dict(sorted(action_counts.items()))
        severity = "medium" if len(denied) < 10 else "high"
        return [
            AuditFinding(
                code="policy_denials",
                severity=severity,
                message="Access control denials were recorded.",
                count=len(denied),
                event_ids=tuple(event["id"] for event in denied[:10]),
                details={"actions": details},
            )
        ]

    def _sensitive_exports(self, events: Sequence[Mapping[str, Any]]) -> list[AuditFinding]:
        exports = [
            event
            for event in events
            if event["type"] in {"export", "share"}
            and bool(event["details"].get("contains_secrets") or event["details"].get("sensitive"))
        ]
        if not exports:
            return []
        return [
            AuditFinding(
                code="sensitive_exports",
                severity="high",
                message="Sensitive exports were observed; review consent and redaction coverage.",
                count=len(exports),
                event_ids=tuple(event["id"] for event in exports[:10]),
            )
        ]

    def _anomalous_clients(self, events: Sequence[Mapping[str, Any]]) -> list[AuditFinding]:
        by_client = Counter(event["client"] for event in events if event["client"])
        findings: list[AuditFinding] = []
        for client, count in sorted(by_client.items()):
            if count < max(20, self.failure_threshold * 4):
                continue
            findings.append(
                AuditFinding(
                    code="client_volume_spike",
                    severity="medium",
                    message=f"Client '{client}' generated unusually high event volume.",
                    count=count,
                    details={"client": client},
                )
            )
        return findings


def normalize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize heterogeneous event payloads into a stable shape."""
    details = event.get("details")
    if not isinstance(details, Mapping):
        details = {}
    event_type = str(event.get("type") or event.get("kind") or event.get("event") or "event")
    outcome = str(event.get("outcome") or event.get("status") or event.get("result") or "unknown")
    action = str(event.get("action") or event.get("route") or "")
    actor = str(event.get("actor") or event.get("user") or "")
    client = str(event.get("client") or event.get("ip") or "")
    identifier = str(event.get("id") or event.get("event_id") or event.get("request_id") or "")
    timestamp = _coerce_timestamp(event.get("timestamp") or event.get("time") or event.get("at"))
    return {
        "id": identifier,
        "type": event_type.lower(),
        "outcome": outcome.lower(),
        "action": action,
        "actor": actor,
        "client": client,
        "timestamp": timestamp,
        "details": dict(details),
    }


def build_timeline(events: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    buckets: dict[str, Counter[str]] = {}
    for event in events:
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, datetime):
            continue
        key = timestamp.replace(minute=0, second=0, microsecond=0).isoformat()
        bucket = buckets.setdefault(key, Counter())
        bucket[event.get("outcome", "unknown")] += 1
        bucket[event.get("type", "event")] += 1
    timeline: list[dict[str, Any]] = []
    for key in sorted(buckets):
        entry: dict[str, Any] = {"bucket": key}
        entry.update({name: int(count) for name, count in buckets[key].items()})
        timeline.append(entry)
    return tuple(timeline)


def _coerce_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _finding_sort_key(finding: AuditFinding) -> tuple[int, str, int]:
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(finding.severity, 5)
    return (rank, finding.code, -finding.count)


def analyze_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Convenience wrapper returning a serializable audit report."""
    return AuditAnalyzer().analyze(events).as_dict()
