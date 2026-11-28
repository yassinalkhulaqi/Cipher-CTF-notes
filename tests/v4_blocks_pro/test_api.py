"""Combined tests for block storage, v4 API envelopes, capabilities, and events."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from tests.v4_blocks_pro.fixtures import (
    clock_factory,
    id_factory,
    make_block,
    make_document,
    sample_document,
    simple_document,
)

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.blocks_pro.api import (
    ROUTE_SPECS,
    BlockRoutes,
    as_api_error,
    error_envelope,
    optional_int,
    register,
    require_str,
)
from redscribe.v4.blocks_pro.service import (
    AutosaveManager,
    BlockValidator,
    CodecError,
    MarkdownCodec,
    SnapshotError,
)
from redscribe.v4.blocks_pro.storage import (
    BlockStore,
    ConflictError,
    DocumentNotFoundError,
    DuplicateDocumentError,
    Revision,
    RevisionNotFoundError,
    StorageError,
)
from redscribe.v4.blocks_pro.types import (
    BlockDocument,
    BlockKind,
    BlockOp,
    EditOperation,
)
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    EnvelopeDecoder,
    ErrorCode,
    PageMeta,
    ok,
)
from redscribe.v4.contracts import (
    fail as fail_envelope,
)
from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox


def build_store() -> BlockStore:
    return BlockStore(
        id_factory=id_factory(*(f"rev{i}" for i in range(40))),
        clock=clock_factory("2026-02-01T00:00:00Z"),
    )


def build_routes(
    store: BlockStore | None = None,
    capabilities: CapabilitySet | None = None,
    bus: EventBus | None = None,
) -> BlockRoutes:
    return BlockRoutes(
        store=store or build_store(),
        capabilities=capabilities if capabilities is not None else CapabilitySet.full(),
        bus=bus,
        request_id_factory=id_factory("req1", "req2"),
        codec=MarkdownCodec(id_factory=id_factory(*(f"x{i}" for i in range(30)))),
    )


def seed(routes: BlockRoutes, document: BlockDocument | None = None) -> BlockDocument:
    value = document or simple_document()
    routes.store.create(value, "seed-author")
    return value


def test_store_create_revision_and_lookup() -> None:
    store = build_store()
    document = simple_document()
    revision = store.create(document, "alice")
    assert revision.number == 1
    assert revision.document_id == "doc1"
    assert revision.author == "alice"
    assert revision.checksum == document.checksum()
    assert store.exists("doc1")
    assert store.get("doc1") == document
    assert store.find("doc1") == document
    assert store.find("missing") is None
    assert store.list() == (document,)
    assert store.checksum("doc1") == document.checksum()


def test_store_rejects_duplicates_and_missing_documents() -> None:
    store = build_store()
    store.create(simple_document())
    with pytest.raises(DuplicateDocumentError, match="already exists"):
        store.create(simple_document())
    with pytest.raises(DocumentNotFoundError, match="document not found"):
        store.get("absent")
    with pytest.raises(DocumentNotFoundError):
        store.checksum("absent")
    assert store.delete("absent") is False
    assert store.delete("doc1") is True
    assert store.delete("doc1") is False


def test_store_revision_serialization() -> None:
    store = build_store()
    revision = store.create(simple_document(), "bob")
    data = revision.to_dict()
    assert data["number"] == 1
    assert data["author"] == "bob"
    assert Revision.from_dict(data) == revision
    with pytest.raises(StorageError, match="revision document must be"):
        Revision.from_dict({"document": "nope"})


def test_store_save_uses_expected_checksum_guard() -> None:
    store = build_store()
    first = store.create(simple_document())
    changed = first.document.with_title("Changed")
    with pytest.raises(ConflictError, match="document changed"):
        store.save(changed, "alice", "stale-checksum")
    second = store.save(changed, "alice", first.checksum)
    assert second.number == 2
    assert store.get("doc1") == changed
    assert store.save(make_document("doc2", "Second")).number == 1
    assert len(store.list()) == 2


def test_store_replace_updates_title_and_blocks() -> None:
    store = build_store()
    store.create(simple_document())
    blocks = (make_block("z", text="replacement"),)
    revision = store.replace("doc1", blocks, "Renamed", "carol")
    assert revision.document.title == "Renamed"
    assert revision.document.block_ids == ("z",)
    assert revision.number == 2
    with pytest.raises(ConflictError):
        store.replace("doc1", blocks, "Again", "carol", "stale")


def test_store_applies_patch_operations() -> None:
    store = build_store()
    store.create(simple_document())
    update = EditOperation(
        BlockOp.UPDATE,
        "a",
        index=0,
        block=make_block("a", text="alpha updated"),
    )
    insert = EditOperation(
        BlockOp.INSERT,
        "x",
        index=3,
        block=make_block("x", text="extra"),
    )
    revision, applied = store.apply("doc1", (update, insert), "dave")
    assert revision.number == 2
    assert applied == (update, insert)
    assert store.get("doc1").block_ids == ("a", "b", "c", "x")
    assert store.get("doc1").get("a").text == "alpha updated"
    with pytest.raises(ConflictError):
        store.apply("doc1", (), "dave", "stale")


def test_store_rejects_invalid_patch_operations() -> None:
    store = build_store()
    store.create(simple_document())
    bad_delete = EditOperation(BlockOp.DELETE, "missing", index=5)
    with pytest.raises(StorageError):
        store.apply("doc1", (bad_delete,), "eve")
    bad_move = EditOperation(BlockOp.MOVE, "a", index=0, target_index=99)
    with pytest.raises(StorageError, match="target index out of range"):
        store.apply("doc1", (bad_move,), "eve")
    conflicting = (
        EditOperation(BlockOp.DELETE, "a", index=0),
        EditOperation(BlockOp.MOVE, "a", index=0, target_index=1),
    )
    with pytest.raises(StorageError, match="more than one destructive"):
        store.apply("doc1", conflicting, "eve")


def test_store_history_revision_and_restore() -> None:
    store = build_store()
    store.create(simple_document())
    store.save(simple_document().with_title("Second"))
    store.save(simple_document().with_title("Third"))
    history = store.history("doc1")
    assert [item.number for item in history] == [1, 2, 3]
    assert store.revision("doc1", 2).document.title == "Second"
    assert store.latest_revision("doc1").number == 3
    with pytest.raises(RevisionNotFoundError, match="revision 9"):
        store.revision("doc1", 9)
    restored = store.restore_revision("doc1", 1, "frank")
    assert restored.number == 4
    assert store.get("doc1").title == "Notes"


def test_store_prunes_history() -> None:
    store = build_store()
    store.create(simple_document())
    for index in range(4):
        store.save(simple_document().with_title(f"Rev {index}"))
    assert store.prune_history("doc1", 2) == 3
    assert [item.number for item in store.history("doc1")] == [4, 5]
    assert store.prune_history("doc1", 10) == 0
    with pytest.raises(StorageError, match="keep must be"):
        store.prune_history("doc1", 0)


def test_store_snapshot_and_restore_snapshot() -> None:
    store = build_store()
    document = simple_document()
    store.create(document)
    snapshot = store.snapshot("doc1", "checkpoint")
    assert snapshot.reason == "checkpoint"
    assert store.snapshots("doc1") == (snapshot,)
    store.save(document.with_title("Later"))
    revision = store.restore_snapshot("doc1", snapshot.id, "", "grace")
    assert revision.document.title == "Notes"
    assert revision.number == 3
    with pytest.raises(SnapshotError, match="snapshot not found"):
        store.restore_snapshot("doc1", "absent")


def test_store_snapshot_staleness_is_conflict() -> None:
    store = build_store()
    store.create(simple_document())
    snapshot = store.snapshot("doc1")
    with pytest.raises(ConflictError, match="stale"):
        store.restore_snapshot("doc1", snapshot.id, "another-checksum")


def test_store_export_and_import_markdown() -> None:
    store = build_store()
    store.create(sample_document())
    markdown = store.export("doc1")
    assert markdown.startswith("# All block kinds")
    assert "<!-- block:b1 -->" in markdown
    imported = store.import_markdown(markdown, "doc2")
    assert imported.id == "doc2"
    assert imported.title == "All block kinds"
    assert imported == replace(sample_document(), id="doc2")
    assert len(store.list()) == 2


def test_store_search_stats_and_digest() -> None:
    store = build_store()
    store.create(simple_document())
    store.create(replace(sample_document(), id="doc2"))
    assert [item.id for item in store.search("bravo")] == ["doc1"]
    assert [item.id for item in store.search("heading")] == ["doc2"]
    assert store.search("") == ()
    assert store.search("bravo", limit=0) == ()
    stats = store.stats()
    assert stats["documents"] == 2
    assert stats["blocks"] == 10
    assert stats["revisions"] == 2
    assert len(store.digest()) == 24
    assert store.digest() == store.digest()


def test_store_validates_documents_on_commit() -> None:
    store = build_store()
    invalid = make_document(
        "bad-doc",
        "Title",
        (make_block("a", BlockKind.HEADING, "", level=1),),
    )
    with pytest.raises(StorageError, match="heading must not be blank"):
        store.create(invalid)
    assert not store.exists("bad-doc")


def test_store_accepts_custom_validator_and_autosave() -> None:
    autosave = AutosaveManager(
        id_factory=id_factory("s1"), clock=clock_factory("2026-02-01T00:00:00Z")
    )
    store = BlockStore(
        id_factory=id_factory("r1"),
        clock=clock_factory("2026-02-01T00:00:00Z"),
        validator=BlockValidator(max_heading_level=3),
        autosave=autosave,
    )
    store.create(make_document("d1", "T", (make_block("h", BlockKind.HEADING, "Hi", level=2),)))
    assert store.snapshot("d1").id == "s1"


def test_api_get_list_envelope_and_pagination() -> None:
    routes = build_routes()
    store = routes.store
    for index in range(3):
        store.create(make_document(f"d{index}", f"Doc {index}"))
    envelope = routes.get({"page": "1", "page_size": "2"}, {"X-Request-ID": "fixed-id"})
    assert set(envelope) == {"data", "meta"}
    assert envelope["meta"]["request_id"] == "fixed-id"
    assert envelope["meta"]["version"] == "v4"
    assert envelope["meta"]["page_size"] == 2
    assert envelope["meta"]["etag"].startswith('W/"')
    assert envelope["data"]["total"] == 3
    assert len(envelope["data"]["items"]) == 2
    assert envelope["data"]["next_cursor"]
    second = routes.get({"page": "2", "page_size": "2"})
    assert len(second["data"]["items"]) == 1
    assert second["data"]["next_cursor"] == ""
    assert second["meta"]["request_id"] != ""


def test_api_get_single_document_with_etag() -> None:
    routes = build_routes()
    document = seed(routes)
    envelope = routes.get({"id": "doc1"})
    assert envelope["data"]["document"] == document.to_dict()
    assert envelope["data"]["word_count"] == document.word_count
    assert envelope["data"]["revision"] == 1
    etag = envelope["meta"]["etag"]
    not_modified = routes.get({"id": "doc1"}, {"If-None-Match": etag})
    assert not_modified["data"]["not_modified"] is True
    assert (
        routes.get({"id": "doc1"}, {"If-None-Match": 'W/"other"'})["data"]["not_modified"] is False
    )


def test_api_get_missing_document_is_not_found() -> None:
    routes = build_routes()
    with pytest.raises(ApiError) as excinfo:
        routes.get({"id": "absent"})
    assert excinfo.value.code is ErrorCode.NOT_FOUND
    payload = fail_envelope(excinfo.value)
    assert payload["error"]["code"] == "not_found"


def test_api_get_validates_query_parameters() -> None:
    routes = build_routes()
    with pytest.raises(ApiError, match="page must be between") as excinfo:
        routes.get({"page": "99999"})
    assert excinfo.value.code is ErrorCode.INVALID_INPUT
    with pytest.raises(ApiError, match="page_size must be between"):
        routes.get({"page_size": "-3"})
    with pytest.raises(ApiError, match="page must be an integer"):
        routes.get({"page": "many"})
    with pytest.raises(ApiError, match="id exceeds"):
        routes.get({"id": "x" * 241})


def test_api_get_search_filter_and_envelope_decoder() -> None:
    routes = build_routes()
    seed(routes, simple_document())
    seed(routes, replace(sample_document(), id="doc2"))
    envelope = routes.get({"query": "bravo"})
    assert envelope["data"]["total"] == 1
    assert envelope["data"]["query"] == "bravo"
    assert envelope["data"]["items"][0]["id"] == "doc1"
    assert EnvelopeDecoder().decode(envelope)["total"] == 1


def test_api_put_creates_document_and_emits_event() -> None:
    bus = EventBus()
    routes = build_routes(bus=bus)
    body = {"document": simple_document().to_dict()}
    envelope = routes.put(body, {"X-Actor": "alice", "X-Request-ID": "put-1"})
    assert envelope["data"]["created"] is True
    assert envelope["data"]["revision"] == 1
    assert envelope["meta"]["request_id"] == "put-1"
    assert routes.store.exists("doc1")
    events = bus.published
    assert len(events) == 1
    assert events[0].kind is EventKind.BLOCK_EDITED
    assert events[0].payload["actor"] == "alice"
    assert events[0].payload["block_count"] == 3
    assert events[0].aggregate_id == "doc1"


def test_api_put_updates_existing_document() -> None:
    routes = build_routes()
    seed(routes)
    body = {"document": simple_document().with_title("Edited").to_dict()}
    envelope = routes.put(body)
    assert envelope["data"]["created"] is False
    assert envelope["data"]["revision"] == 2
    assert routes.store.get("doc1").title == "Edited"


def test_api_put_accepts_markdown_body() -> None:
    routes = build_routes()
    markdown = "# From markdown\n\nhello\n"
    envelope = routes.put({"id": "md-doc", "document": markdown})
    assert envelope["data"]["document"]["title"] == "From markdown"
    assert envelope["data"]["document"]["id"] == "md-doc"
    assert envelope["data"]["created"] is True


def test_api_put_rejects_malformed_document_and_checksum() -> None:
    routes = build_routes()
    seed(routes)
    with pytest.raises(ApiError, match="document must be an object"):
        routes.put({"document": 7})
    with pytest.raises(ApiError, match="id must be a non-empty"):
        routes.put({"document": "# Title\n"})
    with pytest.raises(ApiError) as excinfo:
        routes.put({"document": simple_document().to_dict(), "expected_checksum": "stale"})
    assert excinfo.value.code is ErrorCode.CONFLICT


def test_api_patch_applies_operations_and_emits_event() -> None:
    bus = EventBus()
    routes = build_routes(bus=bus)
    seed(routes)
    operation = EditOperation(
        BlockOp.UPDATE,
        "a",
        index=0,
        block=make_block("a", text="patched"),
        note="manual edit",
    )
    envelope = routes.patch({"id": "doc1", "operations": [operation.to_dict()]})
    assert envelope["data"]["summary"] == {
        "insert": 0,
        "update": 1,
        "delete": 0,
        "move": 0,
    }
    assert envelope["data"]["applied"][0]["note"] == "manual edit"
    assert envelope["data"]["document"]["blocks"][0]["text"] == "patched"
    assert len(bus.published) == 1
    assert bus.published[0].payload["operations"] == ["update:a"]


def test_api_patch_insert_delete_and_move() -> None:
    routes = build_routes()
    seed(routes)
    insert = EditOperation(BlockOp.INSERT, "x", index=3, block=make_block("x", text="new"))
    delete = EditOperation(BlockOp.DELETE, "b", index=1)
    move = EditOperation(BlockOp.MOVE, "c", index=2, target_index=0)
    envelope = routes.patch(
        {
            "id": "doc1",
            "operations": [insert.to_dict(), delete.to_dict(), move.to_dict()],
        }
    )
    assert envelope["data"]["summary"]["insert"] == 1
    assert envelope["data"]["summary"]["delete"] == 1
    assert envelope["data"]["summary"]["move"] == 1
    assert envelope["data"]["document"]["blocks"][0]["id"] == "c"


def test_api_patch_rejects_bad_requests() -> None:
    routes = build_routes()
    seed(routes)
    with pytest.raises(ApiError, match="id must be a non-empty"):
        routes.patch({"operations": []})
    with pytest.raises(ApiError, match="operations must be a list"):
        routes.patch({"id": "doc1", "operations": "bad"})
    with pytest.raises(ApiError, match="Unknown block operation"):
        routes.patch({"id": "doc1", "operations": [{"op": "swap", "block_id": "a"}]})
    with pytest.raises(ApiError) as excinfo:
        routes.patch({"id": "absent", "operations": []})
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_api_capability_and_feature_gate_enforcement() -> None:
    routes = build_routes(capabilities=CapabilitySet(frozenset({Capability.READ})))
    with pytest.raises(ApiError, match="feature disabled") as excinfo:
        routes.get({})
    assert excinfo.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(ApiError, match="missing capability"):
        CapabilitySet(frozenset({Capability.READ})).require(Capability.WRITE)
    routes.capabilities = CapabilitySet(frozenset({Capability.READ}))
    with pytest.raises(ApiError, match="feature disabled"):
        routes.patch({"id": "doc1", "operations": []})


def test_api_history_envelope_and_errors() -> None:
    routes = build_routes()
    seed(routes)
    routes.store.save(simple_document().with_title("Second"))
    envelope = routes.history({"id": "doc1", "page_size": "1"})
    assert envelope["data"]["total"] == 2
    assert len(envelope["data"]["items"]) == 1
    assert envelope["data"]["items"][0]["number"] == 1
    assert envelope["data"]["next_cursor"]
    with pytest.raises(ApiError, match="id must be a non-empty"):
        routes.history({})
    with pytest.raises(ApiError):
        routes.history({"id": "absent"})


def test_api_snapshots_list_create_and_restore() -> None:
    routes = build_routes()
    seed(routes)
    listed = routes.snapshots({"id": "doc1"})
    assert listed["data"]["count"] == 0
    created = routes.snapshots({"id": "doc1", "action": "create", "reason": "checkpoint"})
    assert created["data"]["count"] == 1
    snapshot_id = created["data"]["snapshots"][0]["id"]
    routes.store.save(simple_document().with_title("Later"))
    restored = routes.snapshots({"id": "doc1", "action": "restore", "snapshot_id": snapshot_id})
    assert restored["data"]["restored_from"] == snapshot_id
    assert restored["data"]["document"]["title"] == "Notes"
    with pytest.raises(ApiError, match="snapshot_id must be"):
        routes.snapshots({"id": "doc1", "action": "restore"})


def test_api_snapshot_staleness_maps_to_conflict() -> None:
    routes = build_routes()
    seed(routes)
    snapshot = routes.store.snapshot("doc1")
    with pytest.raises(ApiError) as excinfo:
        routes.snapshots(
            {
                "id": "doc1",
                "action": "restore",
                "snapshot_id": snapshot.id,
                "expected_checksum": "stale",
            }
        )
    assert excinfo.value.code is ErrorCode.CONFLICT


def test_api_error_translation_helpers() -> None:
    assert error_envelope(DocumentNotFoundError("gone"))["error"]["code"] == "not_found"
    assert error_envelope(DuplicateDocumentError("dup"))["error"]["code"] == "conflict"
    assert error_envelope(ConflictError("stale"))["error"]["code"] == "conflict"
    assert error_envelope(RevisionNotFoundError("rev"))["error"]["code"] == "not_found"
    assert error_envelope(SnapshotError("bad"))["error"]["code"] == "not_found"
    assert error_envelope(CodecError("bad markdown"))["error"]["code"] == "invalid_input"
    assert error_envelope(StorageError("bad store"))["error"]["code"] == "invalid_input"
    assert error_envelope(RuntimeError("boom"))["error"]["code"] == "internal"
    api_error = ApiError(ErrorCode.FORBIDDEN, "denied", ("write",))
    assert error_envelope(api_error) == api_error.to_dict()
    converted = as_api_error(ValueError("bad value"))
    assert converted.code is ErrorCode.INVALID_INPUT
    assert converted.message == "bad value"


def test_api_request_parsers() -> None:
    assert require_str({"x": " value "}, "x") == "value"
    assert optional_int({"n": "7"}, "n", 1, 0, 10) == 7
    assert optional_int({}, "n", 3, 0, 10) == 3
    with pytest.raises(ApiError, match="x must be a non-empty"):
        require_str({"x": "  "}, "x")
    with pytest.raises(ApiError, match="x exceeds"):
        require_str({"x": "y" * 500}, "x", 100)


def test_api_register_routes_is_idempotent() -> None:
    registry = RouteRegistry()
    first = register(registry)
    second = register(registry)
    assert len(first) == len(second) == len(ROUTE_SPECS) == 5
    assert len(registry) == 5
    assert registry.get("/api/v4/blocks") is not None
    assert registry.get("/api/v4/blocks/patch") is not None
    assert [route.name for route in registry.all()] == [spec[1] for spec in sorted(ROUTE_SPECS)]
    bare = register(object())
    assert len(bare) == 5


def test_api_envelope_helpers_round_trip() -> None:
    meta = PageMeta(request_id="r1", version="v4", etag='W/"abc"')
    payload = ok({"value": 1}, meta)
    assert EnvelopeDecoder().decode(payload) == {"value": 1}
    with pytest.raises(ApiError, match="missing meta"):
        EnvelopeDecoder().decode({"data": 1})
    with pytest.raises(ApiError, match="unexpected version"):
        EnvelopeDecoder().decode({"data": 1, "meta": {**meta.to_dict(), "version": "v3"}})
    assert fail_envelope(ApiError(ErrorCode.CONFLICT, "clash"))["error"]["message"] == "clash"


def test_api_event_bus_redacts_payloads() -> None:
    outbox = InMemoryOutbox(capacity=10)
    bus = EventBus(outbox=outbox)
    routes = build_routes(bus=bus)
    seed(routes)
    routes.put({"document": simple_document().to_dict(), "password": "secret"})
    records = outbox.records(EventKind.BLOCK_EDITED)
    assert len(records) == 1
    assert records[0].kind == "block.edited"
    assert "password" not in records[0].payload
    replayed = outbox.replay(EventKind.BLOCK_EDITED)
    assert replayed[0].aggregate_id == "doc1"


def test_api_route_metadata_and_capability_constants() -> None:
    assert {spec[2] for spec in ROUTE_SPECS} == {"GET", "PUT", "PATCH"}
    assert {spec[0] for spec in ROUTE_SPECS} == {
        "/blocks",
        "/blocks/document",
        "/blocks/patch",
        "/blocks/history",
        "/blocks/snapshots",
    }
    assert Capability.READ.value == "read"
    assert Capability.WRITE.value == "write"


def test_api_typed_client_shape_matches_envelopes() -> None:
    envelope: dict[str, Any] = ok(
        {"document": simple_document().to_dict()},
        PageMeta(request_id="r", version="v4"),
    )
    decoded = EnvelopeDecoder().decode(envelope)
    assert set(envelope) == {"data", "meta"}
    assert envelope["meta"]["version"] == "v4"
    assert decoded["document"]["id"] == "doc1"
