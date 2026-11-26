"""Tests for parsing, templates, triage transitions, storage, and services."""

from __future__ import annotations

import json
from itertools import product

import pytest

from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.inbox.service import (
    ACTIONS,
    DEFAULT_TEMPLATES,
    CaptureNotFoundError,
    CaptureParser,
    InboxService,
    MissingTemplateKeyError,
    TemplateEngine,
    TransitionError,
    TriageMachine,
    UnknownTemplateError,
)
from redscribe.v4.inbox.storage import (
    DuplicateItemError,
    InboxImportError,
    InboxStore,
    StorageError,
)
from redscribe.v4.inbox.types import (
    CaptureItem,
    CaptureSource,
    TriageState,
    compute_content_hash,
)

ITEM_ID = "11111111-2222-3333-4444-555555555555"
ITEM_ID_2 = "22222222-3333-4444-5555-666666666666"
ITEM_ID_3 = "33333333-4444-5555-6666-777777777777"
TIMESTAMP = "2026-01-02T03:04:05.000Z"


def fixed_clock() -> str:
    return TIMESTAMP


def make_item(
    raw: str,
    source: CaptureSource = CaptureSource.MANUAL,
    state: TriageState = TriageState.UNTRIAGED,
    tags: tuple[str, ...] = (),
    item_id: str = ITEM_ID,
) -> CaptureItem:
    item = CaptureItem.create(raw=raw, source=source, tags=tags, item_id=item_id)
    return item if state is TriageState.UNTRIAGED else item.with_state(state)


@pytest.mark.parametrize(
    ("raw", "source"),
    [
        ("flag{alpha}", CaptureSource.FLAG),
        ("https://example.test/a", CaptureSource.LINK),
        ("def check(x):\n    return x + 1", CaptureSource.SNIPPET),
        ("a plain note", CaptureSource.MANUAL),
        ("```python\nprint(1)\n```", CaptureSource.SNIPPET),
    ],
)
def test_parser_classifies_sources(raw: str, source: CaptureSource) -> None:
    parser = CaptureParser()
    assert parser.classify(raw) is source
    assert parser.parse(raw).source is source


def test_parser_classify_respects_hints() -> None:
    parser = CaptureParser()
    assert parser.classify("flag{alpha}", "clipboard") is CaptureSource.CLIPBOARD
    assert parser.classify("note", CaptureSource.FLAG) is CaptureSource.FLAG
    with pytest.raises(ValueError, match="Unknown capture source"):
        parser.classify("note", "未知")
    with pytest.raises(TypeError, match="hint must be"):
        parser.classify("note", 12)  # type: ignore[arg-type]


def test_parser_extracts_urls_in_order() -> None:
    parser = CaptureParser()
    text = "see https://one.test/a, then http://two.test/b. done"
    assert parser.extract_urls(text) == (
        "https://one.test/a",
        "http://two.test/b",
    )
    assert parser.first_url(text) == "https://one.test/a"
    assert parser.first_url("nothing here") is None


def test_parser_deduplicates_urls_and_trims_punctuation() -> None:
    parser = CaptureParser()
    urls = parser.extract_urls("https://a.test/x?y=1) and https://a.test/x?y=1!")
    assert urls == ("https://a.test/x?y=1",)


def test_parser_ignores_malformed_urls() -> None:
    parser = CaptureParser()
    assert parser.extract_urls("ftp://one.test/x and http://") == ()


def test_parser_detects_flag_tokens() -> None:
    parser = CaptureParser()
    tokens = parser.detect_flags("first flag{alpha} then FLAG{beta} and flag{alpha}")
    assert tokens == ("flag{alpha}", "FLAG{beta}")


def test_parser_flag_pattern_needs_closing_brace() -> None:
    parser = CaptureParser()
    assert parser.detect_flags("flag{unfinished") == ()


def test_parser_tag_hints() -> None:
    parser = CaptureParser()
    hints = parser.tag_hints("TODO: flag{alpha} at https://example.test")
    assert hints == ("flag", "link", "todo", "web")
    assert parser.tag_hints("a plain note") == ()


def test_parser_tag_hints_mark_snippets() -> None:
    parser = CaptureParser()
    hints = parser.tag_hints("def main():\n    return 1")
    assert "snippet" in hints


def test_parser_looks_like_snippet_rules() -> None:
    parser = CaptureParser()
    assert parser.looks_like_snippet("const x = 1; const y = 2;") is True
    assert parser.looks_like_snippet("a b c d e f g h i j k l: x: y: z:") is True
    assert parser.looks_like_snippet("just a sentence") is False


