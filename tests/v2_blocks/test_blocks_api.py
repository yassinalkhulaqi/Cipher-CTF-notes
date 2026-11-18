from __future__ import annotations

from typing import Any

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.namespaces.blocks import (
    BlocksNamespace,
    create_blocks_api,
    register,
)
from redscribe.ui.web.v2.router import V2Router
from redscribe.ui.web.v2.routes import ApiV2
from redscribe.v2.blocks.diff import PatchEntry, PatchOperation, make_patch
from redscribe.v2.blocks.model import make_block


@pytest.fixture
def router(vault: Vault) -> V2Router:
    return V2Router(vault, create_blocks_api(vault))


def _data(response: dict[str, Any]) -> dict[str, Any]:
    assert response["ok"] is True, response
    payload = response["data"]
    assert isinstance(payload, dict)
    return payload


def _create(router: V2Router, document_id: str, markdown: str = "body") -> dict[str, Any]:
    response = router.dispatch(
        "blocks.create",
        {"document_id": document_id, "title": document_id, "markdown": markdown},
    )
    return _data(response)


def test_blocks_namespace_registers_all_routes(vault: Vault) -> None:
    api: ApiV2 = create_blocks_api(vault)
    namespace: BlocksNamespace = register(api)
    names = {name for name in api.routes if name.startswith("blocks.")}
    expected = {
        "blocks.capabilities",
        "blocks.schema",
        "blocks.create",
        "blocks.get",
        "blocks.list",
        "blocks.parse",
        "blocks.serialize",
        "blocks.validate",
        "blocks.diff",
        "blocks.patch",
        "blocks.save",
        "blocks.replace_blocks",
        "blocks.search",
        "blocks.mentions",
        "blocks.autosave",
        "blocks.autosave_status",
        "blocks.flush",
        "blocks.delete",
        "blocks.reindex",
        "blocks.status",
    }
    assert expected <= names
    assert {"system.health", "notes.get"} <= set(api.routes)
    assert namespace.store is namespace.service.store
    assert namespace.service.vault is vault
    capabilities = _data(V2Router(vault, api).dispatch("blocks.capabilities", {}))
    assert capabilities["namespace"] == "blocks"
    assert len(capabilities["block_types"]) == 9
    assert "block_diff" in capabilities["features"]
    assert capabilities["limits"]["max_patch_ops"] > 0
    schema = _data(V2Router(vault, api).dispatch("blocks.schema", {}))
    assert expected <= {route["name"] for route in schema["routes"]}
    assert "mentions" in schema["block_fields"]


def test_create_get_list_serialize_validate_parse_and_delete(router: V2Router) -> None:
    created = _create(
        router,
        "doc-1",
        "## Heading\n\n- one\n- two\n\n@[vault](note:home)",
    )
    assert created["document"]["id"] == "doc-1"
    assert created["token"].startswith("rev1.")
    assert created["markdown"].startswith("## Heading")
    fetched = _data(router.dispatch("blocks.get", {"id": "doc-1"}))
    assert fetched["document"]["revision"] == 0
    listing = router.dispatch("blocks.list", {"limit": 2})
    assert listing["data"][0]["id"] == "doc-1"
    assert listing["meta"]["page"]["total"] == 1
    parsed = _data(
        router.dispatch(
            "blocks.parse",
            {"markdown": "# Title\n\nbody", "title": "Title", "tags": ["ctf"]},
        )
    )
    assert parsed["document"]["blocks"][0]["type"] == "heading"
    serialized = _data(router.dispatch("blocks.serialize", {"id": "doc-1", "include_title": False}))
    assert serialized["markdown"].startswith("## Heading")
    report = _data(router.dispatch("blocks.validate", {"id": "doc-1"}))
    assert report["ok"] is True
    deleted = router.dispatch("blocks.delete", {"id": "doc-1"})
    assert deleted.status == 200
    assert deleted["data"]["removed"] is True


