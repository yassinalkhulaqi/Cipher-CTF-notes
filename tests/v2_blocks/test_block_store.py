from __future__ import annotations

import pytest

from redscribe.storage.db import Vault
from redscribe.v2.blocks.diff import (
    BlockPatch,
    PatchEntry,
    PatchOperation,
    make_patch,
    rebase_patch,
)
from redscribe.v2.blocks.markdown import parse_document
from redscribe.v2.blocks.model import make_block, make_document
from redscribe.v2.blocks.revisions import RevisionConflictError, encode_token
from redscribe.v2.blocks.store import (
    BlockNotFoundError,
    BlockStore,
    BlockValidationError,
    create_store_with_sample,
)
from redscribe.v2.blocks.types import MentionKind
from redscribe.v2.blocks.vault import (
    BlockVaultService,
    document_from_note,
    document_id_for_note,
    ensure_document_block,
    note_content_from_document,
    note_id_for_document,
)


def test_store_create_list_get_and_delete() -> None:
    store = BlockStore()
    first = store.create(document_id="doc-z", title="Zulu", markdown="body one")
    second = store.create(document_id="doc-a", title="Alpha", markdown="body two")
    assert [document.id for document in store.list_documents()] == ["doc-a", "doc-z"]
    assert store.list_ids() == ["doc-a", "doc-z"]
    assert store.get("doc-a").title == "Alpha"
    assert store.find("missing") is None
    with pytest.raises(BlockNotFoundError):
        store.get("missing")
    assert store.delete("doc-a") is True
    assert store.delete("doc-a") is False
    assert store.find("doc-a") is None
    assert first.id == "doc-z"
    assert second.id == "doc-a"


def test_store_create_parses_markdown_and_rejects_invalid_documents() -> None:
    store = BlockStore()
    document = store.create(
        document_id="doc-1",
        title="Report",
        markdown="## Heading\n\n- one\n- two\n\n@[vault](note:home)",
        tags=["CTF", "ctf"],
    )
    assert [block.type.value for block in document.blocks] == ["heading", "list", "paragraph"]
    assert document.tags == ("ctf",)
    assert document.metadata == {}
    assert store.markdown("doc-1").startswith("## Heading")
    broken = make_document("bad", blocks=[make_block("image", source="javascript:alert(1)")])
    with pytest.raises(BlockValidationError):
        store.put(broken)
    assert store.find("bad") is None


def test_store_save_uses_optimistic_tokens() -> None:
    store = BlockStore()
    document = store.create(document_id="doc-1", markdown="original")
    token = store.token_string("doc-1")
    incoming = document.with_blocks([make_block("paragraph", "updated", block_id="new")])
    saved = store.save(incoming, token)
    assert saved.revision == 1
    assert saved.blocks[0].text == "updated"
    assert store.get("doc-1") == saved
    with pytest.raises(RevisionConflictError):
        store.save(incoming, token)
    with pytest.raises(RevisionConflictError):
        store.save(saved, None)
    assert store.save(saved, None, require_token=False).revision == 2


def test_store_apply_patch_updates_document_and_indices() -> None:
    store = BlockStore()
    document = store.create(
        document_id="doc-1",
        markdown="alpha beta\n\n@[vault](note:home)",
    )
    token = store.token_string("doc-1")
    block = document.blocks[0].with_changes(text="alpha gamma")
    patch = make_patch(
        document,
        [PatchEntry(PatchOperation.UPDATE, block.id, block=block, index=0)],
        label="edit",
    )
    patched = store.apply_patch("doc-1", patch, token)
    assert patched.revision == 1
    assert patched.blocks[0].text == "alpha gamma"
    assert [result.block_id for result in store.search("gamma")] == [block.id]
    assert not store.search("beta")
    assert [hit.mention.target for hit in store.mention_hits("home")] == ["home"]
    with pytest.raises(RevisionConflictError):
        store.apply_patch("doc-1", patch, token)
    assert (
        store.apply_patch("doc-1", rebase_patch(patch, 1), None, require_token=False).revision == 2
    )


def test_store_apply_patch_reports_validation_and_payload_errors() -> None:
    store = BlockStore()
    document = store.create(
        document_id="doc-1",
        markdown="body",
    )
    token = store.token_string("doc-1")
    invalid = make_patch(
        document,
        [
            PatchEntry(
                PatchOperation.INSERT,
                "broken",
                block=make_block("image", source="javascript:alert(1)"),
            )
        ],
    )
    with pytest.raises(BlockValidationError):
        store.apply_patch("doc-1", invalid, token)
    with pytest.raises(BlockNotFoundError):
        store.apply_patch("missing", invalid, token)
    with pytest.raises(ValueError, match="Unknown patch operation"):
        store.apply_patch(
            "doc-1",
            {"base_revision": 0, "entries": [{"operation": "explode", "block_id": "b1"}]},
            token,
        )