def test_parser_confidence_ranges_by_source() -> None:
    parser = CaptureParser()
    for source in CaptureSource:
        score = parser.confidence_for("a reasonably long capture text here", source)
        assert 0.0 <= score <= 1.0
    assert parser.confidence_for("flag{alpha}", CaptureSource.FLAG) > parser.confidence_for(
        "hi", CaptureSource.MANUAL
    )
    with pytest.raises(TypeError, match="source must be"):
        parser.confidence_for("note", "manual")  # type: ignore[arg-type]


def test_parser_parse_merges_tags_and_confidence() -> None:
    parser = CaptureParser()
    draft = parser.parse(
        "flag{alpha}",
        tags=[" CTF ", "flag"],
        confidence=0.42,
    )
    assert draft.source is CaptureSource.FLAG
    assert draft.flags == ("flag{alpha}",)
    assert draft.tags == ("ctf", "flag")
    assert draft.confidence == 0.42


def test_template_engine_defaults() -> None:
    engine = TemplateEngine()
    assert engine.names() == tuple(sorted(DEFAULT_TEMPLATES))
    assert engine.get("handoff")
    assert "raw" in engine.keys_for("handoff")


def test_template_engine_renders_all_defaults() -> None:
    item = make_item("flag{alpha}", CaptureSource.FLAG, tags=("ctf",))
    engine = TemplateEngine()
    for name in engine.names():
        rendered = engine.render_capture(item, name)
        assert rendered.strip()
        assert "{{" not in rendered


def test_template_engine_render_text_substitutes() -> None:
    engine = TemplateEngine()
    rendered = engine.render_text("{{ name }} / {{name}}", {"name": "alpha"})
    assert rendered == "alpha / alpha"


def test_template_engine_missing_key_error() -> None:
    engine = TemplateEngine()
    with pytest.raises(MissingTemplateKeyError) as exc_info:
        engine.render("note", {"title": "x"})
    assert exc_info.value.key == "body"
    assert set(exc_info.value.missing) == {"body", "tags"}


def test_template_engine_unknown_template() -> None:
    engine = TemplateEngine()
    with pytest.raises(UnknownTemplateError, match="unknown template"):
        engine.render("missing", {})
    with pytest.raises(UnknownTemplateError):
        engine.keys_for("missing")


@pytest.mark.parametrize("name", ["", "Bad Name", "9start", "a" * 41])
def test_template_engine_rejects_bad_name(name: str) -> None:
    engine = TemplateEngine()
    with pytest.raises(ValueError, match="Invalid template name"):
        engine.register(name, "hello")


@pytest.mark.parametrize("text", ["", "   ", "x" * 4001])
def test_template_engine_rejects_bad_text(text: str) -> None:
    engine = TemplateEngine()
    with pytest.raises(ValueError, match=r"must not be empty|too long"):
        engine.register("custom", text)


def test_template_engine_register_remove() -> None:
    engine = TemplateEngine()
    engine.register("custom", "Hello {{who}}!")
    assert engine.render("custom", {"who": "world"}) == "Hello world!"
    assert engine.remove("custom") is True
    assert engine.remove("custom") is False


def test_machine_legal_targets() -> None:
    machine = TriageMachine()
    assert machine.legal_targets(TriageState.UNTRIAGED) == (
        TriageState.ACCEPTED,
        TriageState.ARCHIVED,
        TriageState.REJECTED,
    )
    assert machine.legal_targets(TriageState.ACCEPTED) == (TriageState.ARCHIVED,)
    assert machine.legal_targets(TriageState.REJECTED) == (TriageState.ARCHIVED,)
    assert machine.legal_targets(TriageState.ARCHIVED) == (TriageState.UNTRIAGED,)
    assert set(machine.graph()) == {state.value for state in TriageState}


@pytest.mark.parametrize(("source", "target"), list(product(TriageState, TriageState)))
def test_machine_all_transition_pairs(source: TriageState, target: TriageState) -> None:
    machine = TriageMachine()
    legal = machine.can_transition(source, target)
    if legal:
        assert machine.transition(source, target) is target
        assert source in machine.graph()
    else:
        with pytest.raises(TransitionError, match="illegal transition"):
            machine.transition(source, target)


def test_machine_transition_type_guards() -> None:
    machine = TriageMachine()
    with pytest.raises(TypeError, match="must be TriageState"):
        machine.transition("untriaged", TriageState.ACCEPTED)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a TriageState"):
        machine.legal_targets("untriaged")  # type: ignore[arg-type]


def test_machine_apply_returns_new_item() -> None:
    machine = TriageMachine()
    item = make_item("note")
    moved = machine.apply(item, TriageState.ACCEPTED)
    assert moved.state is TriageState.ACCEPTED
    assert item.state is TriageState.UNTRIAGED


