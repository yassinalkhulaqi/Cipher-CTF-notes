"""Typed request contracts for the JSON API dispatch layer.

The browser sends JSON objects to ``Api.handle`` through ``POST /api/<method>``.
This module describes those objects once, in a form that can be introspected by
the ``api_schema`` route and enforced by ``Api.handle`` before a route runs.
Contract checks mirror the hand-written validators in :mod:`redscribe.ui.web.api`
so adding the layer does not change existing response bodies or status codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from redscribe import __version__
from redscribe.domain.models import DIFFICULTIES, STATUSES

CONTRACT_VERSION = "1.0.0"

MAX_TITLE_LENGTH = 200
MAX_SHORT_LENGTH = 200
MAX_TAG_LENGTH = 500
MAX_CONTENT_LENGTH = 1_000_000
MAX_SNIPPET_COMMAND_LENGTH = 4_000
MAX_SNIPPET_DESCRIPTION_LENGTH = 2_000


class ApiErrorCode(str, Enum):
    """Stable machine-readable categories for API failures."""

    UNKNOWN_METHOD = "unknown_method"
    MISSING_FIELD = "missing_field"
    INVALID_TYPE = "invalid_type"
    INVALID_CHOICE = "invalid_choice"
    FIELD_TOO_LONG = "field_too_long"
    UNKNOWN_KEYS = "unknown_keys"
    NOT_FOUND = "not_found"
    INVALID_STATE = "invalid_state"
    INTERNAL = "internal"


class FieldKind(str, Enum):
    """Validation strategy applied to one request field."""

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    CHOICE = "choice"
    ANY = "any"


class ContractError(Exception):
    """A request body that does not satisfy its contract."""

    def __init__(
        self,
        code: ApiErrorCode,
        message: str,
        *,
        status: int = 400,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.field = field


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One field accepted by a dispatch method."""

    name: str
    kind: FieldKind = FieldKind.ANY
    required: bool = False
    default: Any = None
    nullable: bool = False
    max_length: int | None = None
    choices: tuple[str, ...] = ()
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "required": self.required,
            "default": self.default,
            "nullable": self.nullable,
            "max_length": self.max_length,
            "choices": list(self.choices),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class Contract:
    """The request shape and expected failures of one dispatch method."""

    name: str
    summary: str
    fields: tuple[FieldSpec, ...] = ()
    allow_unknown: bool = True
    errors: tuple[ApiErrorCode, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "allow_unknown": self.allow_unknown,
            "errors": [code.value for code in self.errors],
            "fields": [spec.as_dict() for spec in self.fields],
        }


def _str(
    name: str,
    *,
    default: str | None = None,
    required: bool = False,
    max_length: int | None = None,
    description: str = "",
) -> FieldSpec:
    return FieldSpec(
        name,
        FieldKind.STRING,
        required=required,
        default=default,
        max_length=max_length,
        description=description,
    )


def _int(
    name: str,
    *,
    required: bool = True,
    nullable: bool = False,
    description: str = "",
) -> FieldSpec:
    return FieldSpec(
        name,
        FieldKind.INTEGER,
        required=required,
        nullable=nullable,
        description=description,
    )


def _bool(name: str, *, description: str = "") -> FieldSpec:
    return FieldSpec(name, FieldKind.BOOLEAN, required=True, description=description)


def _choice(name: str, choices: tuple[str, ...], *, description: str = "") -> FieldSpec:
    return FieldSpec(name, FieldKind.CHOICE, choices=choices, description=description)


def _any(name: str, *, description: str) -> FieldSpec:
    return FieldSpec(name, FieldKind.ANY, description=description)


_ID: tuple[ApiErrorCode, ...] = (ApiErrorCode.INVALID_TYPE,)
_ID_NOT_FOUND = (ApiErrorCode.INVALID_TYPE, ApiErrorCode.NOT_FOUND)
_TEXT = (ApiErrorCode.INVALID_TYPE, ApiErrorCode.MISSING_FIELD)
_TEXT_LONG = (ApiErrorCode.INVALID_TYPE, ApiErrorCode.MISSING_FIELD, ApiErrorCode.FIELD_TOO_LONG)
_DEFAULTED_TEXT_LONG = (ApiErrorCode.INVALID_TYPE, ApiErrorCode.FIELD_TOO_LONG)
_CHOICE_ERRORS = (ApiErrorCode.INVALID_TYPE, ApiErrorCode.INVALID_CHOICE)

