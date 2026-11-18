"""Security and privacy helpers for RedScribe v2."""

from __future__ import annotations

from redscribe.v2.security.audit import (
    AuditAnalyzer,
    AuditFinding,
    AuditReport,
    analyze_events,
)
from redscribe.v2.security.consent import (
    ConsentDecision,
    ConsentFlag,
    ConsentRegistry,
    consent_summary,
)
from redscribe.v2.security.encryption import (
    EncryptedPayload,
    decrypt_bytes,
    decrypt_text,
    encrypt_bytes,
    encrypt_text,
)
from redscribe.v2.security.kdf import (
    DerivedKey,
    KdfParams,
    derive_key,
    derive_key_material,
    generate_salt,
)
from redscribe.v2.security.policies import (
    AccessDecision,
    AccessPolicy,
    PolicyEngine,
    PolicyRule,
    evaluate_access,
)
from redscribe.v2.security.privacy import (
    PRIVACY_LEVELS,
    PrivacyLevel,
    PrivacyMode,
    apply_privacy_level,
    parse_privacy_level,
    privacy_mode_for,
)
from redscribe.v2.security.redaction import (
    RedactionRule,
    RedactionSummary,
    apply_redactions,
    builtin_redaction_rules,
    redact_mapping,
)
from redscribe.v2.security.risk import (
    RiskAssessment,
    RiskFactor,
    RiskScore,
    assess_risk,
    score_factors,
)
from redscribe.v2.security.safety import (
    CommandSafety,
    UrlSafety,
    analyze_command,
    analyze_url,
    is_safe_command,
    is_safe_url,
)
from redscribe.v2.security.scrub import (
    ScrubPolicy,
    ScrubReport,
    scrub_export_payload,
    scrub_text,
)
from redscribe.v2.security.secrets import (
    SecretFinding,
    SecretPattern,
    SecretScanResult,
    builtin_secret_patterns,
    scan_secrets,
)

__all__ = [
    "PRIVACY_LEVELS",
    "AccessDecision",
    "AccessPolicy",
    "AuditAnalyzer",
    "AuditFinding",
    "AuditReport",
    "CommandSafety",
    "ConsentDecision",
    "ConsentFlag",
    "ConsentRegistry",
    "DerivedKey",
    "EncryptedPayload",
    "KdfParams",
    "PolicyEngine",
    "PolicyRule",
    "PrivacyLevel",
    "PrivacyMode",
    "RedactionRule",
    "RedactionSummary",
    "RiskAssessment",
    "RiskFactor",
    "RiskScore",
    "ScrubPolicy",
    "ScrubReport",
    "SecretFinding",
    "SecretPattern",
    "SecretScanResult",
    "UrlSafety",
    "analyze_command",
    "analyze_events",
    "analyze_url",
    "apply_privacy_level",
    "apply_redactions",
    "assess_risk",
    "builtin_redaction_rules",
    "builtin_secret_patterns",
    "consent_summary",
    "decrypt_bytes",
    "decrypt_text",
    "derive_key",
    "derive_key_material",
    "encrypt_bytes",
    "encrypt_text",
    "evaluate_access",
    "generate_salt",
    "is_safe_command",
    "is_safe_url",
    "parse_privacy_level",
    "privacy_mode_for",
    "redact_mapping",
    "scan_secrets",
    "score_factors",
    "scrub_export_payload",
    "scrub_text",
]
