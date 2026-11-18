# Security and Privacy (V2)

`dev/v2-09-security-privacy` adds an additive security and privacy namespace for RedScribe V2. The branch provides backend helpers, a v2 API namespace, frontend feature modules, and tests without changing shared v1 routes or core storage contracts.

## Backend package

`src/redscribe/v2/security/` exposes stdlib-only helpers for local-first security workflows:

- `secrets.py` – secret detection patterns, entropy-aware scanning, masking, and payload scans.
- `redaction.py` – deterministic redaction rules, scoped application, and mapping redaction helpers.
- `encryption.py` – passphrase-based encryption/decryption helpers for UTF-8 text and bytes with authenticated payload envelopes.
- `kdf.py` – PBKDF2-HMAC-SHA256 parameter handling, salt generation, key derivation wrappers, and verification helpers.
- `policies.py` – access policy rules, decision evaluation, and a conservative default policy for export/scan operations.
- `privacy.py` – privacy levels (`open`, `standard`, `sensitive`, `strict`), control defaults, and override merging.
- `audit.py` – audit event normalization and analysis for authentication bursts, rate-limit pressure, policy denials, sensitive exports, and timeline summaries.
- `consent.py` – consent flag definitions, decision tracking, summaries, and required-consent lookup.
- `safety.py` – URL and shell command safety analysis for external links and copy/execute workflows.
- `scrub.py` – safe export scrubbing for text and structured payloads with removal, masking, and redaction reporting.
- `risk.py` – weighted risk factors and aggregate security/privacy risk scoring.

## API namespace

`src/redscribe/ui/web/v2/namespaces/security.py` exposes `register(api)` and registers additive `security.*` routes on an existing `ApiV2` instance.

Primary routes:

- `security.health` – namespace capabilities and counts.
- `security.secret_patterns`, `security.scan_secrets`, `security.scan_payload` – secret detection.
- `security.redaction_rules`, `security.redact_text`, `security.redact_payload` – redaction controls.
- `security.derive_key`, `security.encrypt_text`, `security.decrypt_text` – key derivation and encryption helpers.
- `security.privacy_levels`, `security.privacy_mode` – privacy level resolution and overrides.
- `security.consent_flags`, `security.consent_summary` – consent state management helpers.
- `security.policy_defaults`, `security.evaluate_access` – access policy evaluation.
- `security.audit_analyze` – audit event analysis.
- `security.scrub_text`, `security.scrub_export` – safe export scrubbing.
- `security.check_url`, `security.check_command` – URL/command safety checks.
- `security.assess_risk`, `security.security_dashboard` – risk scoring and aggregated dashboard data.

The namespace is additive: it uses the v2 route registration hook and does not modify shared `routes.py`, `api.py`, `server.py`, `db.py`, or storage migration modules.

## Frontend feature

`frontend/src/features/security/` provides feature-local UI and helpers:

- `types.ts` – typed contracts for scans, redaction, privacy, consent, policy, audit, safety, and risk data.
- `helpers.ts` – pure helpers for severity handling, summaries, filtering, grouping, dashboard alerts, and formatting.
- `safeLink.ts` – safe-link and safe-command decisions, URL sanitization, and display helpers.
- `client.ts` – `SecurityClient` wrapper over `V2Client` for `security.*` routes.
- `SecretScannerUI.tsx` – secret scanning, filtering, and reveal/hide controls.
- `RedactionControls.tsx` – rule toggles and redaction preview/application controls.
- `PrivacyModeSettings.tsx` – privacy level selection, control overrides, and consent flags.
- `RiskDashboard.tsx` – aggregated risk, alerts, recommendations, and safety summaries.
- `AuditViewer.tsx` – audit findings, outcome/type breakdowns, and timeline view.

`frontend/src/App.tsx`, `frontend/src/ui/index.ts`, and `frontend/src/app/routes.ts` are intentionally unchanged; integration can be performed by future feature wiring.

## Tests

- Python: `tests/v2_security/` covers secret detection, redaction/scrubbing, encryption/KDF, policies/privacy/consent, audit/safety/risk, and namespace route behavior.
- Frontend: `frontend/scripts/security.test.ts` covers pure helpers, safe-link/command decisions, and `SecurityClient` route mapping via the node test harness.

## Notes

- Encryption helpers are implemented with Python stdlib primitives only.
- Privacy defaults favor local-first safety: stricter levels restrict external links, command copying, and sensitive exports.
- Risk scoring combines secret exposure, audit findings, privacy posture, consent state, and URL/command safety signals into a single assessment for dashboard use.
