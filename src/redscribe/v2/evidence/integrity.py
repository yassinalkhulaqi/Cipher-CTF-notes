"""Integrity verification for records, payloads, custody, and manifests."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from redscribe.v2.evidence.errors import ValidationError
from redscribe.v2.evidence.hashing import digest_matches, hash_bytes
from redscribe.v2.evidence.models import (
    CustodyEvent,
    IntegrityIssue,
    IntegrityReport,
    IntegritySeverity,
    IntegrityState,
    ManifestEntry,
)
from redscribe.v2.evidence.records import validate_record
from redscribe.v2.evidence.validation import now_iso

UNSET: object = object()

SEVERITY_RANK: dict[IntegritySeverity, int] = {
    IntegritySeverity.INFO: 0,
    IntegritySeverity.WARNING: 1,
    IntegritySeverity.CRITICAL: 2,
}

STATE_LABELS: dict[IntegrityState, str] = {
    IntegrityState.VERIFIED: "Verified",
    IntegrityState.MISMATCH: "Hash mismatch",
    IntegrityState.MISSING: "Payload missing",
    IntegrityState.UNVERIFIED: "Not verified",
    IntegrityState.ERROR: "Integrity error",
}

STATE_TONES: dict[IntegrityState, str] = {
    IntegrityState.VERIFIED: "success",
    IntegrityState.MISMATCH: "danger",
    IntegrityState.MISSING: "warning",
    IntegrityState.UNVERIFIED: "neutral",
    IntegrityState.ERROR: "danger",
}


def issue(
    code: str,
    message: str,
    *,
    severity: IntegritySeverity = IntegritySeverity.WARNING,
    field: str = "",
    expected: str = "",
    actual: str = "",
) -> IntegrityIssue:
    """Build an integrity issue with standardized defaults."""
    return IntegrityIssue(
        code=code,
        severity=severity,
        message=message,
        field=field,
        expected=expected,
        actual=actual,
    )


def state_for(issues: Sequence[IntegrityIssue], *, verified: bool = False) -> IntegrityState:
    """Choose the overall state for a set of issues."""
    codes = {item.code for item in issues}
    if "record_invalid" in codes or "custody_invalid" in codes:
        return IntegrityState.ERROR
    if "blob_missing" in codes or "manifest_missing" in codes:
        return IntegrityState.MISSING
    if any(item.severity is IntegritySeverity.CRITICAL for item in issues):
        return IntegrityState.MISMATCH
    if verified and not issues:
        return IntegrityState.VERIFIED
    return IntegrityState.UNVERIFIED


class IntegrityVerifier:
    """Verifier that compares stored metadata with observed bytes."""

    def __init__(self, *, require_md5: bool = False, require_custody: bool = False) -> None:
        self._require_md5 = require_md5
        self._require_custody = require_custody

    def verify_record(
        self,
        record: Any,
        *,
        data: object = UNSET,
        custody: Sequence[CustodyEvent] | None = None,
        manifest: ManifestEntry | None = None,
        now: str = "",
    ) -> IntegrityReport:
        """Verify one evidence record and return a structured report."""
        issues: list[IntegrityIssue] = []
        try:
            validate_record(record)
        except ValidationError as exc:
            issues.append(
                issue(
                    "record_invalid",
                    exc.message,
                    severity=IntegritySeverity.CRITICAL,
                    field="record",
                )
            )

        digest_ok = False
        if data is UNSET:
            issues.append(
                issue(
                    "blob_unavailable",
                    "Payload bytes were not supplied for verification",
                    field="stored_path",
                )
            )
        elif not isinstance(data, bytes):
            issues.append(
                issue(
                    "blob_missing",
                    "Payload bytes are missing from storage",
                    severity=IntegritySeverity.CRITICAL,
                    field="stored_path",
                    expected=record.stored_path,
                )
            )
        else:
            observed = hash_bytes(data)
            sha_ok = digest_matches(observed.sha256, record.sha256)
            md5_ok = digest_matches(observed.md5, record.md5)
            digest_ok = sha_ok and (md5_ok or not self._require_md5)
            if not sha_ok:
                issues.append(
                    issue(
                        "digest_sha256_mismatch",
                        "SHA-256 digest does not match the record",
                        severity=IntegritySeverity.CRITICAL,
                        field="sha256",
                        expected=record.sha256,
                        actual=observed.sha256,
                    )
                )
            if not md5_ok:
                issues.append(
                    issue(
                        "digest_md5_mismatch",
                        "MD5 digest does not match the record",
                        field="md5",
                        expected=record.md5,
                        actual=observed.md5,
                    )
                )
            if observed.size_bytes != record.size_bytes:
                issues.append(
                    issue(
                        "size_mismatch",
                        "Payload size does not match the record",
                        severity=IntegritySeverity.CRITICAL,
                        field="size_bytes",
                        expected=str(record.size_bytes),
                        actual=str(observed.size_bytes),
                    )
                )

        custody_ok = False
        if custody is None:
            if self._require_custody:
                issues.append(
                    issue(
                        "custody_missing",
                        "No chain of custody was supplied",
                        field="custody",
                    )
                )
        elif not custody:
            issues.append(
                issue(
                    "custody_empty",
                    "The chain of custody has no events",
                    field="custody",
                )
            )
        else:
            valid, problems = self.verify_custody(custody, evidence_id=record.id)
            custody_ok = valid
            for problem in problems:
                issues.append(
                    issue(
                        "custody_invalid",
                        problem,
                        severity=IntegritySeverity.CRITICAL,
                        field="custody",
                    )
                )

        manifest_ok = False
        if manifest is not None:
            manifest_ok = self.verify_manifest_entry(record, manifest, issues)

        verified = digest_ok and (custody_ok or not self._require_custody)
        return IntegrityReport(
            evidence_id=record.id,
            state=state_for(issues, verified=verified),
            checked_at=now or now_iso(),
            digest_match=digest_ok,
            custody_valid=custody_ok,
            manifest_match=manifest_ok,
            issues=tuple(issues),
        )

    def verify_custody(
        self,
        events: Sequence[CustodyEvent],
        *,
        evidence_id: str = "",
    ) -> tuple[bool, list[str]]:
        """Verify a custody chain using the canonical hash rules."""
        from redscribe.v2.evidence.custody import CustodyChain

        relevant = [item for item in events if not evidence_id or item.evidence_id == evidence_id]
        chain = CustodyChain(relevant)
        return chain.verify(evidence_id)

    def verify_manifest_entry(
        self,
        record: Any,
        entry: ManifestEntry,
        issues: list[IntegrityIssue],
    ) -> bool:
        """Compare a record with a manifest entry, appending any issues."""
        matches = True
        if not digest_matches(entry.sha256, record.sha256):
            matches = False
            issues.append(
                issue(
                    "manifest_sha256_mismatch",
                    "Manifest SHA-256 does not match the record",
                    severity=IntegritySeverity.CRITICAL,
                    field="manifest.sha256",
                    expected=entry.sha256,
                    actual=record.sha256,
                )
            )
        if not digest_matches(entry.md5, record.md5):
            matches = False
            issues.append(
                issue(
                    "manifest_md5_mismatch",
                    "Manifest MD5 does not match the record",
                    field="manifest.md5",
                    expected=entry.md5,
                    actual=record.md5,
                )
            )
        if entry.size_bytes != record.size_bytes:
            matches = False
            issues.append(
                issue(
                    "manifest_size_mismatch",
                    "Manifest size does not match the record",
                    severity=IntegritySeverity.CRITICAL,
                    field="manifest.size_bytes",
                    expected=str(entry.size_bytes),
                    actual=str(record.size_bytes),
                )
            )
        return matches

    def verify_many(
        self,
        records: Iterable[Any],
        *,
        blobs: Mapping[str, object] | None = None,
        custody: Mapping[str, Sequence[CustodyEvent]] | None = None,
        manifests: Mapping[str, ManifestEntry] | None = None,
        now: str = "",
    ) -> list[IntegrityReport]:
        """Verify many records with per-item evidence inputs."""
        available_blobs = blobs or {}
        available_custody = custody or {}
        available_manifests = manifests or {}
        return [
            self.verify_record(
                record,
                data=available_blobs.get(record.id, UNSET),
                custody=available_custody.get(record.id),
                manifest=available_manifests.get(record.id),
                now=now,
            )
            for record in records
        ]


def worst_state(reports: Sequence[IntegrityReport]) -> IntegrityState:
    """Return the most severe state present in a set of reports."""
    order = (
        IntegrityState.UNVERIFIED,
        IntegrityState.VERIFIED,
        IntegrityState.MISSING,
        IntegrityState.MISMATCH,
        IntegrityState.ERROR,
    )
    best = IntegrityState.VERIFIED
    for report in reports:
        if order.index(report.state) > order.index(best):
            best = report.state
    return best if reports else IntegrityState.UNVERIFIED


def integrity_badge(report: IntegrityReport) -> dict[str, str]:
    """Render UI metadata for an integrity report."""
    return {
        "label": STATE_LABELS[report.state],
        "tone": STATE_TONES[report.state],
        "state": report.state.value,
        "detail": report.issues[0].message if report.issues else "All checks passed",
    }


def report_summary(reports: Sequence[IntegrityReport]) -> dict[str, Any]:
    """Aggregate verification results for dashboards."""
    counts = {state.value: 0 for state in IntegrityState}
    for report in reports:
        counts[report.state.value] += 1
    return {
        "total": len(reports),
        "states": counts,
        "verified": counts[IntegrityState.VERIFIED.value],
        "alerts": counts[IntegrityState.MISMATCH.value] + counts[IntegrityState.ERROR.value],
        "worst_state": worst_state(reports).value,
        "issue_count": sum(len(report.issues) for report in reports),
    }


def sort_issues(issues: Iterable[IntegrityIssue]) -> list[IntegrityIssue]:
    """Sort issues by severity and code for stable display."""
    return sorted(
        issues,
        key=lambda item: (-SEVERITY_RANK[item.severity], item.code, item.field),
    )
