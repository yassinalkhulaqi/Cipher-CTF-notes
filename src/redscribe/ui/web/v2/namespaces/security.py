"""Additive v2 API namespace for security and privacy workflows."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.contracts import (
    V2Error,
    V2ErrorCode,
    compute_etag,
    optional_str,
    require_str,
)
from redscribe.ui.web.v2.routes import RouteResult
from redscribe.v2.security.audit import analyze_events
from redscribe.v2.security.consent import DEFAULT_FLAGS, ConsentRegistry
from redscribe.v2.security.encryption import decrypt_text, encrypt_text
from redscribe.v2.security.kdf import KdfParams, derive_key
from redscribe.v2.security.policies import (
    AccessDecision,
    AccessPolicy,
    PolicyEffect,
    PolicyRule,
    default_access_policy,
    evaluate_access,
)
from redscribe.v2.security.privacy import (
    apply_privacy_level,
    merge_privacy_preferences,
)
from redscribe.v2.security.redaction import (
    RedactionRule,
    apply_redactions,
    builtin_redaction_rules,
    redact_mapping,
)
from redscribe.v2.security.risk import assess_risk
from redscribe.v2.security.safety import analyze_command, analyze_url
from redscribe.v2.security.scrub import ScrubPolicy, scrub_export_payload, scrub_text
from redscribe.v2.security.secrets import builtin_secret_patterns, scan_mapping, scan_secrets

Handler = Callable[[dict[str, Any]], RouteResult]


class Registrar(Protocol):
    @property
    def vault(self) -> Vault: ...

    def register(
        self,
        name: str,
        handler: Handler,
        description: str,
        *,
        required: tuple[str, ...] = (),
        optional: tuple[str, ...] = (),
        mutating: bool = False,
        entity_type: str = "",
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class RouteSpec:
    action: str
    description: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    mutating: bool = False


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("health", "Report security namespace capabilities and defaults."),
    RouteSpec("secret_patterns", "List available secret detection patterns."),
    RouteSpec(
        "scan_secrets",
        "Scan text for likely secrets and sensitive tokens.",
        required=("text",),
        optional=("patterns", "include_entropy", "context_radius", "max_findings"),
    ),
    RouteSpec(
        "scan_payload",
        "Scan selected string fields in a structured payload for secrets.",
        required=("payload",),
        optional=("keys", "patterns"),
    ),
    RouteSpec("redaction_rules", "List available redaction rules."),
    RouteSpec(
        "redact_text",
        "Apply redaction rules to a text payload.",
        required=("text",),
        optional=("rules", "scopes"),
    ),
    RouteSpec(
        "redact_payload",
        "Apply redaction rules to selected fields in a payload.",
        required=("payload",),
        optional=("keys", "rules"),
    ),
    RouteSpec(
        "derive_key",
        "Derive key material from a passphrase and KDF parameters.",
        required=("passphrase",),
        optional=("salt", "iterations", "length", "salt_bytes", "digest"),
    ),
    RouteSpec(
        "encrypt_text",
        "Encrypt UTF-8 text using a passphrase.",
        required=("text", "passphrase"),
        optional=("iterations", "length", "salt_bytes", "associated_data"),
    ),
    RouteSpec(
        "decrypt_text",
        "Decrypt UTF-8 text from an encrypted payload.",
        required=("payload", "passphrase"),
        optional=("associated_data",),
    ),
    RouteSpec("privacy_levels", "List privacy levels and their control defaults."),
    RouteSpec(
        "privacy_mode",
        "Resolve a privacy mode and merged control overrides.",
        optional=("level", "overrides"),
    ),
    RouteSpec("consent_flags", "List consent flags and default decisions."),
    RouteSpec(
        "consent_summary",
        "Summarize consent decisions for a provided state.",
        optional=("decisions", "flags"),
    ),
    RouteSpec("policy_defaults", "Return the default access policy definition."),
    RouteSpec(
        "evaluate_access",
        "Evaluate an access request against policy rules.",
        required=("action",),
        optional=("role", "resource", "context", "policy"),
    ),
    RouteSpec(
        "audit_analyze",
        "Analyze audit events for security-relevant findings.",
        optional=("events", "failure_threshold", "window_minutes"),
    ),
    RouteSpec(
        "scrub_text",
        "Scrub sensitive values from text using redaction and export rules.",
        required=("text",),
        optional=("policy", "rules"),
    ),
    RouteSpec(
        "scrub_export",
        "Scrub sensitive values from a structured export payload.",
        required=("payload",),
        optional=("policy", "rules"),
    ),
    RouteSpec(
        "check_url",
        "Analyze a URL for safety concerns.",
        required=("url",),
        optional=("allow_localhost", "allow_private_networks", "allowed_schemes"),
    ),
    RouteSpec(
        "check_command", "Analyze a shell command for risky patterns.", required=("command",)
    ),
    RouteSpec(
        "assess_risk",
        "Compute an aggregate security/privacy risk assessment.",
        optional=(
            "secret_result",
            "audit_result",
            "privacy",
            "safety_findings",
            "consent",
            "factors",
        ),
    ),
    RouteSpec(
        "security_dashboard",
        "Build a security dashboard summary from scan, audit, and policy inputs.",
        optional=(
            "text",
            "events",
            "privacy_level",
            "consent",
            "urls",
            "commands",
            "export_payload",
        ),
    ),
)


def _invalid(
    message: str, *, details: dict[str, Any] | None = None, field: str | None = None
) -> V2Error:
    payload = dict(details or {})
    if field and "field" not in payload:
        payload["field"] = field
    return V2Error(400, V2ErrorCode.INVALID_REQUEST, message, details=payload)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _invalid(f"{field} must be an object", field=field)
    return {str(k): v for k, v in value.items()}


def _sequence(value: Any, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _invalid(f"{field} must be an array", field=field)
    return list(value)


def _bool(value: Any, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise _invalid(f"{field} must be a boolean", field=field)
    return value


def _int(value: Any, field: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid(f"{field} must be an integer", field=field)
    return value


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    items = _sequence(value, field)
    return tuple(str(item) for item in items)


def _rule_objects(value: Any) -> tuple[RedactionRule, ...] | None:
    if value is None:
        return None
    items = _sequence(value, "rules")
    if not items:
        return ()
    import re

    rules: list[RedactionRule] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise _invalid("rules entries must be objects", field="rules")
        name = str(item.get("name") or f"rule_{index + 1}")
        pattern = item.get("pattern") or item.get("regex")
        if not isinstance(pattern, str) or not pattern:
            raise _invalid("redaction rule pattern must be a non-empty string", field="rules")
        replacement = str(item.get("replacement", "[REDACTED]"))
        flags = 0
        for flag_name in item.get("flags") or []:
            flag_name = str(flag_name).upper()
            if flag_name == "IGNORECASE":
                flags |= re.IGNORECASE
            elif flag_name == "MULTILINE":
                flags |= re.MULTILINE
            elif flag_name == "DOTALL":
                flags |= re.DOTALL
        try:
            compiled = re.compile(pattern, flags)
        except re.error as exc:
            raise _invalid(f"Invalid redaction regex: {exc}", field="rules") from exc
        rules.append(
            RedactionRule(
                name=name,
                pattern=compiled,
                replacement=replacement,
                description=str(item.get("description", "")),
                scope=str(item.get("scope", "all")),
                priority=_int(item.get("priority"), "priority", 100),
                enabled=_bool(item.get("enabled"), "enabled", True),
                tags=tuple(str(tag) for tag in item.get("tags") or []),
            )
        )
    return tuple(rules)


def _kdf_params(body: Mapping[str, Any]) -> KdfParams:
    iterations = _int(body.get("iterations"), "iterations", 390000)
    length = _int(body.get("length"), "length", 32)
    salt_bytes = _int(body.get("salt_bytes"), "salt_bytes", 16)
    digest = str(body.get("digest", "sha256"))
    try:
        return KdfParams(iterations=iterations, length=length, salt_bytes=salt_bytes, digest=digest)
    except ValueError as exc:
        raise _invalid(str(exc)) from exc


def _scrub_policy(value: Any) -> ScrubPolicy:
    if value is None:
        return ScrubPolicy()
    if not isinstance(value, Mapping):
        raise _invalid("policy must be an object", field="policy")
    remove_keys = tuple(str(item) for item in value.get("remove_keys") or ScrubPolicy().remove_keys)
    mask_keys = tuple(str(item) for item in value.get("mask_keys") or ScrubPolicy().mask_keys)
    return ScrubPolicy(
        redact_text=_bool(value.get("redact_text"), "redact_text", True),
        remove_keys=remove_keys,
        mask_keys=mask_keys,
        drop_empty=_bool(value.get("drop_empty"), "drop_empty", False),
        replacement=str(value.get("replacement", "[SCRUBBED]")),
    )


class SecurityHandlers:
    def __init__(self, service: SecurityService) -> None:
        self._service = service

    @property
    def service(self) -> SecurityService:
        return self._service

    def health(self, body: dict[str, Any]) -> RouteResult:
        data = self._service.health()
        return RouteResult(data, etag=compute_etag(data))

    def secret_patterns(self, body: dict[str, Any]) -> RouteResult:
        data = {"patterns": [pattern.as_dict() for pattern in builtin_secret_patterns()]}
        return RouteResult(data, etag=compute_etag(data))

    def scan_secrets(self, body: dict[str, Any]) -> RouteResult:
        text = require_str(body, "text")
        patterns = None
        names = body.get("patterns")
        if names is not None:
            wanted = {name.lower() for name in _string_list(names, "patterns")}
            selected = tuple(
                pattern for pattern in builtin_secret_patterns() if pattern.name.lower() in wanted
            )
            patterns = selected or builtin_secret_patterns()
        result = scan_secrets(
            text,
            patterns=patterns,
            include_entropy=_bool(body.get("include_entropy"), "include_entropy", True),
            context_radius=_int(body.get("context_radius"), "context_radius", 24),
            max_findings=_int(body.get("max_findings"), "max_findings", 500),
        )
        data = result.as_dict()
        return RouteResult(data, etag=compute_etag(data))

    def scan_payload(self, body: dict[str, Any]) -> RouteResult:
        payload = _mapping(body.get("payload"), "payload")
        keys = body.get("keys")
        key_list = _string_list(keys, "keys") if keys is not None else None
        data = scan_mapping(payload, keys=key_list)
        return RouteResult(data, etag=compute_etag(data))

    def redaction_rules(self, body: dict[str, Any]) -> RouteResult:
        data = {"rules": [rule.as_dict() for rule in builtin_redaction_rules()]}
        return RouteResult(data, etag=compute_etag(data))

    def redact_text(self, body: dict[str, Any]) -> RouteResult:
        text = require_str(body, "text")
        rules = _rule_objects(body.get("rules")) or builtin_redaction_rules()
        scopes = (
            _string_list(body.get("scopes"), "scopes") if body.get("scopes") is not None else None
        )
        summary = apply_redactions(text, rules=rules, scopes=scopes)
        return RouteResult(summary.as_dict(), etag=compute_etag(summary.as_dict()))

    def redact_payload(self, body: dict[str, Any]) -> RouteResult:
        payload = _mapping(body.get("payload"), "payload")
        rules = _rule_objects(body.get("rules")) or builtin_redaction_rules()
        keys = body.get("keys")
        key_list = _string_list(keys, "keys") if keys is not None else None
        data = redact_mapping(payload, rules=rules, keys=key_list)
        return RouteResult(data, etag=compute_etag(data))

    def derive_key(self, body: dict[str, Any]) -> RouteResult:
        passphrase = require_str(body, "passphrase")
        params = _kdf_params(body)
        salt = body.get("salt")
        if salt is not None and not isinstance(salt, str):
            raise _invalid("salt must be a string", field="salt")
        try:
            derived = derive_key(passphrase, salt=salt, params=params)
        except Exception as exc:
            raise _invalid(str(exc) or "Could not derive key") from exc
        data = derived.as_dict()
        data.pop("key", None)
        data["derived"] = True
        data["fingerprint"] = compute_etag({"key": derived.key_b64})[:24]
        return RouteResult(data)

    def encrypt_text(self, body: dict[str, Any]) -> RouteResult:
        text = require_str(body, "text")
        passphrase = require_str(body, "passphrase")
        params = _kdf_params(body)
        associated = optional_str(body, "associated_data", default="") or ""
        try:
            payload = encrypt_text(text, passphrase, params=params, associated_data=associated)
        except Exception as exc:
            raise _invalid(str(exc) or "Encryption failed") from exc
        return RouteResult({"payload": payload})

    def decrypt_text(self, body: dict[str, Any]) -> RouteResult:
        payload = body.get("payload")
        if payload is None:
            raise V2Error(
                400, V2ErrorCode.MISSING_FIELD, "Missing 'payload'", details={"field": "payload"}
            )
        if not isinstance(payload, (str, Mapping)):
            raise _invalid("payload must be an object or string", field="payload")
        passphrase = require_str(body, "passphrase")
        associated = optional_str(body, "associated_data", default="") or ""
        try:
            text = decrypt_text(payload, passphrase, associated_data=associated)
        except Exception as exc:
            raise _invalid(str(exc) or "Decryption failed") from exc
        return RouteResult({"text": text})

    def privacy_levels(self, body: dict[str, Any]) -> RouteResult:
        data = {
            "levels": [
                apply_privacy_level(level) for level in ("open", "standard", "sensitive", "strict")
            ]
        }
        return RouteResult(data, etag=compute_etag(data))

    def privacy_mode(self, body: dict[str, Any]) -> RouteResult:
        level = optional_str(body, "level", default="standard")
        overrides = (
            _mapping(body.get("overrides"), "overrides")
            if body.get("overrides") is not None
            else None
        )
        try:
            data = merge_privacy_preferences(level, overrides)
        except Exception as exc:
            raise _invalid(str(exc)) from exc
        return RouteResult(data, etag=compute_etag(data))

    def consent_flags(self, body: dict[str, Any]) -> RouteResult:
        registry = ConsentRegistry.with_defaults()
        data = registry.summary()
        data["flags"] = [flag.as_dict() for flag in DEFAULT_FLAGS]
        return RouteResult(data, etag=compute_etag(data))

    def consent_summary(self, body: dict[str, Any]) -> RouteResult:
        registry = ConsentRegistry.with_defaults()
        decisions = (
            _mapping(body.get("decisions"), "decisions")
            if body.get("decisions") is not None
            else {}
        )
        if decisions:
            registry.apply_bulk(
                {k: v for k, v in decisions.items() if isinstance(v, bool)}, source="request"
            )
        data = registry.summary()
        data["context"] = registry.context()
        return RouteResult(data, etag=compute_etag(data))

    def policy_defaults(self, body: dict[str, Any]) -> RouteResult:
        data = default_access_policy().as_dict()
        return RouteResult(data, etag=compute_etag(data))

    def evaluate_access(self, body: dict[str, Any]) -> RouteResult:
        action = require_str(body, "action")
        role = optional_str(body, "role", default="anonymous") or "anonymous"
        resource = optional_str(body, "resource", default="*") or "*"
        context = (
            _mapping(body.get("context"), "context") if body.get("context") is not None else {}
        )
        policy_data = body.get("policy")
        policy = None
        if policy_data is not None:
            policy = _policy_from_mapping(policy_data)
        result = evaluate_access(
            action, role=role, resource=resource, context=context, policy=policy
        )
        return RouteResult(result.as_dict(), etag=compute_etag(result.as_dict()))

    def audit_analyze(self, body: dict[str, Any]) -> RouteResult:
        events = _sequence(body.get("events"), "events") if body.get("events") is not None else []
        normalized = [event for event in events if isinstance(event, Mapping)]
        failure_threshold = _int(body.get("failure_threshold"), "failure_threshold", 5)
        window_minutes = _int(body.get("window_minutes"), "window_minutes", 10)
        try:
            from redscribe.v2.security.audit import AuditAnalyzer

            report = (
                AuditAnalyzer(failure_threshold=failure_threshold, window_minutes=window_minutes)
                .analyze(normalized)
                .as_dict()
            )
        except Exception as exc:
            raise _invalid(str(exc)) from exc
        return RouteResult(report, etag=compute_etag(report))

    def scrub_text(self, body: dict[str, Any]) -> RouteResult:
        text = require_str(body, "text")
        policy = _scrub_policy(body.get("policy"))
        rules = _rule_objects(body.get("rules")) or builtin_redaction_rules()
        cleaned, summary = scrub_text(text, rules=rules, policy=policy)
        data = {"text": cleaned, "redaction": summary.as_dict()}
        return RouteResult(data, etag=compute_etag(data))

    def scrub_export(self, body: dict[str, Any]) -> RouteResult:
        payload = _mapping(body.get("payload"), "payload")
        policy = _scrub_policy(body.get("policy"))
        rules = _rule_objects(body.get("rules")) or builtin_redaction_rules()
        cleaned, report = scrub_export_payload(payload, policy=policy, rules=rules)
        data = {"payload": cleaned, "report": report.as_dict()}
        return RouteResult(data, etag=compute_etag(data))

    def check_url(self, body: dict[str, Any]) -> RouteResult:
        url = require_str(body, "url")
        allowed = body.get("allowed_schemes")
        allowed_set = set(_string_list(allowed, "allowed_schemes")) if allowed is not None else None
        result = analyze_url(
            url,
            allowed_schemes=allowed_set,
            allow_localhost=_bool(body.get("allow_localhost"), "allow_localhost", True),
            allow_private_networks=_bool(
                body.get("allow_private_networks"), "allow_private_networks", False
            ),
        )
        data = result.as_dict()
        return RouteResult(data, etag=compute_etag(data))

    def check_command(self, body: dict[str, Any]) -> RouteResult:
        command = require_str(body, "command")
        data = analyze_command(command).as_dict()
        return RouteResult(data, etag=compute_etag(data))

    def assess_risk(self, body: dict[str, Any]) -> RouteResult:
        assessment = assess_risk(
            secret_result=_mapping(body.get("secret_result"), "secret_result")
            if body.get("secret_result") is not None
            else None,
            audit_result=_mapping(body.get("audit_result"), "audit_result")
            if body.get("audit_result") is not None
            else None,
            privacy=_mapping(body.get("privacy"), "privacy")
            if body.get("privacy") is not None
            else None,
            safety_findings=[
                item
                for item in _sequence(body.get("safety_findings"), "safety_findings")
                if isinstance(item, Mapping)
            ]
            if body.get("safety_findings") is not None
            else None,
            consent=_mapping(body.get("consent"), "consent")
            if body.get("consent") is not None
            else None,
        )
        data = assessment.as_dict()
        return RouteResult(data, etag=compute_etag(data))

    def security_dashboard(self, body: dict[str, Any]) -> RouteResult:
        data = self._service.dashboard(body)
        return RouteResult(data, etag=compute_etag(data))


def _policy_from_mapping(payload: Any) -> AccessPolicy:
    if not isinstance(payload, Mapping):
        raise _invalid("policy must be an object", field="policy")
    name = str(payload.get("name", "custom"))
    description = str(payload.get("description", ""))
    default_raw = str(payload.get("default_decision", "review")).lower()
    try:
        default_decision = AccessDecision(default_raw)
    except ValueError as exc:
        raise _invalid("Invalid default_decision", field="policy") from exc
    rules_payload = payload.get("rules") or []
    if not isinstance(rules_payload, Sequence) or isinstance(
        rules_payload, (str, bytes, bytearray)
    ):
        raise _invalid("policy.rules must be an array", field="policy")
    rules: list[PolicyRule] = []
    for item in rules_payload:
        if not isinstance(item, Mapping):
            raise _invalid("policy rules must be objects", field="policy")
        effect_raw = str(item.get("effect", "deny")).lower()
        try:
            effect = PolicyEffect(effect_raw)
        except ValueError as exc:
            raise _invalid("Invalid policy effect", field="policy") from exc
        actions = tuple(str(v) for v in item.get("actions") or ("*",))
        roles = tuple(str(v) for v in item.get("roles") or ("*",))
        resources = tuple(str(v) for v in item.get("resources") or ("*",))
        conditions = (
            _mapping(item.get("conditions"), "conditions")
            if item.get("conditions") is not None
            else {}
        )
        rules.append(
            PolicyRule(
                name=str(item.get("name", "rule")),
                effect=effect,
                actions=actions,
                roles=roles,
                resources=resources,
                conditions=conditions,
                priority=_int(item.get("priority"), "priority", 100),
                reason=str(item.get("reason", "")),
            )
        )
    return AccessPolicy(
        name=name, description=description, rules=tuple(rules), default_decision=default_decision
    )


class SecurityService:
    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    @property
    def vault(self) -> Vault:
        return self._vault

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "namespace": "security",
            "features": [
                "secret_detection",
                "redaction",
                "encryption",
                "key_derivation",
                "access_policies",
                "privacy_levels",
                "audit_analysis",
                "consent_flags",
                "export_scrubbing",
                "url_command_safety",
                "risk_scoring",
            ],
            "secret_patterns": len(builtin_secret_patterns()),
            "redaction_rules": len(builtin_redaction_rules()),
            "privacy_levels": ["open", "standard", "sensitive", "strict"],
        }

    def dashboard(self, body: Mapping[str, Any]) -> dict[str, Any]:
        text = str(body.get("text", "") or "")
        events = (
            [item for item in _sequence(body.get("events"), "events") if isinstance(item, Mapping)]
            if body.get("events") is not None
            else []
        )
        privacy_level = str(body.get("privacy_level", "standard") or "standard")
        privacy = apply_privacy_level(privacy_level)
        consent = (
            _mapping(body.get("consent"), "consent")
            if body.get("consent") is not None
            else ConsentRegistry.with_defaults().context()
        )
        secret_result = (
            scan_secrets(text).as_dict()
            if text
            else {"count": 0, "highest_severity": "none", "findings": []}
        )
        audit_result = (
            analyze_events(events)
            if events
            else {"total_events": 0, "highest_severity": "none", "findings": []}
        )
        urls = []
        for raw in _sequence(body.get("urls"), "urls") if body.get("urls") is not None else []:
            urls.append(analyze_url(str(raw)).as_dict())
        commands = []
        for raw in (
            _sequence(body.get("commands"), "commands") if body.get("commands") is not None else []
        ):
            commands.append(analyze_command(str(raw)).as_dict())
        export_payload = (
            _mapping(body.get("export_payload"), "export_payload")
            if body.get("export_payload") is not None
            else None
        )
        scrubbed = None
        if export_payload is not None:
            cleaned, report = scrub_export_payload(export_payload)
            scrubbed = {"payload": cleaned, "report": report.as_dict()}
        safety_findings = [item for item in urls + commands if not item.get("safe", True)]
        assessment = assess_risk(
            secret_result=secret_result,
            audit_result=audit_result,
            privacy=privacy,
            safety_findings=safety_findings,
            consent=consent,
        ).as_dict()
        return {
            "privacy": privacy,
            "consent": consent,
            "secrets": secret_result,
            "audit": audit_result,
            "urls": urls,
            "commands": commands,
            "scrub": scrubbed,
            "risk": assessment,
            "safe_link_policy": {
                "allow_external_links": privacy.get("allow_external_links", False),
                "allow_command_copy": privacy.get("allow_command_copy", False),
            },
        }


class SecurityNamespace:
    def __init__(self, service: SecurityService) -> None:
        self._service = service
        self.handlers = SecurityHandlers(service)

    @property
    def service(self) -> SecurityService:
        return self._service

    def routes(self) -> tuple[str, ...]:
        return tuple(f"security.{spec.action}" for spec in ROUTE_SPECS)

    def handler_map(self) -> dict[str, Handler]:
        return {spec.action: getattr(self.handlers, spec.action) for spec in ROUTE_SPECS}

    def register(self, api: Registrar) -> tuple[str, ...]:
        register = getattr(api, "register", None)
        if register is None:
            register = getattr(api, "_register", None)
        if not callable(register):
            raise TypeError("API does not expose a route registration method")
        for spec in ROUTE_SPECS:
            handler = getattr(self.handlers, spec.action)
            register(
                f"security.{spec.action}",
                handler,
                spec.description,
                required=spec.required,
                optional=spec.optional,
                mutating=spec.mutating,
                entity_type="security",
            )
        return self.routes()


def register(api: Registrar) -> SecurityNamespace:
    vault = api.vault
    namespace = SecurityNamespace(SecurityService(vault))
    namespace.register(api)
    return namespace


def register_with_vault(vault: Vault) -> SecurityNamespace:
    return SecurityNamespace(SecurityService(vault))


def route_names() -> tuple[str, ...]:
    return tuple(f"security.{spec.action}" for spec in ROUTE_SPECS)


def route_specs() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "action": spec.action,
            "description": spec.description,
            "required": spec.required,
            "optional": spec.optional,
            "mutating": spec.mutating,
        }
        for spec in ROUTE_SPECS
    )
