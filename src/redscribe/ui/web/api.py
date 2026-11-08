"""JSON API surface shared by the web window and the browser frontend.

Every method takes a JSON-serializable dict and returns a JSON-serializable
value. The HTTP layer (:mod:`redscribe.ui.web.server`) routes
``POST /api/<method>`` calls into :meth:`Api.handle` and serializes the
result. Vault behavior (SQLite, FTS search, snippets, exporters) is reused
from the storage layer without modification.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from redscribe import __version__
from redscribe.content.markdown import render_html, render_markdown_body
from redscribe.content.snippets import (
    BUILTIN_SNIPPETS,
    resolve_command,
)
from redscribe.content.templates import TEMPLATES, get_template, render_template
from redscribe.domain.fuzzy import rank_items
from redscribe.domain.models import DIFFICULTIES, STATUSES, Node, SearchHit, Snippet
from redscribe.services.demo import seed_demo
from redscribe.services.exporter import note_to_markdown, vault_report_text
from redscribe.services.flag_intel import (
    build_flag_insights,
    flag_insights_payload,
    flag_patterns_payload,
)
from redscribe.services.graph import build_vault_graph, graph_payload
from redscribe.storage.db import Vault
import hashlib

_SETTING_KEYS = (
    "theme",
    "font_size",
    "last_template",
    "last_note",
    "view_mode",
    "restore_last_note",
    "sidebar_width",
    "split_sash",
    "sync_preview_scroll",
    "tree_expanded",
    "onboarding_seen",
)
_OFF_AXIS_KEYS = frozenset(_SETTING_KEYS)
_FONT_RANGE = range(9, 19)


class ApiError(Exception):
    """An error that is safe to surface to the web frontend."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(slots=True)
class WebOverrides:
    """Command-line overrides applied on top of the stored settings."""

    theme: str | None = None
    font_size: int | None = None


def _require_str(body: dict[str, Any], key: str, *, default: str | None = None) -> str:
    if key not in body:
        if default is None:
            raise ApiError(f"Missing '{key}'")
        return default
    value = body[key]
    if not isinstance(value, str):
        raise ApiError(f"'{key}' must be a string")
    return value