def test_save_and_patch_use_revision_tokens(router: V2Router) -> None:
    created = _create(router, "doc-1", "original body")
    token = created["token"]
    incoming = dict(created["document"])
    incoming["blocks"] = [make_block("paragraph", "saved body", block_id="saved").as_dict()]
    saved = _data(router.dispatch("blocks.save", {"document": incoming, "token": token}))
    assert saved["document"]["revision"] == 1
    assert saved["document"]["blocks"][0]["text"] == "saved body"

    current = _data(router.dispatch("blocks.get", {"id": "doc-1"}))
    block = current["document"]["blocks"][0]
    patch = make_patch(
        make_document_from_payload(current["document"]),
        [
            PatchEntry(
                PatchOperation.UPDATE,
                block["id"],
                block=make_block("paragraph", "patched body", block_id=block["id"]),
                index=0,
            )
        ],
        label="api-edit",
    )
    patched = _data(router.dispatch("blocks.patch", {"id": "doc-1", "patch": patch.as_dict()}))
    assert patched["document"]["blocks"][0]["text"] == "patched body"
    assert patched["document"]["revision"] == 2

    stale = router.dispatch(
        "blocks.patch",
        {
            "id": "doc-1",
            "patch": patch.as_dict(),
            "token": token,
        },
    )
    assert stale.status == 409
    assert stale["error"]["code"] == "conflict"
    assert stale["error"]["details"]["code"] == "revision_conflict"


def make_document_from_payload(payload: dict[str, Any]) -> Any:
    from redscribe.v2.blocks.model import BlockDocument

    return BlockDocument.from_dict(payload)


def test_diff_replace_blocks_and_status(router: V2Router) -> None:
    first = _create(router, "doc-1", "alpha body")
    _create(router, "doc-2", "beta body")
    diff = _data(router.dispatch("blocks.diff", {"left": "doc-1", "right": "doc-2"}))
    assert diff["changed"] is True
    assert sum(diff["counts"].values()) >= 1
    assert diff["entries"]

    replaced = _data(
        router.dispatch(
            "blocks.replace_blocks",
            {"id": "doc-1", "markdown": "## Replaced\n\nnew body"},
        )
    )
    assert replaced["document"]["blocks"][0]["type"] == "heading"
    assert "Replaced" in replaced["markdown"]
    status = _data(router.dispatch("blocks.status", {}))
    assert status["documents"] == 2
    assert status["route_count"] >= 20
    reindexed = _data(router.dispatch("blocks.reindex", {}))
    assert reindexed["reindexed"] == 2
    assert first["document"]["id"] == "doc-1"


def test_search_mentions_and_filters(router: V2Router) -> None:
    _create(router, "doc-1", "alpha beta\n\n@[vault](note:home)")
    _create(router, "doc-2", "gamma alpha\n\n@[root](target:root)")
    results = _data(router.dispatch("blocks.search", {"query": "alpha"}))
    assert {item["document_id"] for item in results["items"]} == {"doc-1", "doc-2"}
    filtered = _data(
        router.dispatch(
            "blocks.search",
            {"query": "alpha", "block_types": ["paragraph"], "document_id": "doc-1"},
        )
    )
    assert [item["document_id"] for item in filtered["items"]] == ["doc-1"]
    invalid = router.dispatch("blocks.search", {"query": "alpha", "block_types": ["canvas"]})
    assert invalid.status == 400
    assert invalid["error"]["code"] == "invalid_choice"

    hits = _data(router.dispatch("blocks.mentions", {"target": "home"}))
    assert hits["mode"] == "hits"
    assert hits["items"][0]["target"] == "home"
    suggestions = _data(router.dispatch("blocks.mentions", {"query": "hom"}))
    assert suggestions["mode"] == "suggestions"
    assert suggestions["items"][0]["target"] == "home"


def test_autosave_status_and_flush(router: V2Router) -> None:
    created = _create(router, "doc-1", "original")
    block = created["document"]["blocks"][0]
    patch = make_patch(
        make_document_from_payload(created["document"]),
        [
            PatchEntry(
                PatchOperation.UPDATE,
                block["id"],
                block=make_block("paragraph", "autosaved", block_id=block["id"]),
                index=0,
            )
        ],
        label="autosave",
    )
    queued = _data(
        router.dispatch(
            "blocks.autosave",
            {"id": "doc-1", "patch": patch.as_dict(), "token": created["token"]},
        )
    )
    assert queued["queued"] is True
    assert queued["state"]["pending"] == 1
    status = _data(router.dispatch("blocks.autosave_status", {}))
    assert status["status"]["pending"] == 1
    assert "doc-1" in status["documents"]
    flushed = _data(router.dispatch("blocks.flush", {"id": "doc-1"}))
    assert flushed["count"] == 1
    assert flushed["saved"][0]["blocks"][0]["text"] == "autosaved"
    assert flushed["state"]["pending"] == 0