def test_store_autosave_queue_and_flush() -> None:
    store = BlockStore(autosave_interval_ms=100, autosave_max_wait_ms=500)
    document = store.create(document_id="doc-1", markdown="original")
    token = store.token_string("doc-1")
    first = make_block("paragraph", "one", block_id="b2")
    second = make_block("paragraph", "two", block_id="b3")
    assert (
        store.queue_autosave(
            "doc-1",
            make_patch(document, [PatchEntry(PatchOperation.INSERT, "b2", block=first, index=1)]),
            token=token,
        )
        is None
    )
    assert (
        store.queue_autosave(
            "doc-1",
            make_patch(document, [PatchEntry(PatchOperation.INSERT, "b3", block=second, index=2)]),
            token=token,
        )
        is None
    )
    assert store.status()["autosave"]["pending"] == 1
    saved = store.flush_autosave("doc-1")
    assert len(saved) == 1
    assert saved[0].revision == 1
    assert saved[0].block_ids == ("blk-1", "b2", "b3") or len(saved[0].blocks) == 3
    assert not store.autosave.has_pending("doc-1")
    assert store.flush_autosave("doc-1") == []


def test_store_flush_all_autosave_and_acknowledge() -> None:
    store = BlockStore()
    first = store.create(document_id="doc-1", markdown="one")
    second = store.create(document_id="doc-2", markdown="two")
    added = make_block("paragraph", "extra", block_id="extra")
    for document in (first, second):
        store.queue_autosave(
            document.id,
            make_patch(
                document,
                [PatchEntry(PatchOperation.INSERT, "extra", block=added, index=1)],
            ),
        )
    saved = store.flush_all_autosave()
    assert {document.id for document in saved} == {"doc-1", "doc-2"}
    assert all(document.revision == 1 for document in saved)
    assert store.status()["autosave"]["pending"] == 0


def test_store_diff_validate_and_helpers() -> None:
    store = BlockStore()
    document = store.create(document_id="doc-1", markdown="original")
    changed = document.with_blocks(
        [make_block("paragraph", "changed", block_id=document.blocks[0].id)]
    )
    result = store.diff(document.id, changed)
    assert result.counts()["replace"] == 1
    assert store.validate(document.id).ok
    assert store.validate(changed).ok
    assert store.block("doc-1", document.blocks[0].id) == document.blocks[0]
    with pytest.raises(BlockNotFoundError):
        store.block("doc-1", "missing")
    normalized = store.normalize_detached({"id": "doc-9", "blocks": []})
    assert len(normalized.blocks) == 1
    assert store.token("doc-1").document_id == "doc-1"
    assert encode_token(store.token("doc-1")).startswith("rev1.")
    assert store.reindex() == 1


def test_store_search_and_mention_facets() -> None:
    store = BlockStore()
    store.create(
        document_id="doc-1",
        title="First",
        markdown="alpha beta\n\n@[vault](note:home)",
    )
    store.create(
        document_id="doc-2",
        title="Second",
        markdown="gamma alpha\n\n@[root](target:root)",
    )
    results = store.search("alpha", block_types=["paragraph"])
    assert {result.document_id for result in results} == {"doc-1", "doc-2"}
    assert [result.block_id for result in store.search("alpha", document_id="doc-1")] == [
        store.get("doc-1").blocks[0].id
    ]
    assert store.search("alpha", limit=1)[0].document_id == "doc-1"
    assert [hit.mention.target for hit in store.mention_hits("home")] == ["home"]
    assert [hit.mention.target for hit in store.mention_hits(kind=MentionKind.TARGET)] == ["root"]
    assert [hit.mention.target for hit in store.mention_hits()] == ["home", "root"]
    assert store.mention_suggestions("hom")[0].target == "home"
    assert len(store.reindex_mentions_for("b9", "@[again](note:home)")) == 1
    status = store.status()
    assert status["documents"] == 2
    assert status["indexed_blocks"] >= 4
    assert status["indexed_mentions"] == 2


def test_store_replace_blocks_and_reset() -> None:
    store = BlockStore()
    store.create(document_id="doc-1", markdown="original")
    replaced = store.replace_blocks("doc-1", "## New heading\n\nreplacement body")
    assert replaced.revision == 1
    assert [block.type.value for block in replaced.blocks] == ["heading", "paragraph"]
    assert store.markdown("doc-1").startswith("## New heading")
    store.reset()
    assert store.list_ids() == []
    assert store.status()["documents"] == 0


def test_create_store_with_sample_is_usable() -> None:
    store, document = create_store_with_sample()
    assert store.get(document.id) == document
    assert document.title == "Block notes"
    assert store.search("vault")


def test_note_identity_helpers() -> None:
    assert document_id_for_note(12) == "note-12"
    assert note_id_for_document("note-12") == 12
    assert note_id_for_document("doc-12") is None
    assert note_id_for_document("note-x") is None


