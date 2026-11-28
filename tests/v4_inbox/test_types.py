"""Tests for immutable capture records and their validation rules."""

from __future__ import annotations

import pytest

from redscribe.v4.inbox.types import (
    MAX_RAW_LENGTH,
    MAX_TAGS,
    CaptureDraft,
    CaptureItem,
    CaptureSource,
    TriageState,
    compute_content_hash,
    normalize_raw,
    normalize_tag,
    normalize_tags,
    validate_confidence,
    validate_timestamp,
)

ITEM_ID = "11111111-2222-3333-4444-555555555555"
ITEM_ID_2 = "22222222-3333-4444-5555-666666666666"
TIMESTAMP = "2026-01-02T03:04:05.000Z"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("manual", CaptureSource.MANUAL),
        (" LINK ", CaptureSource.LINK),
        ("Snippet", CaptureSource.SNIPPET),
        ("flag", CaptureSource.FLAG),
        ("clipboard", CaptureSource.CLIPBOARD),
    ],
)
def test_capture_source_parse(value: str, expected: CaptureSource) -> None:
    assert CaptureSource.parse(value) is expected


@pytest.mark.parametrize("value", ["", "pasted", "https://example.test"])
def test_capture_source_parse_rejects_unknown(value: str) -> None:
    with pytest.raises(ValueError, match="Unknown capture source"):
        CaptureSource.parse(value)


def test_capture_source_properties() -> None:
    assert CaptureSource.MANUAL.label == "Manual"
    assert CaptureSource.CLIPBOARD.auto_detected is False
    assert all(
        source.auto_detected for source in CaptureSource if source is not CaptureSource.CLIPBOARD
    )
    assert len(CaptureSource) == 5


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("untriaged", TriageState.UNTRIAGED),
        (" ACCEPTED ", TriageState.ACCEPTED),
        ("Rejected", TriageState.REJECTED),
        ("archived", TriageState.ARCHIVED),
    ],
)
def test_triage_state_parse(value: str, expected: TriageState) -> None:
    assert TriageState.parse(value) is expected


def test_triage_state_properties() -> None:
    with pytest.raises(ValueError, match="Unknown triage state"):
        TriageState.parse("deleted")
    assert TriageState.UNTRIAGED.label == "Untriaged"
    assert TriageState.UNTRIAGED.is_terminal is False
    assert TriageState.ACCEPTED.is_terminal is True
    assert TriageState.REJECTED.is_terminal is True
    assert TriageState.ARCHIVED.is_terminal is True


def test_normalize_raw_folds_whitespace() -> None:
    assert normalize_raw("  hello\t\nworld  ") == "hello world"
    assert normalize_raw("a\r\nb") == "a b"


@pytest.mark.parametrize("raw", ["", "   ", "\n\t  "])
def test_normalize_raw_rejects_blank(raw: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        normalize_raw(raw)


def test_normalize_raw_rejects_oversize() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        normalize_raw("a" * (MAX_RAW_LENGTH + 1))


def test_normalize_raw_rejects_non_string() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        normalize_raw(42)  # type: ignore[arg-type]


def test_content_hash_is_stable_and_normalized() -> None:
    first = compute_content_hash("  Hello   World ")
    second = compute_content_hash("hello world")
    assert first == second
    assert len(first) == 64
    assert first == compute_content_hash("hello world")
    assert first != compute_content_hash("hello  world!")


def test_content_hash_changes_with_text() -> None:
    assert compute_content_hash("alpha") != compute_content_hash("beta")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("TODO", "todo"),
        (" Deep Work ", "deep-work"),
        ("cve-2026-1234", "cve-2026-1234"),
        ("web/http", "web/http"),
    ],
)
def test_normalize_tag(value: str, expected: str) -> None:
    assert normalize_tag(value) == expected


@pytest.mark.parametrize("value", ["", "-bad", "9lead", "!!!", "bad!tag"])
def test_normalize_tag_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid tag"):
        normalize_tag(value)


def test_normalize_tag_rejects_non_string() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        normalize_tag(7)  # type: ignore[arg-type]


def test_normalize_tags_sorts_and_deduplicates() -> None:
    assert normalize_tags(["Zebra", "alpha", "ALPHA", "Beta"]) == ("alpha", "beta", "zebra")


def test_normalize_tags_rejects_single_string() -> None:
    with pytest.raises(TypeError, match="not a single string"):
        normalize_tags("solo")  # type: ignore[arg-type]


def test_normalize_tags_enforces_limit() -> None:
    tags = [f"tag-{index}" for index in range(MAX_TAGS + 1)]
    with pytest.raises(ValueError, match="at most"):
        normalize_tags(tags)


@pytest.mark.parametrize("value", [0.0, 0.5, 1, 0.999])
def test_validate_confidence_accepts_range(value: float) -> None:
    assert validate_confidence(value) == float(value)


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan")])
def test_validate_confidence_rejects_out_of_range(value: float) -> None:
    with pytest.raises(ValueError, match="between"):
        validate_confidence(value)


def test_validate_confidence_rejects_bool_and_string() -> None:
    with pytest.raises(TypeError, match="must be a number"):
        validate_confidence(True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a number"):
        validate_confidence("0.5")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    ["2026-01-02T03:04:05Z", "2026-01-02T03:04:05+00:00", " 2026-01-02T03:04:05.123Z "],
)
def test_validate_timestamp_accepts_aware_values(value: str) -> None:
    assert validate_timestamp(value) == value.strip()