def test_machine_actions() -> None:
    machine = TriageMachine()
    assert set(ACTIONS) == {"accept", "reject", "archive", "reset"}
    assert machine.action_for(TriageState.REJECTED) == "reject"
    assert machine.target_for(" ACCEPT ") is TriageState.ACCEPTED
    assert machine.validate_action(TriageState.UNTRIAGED, "accept") is TriageState.ACCEPTED
    with pytest.raises(ValueError, match="unknown triage action"):
        machine.target_for("delete")
    assert machine.action_for(TriageState.UNTRIAGED) == "reset"


def test_machine_custom_transitions() -> None:
    machine = TriageMachine({TriageState.UNTRIAGED: [TriageState.ARCHIVED]})
    assert machine.can_transition(TriageState.UNTRIAGED, TriageState.ARCHIVED)
    assert not machine.can_transition(TriageState.UNTRIAGED, TriageState.ACCEPTED)


def test_store_insert_get_and_duplicates() -> None:
    store = InboxStore()
    item = make_item("note")
    store.insert(item)
    assert store.get(ITEM_ID) == item
    assert ITEM_ID in store
    assert len(store) == 1
    with pytest.raises(DuplicateItemError, match="duplicate id"):
        store.insert(item)
    with pytest.raises(DuplicateItemError, match="duplicate content_hash"):
        store.insert(make_item("  note  ", item_id=ITEM_ID_2))


def test_store_update_delete_and_index_sync() -> None:
    store = InboxStore([make_item("note")])
    moved = make_item("note").with_state(TriageState.ACCEPTED)
    store.update(moved)
    assert store.get(ITEM_ID) == moved
    updated = make_item("different")
    store.update(updated)
    assert store.find_by_hash(compute_content_hash("note")) is None
    assert store.find_by_hash(compute_content_hash("different")) == updated
    with pytest.raises(DuplicateItemError):
        store.insert(make_item("different", item_id=ITEM_ID_2))
    with pytest.raises(StorageError, match="cannot update missing"):
        store.update(make_item("other", item_id=ITEM_ID_3))
    assert store.delete(ITEM_ID) is True
    assert store.delete(ITEM_ID) is False
    assert len(store) == 0


def test_store_filters() -> None:
    store = InboxStore(
        [
            make_item("flag{alpha}", CaptureSource.FLAG, tags=("ctf",), item_id=ITEM_ID),
            make_item(
                "https://example.test/a",
                CaptureSource.LINK,
                state=TriageState.ACCEPTED,
                tags=("web",),
                item_id=ITEM_ID_2,
            ),
            make_item("just a note", item_id=ITEM_ID_3),
        ]
    )
    assert len(store.list(state=TriageState.UNTRIAGED)) == 2
    assert len(store.list(source=CaptureSource.FLAG)) == 1
    assert store.list(tag="WEB")[0].id == ITEM_ID_2
    assert store.list(query="EXAMPLE")[0].id == ITEM_ID_2
    assert store.list(state=TriageState.ACCEPTED, source=CaptureSource.LINK)[0].id == ITEM_ID_2
    assert store.list(state=TriageState.ARCHIVED) == ()
    assert store.all() == store.list()


def test_store_rebuild_index_and_reports() -> None:
    store = InboxStore([make_item("one", item_id=ITEM_ID), make_item("two", item_id=ITEM_ID_2)])
    assert store.rebuild_index() == 2
    assert store.index_report() == {"items": 2, "hashes": 2, "order": 2}
    assert store.is_consistent() is True
    assert store.ids() == (ITEM_ID, ITEM_ID_2)
    store.clear()
    assert len(store) == 0
    assert store.is_consistent() is True


def test_store_export_import_roundtrip() -> None:
    original = InboxStore([make_item("one", item_id=ITEM_ID)])
    payload = original.export_json()
    restored = InboxStore()
    assert restored.import_json(payload) == 1
    assert restored.import_json(payload) == 0
    assert restored.get(ITEM_ID) == original.get(ITEM_ID)


def test_store_import_validation_errors() -> None:
    store = InboxStore()
    with pytest.raises(InboxImportError, match="non-empty"):
        store.import_json("")
    with pytest.raises(InboxImportError, match="not valid JSON"):
        store.import_json("{")
    with pytest.raises(InboxImportError, match="unsupported import version"):
        store.import_json('{"version": 9, "items": []}')
    with pytest.raises(InboxImportError, match="items must be a list"):
        store.import_json('{"version": 1, "items": {}}')
    with pytest.raises(InboxImportError, match="must be an object"):
        store.import_json("[42]")


def test_store_import_skips_duplicate_hash() -> None:
    store = InboxStore([make_item("note", item_id=ITEM_ID)])
    payload = json.dumps(
        {"version": 1, "items": [make_item("  NOTE  ", item_id=ITEM_ID_2).to_dict()]}
    )
    assert store.import_json(payload) == 0
    assert len(store) == 1


