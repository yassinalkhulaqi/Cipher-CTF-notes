"""Domain models for the engagement core.

The models are deliberately storage agnostic. Each entity owns its JSON shape so
repositories, services, API handlers, and the frontend can exchange stable
snapshots without leaking implementation details.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

from redscribe.v2.engagements.util import now_iso

EntityT = TypeVar("EntityT", bound="Entity")


class StrEnum(str, Enum):
    """String enum with a readable label derived from its value."""

    @property
    def label(self) -> str:
        return str(self.value).replace("_", " ").title()


class EngagementStatus(StrEnum):
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    REPORTING = "reporting"
    CLOSED = "closed"
    ARCHIVED = "archived"


class EngagementKind(StrEnum):
    PENTEST = "pentest"
    RED_TEAM = "red_team"
    CTF = "ctf"
    LAB = "lab"
    AUDIT = "audit"
    RESEARCH = "research"


class TargetKind(StrEnum):
    DOMAIN = "domain"
    IP_ADDRESS = "ip_address"
    CIDR = "cidr"
    URL = "url"
    HOST = "host"
    APPLICATION = "application"
    NETWORK = "network"
    CLOUD = "cloud"


class TargetStatus(StrEnum):
    DISCOVERED = "discovered"
    CONFIRMED = "confirmed"
    TESTED = "tested"
    EXCLUDED = "excluded"
    OUT_OF_SERVICE = "out_of_service"


class ScopeStatus(StrEnum):
    UNSPECIFIED = "unspecified"
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    PENDING = "pending"
    WAIVED = "waived"


class AssetKind(StrEnum):
    SERVER = "server"
    WORKSTATION = "workstation"
    DATABASE = "database"
    DEVICE = "device"
    REPOSITORY = "repository"
    CONTAINER = "container"
    CLOUD_RESOURCE = "cloud_resource"
    IDENTITY = "identity"
    UNKNOWN = "unknown"


class AssetStatus(StrEnum):
    IDENTIFIED = "identified"
    ENUMERATED = "enumerated"
    ASSESSED = "assessed"
    REMEDIATED = "remediated"
    DECOMMISSIONED = "decommissioned"


class Criticality(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ServiceStatus(StrEnum):
    SUSPECTED = "suspected"
    DISCOVERED = "discovered"
    VERIFIED = "verified"
    TESTED = "tested"
    CLOSED = "closed"


class CredentialKind(StrEnum):
    PASSWORD = "password"
    API_TOKEN = "api_token"
    SSH_KEY = "ssh_key"
    CERTIFICATE = "certificate"
    COOKIE = "cookie"
    HASH = "hash"


class CredentialStatus(StrEnum):
    CANDIDATE = "candidate"
    VALID = "valid"
    INVALID = "invalid"
    REVOKED = "revoked"
    ROTATED = "rotated"


class FindingStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    VERIFIED = "verified"
    ACCEPTED_RISK = "accepted_risk"
    DUPLICATE = "duplicate"
    REMEDIATED = "remediated"
    CLOSED = "closed"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def numeric_score(self) -> float:
        """Return the representative CVSS score for this severity band."""
        return {
            Severity.INFO: 0.0,
            Severity.LOW: 3.9,
            Severity.MEDIUM: 6.9,
            Severity.HIGH: 8.9,
            Severity.CRITICAL: 10.0,
        }[self]


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CONFIRMED = "confirmed"


class ScopeAction(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"


class ScopeRuleKind(StrEnum):
    DOMAIN = "domain"
    IP_ADDRESS = "ip_address"
    CIDR = "cidr"
    URL = "url"
    PORT = "port"
    KEYWORD = "keyword"


class ActivityAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    TRANSITIONED = "transitioned"
    LINKED = "linked"
    REVIEWED = "reviewed"


def _as_str(data: Mapping[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    return value if isinstance(value, str) else default


def _as_int(data: Mapping[str, Any], key: str, default: int = 0) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _as_float(data: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _as_bool(data: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    return value if isinstance(value, bool) else default


def _as_str_list(data: Mapping[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]


def _as_transitions(data: Mapping[str, Any]) -> list[FindingEvent]:
    value = data.get("transitions", [])
    if not isinstance(value, (list, tuple)):
        return []
    result: list[FindingEvent] = []
    for item in value:
        if isinstance(item, Mapping):
            result.append(FindingEvent.from_dict(item))
    return result


def _enum_value(value: Enum | str) -> str:
    return value.value if isinstance(value, Enum) else value


class Entity:
    """Common JSON contract implemented by every persisted entity."""

    id: int
    engagement_id: int

    def as_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls: type[EntityT], data: Mapping[str, Any]) -> EntityT:
        raise NotImplementedError


@dataclass(slots=True, kw_only=True)
class Engagement(Entity):
    id: int = 0
    key: str = ""
    name: str = ""
    client: str = ""
    description: str = ""
    kind: EngagementKind = EngagementKind.PENTEST
    status: EngagementStatus = EngagementStatus.PLANNING
    owner: str = ""
    start_date: str = ""
    end_date: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "client": self.client,
            "description": self.description,
            "kind": _enum_value(self.kind),
            "status": _enum_value(self.status),
            "owner": self.owner,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Engagement:
        return cls(
            id=_as_int(data, "id"),
            key=_as_str(data, "key"),
            name=_as_str(data, "name"),
            client=_as_str(data, "client"),
            description=_as_str(data, "description"),
            kind=EngagementKind(_as_str(data, "kind", EngagementKind.PENTEST.value)),
            status=EngagementStatus(_as_str(data, "status", EngagementStatus.PLANNING.value)),
            owner=_as_str(data, "owner"),
            start_date=_as_str(data, "start_date"),
            end_date=_as_str(data, "end_date"),
            tags=_as_str_list(data, "tags"),
            created_at=_as_str(data, "created_at", now_iso()),
            updated_at=_as_str(data, "updated_at", now_iso()),
        )

    @property
    def display_name(self) -> str:
        return self.name or self.key or f"Engagement {self.id}"


@dataclass(slots=True, kw_only=True)
class ScopeRule(Entity):
    id: int = 0
    engagement_id: int = 0
    kind: ScopeRuleKind = ScopeRuleKind.KEYWORD
    value: str = ""
    action: ScopeAction = ScopeAction.INCLUDE
    notes: str = ""
    created_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engagement_id": self.engagement_id,
            "kind": _enum_value(self.kind),
            "value": self.value,
            "action": _enum_value(self.action),
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ScopeRule:
        return cls(
            id=_as_int(data, "id"),
            engagement_id=_as_int(data, "engagement_id"),
            kind=ScopeRuleKind(_as_str(data, "kind", ScopeRuleKind.KEYWORD.value)),
            value=_as_str(data, "value"),
            action=ScopeAction(_as_str(data, "action", ScopeAction.INCLUDE.value)),
            notes=_as_str(data, "notes"),
            created_at=_as_str(data, "created_at", now_iso()),
        )


@dataclass(slots=True, kw_only=True)
class Target(Entity):
    id: int = 0
    engagement_id: int = 0
    value: str = ""
    name: str = ""
    kind: TargetKind = TargetKind.HOST
    description: str = ""
    status: TargetStatus = TargetStatus.DISCOVERED
    scope_status: ScopeStatus = ScopeStatus.UNSPECIFIED
    criticality: Criticality = Criticality.MEDIUM
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engagement_id": self.engagement_id,
            "value": self.value,
            "name": self.name,
            "kind": _enum_value(self.kind),
            "description": self.description,
            "status": _enum_value(self.status),
            "scope_status": _enum_value(self.scope_status),
            "criticality": _enum_value(self.criticality),
            "tags": list(self.tags),
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Target:
        return cls(
            id=_as_int(data, "id"),
            engagement_id=_as_int(data, "engagement_id"),
            value=_as_str(data, "value"),
            name=_as_str(data, "name"),
            kind=TargetKind(_as_str(data, "kind", TargetKind.HOST.value)),
            description=_as_str(data, "description"),
            status=TargetStatus(_as_str(data, "status", TargetStatus.DISCOVERED.value)),
            scope_status=ScopeStatus(_as_str(data, "scope_status", ScopeStatus.UNSPECIFIED.value)),
            criticality=Criticality(_as_str(data, "criticality", Criticality.MEDIUM.value)),
            tags=_as_str_list(data, "tags"),
            notes=_as_str(data, "notes"),
            created_at=_as_str(data, "created_at", now_iso()),
            updated_at=_as_str(data, "updated_at", now_iso()),
        )

    @property
    def display_name(self) -> str:
        return self.name or self.value or f"Target {self.id}"


@dataclass(slots=True, kw_only=True)
class Asset(Entity):
    id: int = 0
    engagement_id: int = 0
    target_id: int = 0
    name: str = ""
    kind: AssetKind = AssetKind.UNKNOWN
    identifier: str = ""
    status: AssetStatus = AssetStatus.IDENTIFIED
    criticality: Criticality = Criticality.MEDIUM
    owner: str = ""
    notes: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engagement_id": self.engagement_id,
            "target_id": self.target_id,
            "name": self.name,
            "kind": _enum_value(self.kind),
            "identifier": self.identifier,
            "status": _enum_value(self.status),
            "criticality": _enum_value(self.criticality),
            "owner": self.owner,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Asset:
        return cls(
            id=_as_int(data, "id"),
            engagement_id=_as_int(data, "engagement_id"),
            target_id=_as_int(data, "target_id"),
            name=_as_str(data, "name"),
            kind=AssetKind(_as_str(data, "kind", AssetKind.UNKNOWN.value)),
            identifier=_as_str(data, "identifier"),
            status=AssetStatus(_as_str(data, "status", AssetStatus.IDENTIFIED.value)),
            criticality=Criticality(_as_str(data, "criticality", Criticality.MEDIUM.value)),
            owner=_as_str(data, "owner"),
            notes=_as_str(data, "notes"),
            created_at=_as_str(data, "created_at", now_iso()),
            updated_at=_as_str(data, "updated_at", now_iso()),
        )


@dataclass(slots=True, kw_only=True)
class Service(Entity):
    id: int = 0
    engagement_id: int = 0
    target_id: int = 0
    asset_id: int = 0
    name: str = ""
    port: int = 0
    protocol: str = "tcp"
    product: str = ""
    version: str = ""
    status: ServiceStatus = ServiceStatus.DISCOVERED
    notes: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engagement_id": self.engagement_id,
            "target_id": self.target_id,
            "asset_id": self.asset_id,
            "name": self.name,
            "port": self.port,
            "protocol": self.protocol,
            "product": self.product,
            "version": self.version,
            "status": _enum_value(self.status),
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Service:
        return cls(
            id=_as_int(data, "id"),
            engagement_id=_as_int(data, "engagement_id"),
            target_id=_as_int(data, "target_id"),
            asset_id=_as_int(data, "asset_id"),
            name=_as_str(data, "name"),
            port=_as_int(data, "port"),
            protocol=_as_str(data, "protocol", "tcp"),
            product=_as_str(data, "product"),
            version=_as_str(data, "version"),
            status=ServiceStatus(_as_str(data, "status", ServiceStatus.DISCOVERED.value)),
            notes=_as_str(data, "notes"),
            created_at=_as_str(data, "created_at", now_iso()),
            updated_at=_as_str(data, "updated_at", now_iso()),
        )

    @property
    def endpoint(self) -> str:
        return f"{self.name}:{self.port}/{self.protocol}" if self.port else self.name


@dataclass(slots=True, kw_only=True)
class Credential(Entity):
    id: int = 0
    engagement_id: int = 0
    target_id: int = 0
    username: str = ""
    secret_ref: str = ""
    kind: CredentialKind = CredentialKind.PASSWORD
    status: CredentialStatus = CredentialStatus.CANDIDATE
    rotated_at: str = ""
    notes: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engagement_id": self.engagement_id,
            "target_id": self.target_id,
            "username": self.username,
            "secret_ref": self.secret_ref,
            "kind": _enum_value(self.kind),
            "status": _enum_value(self.status),
            "rotated_at": self.rotated_at,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Credential:
        return cls(
            id=_as_int(data, "id"),
            engagement_id=_as_int(data, "engagement_id"),
            target_id=_as_int(data, "target_id"),
            username=_as_str(data, "username"),
            secret_ref=_as_str(data, "secret_ref"),
            kind=CredentialKind(_as_str(data, "kind", CredentialKind.PASSWORD.value)),
            status=CredentialStatus(_as_str(data, "status", CredentialStatus.CANDIDATE.value)),
            rotated_at=_as_str(data, "rotated_at"),
            notes=_as_str(data, "notes"),
            created_at=_as_str(data, "created_at", now_iso()),
            updated_at=_as_str(data, "updated_at", now_iso()),
        )

    def safe_dict(self) -> dict[str, Any]:
        data = self.as_dict()
        data["secret_ref"] = "***" if self.secret_ref else ""
        return data


@dataclass(slots=True, kw_only=True)
class FindingEvent:
    at: str
    actor: str = ""
    action: str = ""
    from_status: str = ""
    to_status: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "actor": self.actor,
            "action": self.action,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FindingEvent:
        return cls(
            at=_as_str(data, "at", now_iso()),
            actor=_as_str(data, "actor"),
            action=_as_str(data, "action"),
            from_status=_as_str(data, "from_status"),
            to_status=_as_str(data, "to_status"),
            note=_as_str(data, "note"),
        )


@dataclass(slots=True, kw_only=True)
class Finding(Entity):
    id: int = 0
    engagement_id: int = 0
    target_id: int = 0
    asset_id: int = 0
    service_id: int = 0
    title: str = ""
    summary: str = ""
    severity: Severity = Severity.MEDIUM
    confidence: Confidence = Confidence.MEDIUM
    cvss_vector: str = ""
    cvss_score: float = 0.0
    cwe: str = ""
    cwes: list[str] = field(default_factory=list)
    cves: list[str] = field(default_factory=list)
    status: FindingStatus = FindingStatus.DRAFT
    duplicate_of: int = 0
    owner: str = ""
    impact: str = ""
    remediation: str = ""
    reproduction_steps: str = ""
    references: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    transitions: list[FindingEvent] = field(default_factory=list)
    resolved_at: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engagement_id": self.engagement_id,
            "target_id": self.target_id,
            "asset_id": self.asset_id,
            "service_id": self.service_id,
            "title": self.title,
            "summary": self.summary,
            "severity": _enum_value(self.severity),
            "confidence": _enum_value(self.confidence),
            "cvss_vector": self.cvss_vector,
            "cvss_score": self.cvss_score,
            "cwe": self.cwe,
            "cwes": list(self.cwes),
            "cves": list(self.cves),
            "status": _enum_value(self.status),
            "duplicate_of": self.duplicate_of,
            "owner": self.owner,
            "impact": self.impact,
            "remediation": self.remediation,
            "reproduction_steps": self.reproduction_steps,
            "references": list(self.references),
            "tags": list(self.tags),
            "transitions": [event.as_dict() for event in self.transitions],
            "resolved_at": self.resolved_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Finding:
        return cls(
            id=_as_int(data, "id"),
            engagement_id=_as_int(data, "engagement_id"),
            target_id=_as_int(data, "target_id"),
            asset_id=_as_int(data, "asset_id"),
            service_id=_as_int(data, "service_id"),
            title=_as_str(data, "title"),
            summary=_as_str(data, "summary"),
            severity=Severity(_as_str(data, "severity", Severity.MEDIUM.value)),
            confidence=Confidence(_as_str(data, "confidence", Confidence.MEDIUM.value)),
            cvss_vector=_as_str(data, "cvss_vector"),
            cvss_score=_as_float(data, "cvss_score"),
            cwe=_as_str(data, "cwe"),
            cwes=_as_str_list(data, "cwes"),
            cves=_as_str_list(data, "cves"),
            status=FindingStatus(_as_str(data, "status", FindingStatus.DRAFT.value)),
            duplicate_of=_as_int(data, "duplicate_of"),
            owner=_as_str(data, "owner"),
            impact=_as_str(data, "impact"),
            remediation=_as_str(data, "remediation"),
            reproduction_steps=_as_str(data, "reproduction_steps"),
            references=_as_str_list(data, "references"),
            tags=_as_str_list(data, "tags"),
            transitions=_as_transitions(data),
            resolved_at=_as_str(data, "resolved_at"),
            created_at=_as_str(data, "created_at", now_iso()),
            updated_at=_as_str(data, "updated_at", now_iso()),
        )

    @property
    def is_open(self) -> bool:
        return self.status in {
            FindingStatus.OPEN,
            FindingStatus.VERIFIED,
            FindingStatus.ACCEPTED_RISK,
        }

    @property
    def effective_score(self) -> float:
        return self.cvss_score if self.cvss_score > 0 else self.severity.numeric_score()


@dataclass(slots=True, kw_only=True)
class Activity(Entity):
    id: int = 0
    engagement_id: int = 0
    entity_type: str = ""
    entity_id: int = 0
    action: ActivityAction = ActivityAction.UPDATED
    summary: str = ""
    actor: str = ""
    created_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engagement_id": self.engagement_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": _enum_value(self.action),
            "summary": self.summary,
            "actor": self.actor,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Activity:
        return cls(
            id=_as_int(data, "id"),
            engagement_id=_as_int(data, "engagement_id"),
            entity_type=_as_str(data, "entity_type"),
            entity_id=_as_int(data, "entity_id"),
            action=ActivityAction(_as_str(data, "action", ActivityAction.UPDATED.value)),
            summary=_as_str(data, "summary"),
            actor=_as_str(data, "actor"),
            created_at=_as_str(data, "created_at", now_iso()),
        )


SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.INFO,
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)

CONFIDENCE_ORDER: tuple[Confidence, ...] = (
    Confidence.LOW,
    Confidence.MEDIUM,
    Confidence.HIGH,
    Confidence.CONFIRMED,
)

CRITICALITY_ORDER: tuple[Criticality, ...] = (
    Criticality.INFORMATIONAL,
    Criticality.LOW,
    Criticality.MEDIUM,
    Criticality.HIGH,
    Criticality.CRITICAL,
)


def severity_index(severity: Severity) -> int:
    return SEVERITY_ORDER.index(severity)


def confidence_index(confidence: Confidence) -> int:
    return CONFIDENCE_ORDER.index(confidence)


def criticality_index(criticality: Criticality) -> int:
    return CRITICALITY_ORDER.index(criticality)
