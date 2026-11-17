"""Import, export, and JSON round-trip helpers for playbook data."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from redscribe.v2.playbooks.errors import BundleError, VersionConflictError
from redscribe.v2.playbooks.types import (
    ChecklistItem,
    Condition,
    ConditionOperator,
    Issue,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    RunEvent,
    RunState,
    RunStatus,
    SnippetRecord,
    StepKind,
    StepStatus,
    TemplateRecord,
    Value,
    VariableDefinition,
    VariableKind,
)

BUNDLE_KIND = "redscribe-playbooks"
BUNDLE_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ImportReport:
    """The result of importing one bundle."""

    playbooks: tuple[Playbook, ...] = ()
    snippets: tuple[SnippetRecord, ...] = ()
    templates: tuple[TemplateRecord, ...] = ()
    runs: tuple[RunState, ...] = ()
    conflicts: tuple[str, ...] = ()
    renamed: tuple[str, ...] = ()
    issues: tuple[Issue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(issue.is_error for issue in self.issues)

    def as_dict(self) -> dict[str, Any]:
        return {
            "playbooks": [item.key for item in self.playbooks],
            "snippets": [item.key for item in self.snippets],
            "templates": [item.key for item in self.templates],
            "runs": [item.id for item in self.runs],
            "conflicts": list(self.conflicts),
            "renamed": list(self.renamed),
            "issues": [issue.as_dict() for issue in self.issues],
            "ok": self.ok,
        }


@dataclass(frozen=True, slots=True)
class ExportBundle:
    """A portable, deterministic playbook export."""

    kind: str
    schema_version: str
    exported_at: str
    source: str
    playbooks: tuple[dict[str, Any], ...]
    snippets: tuple[dict[str, Any], ...]
    templates: tuple[dict[str, Any], ...]
    runs: tuple[dict[str, Any], ...] = ()
    manifest: dict[str, Any] | None = None
    checksum: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schema_version": self.schema_version,
            "exported_at": self.exported_at,
            "source": self.source,
            "playbooks": list(self.playbooks),
            "snippets": list(self.snippets),
            "templates": list(self.templates),
            "runs": list(self.runs),
            "manifest": dict(self.manifest or {}),
            "checksum": self.checksum,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the bundle as canonical JSON."""
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=indent, sort_keys=True)


def canonical_json(payload: Any) -> str:
    """Return canonical compact JSON used for checksums."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def checksum(payload: Any) -> str:
    """Return a SHA-256 checksum for a JSON-like payload."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_bundle(
    playbooks: tuple[Playbook, ...] | list[Playbook],
    snippets: tuple[SnippetRecord, ...] | list[SnippetRecord],
    templates: tuple[TemplateRecord, ...] | list[TemplateRecord],
    runs: tuple[RunState, ...] | list[RunState] = (),
    *,
    source: str = "redscribe",
    exported_at: str | None = None,
) -> ExportBundle:
    """Create a checksummed export bundle from domain objects."""
    playbook_data = tuple(item.as_dict() for item in sorted(playbooks, key=lambda item: item.key))
    snippet_data = tuple(item.as_dict() for item in sorted(snippets, key=lambda item: item.key))
    template_data = tuple(item.as_dict() for item in sorted(templates, key=lambda item: item.key))
    run_data = tuple(item.as_dict() for item in sorted(runs, key=lambda item: item.id))
    manifest = {
        "playbooks": len(playbook_data),
        "snippets": len(snippet_data),
        "templates": len(template_data),
        "runs": len(run_data),
        "keys": {
            "playbooks": [str(item["key"]) for item in playbook_data],
            "snippets": [str(item["key"]) for item in snippet_data],
            "templates": [str(item["key"]) for item in template_data],
        },
    }
    payload = {
        "kind": BUNDLE_KIND,
        "schema_version": BUNDLE_VERSION,
        "exported_at": exported_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "playbooks": list(playbook_data),
        "snippets": list(snippet_data),
        "templates": list(template_data),
        "runs": list(run_data),
        "manifest": manifest,
    }
    return ExportBundle(
        kind=str(payload["kind"]),
        schema_version=str(payload["schema_version"]),
        exported_at=str(payload["exported_at"]),
        source=str(payload["source"]),
        playbooks=playbook_data,
        snippets=snippet_data,
        templates=template_data,
        runs=run_data,
        manifest=manifest,
        checksum=checksum(payload),
    )