_CONTRACTS: tuple[Contract, ...] = (
    Contract("boot", "Bootstrap theme, layout, stats, and vault path for the UI."),
    Contract("tree", "Return the folder tree for the sidebar."),
    Contract(
        "node",
        "Return one node with children or rendered note preview.",
        fields=(_int("id"),),
        errors=_ID_NOT_FOUND,
    ),
    Contract(
        "create_note",
        "Create a note from a template.",
        fields=(
            _str("template_key", default="blank", description="Template registry key."),
            _str("title", default="", max_length=MAX_TITLE_LENGTH),
            _str("target", default="", max_length=MAX_SHORT_LENGTH),
            _int(
                "parent_id",
                required=False,
                nullable=True,
                description="Folder id or null for the root.",
            ),
        ),
        errors=(*_DEFAULTED_TEXT_LONG, ApiErrorCode.INVALID_STATE),
    ),
    Contract(
        "create_folder",
        "Create a folder, optionally under a parent folder.",
        fields=(
            _str("title", default="", max_length=MAX_TITLE_LENGTH),
            _int(
                "parent_id",
                required=False,
                nullable=True,
                description="Folder id or null for the root.",
            ),
        ),
        errors=(*_DEFAULTED_TEXT_LONG, ApiErrorCode.INVALID_STATE),
    ),
    Contract(
        "rename",
        "Rename one node.",
        fields=(
            _int("id"),
            _str("title", default="", max_length=MAX_TITLE_LENGTH),
        ),
        errors=(*_DEFAULTED_TEXT_LONG, ApiErrorCode.INVALID_STATE),
    ),
    Contract(
        "update_node",
        "Update any subset of mutable node fields.",
        fields=(
            _int("id"),
            _str("title", max_length=MAX_TITLE_LENGTH, description="Optional new title."),
            _any("tags", description="Optional tag string, coerced and capped server-side."),
            _any("target", description="Optional target string, coerced and capped server-side."),
            _choice("status", STATUSES),
            _choice("difficulty", DIFFICULTIES),
            _any("flag", description="Optional flag string, coerced and capped server-side."),
            _any("pinned", description="Optional boolean converted to an integer column."),
        ),
        errors=(*_CHOICE_ERRORS, ApiErrorCode.INVALID_STATE),
    ),
    Contract(
        "save_content",
        "Replace a note's Markdown body and record a version.",
        fields=(
            _int("id"),
            _str("content", required=True, max_length=MAX_CONTENT_LENGTH),
        ),
        errors=_TEXT_LONG,
    ),
    Contract(
        "set_pinned",
        "Pin or unpin one node.",
        fields=(_int("id"), _bool("pinned")),
        errors=_ID,
    ),
    Contract(
        "duplicate_node",
        "Duplicate one node and its subtree.",
        fields=(_int("id"),),
        errors=_ID_NOT_FOUND,
    ),
    Contract(
        "reorder_node",
        "Move one node by a relative offset among its siblings.",
        fields=(_int("id"), _int("offset")),
        errors=_ID,
    ),
    Contract(
        "move_node",
        "Reparent one node, optionally before a sibling.",
        fields=(
            _int("id"),
            _int(
                "parent_id",
                required=False,
                nullable=True,
                description="Destination folder or null.",
            ),
            _int(
                "before_id",
                required=False,
                nullable=True,
                description="Sibling id or null to append.",
            ),
        ),
        errors=_ID,
    ),
    Contract("trash_node", "Move one node to the trash.", fields=(_int("id"),), errors=_ID),
    Contract("restore_node", "Restore one trashed node.", fields=(_int("id"),), errors=_ID),
    Contract("trashed_nodes", "List top-level trashed nodes."),
    Contract(
        "empty_trash",
        "Back up the vault and permanently remove all trashed nodes.",
        errors=(ApiErrorCode.INTERNAL,),
    ),
    Contract(
        "list_versions",
        "List saved versions of one note.",
        fields=(_int("id"),),
        errors=_ID_NOT_FOUND,
    ),
    Contract(
        "get_version",
        "Return one stored note version.",
        fields=(_int("version_id"),),
        errors=_ID_NOT_FOUND,
    ),
    Contract(
        "restore_version",
        "Restore a note from one stored version.",
        fields=(_int("version_id"),),
        errors=_ID_NOT_FOUND,
    ),
    Contract("rebuild_search_index", "Rebuild the full-text search index."),
    Contract("backup_vault", "Write an automatic vault backup.", errors=(ApiErrorCode.INTERNAL,)),
    Contract(
        "search",
        "Full-text search across notes.",
        fields=(_str("query", required=True),),
        errors=_TEXT,
    ),
    Contract(
        "quick_jump",
        "Fuzzy-match note titles and paths.",
        fields=(_str("query", required=True),),
        errors=_TEXT,
    ),
    Contract(
        "recent_notes",
        "List the most recently updated notes.",
        fields=(
            _int(
                "limit", required=False, nullable=True, description="Maximum results, default 10."
            ),
        ),
        errors=_ID,
    ),
    Contract("pinned_notes", "List pinned notes."),
    Contract("stats", "Return aggregate vault statistics."),
    Contract("collected_flags", "List flags collected from notes."),
    Contract("flag_patterns", "Return the known flag-format registry."),
    Contract("flag_insights", "Return aggregate flag analytics."),
    Contract("tag_counts", "Return tag frequencies."),
    Contract(
        "notes_tagged",
        "List notes carrying one tag.",
        fields=(_str("tag", required=True),),
        errors=_TEXT,
    ),
    Contract("graph", "Return the vault knowledge graph."),
    Contract(
        "backlinks",
        "Return links, backlinks, and unresolved links for one note.",
        fields=(_int("id"),),
        errors=_ID_NOT_FOUND,
    ),
    Contract(
        "timeline",
        "Return recent activity, optionally scoped to a folder.",
        fields=(
            _int(
                "folder_id",
                required=False,
                nullable=True,
                description="Folder subtree or null for all notes.",
            ),
            _int("limit", required=False, nullable=True, description="Maximum events, default 50."),
        ),
        errors=_ID,
    ),
    Contract("templates", "Return the note template registry."),
    Contract("list_snippets", "List built-in and custom snippets."),
    Contract(
        "search_snippets",
        "Fuzzy-search built-in and custom snippets.",
        fields=(
            _str("query", required=True),
            _int(
                "limit", required=False, nullable=True, description="Maximum results, default 12."
            ),
        ),
        errors=_TEXT,
    ),
    Contract(
        "resolve_snippet",
        "Expand a snippet command against a target.",
        fields=(
            _str("command", required=True),
            _str("target", default="", description="Replacement for target placeholders."),
        ),
        errors=_TEXT,
    ),
    Contract(
        "create_snippet",
        "Create a custom snippet.",
        fields=(
            _str("title", required=True, max_length=MAX_TITLE_LENGTH),
            _str("command", required=True, max_length=MAX_SNIPPET_COMMAND_LENGTH),
            _str("description", default="", max_length=MAX_SNIPPET_DESCRIPTION_LENGTH),
            _str("tags", default="", max_length=MAX_TAG_LENGTH),
        ),
        errors=_TEXT_LONG,
    ),
    Contract(
        "update_snippet",
        "Replace all fields of a custom snippet.",
        fields=(
            _int("id"),
            _str("title", required=True, max_length=MAX_TITLE_LENGTH),
            _str("command", required=True, max_length=MAX_SNIPPET_COMMAND_LENGTH),
            _str("description", default="", max_length=MAX_SNIPPET_DESCRIPTION_LENGTH),
            _str("tags", default="", max_length=MAX_TAG_LENGTH),
        ),
        errors=(*_TEXT_LONG, ApiErrorCode.NOT_FOUND),
    ),
    Contract(
        "delete_snippet",
        "Delete one custom snippet.",
        fields=(_int("id"),),
        errors=_ID_NOT_FOUND,
    ),
    Contract(
        "render_preview",
        "Render Markdown to HTML for the editor preview.",
        fields=(_str("content", required=True),),
        errors=_TEXT,
    ),
    Contract("get_settings", "Read all UI settings."),
    Contract(
        "set_settings",
        "Validate and persist any subset of UI settings.",
        fields=(
            _str("theme", description="Lowercased light or dark."),
            _int(
                "font_size",
                required=False,
                nullable=True,
                description="Integer from 9 through 18.",
            ),
            _str("last_template", description="Template key."),
            _str("view_mode", description="editor, split, or preview."),
            _any("restore_last_note", description="Boolean or its string form."),
            _any("sync_preview_scroll", description="Boolean or its string form."),
            _any("sidebar_width", description="Integer 200-600 or empty to clear."),
            _any("split_sash", description="Integer 20-85 or empty to clear."),
            _any("last_note", description="Note id or empty to clear."),
            _any("tree_expanded", description="Comma-separated id list or empty."),
        ),
        allow_unknown=False,
        errors=(ApiErrorCode.INVALID_TYPE, ApiErrorCode.UNKNOWN_KEYS, ApiErrorCode.INVALID_STATE),
    ),
    Contract("load_demo", "Seed the vault with demonstration content."),
    Contract(
        "export_note_markdown",
        "Render one note as downloadable Markdown.",
        fields=(_int("id"),),
        errors=(ApiErrorCode.INVALID_TYPE, ApiErrorCode.NOT_FOUND, ApiErrorCode.INVALID_STATE),
    ),
    Contract(
        "export_note_html",
        "Render one note as a standalone HTML document.",
        fields=(_int("id"),),
        errors=(ApiErrorCode.INVALID_TYPE, ApiErrorCode.NOT_FOUND, ApiErrorCode.INVALID_STATE),
    ),
    Contract("export_vault_html", "Render a vault-wide HTML report."),
    Contract(
        "quick_capture",
        "Create a note from a single capture payload.",
        fields=(
            _str("title", default="", max_length=MAX_TITLE_LENGTH),
            _str("content", default="", max_length=MAX_CONTENT_LENGTH),
            _str("tags", default="", max_length=MAX_TAG_LENGTH),
            _str("target", default="", max_length=MAX_SHORT_LENGTH),
        ),
        errors=(*_DEFAULTED_TEXT_LONG, ApiErrorCode.INVALID_STATE),
    ),
    Contract("api_health", "Report runtime and contract metadata."),
    Contract("api_schema", "Return the complete API contract description."),
)

