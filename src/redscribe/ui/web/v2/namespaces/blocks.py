"""Additive ``blocks`` namespace for the versioned API.

The module is intentionally self-contained: shared route and API modules are
not modified. Call :func:`register` with an existing :class:`ApiV2` instance to
attach every block route, or use :func:`create_blocks_api` for a standalone
registry.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.contracts import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    V2Error,
    V2ErrorCode,
    compute_etag,
    optional_int,
    optional_str,
    paginate,
    require_str,
)
from redscribe.ui.web.v2.routes import ApiV2, RouteResult
from redscribe.v2.blocks.constants import (
    MAX_AUTOSAVE_INTERVAL_MS,
    MAX_AUTOSAVE_MAX_WAIT_MS,
    MAX_BLOCKS,
    MAX_PATCH_OPS,
    MAX_TEXT_LENGTH,
)
from redscribe.v2.blocks.diff import (
    BlockPatch,
    PatchEntry,
    PatchError,
)
from redscribe.v2.blocks.markdown import parse_document, serialize_document
from redscribe.v2.blocks.model import Block, BlockDocument
from redscribe.v2.blocks.normalize import normalize_document
from redscribe.v2.blocks.revisions import RevisionConflictError, encode_token
from redscribe.v2.blocks.store import (
    BlockNotFoundError,
    BlockStore,
    BlockStoreError,
    BlockValidationError,
)
from redscribe.v2.blocks.types import BlockType, MentionKind, PatchOperation
from redscribe.v2.blocks.vault import BlockVaultService, note_id_for_document

RouteHandler = Callable[[dict[str, Any]], RouteResult]


def _patch_from_body(body: Mapping[str, Any]) -> BlockPatch:
    raw = body.get("patch")
    if isinstance(raw, Mapping):
        return BlockPatch.from_dict(raw)
    operations = body.get("operations", body.get("entries"))
    if not isinstance(operations, Sequence) or isinstance(operations, (str, bytes)):
        raise V2Error(
            400,
            V2ErrorCode.MISSING_FIELD,
            "A patch or operations array is required",
            details={"field": "patch"},
        )
    revision = optional_int(body, "base_revision")
    if revision is None:
        raise V2Error(
            400,
            V2ErrorCode.MISSING_FIELD,
            "base_revision is required",
            details={"field": "base_revision"},
        )
    return BlockPatch(
        document_id=optional_str(body, "document_id", default="") or "",
        base_revision=revision,
        entries=tuple(
            PatchEntry.from_dict(item) for item in operations if isinstance(item, Mapping)
        ),
        label=optional_str(body, "label", default="") or "",
    )


def _as_failure(exc: Exception) -> V2Error:
    if isinstance(exc, RevisionConflictError):
        return V2Error(
            409,
            V2ErrorCode.CONFLICT,
            str(exc),
            details=exc.as_dict(),
        )
    if isinstance(exc, BlockNotFoundError):
        return V2Error(
            404,
            V2ErrorCode.NOT_FOUND,
            str(exc),
            details={"document_id": getattr(exc, "document_id", "")},
        )
    if isinstance(exc, BlockValidationError):
        return V2Error(
            422,
            V2ErrorCode.INVALID_REQUEST,
            "Block document failed validation",
            details={"report": exc.report.as_dict()},
        )
    if isinstance(exc, PatchError):
        return V2Error(400, V2ErrorCode.INVALID_REQUEST, str(exc))
    if isinstance(exc, LookupError):
        return V2Error(404, V2ErrorCode.NOT_FOUND, str(exc))
    if isinstance(exc, BlockStoreError):
        return V2Error(400, V2ErrorCode.INVALID_REQUEST, str(exc))
    raise exc


def _json_document(body: Mapping[str, Any]) -> BlockDocument | None:
    raw = body.get("document")
    if isinstance(raw, Mapping):
        return normalize_document(raw)
    return None


def _block_types(body: Mapping[str, Any]) -> list[BlockType | str] | None:
    raw = body.get("block_types", body.get("types"))
    if raw is None:
        return None
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise V2Error(400, V2ErrorCode.INVALID_TYPE, "block_types must be a list")
    result: list[BlockType | str] = []
    for item in raw:
        if not isinstance(item, str):
            raise V2Error(400, V2ErrorCode.INVALID_TYPE, "block_types must contain strings")
        if item not in {entry.value for entry in BlockType}:
            raise V2Error(
                400,
                V2ErrorCode.INVALID_CHOICE,
                f"Unknown block type: {item}",
                details={"field": "block_types"},
            )
        result.append(BlockType(item))
    return result


class BlocksNamespace:
    """Route handlers for structured block editing."""

    def __init__(self, api: ApiV2, service: BlockVaultService | None = None) -> None:
        self._api = api
        self._service = service or BlockVaultService(api.vault)

    @property
    def service(self) -> BlockVaultService:
        return self._service

    @property
    def store(self) -> BlockStore:
        return self._service.store

    def register(self) -> None:
        """Attach all block routes to the supplied API registry."""
        self._add(
            "blocks.capabilities",
            self._capabilities,
            "Report block types, mention kinds, autosave limits, and features.",
        )
        self._add(
            "blocks.schema",
            self._schema,
            "Describe block payloads and route field contracts.",
        )
        self._add(
            "blocks.create",
            self._create,
            "Create an in-memory block document or load a vault note as one.",
            optional=("document_id", "note_id", "title", "markdown", "blocks", "tags", "metadata"),
            mutating=True,
            entity_type="block_document",
        )
        self._add(
            "blocks.get",
            self._get,
            "Return one block document and a fresh revision token.",
            optional=("id", "document_id", "note_id"),
        )
        self._add(
            "blocks.list",
            self._list,
            "List block document summaries with cursor pagination.",
            optional=("cursor", "limit"),
        )
        self._add(
            "blocks.parse",
            self._parse,
            "Parse Markdown-like IR into structured blocks.",
            required=("markdown",),
            optional=("document_id", "title", "tags"),
        )
        self._add(
            "blocks.serialize",
            self._serialize,
            "Serialize a document to Markdown-like IR.",
            optional=("id", "document_id", "document", "include_title"),
        )
        self._add(
            "blocks.validate",
            self._validate,
            "Validate a document and return every structural issue.",
            optional=("id", "document_id", "document"),
        )
        self._add(
            "blocks.diff",
            self._diff,
            "Compute a block-level diff between two document values.",
            required=("left", "right"),
        )
        self._add(
            "blocks.patch",
            self._patch,
            "Apply an optimistic patch and persist note-backed documents.",
            required=("patch",),
            optional=("id", "document_id", "token", "base_revision", "operations", "label"),
            mutating=True,
            entity_type="block_document",
        )
        self._add(
            "blocks.save",
            self._save,
            "Save a full document with an optimistic revision token.",
            required=("document", "token"),
            mutating=True,
            entity_type="block_document",
        )
        self._add(
            "blocks.replace_blocks",
            self._replace_blocks,
            "Replace all blocks from Markdown-like IR.",
            required=("id", "markdown"),
            optional=("token",),
            mutating=True,
            entity_type="block_document",
        )
        self._add(
            "blocks.search",
            self._search,
            "Search indexed blocks with type and document filters.",
            required=("query",),
            optional=(
                "block_types",
                "types",
                "document_id",
                "match_all",
                "limit",
                "offset",
                "cursor",
            ),
        )
        self._add(
            "blocks.mentions",
            self._mentions,
            "List indexed mentions or autocomplete mention targets.",
            optional=("target", "kind", "query", "limit"),
        )
        self._add(
            "blocks.autosave",
            self._autosave,
            "Queue patch operations for debounced coalescing.",
            required=("id", "patch"),
            optional=("token",),
            mutating=True,
            entity_type="block_autosave",
        )
        self._add(
            "blocks.autosave_status",
            self._autosave_status,
            "Report queued autosave batches and timing state.",
        )
        self._add(
            "blocks.flush",
            self._flush,
            "Flush queued autosave batches into stored documents.",
            optional=("id",),
            mutating=True,
            entity_type="block_autosave",
        )
        self._add(
            "blocks.delete",
            self._delete,
            "Delete a block document and its derived indices.",
            required=("id",),
            mutating=True,
            entity_type="block_document",
        )
        self._add(
            "blocks.reindex",
            self._reindex,
            "Rebuild block search and mention indices.",
            mutating=True,
            entity_type="block_document",
        )
        self._add(
            "blocks.status",
            self._status,
            "Return block store and service telemetry.",
        )

    def _add(
        self,
        name: str,
        handler: RouteHandler,
        description: str,
        *,
        required: tuple[str, ...] = (),
        optional: tuple[str, ...] = (),
        mutating: bool = False,
        entity_type: str = "",
    ) -> None:
        self._api._register(
            name,
            handler,
            description,
            required=required,
            optional=optional,
            mutating=mutating,
            entity_type=entity_type,
        )

    def _document(self, body: Mapping[str, Any]) -> BlockDocument:
        inline = _json_document(body)
        if inline is not None:
            return inline
        document_id = optional_str(body, "id") or optional_str(body, "document_id")
        if document_id:
            try:
                return self.store.get(document_id)
            except BlockNotFoundError as exc:
                raise V2Error(
                    404,
                    V2ErrorCode.NOT_FOUND,
                    str(exc),
                    details={"document_id": document_id},
                ) from exc
        note_id = optional_int(body, "note_id")
        if note_id is not None:
            return self._service.load(note_id)
        raise V2Error(
            400,
            V2ErrorCode.MISSING_FIELD,
            "A document, id, or note_id is required",
            details={"fields": ["document", "id", "note_id"]},
        )

    def _token(self, body: Mapping[str, Any]) -> str:
        value = optional_str(body, "token") or optional_str(body, "revision_token")
        if value:
            return value
        document_id = optional_str(body, "id") or optional_str(body, "document_id")
        if document_id:
            return encode_token(self.store.token(document_id))
        note_id = optional_int(body, "note_id")
        if note_id is not None:
            return encode_token(self._service.token(note_id))
        raise V2Error(
            400,
            V2ErrorCode.MISSING_FIELD,
            "A revision token is required",
            details={"field": "token"},
        )

    def _payload(self, document: BlockDocument) -> dict[str, Any]:
        return {
            "document": document.as_dict(),
            "token": encode_token(self.store.revisions.issue(document)),
            "markdown": serialize_document(document),
        }

    def _capabilities(self, body: dict[str, Any]) -> RouteResult:
        data = {
            "namespace": "blocks",
            "block_types": [item.value for item in BlockType],
            "patch_operations": [item.value for item in PatchOperation],
            "mention_kinds": [item.value for item in MentionKind],
            "features": [
                "structured_blocks",
                "markdown_ir",
                "block_diff",
                "optimistic_revisions",
                "autosave_coalescing",
                "mentions",
                "block_search",
            ],
            "limits": {
                "max_blocks": MAX_BLOCKS,
                "max_text_length": MAX_TEXT_LENGTH,
                "max_patch_ops": MAX_PATCH_OPS,
                "autosave_interval_ms": self.store.autosave.interval_ms,
                "autosave_max_wait_ms": self.store.autosave.max_wait_ms,
                "autosave_max_interval_ms": MAX_AUTOSAVE_INTERVAL_MS,
                "autosave_max_wait_limit_ms": MAX_AUTOSAVE_MAX_WAIT_MS,
            },
        }
        return RouteResult(data, etag=compute_etag(data))

    def _schema(self, body: dict[str, Any]) -> RouteResult:
        routes = [
            route.as_schema()
            for name, route in sorted(self._api.routes.items())
            if name.startswith("blocks.")
        ]
        data = {
            "namespace": "blocks",
            "routes": routes,
            "document_fields": [
                "id",
                "title",
                "blocks",
                "revision",
                "updated_at",
                "tags",
                "metadata",
            ],
            "block_fields": [
                "id",
                "type",
                "text",
                "level",
                "language",
                "items",
                "checked",
                "style",
                "headers",
                "rows",
                "tone",
                "alt",
                "source",
                "mentions",
                "attrs",
            ],
        }
        return RouteResult(data, etag=compute_etag(data))

    def _create(self, body: dict[str, Any]) -> RouteResult:
        note_id = optional_int(body, "note_id")
        if note_id is not None:
            document = self._service.load(note_id)
        else:
            title = optional_str(body, "title", default="") or ""
            markdown = optional_str(body, "markdown", default="") or ""
            raw_blocks = body.get("blocks", ())
            blocks: tuple[Block, ...] = ()
            if isinstance(raw_blocks, Sequence):
                blocks = tuple(
                    Block.from_dict(item) for item in raw_blocks if isinstance(item, Mapping)
                )
            tags_raw = body.get("tags", ())
            tags = (
                tuple(item for item in tags_raw if isinstance(item, str))
                if isinstance(tags_raw, Sequence)
                else ()
            )
            metadata_raw = body.get("metadata", {})
            metadata = (
                {str(key): str(value) for key, value in metadata_raw.items()}
                if isinstance(metadata_raw, Mapping)
                else {}
            )
            document = self.store.create(
                document_id=optional_str(body, "document_id"),
                title=title,
                markdown=markdown,
                blocks=blocks,
                tags=tags,
                metadata=metadata,
            )
        data = self._payload(document)
        return RouteResult(data, etag=compute_etag(data))

    def _get(self, body: dict[str, Any]) -> RouteResult:
        data = self._payload(self._document(body))
        return RouteResult(data, etag=compute_etag(data))

    def _list(self, body: dict[str, Any]) -> RouteResult:
        limit = optional_int(body, "limit")
        if limit is None:
            limit = DEFAULT_PAGE_SIZE
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise V2Error(
                400,
                V2ErrorCode.INVALID_REQUEST,
                f"limit must be between 1 and {MAX_PAGE_SIZE}",
                details={"field": "limit"},
            )
        documents = self.store.list_documents()
        summaries = [
            {
                "id": document.id,
                "title": document.title,
                "revision": document.revision,
                "block_count": len(document.blocks),
                "word_count": document.word_count,
                "updated_at": document.updated_at,
            }
            for document in documents
        ]
        items, page = paginate(summaries, cursor=optional_str(body, "cursor"), limit=limit)
        return RouteResult(
            items, page=page, etag=compute_etag({"items": items, "page": page.as_dict()})
        )

    def _parse(self, body: dict[str, Any]) -> RouteResult:
        markdown = require_str(body, "markdown")
        tags_raw = body.get("tags", ())
        tags = (
            tuple(item for item in tags_raw if isinstance(item, str))
            if isinstance(tags_raw, Sequence)
            else ()
        )
        document = parse_document(
            markdown,
            document_id=optional_str(body, "document_id"),
            title=optional_str(body, "title", default="") or "",
            tags=tags,
        )
        data = self._payload(document)
        return RouteResult(data, etag=compute_etag(data))

    def _serialize(self, body: dict[str, Any]) -> RouteResult:
        document = self._document(body)
        include_title = bool(body.get("include_title", False))
        markdown = serialize_document(document, include_title=include_title)
        data = {
            "id": document.id,
            "revision": document.revision,
            "markdown": markdown,
        }
        return RouteResult(data, etag=compute_etag(data))

    def _validate(self, body: dict[str, Any]) -> RouteResult:
        report = self.store.validate(self._document(body))
        data = report.as_dict()
        return RouteResult(data, etag=compute_etag(data))

    def _diff(self, body: dict[str, Any]) -> RouteResult:
        left = body.get("left")
        right = body.get("right")
        if left is None or right is None:
            raise V2Error(
                400,
                V2ErrorCode.MISSING_FIELD,
                "Both left and right documents are required",
            )

        def resolve(value: Any) -> BlockDocument:
            if isinstance(value, str):
                try:
                    return self.store.get(value)
                except BlockNotFoundError as exc:
                    raise V2Error(404, V2ErrorCode.NOT_FOUND, str(exc)) from exc
            if isinstance(value, Mapping):
                return normalize_document(value)
            raise V2Error(400, V2ErrorCode.INVALID_TYPE, "Diff sides must be ids or documents")

        result = self.store.diff(resolve(left), resolve(right))
        data = result.as_dict()
        return RouteResult(data, etag=compute_etag(data))

    def _patch(self, body: dict[str, Any]) -> RouteResult:
        document = self._document(body)
        patch = _patch_from_body(body)
        if not patch.document_id:
            patch = replace(patch, document_id=document.id)
        try:
            token = self._token(body)
            patched = self.store.apply_patch(document.id, patch, token)
            note_id = note_id_for_document(patched.id)
            if note_id is not None and self.store.find(patched.id) is not None:
                self._service.sync_note(note_id, patched)
        except (RevisionConflictError, PatchError, BlockStoreError) as exc:
            raise _as_failure(exc) from exc
        data = self._payload(patched)
        return RouteResult(data, etag=compute_etag(data))

    def _save(self, body: dict[str, Any]) -> RouteResult:
        raw_document = body.get("document")
        if not isinstance(raw_document, Mapping):
            raise V2Error(
                400,
                V2ErrorCode.INVALID_TYPE,
                "document must be an object",
                details={"field": "document"},
            )
        incoming = normalize_document(raw_document)
        try:
            token = self._token(body)
            note_id = note_id_for_document(incoming.id)
            if note_id is not None:
                document = self._service.save(note_id, incoming, token)
            else:
                document = self.store.save(incoming, token)
        except (RevisionConflictError, PatchError, BlockStoreError, LookupError) as exc:
            raise _as_failure(exc) from exc
        data = self._payload(document)
        return RouteResult(data, etag=compute_etag(data))

    def _replace_blocks(self, body: dict[str, Any]) -> RouteResult:
        document_id = require_str(body, "id")
        markdown = require_str(body, "markdown")
        try:
            token = self._token(body)
            document = self.store.replace_blocks(document_id, markdown, token)
            note_id = note_id_for_document(document_id)
            if note_id is not None:
                self._service.sync_note(note_id, document)
        except (RevisionConflictError, PatchError, BlockStoreError) as exc:
            raise _as_failure(exc) from exc
        data = self._payload(document)
        return RouteResult(data, etag=compute_etag(data))

    def _search(self, body: dict[str, Any]) -> RouteResult:
        query = require_str(body, "query")
        limit = optional_int(body, "limit")
        if limit is None:
            limit = DEFAULT_PAGE_SIZE
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise V2Error(400, V2ErrorCode.INVALID_REQUEST, "Invalid search limit")
        offset = optional_int(body, "offset")
        if offset is None or offset < 0:
            offset = 0
        results = self.store.search(
            query,
            block_types=_block_types(body),
            document_id=optional_str(body, "document_id"),
            match_all=bool(body.get("match_all", True)),
            limit=limit,
            offset=offset,
        )
        data = {
            "query": query,
            "total": len(results),
            "items": [result.as_dict() for result in results],
        }
        return RouteResult(data, etag=compute_etag(data))

    def _mentions(self, body: dict[str, Any]) -> RouteResult:
        query = optional_str(body, "query")
        limit = optional_int(body, "limit") or 12
        if query:
            kind = optional_str(body, "kind")
            suggestions = self.store.mention_suggestions(
                query,
                kind=kind,
                limit=limit,
            )
            data = {
                "mode": "suggestions",
                "items": [item.as_dict() for item in suggestions],
            }
        else:
            target = optional_str(body, "target")
            kind = optional_str(body, "kind")
            hits = self.store.mention_hits(target, kind=kind)
            data = {"mode": "hits", "items": [item.as_dict() for item in hits]}
        return RouteResult(data, etag=compute_etag(data))

    def _autosave(self, body: dict[str, Any]) -> RouteResult:
        document_id = require_str(body, "id")
        patch = _patch_from_body(body)
        try:
            batch = self.store.queue_autosave(
                document_id,
                patch,
                token=optional_str(body, "token", default="") or "",
            )
        except (BlockStoreError, PatchError) as exc:
            raise _as_failure(exc) from exc
        data = {
            "queued": batch is not None or self.store.autosave.has_pending(document_id),
            "batch": batch.as_dict() if batch is not None else None,
            "state": self.store.autosave.state(),
        }
        return RouteResult(data, etag=compute_etag(data))

    def _autosave_status(self, body: dict[str, Any]) -> RouteResult:
        data = {"status": self.store.autosave.state(), "documents": self.store.list_ids()}
        return RouteResult(data, etag=compute_etag(data))

    def _flush(self, body: dict[str, Any]) -> RouteResult:
        document_id = optional_str(body, "id")
        try:
            saved = (
                self.store.flush_all_autosave()
                if document_id is None
                else self.store.flush_autosave(document_id)
            )
            for document in saved:
                note_id = note_id_for_document(document.id)
                if note_id is not None:
                    self._service.sync_note(note_id, document)
        except (BlockStoreError, PatchError) as exc:
            raise _as_failure(exc) from exc
        data = {
            "saved": [document.as_dict() for document in saved],
            "count": len(saved),
            "state": self.store.autosave.state(),
        }
        return RouteResult(data, etag=compute_etag(data))

    def _delete(self, body: dict[str, Any]) -> RouteResult:
        document_id = require_str(body, "id")
        removed = self.store.delete(document_id)
        data = {"id": document_id, "removed": removed}
        return RouteResult(data, status=200 if removed else 404)

    def _reindex(self, body: dict[str, Any]) -> RouteResult:
        count = self.store.reindex()
        data = {"reindexed": count, "status": self.store.status()}
        return RouteResult(data)

    def _status(self, body: dict[str, Any]) -> RouteResult:
        data = self._service.status()
        data["route_count"] = sum(1 for name in self._api.routes if name.startswith("blocks."))
        return RouteResult(data, etag=compute_etag(data))


def register(api: ApiV2, service: BlockVaultService | None = None) -> BlocksNamespace:
    """Register every ``blocks.*`` route on ``api`` and return the namespace."""
    namespace = BlocksNamespace(api, service)
    namespace.register()
    return namespace


def create_blocks_api(vault: Vault, *, service: BlockVaultService | None = None) -> ApiV2:
    """Build an API v2 registry containing the platform and block routes."""
    api = ApiV2(vault)
    register(api, service)
    return api