@pytest.mark.parametrize("value", ["", "2026-01-02", "not-a-date", "2026-13-45T00:00:00Z"])
def test_validate_timestamp_rejects_bad_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_timestamp(value)


def test_capture_item_create_derives_fields() -> None:
    item = CaptureItem.create(
        raw="  flag{alpha}  ",
        source=CaptureSource.FLAG,
        tags=["CTF", "alpha"],
        confidence=0.9,
        created_at=TIMESTAMP,
        item_id=ITEM_ID,
    )
    assert item.id == ITEM_ID
    assert item.raw == "flag{alpha}"
    assert item.tags == ("alpha", "ctf")
    assert item.content_hash == compute_content_hash("flag{alpha}")
    assert item.state is TriageState.UNTRIAGED
    assert item.created_at == TIMESTAMP


def test_capture_item_create_generates_id_and_timestamp() -> None:
    item = CaptureItem.create(raw="plain note")
    assert len(item.id) == 36
    assert item.source is CaptureSource.MANUAL
    assert item.confidence == 0.5


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "AAAAAAAA-2222-3333-4444-555555555555"])
def test_capture_item_rejects_bad_id(bad_id: str) -> None:
    with pytest.raises(ValueError, match="Invalid capture id"):
        CaptureItem.create(raw="note", item_id=bad_id)


def test_capture_item_treats_empty_id_as_unspecified() -> None:
    item = CaptureItem.create(raw="note", item_id="")
    assert len(item.id) == 36


def test_capture_item_rejects_mismatched_hash() -> None:
    with pytest.raises(ValueError, match="does not match"):
        CaptureItem(
            id=ITEM_ID,
            raw="note",
            source=CaptureSource.MANUAL,
            state=TriageState.UNTRIAGED,
            tags=(),
            confidence=0.5,
            created_at=TIMESTAMP,
            content_hash="0" * 64,
        )


def test_capture_item_rejects_bad_hash_shape() -> None:
    with pytest.raises(ValueError, match="64 lowercase hex"):
        CaptureItem(
            id=ITEM_ID,
            raw="note",
            source=CaptureSource.MANUAL,
            state=TriageState.UNTRIAGED,
            tags=(),
            confidence=0.5,
            created_at=TIMESTAMP,
            content_hash="ABC",
        )


def test_capture_item_rejects_wrong_enum_types() -> None:
    with pytest.raises(TypeError, match="source must be"):
        CaptureItem.create(raw="note", source="manual")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="state must be"):
        CaptureItem.create(raw="note", state="accepted")  # type: ignore[arg-type]


def test_capture_item_helpers() -> None:
    item = CaptureItem.create(raw="note", tags=["alpha"], item_id=ITEM_ID)
    assert item.has_tag("ALPHA") is True
    assert item.has_tag("beta") is False
    assert item.tag_line == "#alpha"
    assert item.is_triaged is False
    assert item.with_state(TriageState.ACCEPTED).is_triaged is True
    assert item.with_state(TriageState.ACCEPTED).id == ITEM_ID
    assert item.with_tags(["Beta", "alpha"]).tags == ("alpha", "beta")


def test_capture_item_roundtrip() -> None:
    item = CaptureItem.create(
        raw="https://example.test/path",
        source=CaptureSource.LINK,
        tags=["web"],
        confidence=0.86,
        created_at=TIMESTAMP,
        item_id=ITEM_ID,
    )
    data = item.to_dict()
    assert data["source"] == "link"
    assert data["state"] == "untriaged"
    assert data["tags"] == ["web"]
    restored = CaptureItem.from_dict(data)
    assert restored == item


def test_capture_item_from_dict_defaults() -> None:
    item = CaptureItem.from_dict({"id": ITEM_ID_2, "raw": "fresh", "source": "manual"})
    assert item.state is TriageState.UNTRIAGED
    assert item.tags == ()
    assert item.content_hash == compute_content_hash("fresh")
    assert item.created_at == validate_timestamp(item.created_at)


def test_capture_item_from_dict_rejects_conflict() -> None:
    data = CaptureItem.create(raw="note", item_id=ITEM_ID).to_dict()
    data["content_hash"] = "f" * 64
    with pytest.raises(ValueError, match="does not match"):
        CaptureItem.from_dict(data)


def test_capture_draft_validation_and_materialization() -> None:
    draft = CaptureDraft(
        raw="  note ",
        source=CaptureSource.SNIPPET,
        tags=["Code"],
        confidence=0.7,
        urls=("https://example.test",),
        flags=(),
    )
    assert draft.raw == "note"
    assert "1 link(s)" in draft.summary
    item = draft.to_item(item_id=ITEM_ID, created_at=TIMESTAMP)
    assert item.source is CaptureSource.SNIPPET
    assert item.raw == draft.raw
    assert item.tags == ("code",)


def test_capture_draft_rejects_invalid_values() -> None:
    with pytest.raises(TypeError, match="source must be"):
        CaptureDraft("note", "manual", (), 0.5, (), ())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="between"):
        CaptureDraft("note", CaptureSource.MANUAL, (), 2.0, (), ())