def validate_bundle(payload: Any) -> tuple[Issue, ...]:
    """Validate the shape and version of an import payload."""
    if not isinstance(payload, dict):
        return (Issue("invalid-bundle", "Bundle must be a JSON object"),)
    issues: list[Issue] = []
    if payload.get("kind") != BUNDLE_KIND:
        issues.append(Issue("invalid-kind", f"Bundle kind must be {BUNDLE_KIND}"))
    version = str(payload.get("schema_version", ""))
    try:
        major = int(version.split(".", 1)[0])
    except ValueError:
        major = -1
    if major != 1:
        issues.append(
            Issue(
                "unsupported-version",
                f"Unsupported bundle version: {version}",
                severity="error" if major > 1 else "warning",
            )
        )
    for key in ("playbooks", "snippets", "templates", "runs"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            issues.append(Issue("invalid-section", f"Bundle section '{key}' must be a list"))
    expected = payload.get("manifest", {})
    if isinstance(expected, dict):
        for key, section in (
            ("playbooks", "playbooks"),
            ("snippets", "snippets"),
            ("templates", "templates"),
        ):
            declared = expected.get(key)
            actual = payload.get(section, [])
            if isinstance(declared, int) and isinstance(actual, list) and declared != len(actual):
                issues.append(
                    Issue(
                        "manifest-mismatch", f"Manifest count for {section} does not match payload"
                    )
                )
    return tuple(issues)


def verify_checksum(payload: Any) -> bool:
    """Verify a bundle checksum when one is present."""
    if not isinstance(payload, dict) or not payload.get("checksum"):
        return False
    expected = str(payload["checksum"])
    naked = {key: value for key, value in payload.items() if key != "checksum"}
    return checksum(naked) == expected


def import_bundle(
    payload: Any,
    *,
    strategy: str = "skip",
    existing: dict[str, set[str]] | None = None,
) -> ImportReport:
    """Import a bundle with explicit duplicate handling."""
    if strategy not in ("skip", "replace", "rename"):
        raise BundleError(f"Unknown import strategy: {strategy}")
    issues = list(validate_bundle(payload))
    if any(issue.is_error for issue in issues):
        raise BundleError(
            "Bundle validation failed", details={"issues": [i.as_dict() for i in issues]}
        )
    if not isinstance(payload, dict):
        raise BundleError("Bundle must be an object")
    if payload.get("checksum") and not verify_checksum(payload):
        issues.append(Issue("checksum-mismatch", "Bundle checksum does not match payload"))
        raise BundleError("Bundle checksum does not match payload")
    present = existing or {"playbooks": set(), "snippets": set(), "templates": set()}
    playbooks, playbook_conflicts, playbook_renames = _import_section(
        payload.get("playbooks", []),
        "playbooks",
        playbook_from_dict,
        strategy,
        present.get("playbooks", set()),
    )
    snippets, snippet_conflicts, snippet_renames = _import_section(
        payload.get("snippets", []),
        "snippets",
        snippet_from_dict,
        strategy,
        present.get("snippets", set()),
    )
    templates, template_conflicts, template_renames = _import_section(
        payload.get("templates", []),
        "templates",
        template_from_dict,
        strategy,
        present.get("templates", set()),
    )
    runs: list[RunState] = []
    for raw in payload.get("runs", []) or []:
        try:
            runs.append(run_from_dict(raw))
        except (BundleError, VersionConflictError, ValueError) as exc:
            issues.append(Issue("invalid-run", f"Skipped invalid run: {exc}", severity="warning"))
    return ImportReport(
        playbooks=tuple(playbooks),
        snippets=tuple(snippets),
        templates=tuple(templates),
        runs=tuple(runs),
        conflicts=(*playbook_conflicts, *snippet_conflicts, *template_conflicts),
        renamed=(*playbook_renames, *snippet_renames, *template_renames),
        issues=tuple(issues),
    )


def merge_bundles(*bundles: ExportBundle) -> ExportBundle:
    """Merge bundles with first-wins duplicate semantics."""
    if not bundles:
        return build_bundle((), (), ())
    playbooks: dict[str, dict[str, Any]] = {}
    snippets: dict[str, dict[str, Any]] = {}
    templates: dict[str, dict[str, Any]] = {}
    runs: dict[int, dict[str, Any]] = {}
    for bundle in bundles:
        for key, item in _keyed(bundle.playbooks):
            playbooks.setdefault(key, item)
        for key, item in _keyed(bundle.snippets):
            snippets.setdefault(key, item)
        for key, item in _keyed(bundle.templates):
            templates.setdefault(key, item)
        for run in bundle.runs:
            runs.setdefault(int(run.get("id", 0)), run)
    return build_bundle(
        tuple(playbook_from_dict(item) for item in playbooks.values()),
        tuple(snippet_from_dict(item) for item in snippets.values()),
        tuple(template_from_dict(item) for item in templates.values()),
        tuple(run_from_dict(item) for item in runs.values()),
        source="merge",
    )


def variable_from_dict(payload: Any) -> VariableDefinition:
    """Restore a variable definition from JSON data."""
    data = _object(payload, "variable")
    kind = _enum(VariableKind, data.get("kind", "text"), VariableKind.TEXT)
    minimum, maximum = data.get("minimum"), data.get("maximum")
    return VariableDefinition(
        key=str(data.get("key", "")),
        label=str(data.get("label", "")),
        kind=kind,
        required=bool(data.get("required", False)),
        default=value_from_json(data.get("default", "")),
        choices=tuple(str(item) for item in _sequence(data.get("choices", []))),
        description=str(data.get("description", "")),
        secret=bool(data.get("secret", False)),
        pattern=str(data.get("pattern", "")),
        minimum=float(minimum)
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool)
        else None,
        maximum=float(maximum)
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool)
        else None,
    )


