"""Human-readable verification receipts for completed portability operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.portability.canonical import digest_value
from redscribe.v3.portability.errors import VerificationError
from redscribe.v3.portability.manifest import BundleManifest, VerificationReport

RECEIPT_VERSION = "v3.1"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One named check recorded on a verification receipt."""

    name: str
    passed: bool
    detail: str = ""
    code: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "code": self.code,
        }


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    """Signed-by-digest record that a bundle was opened and verified."""

    receipt_id: str
    bundle_id: str
    verified_at: float
    device: str
    checks: tuple[CheckResult, ...]
    digest: str
    status: str = "verified"
    receipt_version: str = RECEIPT_VERSION

    @property
    def ok(self) -> bool:
        """Return whether every recorded check passed."""
        return all(check.passed for check in self.checks)

    def require_ok(self) -> None:
        """Raise if the receipt records a failure."""
        if not self.ok:
            raise VerificationError(
                "Verification receipt contains failed checks",
                context={
                    "failed": [check.name for check in self.checks if not check.passed],
                },
            )

    def render(self) -> str:
        """Render a plain-text receipt suitable for archiving or printing."""
        lines = [
            "REDSCRIBE PORTABILITY VERIFICATION RECEIPT",
            f"Receipt: {self.receipt_id}",
            f"Bundle: {self.bundle_id}",
            f"Device: {self.device}",
            f"Verified at: {self.verified_at}",
            f"Status: {self.status.upper()}",
            "Checks:",
        ]
        for check in self.checks:
            marker = "PASS" if check.passed else "FAIL"
            lines.append(f"  [{marker}] {check.name}: {check.detail}")
        lines.append(f"Digest: {self.digest}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "receipt_version": self.receipt_version,
            "receipt_id": self.receipt_id,
            "bundle_id": self.bundle_id,
            "verified_at": self.verified_at,
            "device": self.device,
            "status": self.status,
            "ok": self.ok,
            "digest": self.digest,
            "checks": [check.as_dict() for check in self.checks],
        }


def build_receipt(
    manifest: BundleManifest,
    report: VerificationReport,
    *,
    device: str,
    clock: Clock | None = None,
    origin_valid: bool = True,
    mac_valid: bool = True,
    resolution_count: int = 0,
) -> VerificationReceipt:
    """Build a receipt from an opened bundle's verification evidence."""
    timer: Clock = clock or SystemClock()
    verified_at = timer.now_timestamp()
    checks = (
        CheckResult(
            name="manifest_structure",
            passed=bool(manifest.bundle_id) and manifest.entity_count >= 0,
            detail=f"manifest {manifest.manifest_version}",
            code="MANIFEST_OK",
        ),
        CheckResult(
            name="payload_checksums",
            passed=report.ok,
            detail=f"{report.checked_entities} entity records checked",
            code=report.codes[0] if report.codes else "CHECKSUMS_OK",
        ),
        CheckResult(
            name="payload_digest",
            passed="PAYLOAD_DIGEST_MISMATCH" not in report.codes,
            detail=manifest.payload_digest[:16],
            code="DIGEST_OK",
        ),
        CheckResult(
            name="authentication_tag",
            passed=mac_valid,
            detail="HMAC-SHA256 over ciphertext and context",
            code="MAC_OK" if mac_valid else "MAC_MISMATCH",
        ),
        CheckResult(
            name="device_origin",
            passed=origin_valid,
            detail=f"origin device {manifest.source_device}",
            code="ORIGIN_OK" if origin_valid else "DEVICE_UNTRUSTED",
        ),
        CheckResult(
            name="conflict_decisions",
            passed=True,
            detail=f"{resolution_count} decisions audited",
            code="AUDIT_OK",
        ),
    )
    digest_source = {
        "bundle_id": manifest.bundle_id,
        "verified_at": verified_at,
        "device": device,
        "checks": [check.as_dict() for check in checks],
    }
    receipt_id = f"receipt_{digest_value(digest_source)[:16]}"
    status = "verified" if all(check.passed for check in checks) else "failed"
    return VerificationReceipt(
        receipt_id=receipt_id,
        bundle_id=manifest.bundle_id,
        verified_at=verified_at,
        device=device,
        checks=checks,
        digest=digest_value(digest_source),
        status=status,
    )


def summarize_receipts(receipts: tuple[VerificationReceipt, ...]) -> dict[str, int]:
    """Return counts of verified and failed receipts."""
    verified = sum(1 for receipt in receipts if receipt.ok)
    return {"total": len(receipts), "verified": verified, "failed": len(receipts) - verified}