def test_service_capture_emits_event_and_dedupes() -> None:
    outbox = InMemoryOutbox()
    service = InboxService(bus=EventBus(outbox), clock=fixed_clock)
    first = service.capture("flag{alpha}", tags=["ctf"], item_id=ITEM_ID)
    assert first.created is True
    assert first.item.id == ITEM_ID
    assert first.item.created_at == TIMESTAMP
    assert first.item.source is CaptureSource.FLAG
    duplicate = service.capture("  FLAG{ALPHA}  ", item_id=ITEM_ID_2)
    assert duplicate.created is False
    assert duplicate.item.id == ITEM_ID
    assert service.total == 1
    created = outbox.records(EventKind.CAPTURE_CREATED)
    assert len(created) == 1
    assert created[0].payload["source"] == "flag"
    assert created[0].payload["raw_length"] == len("flag{alpha}")


def test_service_capture_many_and_source_override() -> None:
    service = InboxService(clock=fixed_clock)
    results = service.capture_many(["one", "two", "flag{x}", "one"])
    assert len(results) == 4
    assert sum(result.created for result in results) == 3
    pasted = service.capture("plain text", source="clipboard")
    assert pasted.item.source is CaptureSource.CLIPBOARD


def test_service_triage_emits_event() -> None:
    outbox = InMemoryOutbox()
    service = InboxService(bus=EventBus(outbox), clock=fixed_clock)
    service.capture("note", item_id=ITEM_ID)
    updated = service.triage(ITEM_ID, "accepted", "tester")
    assert updated.state is TriageState.ACCEPTED
    assert service.get(ITEM_ID).state is TriageState.ACCEPTED
    records = outbox.records(EventKind.CAPTURE_TRAGED)
    assert len(records) == 1
    assert records[0].payload["from_state"] == "untriaged"
    assert records[0].payload["to_state"] == "accepted"
    assert records[0].payload["actor"] == "tester"


def test_service_triage_shortcuts() -> None:
    service = InboxService(clock=fixed_clock)
    service.capture("one", item_id=ITEM_ID)
    service.capture("two", item_id=ITEM_ID_2)
    service.capture("three", item_id=ITEM_ID_3)
    assert service.accept(ITEM_ID).state is TriageState.ACCEPTED
    assert service.reject(ITEM_ID_2).state is TriageState.REJECTED
    assert service.archive(ITEM_ID_3).state is TriageState.ARCHIVED
    assert service.archive(ITEM_ID).state is TriageState.ARCHIVED
    assert service.triage(ITEM_ID, TriageState.UNTRIAGED).state is TriageState.UNTRIAGED


def test_service_triage_rejects_illegal_and_unknown() -> None:
    service = InboxService(clock=fixed_clock)
    service.capture("note", item_id=ITEM_ID)
    service.accept(ITEM_ID)
    with pytest.raises(TransitionError, match="illegal transition"):
        service.reject(ITEM_ID)
    with pytest.raises(ValueError, match="Unknown triage state"):
        service.triage(ITEM_ID, "deleted")
    with pytest.raises(CaptureNotFoundError, match="capture not found"):
        service.triage(ITEM_ID_3, "accepted")


def test_service_list_filters_and_stats() -> None:
    service = InboxService(clock=fixed_clock)
    service.capture("flag{alpha}", tags=["ctf"], item_id=ITEM_ID)
    service.capture("https://example.test", tags=["web"], item_id=ITEM_ID_2)
    service.accept(ITEM_ID_2)
    assert len(service.list(state="accepted")) == 1
    assert len(service.list(source=CaptureSource.FLAG)) == 1
    assert len(service.list(tag="web")) == 1
    assert len(service.list(query="alpha")) == 1
    stats = service.stats()
    assert stats["total"] == 2
    assert stats["state_untriaged"] == 1
    assert stats["state_accepted"] == 1
    assert stats["source_flag"] == 1
    assert stats["source_link"] == 1


def test_service_render_and_import_export() -> None:
    service = InboxService(clock=fixed_clock)
    service.capture("flag{alpha}", item_id=ITEM_ID)
    rendered = service.render(ITEM_ID)
    assert ITEM_ID in rendered
    assert "flag{alpha}" in rendered
    assert "flag{alpha}" in service.render(ITEM_ID, "flag")
    with pytest.raises(UnknownTemplateError):
        service.render(ITEM_ID, "nope")
    payload = service.export_json()
    other = InboxService(clock=fixed_clock)
    assert other.import_json(payload) == 1
    assert other.get(ITEM_ID).raw == "flag{alpha}"
    assert other.remove(ITEM_ID) is True
    assert other.remove(ITEM_ID) is False
