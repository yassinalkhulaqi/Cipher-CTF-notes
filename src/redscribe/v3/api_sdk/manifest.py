"""Data-only extension manifests with strict schema validation."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.api.envelope import PageMeta
from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.idempotency import compute_etag, etag_matches
from redscribe.v3.api.pagination import PageRequest, paginate
from redscribe.v3.api_sdk.errors import ManifestError
from redscribe.v3.capabilities import ALL_CAPABILITIES
from redscribe.v3.entities.validation import check_metadata, clean_text

SCHEMA_ID = "redscribe-extension/1"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_CONTRIBUTIONS = 32
MAX_DEPTH = 8
MAX_NODES = 512
MAX_STRING_LENGTH = 4000

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{2,63}$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][a-z0-9.-]+)?$")
_BINDING_PATTERN = re.compile(r"^(?:Ctrl|Alt|Shift|Meta)\+[A-Za-z0-9]{1,16}$")
_ROUTE_PATTERN = re.compile(r"^[a-z][a-z0-9/_-]{1,63}$")

TOP_LEVEL_FIELDS: dict[str, tuple[str, bool]] = {
    "schema": ("str", True),
    "id": ("str", True),
    "version": ("str", True),
    "title": ("str", True),
    "summary": ("str", False),
    "requires": ("str_list", False),
    "contributions": ("contributions", True),
    "metadata": ("dict", False),
}

CONTRIBUTION_FIELDS: dict[str, dict[str, tuple[str, bool]]] = {
    "panel": {
        "kind": ("str", True),
        "id": ("str", True),
        "title": ("str", True),
        "location": ("choice", True),
        "description": ("str", False),
    },
    "command": {
        "kind": ("str", True),
        "id": ("str", True),
        "title": ("str", True),
        "group": ("str", False),
        "description": ("str", False),
    },
    "theme": {
        "kind": ("str", True),
        "id": ("str", True),
        "title": ("str", True),
        "tokens": ("str_dict", False),
        "description": ("str", False),
    },
    "shortcut": {
        "kind": ("str", True),
        "id": ("str", True),
        "title": ("str", True),
        "binding": ("binding", True),
        "description": ("str", False),
    },
    "view": {
        "kind": ("str", True),
        "id": ("str", True),
        "title": ("str", True),
        "route": ("route", True),
        "description": ("str", False),
    },
}

PANEL_LOCATIONS: tuple[str, ...] = ("sidebar", "inspector", "dashboard", "console")

FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "args",
        "argv",
        "binary",
        "bytes",
        "call",
        "callable",
        "callback",
        "class",
        "code",
        "command",
        "compile",
        "entrypoint",
        "eval",
        "evaluate",
        "exec",
        "filepath",
        "filename",
        "function",
        "handler",
        "hook",
        "host",
        "import",
        "instance",
        "lambda",
        "module",
        "network",
        "on_load",
        "path",
        "port",
        "script",
        "shell",
        "socket",
        "source",
        "source_code",
        "subprocess",
        "uri",
        "url",
    }
)


@dataclass(frozen=True, slots=True)
class ManifestIssue:
    """One validation finding."""

    path: str
    code: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-safe representation."""
        return {
            "path": self.path,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Result of validating an untrusted manifest document."""

    valid: bool
    issues: tuple[ManifestIssue, ...] = ()
    normalized: dict[str, Any] | None = None
    fingerprint: str = ""

    @property
    def errors(self) -> tuple[ManifestIssue, ...]:
        """Return only blocking issues."""
        return tuple(item for item in self.issues if item.severity == "error")

    @property
    def warnings(self) -> tuple[ManifestIssue, ...]:
        """Return only advisory issues."""
        return tuple(item for item in self.issues if item.severity == "warning")

    def messages(self) -> tuple[str, ...]:
        """Return formatted issue messages."""
        return tuple(f"{item.path}: {item.message}" for item in self.issues)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "valid": self.valid,
            "issues": [item.as_dict() for item in self.issues],
            "normalized": self.normalized,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class Contribution:
    """One declarative contribution. It never contains executable data."""

    kind: str
    id: str
    title: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"kind": self.kind, "id": self.id, "title": self.title, **self.attributes}


@dataclass(frozen=True, slots=True)
class ExtensionManifest:
    """A validated, data-only extension declaration."""

    id: str
    version: str
    title: str
    schema: str = SCHEMA_ID
    summary: str = ""
    requires: tuple[str, ...] = ()
    contributions: tuple[Contribution, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Return a strong ETag fingerprint of the declaration."""
        return compute_etag(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "schema": self.schema,
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "summary": self.summary,
            "requires": list(self.requires),
            "contributions": [item.as_dict() for item in self.contributions],
            "metadata": dict(self.metadata),
        }


def example_manifest() -> dict[str, Any]:
    """Return a fresh, valid example manifest."""
    return {
        "schema": SCHEMA_ID,
        "id": "example.panel",
        "version": "1.0.0",
        "title": "Example Panel",
        "summary": "Declares UI contributions only; no code is shipped or run.",
        "requires": ["extensions"],
        "contributions": [
            {
                "kind": "panel",
                "id": "example-panel",
                "title": "Example",
                "location": "sidebar",
                "description": "A read-only summary panel.",
            },
            {
                "kind": "command",
                "id": "example-refresh",
                "title": "Refresh example panel",
                "group": "Extensions",
            },
            {
                "kind": "shortcut",
                "id": "example-shortcut",
                "title": "Open example panel",
                "binding": "Ctrl+K",
            },
        ],
        "metadata": {"origin": "local"},
    }


def manifest_schema() -> dict[str, Any]:
    """Return the machine-readable schema descriptor used by editors."""
    return {
        "schema_id": SCHEMA_ID,
        "top_level": {key: list(value) for key, value in TOP_LEVEL_FIELDS.items()},
        "contribution_kinds": {
            kind: {key: list(value) for key, value in fields.items()}
            for kind, fields in CONTRIBUTION_FIELDS.items()
        },
        "panel_locations": list(PANEL_LOCATIONS),
        "forbidden_keys": sorted(FORBIDDEN_KEYS),
        "limits": {
            "max_bytes": MAX_MANIFEST_BYTES,
            "max_contributions": MAX_CONTRIBUTIONS,
            "max_depth": MAX_DEPTH,
            "max_nodes": MAX_NODES,
            "max_string_length": MAX_STRING_LENGTH,
        },
        "data_only": True,
        "executes_code": False,
    }


def _walk_data(
    value: Any,
    path: str,
    issues: list[ManifestIssue],
    *,
    depth: int = 0,
    nodes: list[int],
) -> None:
    if depth > MAX_DEPTH:
        issues.append(ManifestIssue(path, "too_deep", "Manifest nesting is too deep"))
        return
    nodes[0] += 1
    if nodes[0] > MAX_NODES:
        issues.append(ManifestIssue(path, "too_large", "Manifest has too many values"))
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            if not isinstance(key, str):
                issues.append(ManifestIssue(child, "invalid_key", "Object keys must be strings"))
                continue
            if key.casefold() in FORBIDDEN_KEYS:
                issues.append(
                    ManifestIssue(
                        child,
                        "forbidden_key",
                        f"Key '{key}' is not allowed in a data-only manifest",
                    )
                )
            _walk_data(item, child, issues, depth=depth + 1, nodes=nodes)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _walk_data(item, f"{path}[{index}]", issues, depth=depth + 1, nodes=nodes)
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            issues.append(ManifestIssue(path, "field_too_long", "String value is too long"))
        return
    if value is not None and not isinstance(value, (bool, int, float)):
        issues.append(
            ManifestIssue(path, "not_data_only", "Manifest values must be JSON primitives")
        )


def _string_field(
    raw: Mapping[str, Any],
    key: str,
    issues: list[ManifestIssue],
    *,
    required: bool,
    limit: int = 240,
    path: str = "",
) -> str:
    value = raw.get(key)
    if value is None:
        if required:
            issues.append(ManifestIssue(f"{path}.{key}", "missing_field", "Field is required"))
        return ""
    if not isinstance(value, str):
        issues.append(ManifestIssue(f"{path}.{key}", "invalid_type", "Field must be a string"))
        return ""
    try:
        return clean_text(value, limit=limit)
    except ValueError as error:
        issues.append(ManifestIssue(f"{path}.{key}", "field_too_long", str(error)))
        return ""


def _validate_contribution(
    raw: Any,
    index: int,
    issues: list[ManifestIssue],
    seen_ids: set[str],
) -> dict[str, Any] | None:
    path = f"contributions[{index}]"
    if not isinstance(raw, Mapping):
        issues.append(ManifestIssue(path, "invalid_type", "Contribution must be an object"))
        return None
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in CONTRIBUTION_FIELDS:
        issues.append(
            ManifestIssue(
                f"{path}.kind",
                "invalid_choice",
                f"Contribution kind must be one of {sorted(CONTRIBUTION_FIELDS)}",
            )
        )
        return None
    schema = CONTRIBUTION_FIELDS[kind]
    for key in raw:
        if key not in schema:
            issues.append(
                ManifestIssue(f"{path}.{key}", "unknown_field", "Field is not part of the schema")
            )
    result: dict[str, Any] = {"kind": kind}
    for key, (_, required) in schema.items():
        if key == "kind":
            continue
        value = raw.get(key)
        if value is None:
            if required:
                issues.append(ManifestIssue(f"{path}.{key}", "missing_field", "Field is required"))
            continue
        if key in ("title", "id", "description", "group"):
            result[key] = _string_field(raw, key, issues, required=required, path=path)
        elif key == "location":
            if value not in PANEL_LOCATIONS:
                issues.append(
                    ManifestIssue(f"{path}.{key}", "invalid_choice", "Unknown panel location")
                )
            else:
                result[key] = str(value)
        elif key == "binding":
            if not isinstance(value, str) or not _BINDING_PATTERN.fullmatch(value):
                issues.append(
                    ManifestIssue(f"{path}.{key}", "invalid_choice", "Invalid shortcut binding")
                )
            else:
                result[key] = value
        elif key == "route":
            if not isinstance(value, str) or not _ROUTE_PATTERN.fullmatch(value):
                issues.append(
                    ManifestIssue(f"{path}.{key}", "invalid_choice", "Invalid view route label")
                )
            else:
                result[key] = value
        elif key == "tokens":
            if not isinstance(value, Mapping) or any(
                not isinstance(name, str) or not isinstance(token, str)
                for name, token in value.items()
            ):
                issues.append(
                    ManifestIssue(
                        f"{path}.{key}", "invalid_type", "Tokens must be string to string"
                    )
                )
            else:
                result[key] = dict(value)
    identifier = result.get("id", "")
    if identifier:
        if identifier in seen_ids:
            issues.append(
                ManifestIssue(f"{path}.id", "conflict", "Contribution ids must be unique")
            )
        seen_ids.add(identifier)
    return result


def validate_manifest(raw: Any) -> ValidationReport:
    """Validate an untrusted manifest and return a normalized document."""
    issues: list[ManifestIssue] = []
    if not isinstance(raw, Mapping):
        return ValidationReport(
            valid=False,
            issues=(ManifestIssue("manifest", "invalid_type", "Manifest must be an object"),),
        )
    try:
        encoded = json.dumps(raw, sort_keys=True, default=str)
        if len(encoded.encode("utf-8")) > MAX_MANIFEST_BYTES:
            issues.append(
                ManifestIssue("manifest", "payload_too_large", "Manifest exceeds the size limit")
            )
        json.loads(encoded)
    except (TypeError, ValueError) as error:
        return ValidationReport(
            valid=False,
            issues=(ManifestIssue("manifest", "not_data_only", f"Not JSON data: {error}"),),
        )
    _walk_data(raw, "", issues, nodes=[0])

    for key in raw:
        if key not in TOP_LEVEL_FIELDS:
            issues.append(
                ManifestIssue(str(key), "unknown_field", "Field is not part of the schema")
            )

    schema = _string_field(raw, "schema", issues, required=True)
    if schema and schema != SCHEMA_ID:
        issues.append(ManifestIssue("schema", "invalid_choice", f"Expected {SCHEMA_ID}"))
    identifier = _string_field(raw, "id", issues, required=True)
    if identifier and not _ID_PATTERN.fullmatch(identifier):
        issues.append(ManifestIssue("id", "invalid_choice", "Invalid extension id"))
    version = _string_field(raw, "version", issues, required=True)
    if version and not _VERSION_PATTERN.fullmatch(version):
        issues.append(ManifestIssue("version", "invalid_choice", "Version must be semantic"))
    title = _string_field(raw, "title", issues, required=True)
    summary = _string_field(raw, "summary", issues, required=False, limit=4000)

    requires: list[str] = []
    raw_requires = raw.get("requires", [])
    if raw_requires is not None:
        if not isinstance(raw_requires, (list, tuple)):
            issues.append(ManifestIssue("requires", "invalid_type", "Requires must be a list"))
        else:
            for capability in raw_requires:
                if not isinstance(capability, str) or capability not in ALL_CAPABILITIES:
                    issues.append(
                        ManifestIssue(
                            "requires", "unknown_capability", f"Unknown capability: {capability}"
                        )
                    )
                else:
                    requires.append(capability)

    contributions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    raw_contributions = raw.get("contributions", ())
    if not isinstance(raw_contributions, (list, tuple)):
        issues.append(
            ManifestIssue("contributions", "invalid_type", "Contributions must be a list")
        )
    elif not raw_contributions:
        issues.append(
            ManifestIssue("contributions", "missing_field", "At least one contribution is required")
        )
    elif len(raw_contributions) > MAX_CONTRIBUTIONS:
        issues.append(
            ManifestIssue(
                "contributions", "field_too_long", f"At most {MAX_CONTRIBUTIONS} contributions"
            )
        )
    else:
        for index, item in enumerate(raw_contributions):
            contribution = _validate_contribution(item, index, issues, seen_ids)
            if contribution is not None:
                contributions.append(contribution)

    metadata: dict[str, Any] = {}
    raw_metadata = raw.get("metadata", {})
    if raw_metadata is not None:
        if not isinstance(raw_metadata, Mapping):
            issues.append(ManifestIssue("metadata", "invalid_type", "Metadata must be an object"))
        else:
            try:
                metadata = check_metadata(raw_metadata)
            except ValueError as error:
                issues.append(ManifestIssue("metadata", "invalid_request", str(error)))

    normalized: dict[str, Any] | None = None
    fingerprint = ""
    if not any(item.severity == "error" for item in issues):
        normalized = {
            "schema": schema,
            "id": identifier,
            "version": version,
            "title": title,
            "summary": summary,
            "requires": sorted(set(requires)),
            "contributions": contributions,
            "metadata": metadata,
        }
        fingerprint = compute_etag(normalized)
    return ValidationReport(
        valid=normalized is not None,
        issues=tuple(issues),
        normalized=normalized,
        fingerprint=fingerprint,
    )


def parse_manifest(raw: Mapping[str, Any]) -> ExtensionManifest:
    """Parse a validated document into a typed manifest."""
    report = validate_manifest(raw)
    if report.normalized is None:
        raise ManifestError(
            "Invalid extension manifest: " + "; ".join(report.messages()),
            field="manifest",
            context={"issues": [item.as_dict() for item in report.errors]},
        )
    document = report.normalized
    contributions = tuple(
        Contribution(
            kind=str(item["kind"]),
            id=str(item["id"]),
            title=str(item["title"]),
            attributes={
                key: value for key, value in item.items() if key not in {"kind", "id", "title"}
            },
        )
        for item in document["contributions"]
    )
    return ExtensionManifest(
        id=str(document["id"]),
        version=str(document["version"]),
        title=str(document["title"]),
        schema=str(document["schema"]),
        summary=str(document["summary"]),
        requires=tuple(str(item) for item in document["requires"]),
        contributions=contributions,
        metadata=dict(document["metadata"]),
    )


class ManifestStore:
    """In-memory manifest registry with ETag concurrency control."""

    def __init__(self) -> None:
        self._records: dict[str, ExtensionManifest] = {}
        self._revision = 0

    @property
    def revision(self) -> int:
        """Return the number of accepted mutations."""
        return self._revision

    def install(
        self,
        manifest: ExtensionManifest,
        *,
        expected_etag: str = "",
    ) -> tuple[ExtensionManifest, bool]:
        """Install or update a manifest, returning it and a replaced flag."""
        current = self._records.get(manifest.id)
        current_etag = current.fingerprint if current is not None else ""
        if expected_etag and not etag_matches(expected_etag, current_etag):
            raise V3Error(
                V3ErrorCode.PRECONDITION_FAILED,
                "Manifest ETag does not match the stored version",
                field="if_none_match",
            )
        if current is not None and current.fingerprint == manifest.fingerprint:
            return current, False
        self._records[manifest.id] = manifest
        self._revision += 1
        return manifest, current is not None

    def remove(self, identifier: str, *, expected_etag: str = "") -> ExtensionManifest:
        """Remove a manifest by id."""
        current = self._records.get(identifier)
        if current is None:
            raise V3Error(V3ErrorCode.NOT_FOUND, f"Unknown extension: {identifier}")
        if expected_etag and not etag_matches(expected_etag, current.fingerprint):
            raise V3Error(
                V3ErrorCode.PRECONDITION_FAILED,
                "Manifest ETag does not match the stored version",
                field="if_none_match",
            )
        del self._records[identifier]
        self._revision += 1
        return current

    def get(self, identifier: str) -> ExtensionManifest:
        """Return a manifest by id."""
        manifest = self._records.get(identifier)
        if manifest is None:
            raise V3Error(V3ErrorCode.NOT_FOUND, f"Unknown extension: {identifier}")
        return manifest

    def list(self) -> tuple[ExtensionManifest, ...]:
        """Return all manifests in stable id order."""
        return tuple(self._records[key] for key in sorted(self._records))

    def contains(self, identifier: str) -> bool:
        """Return whether an id is installed."""
        return identifier in self._records

    def page(self, offset: int, size: int) -> tuple[tuple[ExtensionManifest, ...], PageMeta, str]:
        """Return a slice using B00 pagination metadata."""
        request = PageRequest(offset=offset, size=size)
        items, meta, cursor = paginate(self.list(), request)
        return items, meta, cursor

    def size(self) -> int:
        """Return the manifest count."""
        return len(self._records)

    def clear(self) -> None:
        """Remove every manifest."""
        self._records.clear()
        self._revision += 1

    def identifiers(self) -> tuple[str, ...]:
        """Return installed ids in stable order."""
        return tuple(sorted(self._records))

    def summaries(self, capabilities: Iterable[str] = ()) -> tuple[dict[str, Any], ...]:
        """Return compact manifests for listings."""
        wanted = set(capabilities)
        return tuple(
            {
                "id": manifest.id,
                "version": manifest.version,
                "title": manifest.title,
                "summary": manifest.summary,
                "requires": list(manifest.requires),
                "contributions": [item.as_dict() for item in manifest.contributions],
                "etag": manifest.fingerprint,
                "matched": not wanted or bool(wanted.intersection(manifest.requires)),
            }
            for manifest in self.list()
        )