def condition_from_dict(payload: Any) -> Condition:
    """Restore a condition from JSON data."""
    data = _object(payload, "condition")
    return Condition(
        field=str(data.get("field", "")),
        operator=_enum(ConditionOperator, data.get("operator", "exists"), ConditionOperator.EXISTS),
        value=value_from_json(data.get("value", "")),
    )


def checklist_from_dict(payload: Any) -> ChecklistItem:
    """Restore a checklist item from JSON data."""
    data = _object(payload, "checklist item")
    raw_condition = data.get("condition")
    condition = condition_from_dict(raw_condition) if isinstance(raw_condition, dict) else None
    return ChecklistItem(
        id=str(data.get("id", "")),
        label=str(data.get("label", "")),
        detail=str(data.get("detail", "")),
        required=bool(data.get("required", True)),
        condition=condition,
        tags=tuple(str(item) for item in _sequence(data.get("tags", []))),
    )


def step_from_dict(payload: Any) -> PlaybookStep:
    """Restore a playbook step from JSON data."""
    data = _object(payload, "step")
    return PlaybookStep(
        id=str(data.get("id", "")),
        title=str(data.get("title", "")),
        kind=_enum(StepKind, data.get("kind", "action"), StepKind.ACTION),
        summary=str(data.get("summary", "")),
        command_template=str(data.get("command_template", "")),
        snippet_key=str(data.get("snippet_key", "")),
        checklist=tuple(checklist_from_dict(item) for item in _sequence(data.get("checklist", []))),
        depends_on=tuple(str(item) for item in _sequence(data.get("depends_on", []))),
        when=tuple(condition_from_dict(item) for item in _sequence(data.get("when", []))),
        variables=tuple(str(item) for item in _sequence(data.get("variables", []))),
        optional=bool(data.get("optional", False)),
        estimated_minutes=int(data.get("estimated_minutes", 0) or 0),
        tags=tuple(str(item) for item in _sequence(data.get("tags", []))),
        note=str(data.get("note", "")),
    )


def playbook_from_dict(payload: Any) -> Playbook:
    """Restore a playbook from JSON data."""
    data = _object(payload, "playbook")
    return Playbook(
        id=int(data.get("id", 0) or 0),
        key=str(data.get("key", "")),
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        status=_enum(PlaybookStatus, data.get("status", "draft"), PlaybookStatus.DRAFT),
        category=str(data.get("category", "general") or "general"),
        tags=tuple(str(item) for item in _sequence(data.get("tags", []))),
        version=str(data.get("version", "0.1.0") or "0.1.0"),
        steps=tuple(step_from_dict(item) for item in _sequence(data.get("steps", []))),
        variables=tuple(variable_from_dict(item) for item in _sequence(data.get("variables", []))),
        owner=str(data.get("owner", "")),
        created_at=str(data.get("created_at", "")),
        updated_at=str(data.get("updated_at", "")),
        references=tuple(str(item) for item in _sequence(data.get("references", []))),
    )


def snippet_from_dict(payload: Any) -> SnippetRecord:
    """Restore a snippet record from JSON data."""
    data = _object(payload, "snippet")
    return SnippetRecord(
        id=int(data.get("id", 0) or 0),
        key=str(data.get("key", "")),
        title=str(data.get("title", "")),
        command=str(data.get("command", "")),
        description=str(data.get("description", "")),
        tags=tuple(str(item) for item in _sequence(data.get("tags", []))),
        library=str(data.get("library", "personal") or "personal"),
        variables=tuple(str(item) for item in _sequence(data.get("variables", []))),
        usage_count=int(data.get("usage_count", 0) or 0),
        version=str(data.get("version", "1.0.0") or "1.0.0"),
        created_at=str(data.get("created_at", "")),
        updated_at=str(data.get("updated_at", "")),
    )