CONTRACTS: dict[str, Contract] = {contract.name: contract for contract in _CONTRACTS}
_FIELD_MAPS: dict[str, dict[str, FieldSpec]] = {
    name: {spec.name: spec for spec in contract.fields} for name, contract in CONTRACTS.items()
}


def contract_counts() -> dict[str, int]:
    """Return stable counts used by both the health and schema routes."""
    fields = [spec for contract in CONTRACTS.values() for spec in contract.fields]
    return {
        "methods": len(CONTRACTS),
        "fields": len(fields),
        "required_fields": sum(1 for spec in fields if spec.required),
        "error_codes": len(list(ApiErrorCode)),
    }


def describe_api() -> dict[str, Any]:
    """Return a JSON-serializable description of every dispatch contract."""
    return {
        "version": CONTRACT_VERSION,
        "application_version": __version__,
        "counts": contract_counts(),
        "error_codes": [code.value for code in ApiErrorCode],
        "methods": {name: contract.as_dict() for name, contract in CONTRACTS.items()},
    }


def _type_message(spec: FieldSpec) -> str:
    if spec.kind is FieldKind.STRING:
        return f"Missing '{spec.name}'" if spec.required else f"'{spec.name}' must be a string"
    if spec.kind is FieldKind.INTEGER:
        return f"'{spec.name}' must be an integer"
    return f"'{spec.name}' must be a boolean"