def test_note_backed_routes_sync_vault(vault: Vault, router: V2Router) -> None:
    note = vault.create_node("Note", content="# Note\n\noriginal", tags="ctf")
    created = _data(router.dispatch("blocks.create", {"note_id": note.id}))
    document_id = created["document"]["id"]
    assert document_id == f"note-{note.id}"
    fetched = _data(router.dispatch("blocks.get", {"note_id": note.id}))
    assert fetched["document"]["id"] == document_id
    block = fetched["document"]["blocks"][1]
    patch = make_patch(
        make_document_from_payload(fetched["document"]),
        [
            PatchEntry(
                PatchOperation.UPDATE,
                block["id"],
                block=make_block("paragraph", "synced body", block_id=block["id"]),
                index=1,
            )
        ],
    )
    patched = _data(router.dispatch("blocks.patch", {"note_id": note.id, "patch": patch.as_dict()}))
    assert patched["document"]["blocks"][1]["text"] == "synced body"
    assert "synced body" in vault.get_node(note.id).content


def test_autosave_and_flush_sync_note_backed_document(vault: Vault, router: V2Router) -> None:
    note = vault.create_node("Autosave note", content="# Autosave note\n\noriginal")
    created = _data(router.dispatch("blocks.create", {"note_id": note.id}))
    document = make_document_from_payload(created["document"])
    block = document.blocks[1]
    patch = make_patch(
        document,
        [
            PatchEntry(
                PatchOperation.UPDATE,
                block.id,
                block=block.with_changes(text="queued body"),
                index=1,
            )
        ],
    )
    queued = _data(
        router.dispatch("blocks.autosave", {"id": document.id, "patch": patch.as_dict()})
    )
    assert queued["queued"] is True
    flushed = _data(router.dispatch("blocks.flush", {}))
    assert flushed["count"] == 1
    assert "queued body" in vault.get_node(note.id).content


def test_blocks_error_envelopes(router: V2Router) -> None:
    missing = router.dispatch("blocks.get", {"id": "missing"})
    assert missing.status == 404
    assert missing["ok"] is False
    assert missing["error"]["code"] == "not_found"

    invalid_type = router.dispatch("blocks.serialize", {"document": "not-an-object"})
    assert invalid_type.status == 400
    assert invalid_type["error"]["code"] == "missing_field"

    missing_id = router.dispatch("blocks.autosave", {"patch": {"entries": []}})
    assert missing_id.status == 400
    assert missing_id["error"]["code"] == "missing_field"

    missing_delete = router.dispatch("blocks.delete", {"id": "missing"})
    assert missing_delete.status == 404
    assert missing_delete["data"]["removed"] is False


def test_patch_body_accepts_operations_array(router: V2Router) -> None:
    created = _create(router, "doc-1", "original")
    block = created["document"]["blocks"][0]
    patched = _data(
        router.dispatch(
            "blocks.patch",
            {
                "id": "doc-1",
                "base_revision": 0,
                "operations": [
                    {
                        "operation": "update",
                        "block_id": block["id"],
                        "block": make_block(
                            "paragraph", "array body", block_id=block["id"]
                        ).as_dict(),
                        "index": 0,
                    }
                ],
            },
        )
    )
    assert patched["document"]["blocks"][0]["text"] == "array body"


def test_namespace_can_register_on_an_existing_api(vault: Vault) -> None:
    api = ApiV2(vault)
    namespace = register(api)
    assert "blocks.get" in api.routes
    assert isinstance(namespace, BlocksNamespace)
    assert api.route("blocks.get").description
    assert api.route("blocks.patch").mutating is True
    assert api.route("blocks.get").required == ()