def template_from_dict(payload: Any) -> TemplateRecord:
    """Restore a template record from JSON data."""
    data = _object(payload, "template")
    return TemplateRecord(
        id=int(data.get("id", 0) or 0),
        key=str(data.get("key", "")),
        name=str(data.get("name", "")),
        content=str(data.get("content", "")),
        description=str(data.get("description", "")),
        tags=tuple(str(item) for item in _sequence(data.get("tags", []))),
        category=str(data.get("category", "general") or "general"),
        variables=tuple(variable_from_dict(item) for item in _sequence(data.get("variables", []))),
        version=str(data.get("version", "1.0.0") or "1.0.0"),
        changelog=tuple(str(item) for item in _sequence(data.get("changelog", []))),
        default_title=str(data.get("default_title", "Untitled") or "Untitled"),
    )


def run_from_dict(payload: Any) -> RunState:
    """Restore a run snapshot from JSON data."""
    data = _object(payload, "run")
    events: list[RunEvent] = []
    for raw in _sequence(data.get("events", [])):
        event = _object(raw, "event")
        events.append(
            RunEvent(
                seq=int(event.get("seq", 0) or 0),
                at=str(event.get("at", "")),
                kind=str(event.get("kind", "")),
                message=str(event.get("message", "")),
                step_id=str(event.get("step_id", "")),
                data=dict(event.get("data", {})) if isinstance(event.get("data"), dict) else {},
            )
        )
    statuses: dict[str, StepStatus] = {}
    raw_statuses = data.get("step_status", {})
    if isinstance(raw_statuses, dict):
        for key, status in raw_statuses.items():
            try:
                statuses[str(key)] = StepStatus(status)
            except (ValueError, TypeError) as exc:
                raise VersionConflictError(
                    f"Unsupported StepStatus: {status}", details={"step": str(key)}
                ) from exc
    context = data.get("context", {})
    return RunState(
        id=int(data.get("id", 0) or 0),
        playbook_key=str(data.get("playbook_key", "")),
        version=str(data.get("version", "0.1.0")),
        status=_enum(RunStatus, data.get("status", "planned"), RunStatus.PLANNED),
        values={
            str(key): value_from_json(value)
            for key, value in _mapping(data.get("values", {})).items()
        },
        step_status=statuses,
        checklist={
            str(key): str(value) for key, value in _mapping(data.get("checklist", {})).items()
        },
        notes={str(key): str(value) for key, value in _mapping(data.get("notes", {})).items()},
        events=tuple(events),
        current_step=str(data.get("current_step", "")),
        started_at=str(data.get("started_at", "")),
        updated_at=str(data.get("updated_at", "")),
        finished_at=str(data.get("finished_at", "")),
        context=dict(context) if isinstance(context, dict) else {},
    )


def value_from_json(payload: Any) -> Value:
    """Convert an untrusted JSON value into a domain value."""
    if isinstance(payload, (bool, int, float, str)):
        return payload
    if isinstance(payload, list):
        return tuple(value_from_json(item) for item in payload)
    return str(payload) if payload is not None else ""


def _import_section(
    payload: Any,
    section: str,
    parser: Any,
    strategy: str,
    existing_keys: set[str],
) -> tuple[list[Any], tuple[str, ...], tuple[str, ...]]:
    items: list[Any] = []
    conflicts: list[str] = []
    renamed: list[str] = []
    used: set[str] = set(existing_keys)
    for raw in _sequence(payload):
        key = str(_object(raw, section).get("key", ""))
        if key in used:
            if strategy == "skip":
                conflicts.append(key)
                continue
            if strategy == "rename":
                suffix = 2
                candidate = f"{key}-import-{suffix}"
                while candidate in used:
                    suffix += 1
                    candidate = f"{key}-import-{suffix}"
                raw = {**_object(raw, section), "key": candidate}
                key = candidate
                renamed.append(candidate)
        used.add(key)
        try:
            items.append(parser(raw))
        except (ValueError, TypeError, BundleError) as exc:
            raise BundleError(f"Invalid {section} entry: {exc}", details={"key": key}) from exc
    return items, tuple(conflicts), tuple(renamed)


def _keyed(items: Sequence[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [(str(item.get("key", "")), item) for item in items]


def _object(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BundleError(f"Expected {label} to be an object")
    return payload


def _sequence(payload: Any) -> list[Any]:
    return list(payload) if isinstance(payload, (list, tuple)) else []


def _mapping(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _enum(enum_type: Any, value: Any, default: Any) -> Any:
    try:
        return enum_type(value)
    except (ValueError, TypeError):
        return default