def _check_value(spec: FieldSpec, value: Any) -> None:
    if spec.kind is FieldKind.ANY:
        return
    if spec.kind is FieldKind.STRING and not isinstance(value, str):
        raise ContractError(
            ApiErrorCode.INVALID_TYPE,
            f"'{spec.name}' must be a string",
            field=spec.name,
        )
    if spec.kind is FieldKind.INTEGER and (isinstance(value, bool) or not isinstance(value, int)):
        raise ContractError(
            ApiErrorCode.INVALID_TYPE,
            f"'{spec.name}' must be an integer",
            field=spec.name,
        )
    if spec.kind is FieldKind.BOOLEAN and not isinstance(value, bool):
        raise ContractError(
            ApiErrorCode.INVALID_TYPE,
            f"'{spec.name}' must be a boolean",
            field=spec.name,
        )
    if isinstance(value, str) and spec.max_length is not None and len(value) > spec.max_length:
        raise ContractError(
            ApiErrorCode.FIELD_TOO_LONG,
            f"{spec.name} exceeds {spec.max_length} characters",
            field=spec.name,
        )
    if spec.choices and value not in spec.choices:
        raise ContractError(
            ApiErrorCode.INVALID_CHOICE,
            f"Unknown {spec.name}: {value}",
            field=spec.name,
        )


def validate_call(method: str, body: dict[str, Any]) -> dict[str, Any]:
    """Validate ``body`` against a contract and return its normalized view.

    The returned mapping is for inspection only; dispatch methods keep receiving
    the original body so their established coercion rules remain authoritative.
    """
    contract = CONTRACTS.get(method)
    if contract is None:
        raise ContractError(
            ApiErrorCode.UNKNOWN_METHOD,
            f"Unknown API method '{method}'",
            status=404,
        )
    fields = _FIELD_MAPS[method]
    if not contract.allow_unknown:
        unknown = sorted(set(body) - set(fields))
        if unknown:
            raise ContractError(
                ApiErrorCode.UNKNOWN_KEYS,
                f"Unsupported setting keys: {', '.join(unknown)}",
            )
    normalized: dict[str, Any] = {}
    for spec in contract.fields:
        if spec.name not in body:
            if spec.required:
                code = (
                    ApiErrorCode.MISSING_FIELD
                    if spec.kind is FieldKind.STRING
                    else ApiErrorCode.INVALID_TYPE
                )
                raise ContractError(code, _type_message(spec), field=spec.name)
            if spec.default is not None:
                normalized[spec.name] = spec.default
            continue
        value = body[spec.name]
        if value is None and spec.nullable:
            continue
        _check_value(spec, value)
        normalized[spec.name] = value
    return normalized