def test_document_from_note_and_markdown_export() -> None:
    node = parse_document("body", document_id="note-4", title="Title", tags=["ctf"])
    document = make_document("note-4", "Title", node.blocks, tags=["ctf"])
    assert note_content_from_document(document).strip()
    assert ensure_document_block(document) == document
    assert ensure_document_block(document.with_blocks([])).blocks[0].type.value == "paragraph"


def test_vault_service_load_save_and_sync(vault: Vault) -> None:
    note = vault.create_node(
        "KTB Report",
        content="# KTB Report\n\n@[vault](note:home)",
        tags="ctf, web",
        target="example.com",
    )
    service = BlockVaultService(vault)
    document = service.load(note.id)
    assert document.id == document_id_for_note(note.id)
    assert document.metadata["note_id"] == str(note.id)
    assert document.metadata["target"] == "example.com"
    assert document.tags == ("ctf", "web")
    assert service.load(note.id) is document
    refreshed = service.load(note.id, refresh=True)
    assert refreshed.id == document.id
    token = service.token(note.id)
    incoming = refreshed.with_blocks([make_block("paragraph", "updated body", block_id="updated")])
    saved = service.save(note.id, incoming, token)
    assert saved.revision == 1
    assert "updated body" in vault.get_node(note.id).content
    with pytest.raises(RevisionConflictError):
        service.save(note.id, incoming, token)
    assert service.sync_note(note.id, saved)
    assert service.status()["loaded_notes"] == 1


def test_vault_service_patch_autosave_and_queries(vault: Vault) -> None:
    note = vault.create_node(
        "Recon",
        content="# Recon\n\noriginal\n\n@[vault](note:home)",
        tags="recon",
    )
    service = BlockVaultService(vault)
    document = service.load(note.id)
    token = service.token(note.id)
    updated = document.blocks[1].with_changes(text="patched body")
    patch = make_patch(
        document,
        [PatchEntry(PatchOperation.UPDATE, updated.id, block=updated, index=1)],
    )
    saved = service.save_patch(note.id, patch, token)
    assert saved.blocks[1].text == "patched body"
    assert "patched body" in vault.get_node(note.id).content

    current = service.load(note.id, refresh=True)
    inserted = make_block("paragraph", "autosaved line", block_id="auto")
    queued = service.autosave(
        note.id,
        make_patch(
            current,
            [PatchEntry(PatchOperation.INSERT, "auto", block=inserted, index=2)],
        ),
    )
    assert queued is None
    flushed = service.flush(current.id)
    assert len(flushed) == 1
    assert "autosaved line" in vault.get_node(note.id).content
    assert service.search("patched")[0].document_id == current.id
    assert service.mentions("home")
    assert service.suggestions("hom")[0].target == "home"
    service.reset()
    assert service.store.list_ids() == []


def test_vault_service_load_all_and_missing_note(vault: Vault) -> None:
    note_one = vault.create_node("One", content="# One\n\nbody one")
    vault.create_node("Folder", kind="folder")
    note_two = vault.create_node("Two", content="# Two\n\nbody two")
    service = BlockVaultService(vault)
    loaded = service.load_all_notes()
    assert [document.metadata["note_id"] for document in loaded] == [
        str(note_one.id),
        str(note_two.id),
    ]
    assert len(service.load_many([note_one.id, note_two.id])) == 2
    with pytest.raises(LookupError):
        service.load(9999)
    assert service.vault is vault
    assert isinstance(service.store, BlockStore)


def test_document_from_note_uses_node_fields(vault: Vault) -> None:
    node = vault.create_node(
        "Sanitized",
        content="## Body\n\ncontent",
        tags="alpha, beta",
        target="10.0.0.1",
        status="active",
    )
    document = document_from_note(node)
    assert document.id == "note-" + str(node.id)
    assert document.title == "Sanitized"
    assert document.tags == ("alpha", "beta")
    assert document.metadata == {}
    assert document.blocks[0].type.value == "heading"


def test_block_patch_dict_may_be_used_by_vault_service(vault: Vault) -> None:
    note = vault.create_node("Payload", content="# Payload\n\nbody")
    service = BlockVaultService(vault)
    document = service.load(note.id)
    token = encode_token(service.token(note.id))
    updated = document.blocks[1].with_changes(text="from payload")
    payload: dict[str, object] = {
        "document_id": document.id,
        "base_revision": document.revision,
        "label": "payload",
        "entries": [
            {
                "operation": "update",
                "block_id": updated.id,
                "block": updated.as_dict(),
                "index": 1,
            }
        ],
    }
    patched = service.save_patch(note.id, BlockPatch.from_dict(payload), token)
    assert patched.blocks[1].text == "from payload"
    assert "from payload" in vault.get_node(note.id).content