def _require_int(body: dict[str, Any], key: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(f"'{key}' must be an integer")
    return int(value)


def _optional_int(body: dict[str, Any], key: str) -> int | None:
    if key not in body or body[key] is None:
        return None
    return _require_int(body, key)


def _require_bool(body: dict[str, Any], key: str) -> bool:
    value = body.get(key)
    if not isinstance(value, bool):
        raise ApiError(f"'{key}' must be a boolean")
    return value


def _optional_node_id(body: dict[str, Any], key: str = "parent_id") -> int | None:
    if key not in body or body[key] is None:
        return None
    return _require_int(body, key)


def node_summary(node: Node, *, path: str = "") -> dict[str, Any]:
    """Sidebar-level fields for a node."""
    return {
        "id": node.id,
        "parent_id": node.parent_id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "difficulty": node.difficulty,
        "flag": node.flag,
        "tags": node.tags,
        "tag_list": node.tag_list,
        "target": node.target,
        "pinned": node.pinned,
        "trashed": node.is_trashed,
        "path": path,
        "created_at": node.created_at,
        "updated_at": node.updated_at,
    }


def _snippet_data(snippet: Snippet) -> dict[str, Any]:
    data = dataclasses.asdict(snippet)
    data["tag_list"] = snippet.tag_list
    return data


def builtin_plus_custom(vault: Vault) -> list[Snippet]:
    """Return built-in snippets followed by user-created ones."""
    return [*BUILTIN_SNIPPETS, *vault.list_custom_snippets()]


def resolve_snippet_command(command: str, *, target: str) -> str:
    """Fill a snippet's placeholders from the current note's target."""
    return resolve_command(command, target=target)


class Api:
    """Vault operations exposed to the web frontend."""

    def __init__(self, vault: Vault, overrides: WebOverrides | None = None) -> None:
        self._vault = vault
        self._overrides = overrides or WebOverrides()
        self._routes: dict[str, Any] = {
            "boot": self.boot,
            "tree": self.tree,
            "node": self.node,
            "create_note": self.create_note,
            "create_folder": self.create_folder,
            "rename": self.rename,
            "update_node": self.update_node,
            "save_content": self.save_content,
            "set_pinned": self.set_pinned,
            "duplicate_node": self.duplicate_node,
            "reorder_node": self.reorder_node,
            "move_node": self.move_node,
            "trash_node": self.trash_node,
            "restore_node": self.restore_node,
            "trashed_nodes": self.trashed_nodes,
            "empty_trash": self.empty_trash,
            "search": self.search,
            "quick_jump": self.quick_jump,
            "recent_notes": self.recent_notes,
            "pinned_notes": self.pinned_notes,
            "stats": self.stats,
            "collected_flags": self.collected_flags,
            "tag_counts": self.tag_counts,
            "notes_tagged": self.notes_tagged,
            "templates": self.templates,
            "list_snippets": self.list_snippets,
            "resolve_snippet": self.resolve_snippet,
            "create_snippet": self.create_snippet,
            "update_snippet": self.update_snippet,
            "delete_snippet": self.delete_snippet,
            "render_preview": self.render_preview,
            "get_settings": self.get_settings,
            "set_settings": self.set_settings,
            "load_demo": self.load_demo,
            "export_note_markdown": self.export_note_markdown,
            "export_note_html": self.export_note_html,
            "export_vault_html": self.export_vault_html,
            "export_print_html": self.export_print_html,
            "graph": self.graph,
            "flag_patterns": self.flag_patterns,
            "flag_insights": self.flag_insights,
            "attachments": self.attachments,
            "attachment": self.attachment,
            "create_attachment": self.create_attachment,
            "search_snippets": self.search_snippets,
            "quick_capture": self.quick_capture,
        }

    def handle(self, method: str, body: dict[str, Any]) -> Any:
        """Dispatch one API call, converting vault errors into API errors."""
        route = self._routes.get(method)
        if route is None:
            raise ApiError(f"Unknown API method '{method}'", status=404)
        try:
            return route(body)
        except (ValueError, TypeError) as exc:
            raise ApiError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def _path_of(self, node_id: int) -> str:
        return self._vault.path_of(node_id, include_self=False)

    def _setting(self, key: str, default: str) -> str:
        stored = self._vault.get_setting(f"ui.{key}", default)
        return str(stored) if stored is not None else default

    def _tree_walk(self, node: Node) -> dict[str, Any]:
        data = node_summary(node, path=self._path_of(node.id))
        data["children"] = (
            [self._tree_walk(child) for child in self._vault.children(node.id)]
            if node.is_folder
            else []
        )
        return data

    # ------------------------------------------------------------------
    # Boot and layout
    # ------------------------------------------------------------------

    def _setting_int(self, key: str) -> int | None:
        raw = self._setting(key, "").strip()
        if raw.isdigit():
            return int(raw)
        return None

    def boot(self, body: dict[str, Any]) -> dict[str, Any]:
        stats = self._vault.basic_stats()
        return {
            "version": __version__,
            "theme": self._overrides.theme or self._setting("theme", "dark"),
            "font_size": self._overrides.font_size or int(self._setting("font_size", "13")),
            "view_mode": self._setting("view_mode", "split"),
            "restore_last_note": self._setting("restore_last_note", "1") != "0",
            "sync_preview_scroll": self._setting("sync_preview_scroll", "1") != "0",
            "last_note": self._setting_int("last_note"),
            "last_template": self._setting("last_template", "ctf"),
            "sidebar_width": self._setting_int("sidebar_width"),
            "split_sash": self._setting_int("split_sash"),
            "vault_path": self._vault.display_path,
            "stats": dataclasses.asdict(stats),
            "empty": stats.notes == 0 and stats.folders == 0,
        }

    def tree(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [self._tree_walk(node) for node in self._vault.children(None)]

    def node(self, body: dict[str, Any]) -> dict[str, Any]:
        node = self._vault.get_node(_require_int(body, "id"))
        if node is None:
            raise ApiError("Node does not exist", status=404)
        if node.is_folder:
            children = [
                node_summary(child, path=self._path_of(child.id))
                for child in self._vault.children(node.id)
            ]
            return {
                **node_summary(node, path=self._path_of(node.id)),
                "children": children,
                "has_preview": False,
            }
        return {
            **node_summary(node, path=self._path_of(node.id)),
            "content": node.content,
            "preview_html": render_markdown_body(node.content),
        }

    # ------------------------------------------------------------------
    # Node mutation
    # ------------------------------------------------------------------

    def quick_capture(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a note from raw capture text in one round trip."""
        title = _require_str(body, "title", default="").strip()
        content = _require_str(body, "content", default="").strip()
        if not title and not content:
            raise ApiError("A title or some content is required")
        if not title:
            first_line = content.splitlines()[0]
            title = first_line[:60].strip() or "Untitled capture"
        node = self._vault.create_node(
            title,
            None,
            content=content,
            tags=_require_str(body, "tags", default="").strip(),
            target=_require_str(body, "target", default="").strip(),
        )
        return node_summary(node, path=self._path_of(node.id))

    def create_note(self, body: dict[str, Any]) -> dict[str, Any]:
        template = get_template(_require_str(body, "template_key", default="blank"))
        title = _require_str(body, "title", default="").strip() or template.default_title
        target = _require_str(body, "target", default="").strip()
        content = render_template(template, title, target)
        node = self._vault.create_node(
            title,
            parent_id=_optional_node_id(body),
            content=content,
            tags=template.tags,
            status=template.status,
            kind="note",
        )
        self._vault.set_setting("ui.last_template", template.key)
        self._vault.set_setting("ui.last_note", str(node.id))
        return node_summary(node, path=self._path_of(node.id))

    def create_folder(self, body: dict[str, Any]) -> dict[str, Any]:
        title = _require_str(body, "title", default="").strip() or "New folder"
        node = self._vault.create_node(title, parent_id=_optional_node_id(body), kind="folder")
        return node_summary(node, path=self._path_of(node.id))

    def rename(self, body: dict[str, Any]) -> dict[str, Any]:
        node_id = _require_int(body, "id")
        title = _require_str(body, "title", default="").strip()
        if not title:
            raise ApiError("Title cannot be empty")
        node = self._vault.update_node(node_id, title=title)
        return node_summary(node, path=self._path_of(node.id))

    def update_node(self, body: dict[str, Any]) -> dict[str, Any]:
        node_id = _require_int(body, "id")
        if "status" in body and body["status"] not in STATUSES:
            raise ApiError(f"Unknown status: {body['status']}")
        if "difficulty" in body and body["difficulty"] not in DIFFICULTIES:
            raise ApiError(f"Unknown difficulty: {body['difficulty']}")
        fields = {
            key: body[key]
            for key in ("title", "tags", "target", "status", "difficulty", "flag", "pinned")
            if key in body
        }
        if not fields:
            raise ApiError("No fields to update")
        node = self._vault.update_node(node_id, **fields)
        return node_summary(node, path=self._path_of(node.id))

    def save_content(self, body: dict[str, Any]) -> dict[str, Any]:
        node_id = _require_int(body, "id")
        content = _require_str(body, "content")
        node = self._vault.update_node(node_id, content=content)
        return node_summary(node, path=self._path_of(node.id))

    def set_pinned(self, body: dict[str, Any]) -> dict[str, Any]:
        node_id = _require_int(body, "id")
        node = self._vault.update_node(node_id, pinned=_require_bool(body, "pinned"))
        return node_summary(node, path=self._path_of(node.id))

    def duplicate_node(self, body: dict[str, Any]) -> dict[str, Any]:
        node = self._vault.duplicate_node(_require_int(body, "id"))
        return node_summary(node, path=self._path_of(node.id))

    def reorder_node(self, body: dict[str, Any]) -> dict[str, Any] | None:
        node = self._vault.reorder_node(_require_int(body, "id"), _require_int(body, "offset"))
        return node_summary(node) if node is not None else None

    def move_node(self, body: dict[str, Any]) -> dict[str, Any]:
        node = self._vault.move_node(
            _require_int(body, "id"),
            _optional_node_id(body),
            before_id=_optional_int(body, "before_id"),
        )
        return node_summary(node, path=self._path_of(node.id))

    def trash_node(self, body: dict[str, Any]) -> dict[str, Any]:
        count = self._vault.delete_node(_require_int(body, "id"), permanent=False)
        return {"removed": count}

    def restore_node(self, body: dict[str, Any]) -> dict[str, Any]:
        node = self._vault.restore_node(_require_int(body, "id"))
        return node_summary(node, path=self._path_of(node.id))

    def trashed_nodes(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            node_summary(node, path=self._path_of(node.id)) for node in self._vault.trashed_roots()
        ]

    def empty_trash(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"removed": self._vault.empty_trash()}

    # ------------------------------------------------------------------
    # Listing, search, dashboards
    # ------------------------------------------------------------------

    def search(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        hits = self._vault.search(_require_str(body, "query"), limit=100)
        return [self._search_hit(hit) for hit in hits]

    def _search_hit(self, hit: SearchHit) -> dict[str, Any]:
        return dataclasses.asdict(hit)

    def quick_jump(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        query = _require_str(body, "query")
        items = [
            node_summary(node, path=self._path_of(node.id))
            for node in self._vault.live_nodes()
            if node.is_note
        ]
        ranked = rank_items(
            query,
            items,
            key=lambda item: f"{item['title']} {item['path']}",
            limit=40,
        )
        return ranked

    def recent_notes(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        limit = _optional_int(body, "limit") or 10
        return [
            node_summary(node, path=self._path_of(node.id))
            for node in self._vault.recent_notes(limit)
        ]

    def pinned_notes(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            node_summary(node, path=self._path_of(node.id)) for node in self._vault.pinned_notes(24)
        ]

    def stats(self, body: dict[str, Any]) -> dict[str, Any]:
        return dataclasses.asdict(self._vault.stats())

    def collected_flags(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [dataclasses.asdict(hit) for hit in self._vault.collected_flags()]

    # ------------------------------------------------------------------
    # Flag intelligence
    # ------------------------------------------------------------------

    def flag_patterns(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the registry of known event flag formats."""
        return flag_patterns_payload()

    def flag_insights(self, body: dict[str, Any]) -> dict[str, Any]:
        """Return aggregate flag statistics for the dashboard."""
        return flag_insights_payload(build_flag_insights(self._vault))

    def tag_counts(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [dataclasses.asdict(tag) for tag in self._vault.tag_counts()]

    def notes_tagged(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        tag = _require_str(body, "tag")
        return [
            node_summary(node, path=self._path_of(node.id)) for node in self._vault.tag_nodes(tag)
        ]

    def graph(self, body: dict[str, Any]) -> dict[str, Any]:
        """Return the vault knowledge graph: vertices and relationships."""
        return graph_payload(build_vault_graph(self._vault))

    def attachments(self, body: dict[str, Any]) -> dict[str, Any]:
        """List attachments for a note."""
        node_id = _require_int(body, "id")
        return self._vault.list_attachments(node_id)

    def attachment(self, body: dict[str, Any]) -> dict[str, Any]:
        """Get an attachment by ID (returns metadata + allows blob download)."""
        att_id = _require_int(body, "id")
        att = self._vault.get_attachment(att_id)
        if att is None:
            raise ApiError("Attachment does not exist", status=404)
        return att

    def create_attachment(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create an attachment for a note."""
        node_id = _require_int(body, "node_id")
        filename = _require_str(body, "filename")
        mime_type = _require_str(body, "mime_type")
        data = _require_str(body, "data")  # base64-encoded
        import base64
        binary_data = base64.b64decode(data)
        result = self._vault.create_attachment(node_id, filename, mime_type, binary_data)
        return result

    # ------------------------------------------------------------------
    # Templates and snippets
    # ------------------------------------------------------------------

    def templates(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [dataclasses.asdict(template) for template in TEMPLATES]

    def list_snippets(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [_snippet_data(snippet) for snippet in builtin_plus_custom(self._vault)]

    def search_snippets(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        """Search builtin and custom snippets with fuzzy ranking."""
        query = _require_str(body, "query")
        limit = _optional_int(body, "limit") or 12
        snippets = builtin_plus_custom(self._vault)
        ranked = rank_items(
            query,
            snippets,
            key=lambda item: f"{item.title} {item.command} {item.description} {item.tags}",
            limit=limit,
        )
        return [_snippet_data(snippet) for snippet in ranked]

    def resolve_snippet(self, body: dict[str, Any]) -> dict[str, Any]:
        command = _require_str(body, "command")
        resolved = resolve_snippet_command(command, target=_require_str(body, "target", default=""))
        return {"command": resolved}

    def create_snippet(self, body: dict[str, Any]) -> dict[str, Any]:
        snippet = self._vault.create_snippet(
            _require_str(body, "title"),
            _require_str(body, "command"),
            description=_require_str(body, "description", default=""),
            tags=_require_str(body, "tags", default=""),
        )
        return _snippet_data(snippet)

    def update_snippet(self, body: dict[str, Any]) -> dict[str, Any]:
        snippet = self._vault.update_snippet(
            _require_int(body, "id"),
            title=_require_str(body, "title"),
            command=_require_str(body, "command"),
            description=_require_str(body, "description", default=""),
            tags=_require_str(body, "tags", default=""),
        )
        return _snippet_data(snippet)

    def delete_snippet(self, body: dict[str, Any]) -> dict[str, Any]:
        removed = self._vault.delete_snippet(_require_int(body, "id"))
        if not removed:
            raise ApiError("Snippet does not exist", status=404)
        return {"removed": removed}

    # ------------------------------------------------------------------
    # Preview, settings, demo, exports
    # ------------------------------------------------------------------

    def render_preview(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"html": render_markdown_body(_require_str(body, "content"))}

    def get_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        return {key: self._setting(key, "") for key in _SETTING_KEYS}

    def set_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        unknown = set(body) - _OFF_AXIS_KEYS
        if unknown:
            raise ApiError(f"Unsupported setting keys: {', '.join(sorted(unknown))}")
        if "font_size" in body:
            size = _optional_int(body, "font_size")
            if size is None or size not in _FONT_RANGE:
                raise ApiError("font_size must be an integer between 9 and 18")
            self._vault.set_setting("ui.font_size", str(size))
        for key in _OFF_AXIS_KEYS - {"font_size"}:
            if key in body:
                self._vault.set_setting(f"ui.{key}", str(body[key]).strip())
        return self.get_settings({})

    def load_demo(self, body: dict[str, Any]) -> dict[str, Any]:
        seed_demo(self._vault)
        return {"ok": True}

    # ------------------------------------------------------------------
    # Exports (content only; file writing stays in the HTTP layer)
    # ------------------------------------------------------------------

    def export_note_markdown(self, body: dict[str, Any]) -> dict[str, Any]:
        node = self._vault.get_node(_require_int(body, "id"))
        if node is None:
            raise ApiError("Node does not exist", status=404)
        if node.is_folder:
            raise ApiError("Folders cannot be exported as a single Markdown note")
        return {
            "content": note_to_markdown(node),
            "filename": self._vault.node_filename(node.id),
            "mime": "text/markdown",
        }

    def export_note_html(self, body: dict[str, Any]) -> dict[str, Any]:
        node = self._vault.get_node(_require_int(body, "id"))
        if node is None:
            raise ApiError("Node does not exist", status=404)
        if node.is_folder:
            raise ApiError("Folders cannot be exported as a single HTML note")
        meta: list[tuple[str, str]] = [
            ("Target", node.target),
            ("Status", node.status_label),
            ("Difficulty", node.difficulty_label if node.difficulty else ""),
            ("Tags", ", ".join(node.tag_list)),
            ("Flag", node.flag),
            ("Updated", node.updated_at),
        ]
        document = render_html(
            node.content,
            node.title,
            subtitle=self._path_of(node.id) or "RedScribe note",
            meta=meta,
        )
        return {
            "content": document,
            "filename": self._vault.node_filename(node.id).removesuffix(".md") + ".html",
            "mime": "text/html",
        }

    def export_vault_html(self, body: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": vault_report_text(self._vault),
            "filename": "redscribe-vault.html",
            "mime": "text/html",
        }
    def export_print_html(self, body: dict[str, Any]) -> dict[str, Any]:
        html = vault_report_text(self._vault)
        html = html.replace(
            "<style>",
            "<style>\n@media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }\n",
        )
        return {
            "content": html,
            "filename": "redscribe-vault-print.html",
            "mime": "text/html",
        }