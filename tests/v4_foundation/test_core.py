from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from redscribe.v4.clock import Clock
from redscribe.v4.migrations_v4 import (
    DEFAULT_CHAIN,
    MIGRATIONS,
    SCHEMA_VERSION,
    Column,
    Migration,
    MigrationChain,
    MigrationError,
)
from redscribe.v4.pagination import (
    Cursor,
    PaginationError,
    apply_cursor,
    etag_matches,
    paginate,
    weak_etag,
)
from redscribe.v4.preferences import (
    SUPPORTED_LOCALES,
    Preferences,
    PreferenceStore,
)


def test_cursor_round_trip() -> None:
    cursor = Cursor(offset=120, sort_key="note-120")
    token = cursor.encode()
    assert Cursor.decode(token) == cursor
    assert token.startswith("v1.")


def test_cursor_rejects_malformed_tokens() -> None:
    for token in ("bad", "x.abc", "v1.!!!!", "v2.@@@"):
        with pytest.raises(PaginationError):
            Cursor.decode(token)
    with pytest.raises(PaginationError):
        Cursor(offset=-1, sort_key="x")


def test_pagination_pages_and_cursor() -> None:
    items = list(range(10))
    first = paginate(items, page=1, page_size=4)
    assert first.items == (0, 1, 2, 3)
    assert first.total == 10
    assert first.has_more
    assert first.etag
    rest = apply_cursor(items, first.next_cursor)
    assert list(rest) == [4, 5, 6, 7, 8, 9]
    last = paginate(items, page=3, page_size=4)
    assert last.items == (8, 9)
    assert not last.has_more


def test_pagination_validation() -> None:
    with pytest.raises(PaginationError):
        paginate([1], page=0)
    with pytest.raises(PaginationError):
        paginate([1], page_size=0)
    with pytest.raises(PaginationError):
        paginate([1], page_size=501)


def test_etag_helpers() -> None:
    tag = weak_etag("payload")
    assert tag.startswith('W/"')
    assert etag_matches(tag, tag)
    assert etag_matches('"abc"', 'W/"abc"')
    assert not etag_matches('"abc"', '"def"')


def test_preferences_defaults_and_validation() -> None:
    prefs = Preferences()
    assert prefs.to_dict()["locale"] == "en"
    assert Preferences.from_dict(prefs.to_dict()) == prefs
    with pytest.raises(ValueError):
        Preferences(theme="neon")
    with pytest.raises(ValueError):
        Preferences(locale="ar")
    with pytest.raises(ValueError):
        Preferences(font_scale=5.0)


def test_preferences_merge_and_dataset() -> None:
    prefs = Preferences()
    merged = prefs.merged({"theme": "graphite", "unknown": "ignored"})
    assert merged.theme == "graphite"
    assert merged.direction == "ltr"
    assert merged.css_dataset["dir"] == "ltr"
    assert len(SUPPORTED_LOCALES) == 7


def test_preference_store_notifications() -> None:
    store = PreferenceStore()
    seen: list[tuple[Preferences, int]] = []
    store.listen(lambda prefs, revision: seen.append((prefs, revision)))
    store.update({"density": "compact"})
    assert store.revision == 1
    assert seen[-1][0].density == "compact"
    store.update({"density": "compact"})
    assert store.revision == 1
    store.reset()
    assert store.revision == 2


def test_migration_declarations() -> None:
    assert SCHEMA_VERSION == 6
    assert len(MIGRATIONS) == 10
    with pytest.raises(MigrationError):
        Column("Bad Name", "TEXT")
    with pytest.raises(MigrationError):
        Column("name", "VARCHAR")
    with pytest.raises(MigrationError):
        Migration(version=0, name="x", table="y")
    with pytest.raises(MigrationError):
        Migration(version=6, name="x", table="Bad Table")


def test_migration_chain_digest_and_apply() -> None:
    chain = MigrationChain()
    assert len(chain.digest) == 64
    assert len(chain.migrations) == 10
    assert chain.apply_from(6) == []
    assert len(chain.apply_from(5)) == 10
    assert chain.table_names() == sorted(chain.table_names())
    manifest = chain.to_manifest()
    assert manifest["schema_version"] == 6
    assert len(manifest["migrations"]) == 10


def test_migration_chain_refuses_unsafe_changes() -> None:
    chain = MigrationChain()
    with pytest.raises(MigrationError):
        chain.apply_from(7)
    with pytest.raises(MigrationError):
        chain.apply_from(4)
    with pytest.raises(MigrationError):
        chain.refuse_downgrade(5)
    with pytest.raises(MigrationError):
        MigrationChain(())
    with pytest.raises(MigrationError):
        MigrationChain((MIGRATIONS[0], MIGRATIONS[0]))


def test_default_chain_is_shared() -> None:
    assert DEFAULT_CHAIN.table_names() == MigrationChain().table_names()


def test_clock_freeze_and_advance() -> None:
    clock = Clock()
    assert not clock.is_frozen
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock.freeze(base)
    assert clock.is_frozen
    assert clock.now() == base
    clock.advance(timedelta(days=1))
    assert clock.now() == base + timedelta(days=1)
    assert clock.iso().endswith("Z")
    clock.unfreeze()
    assert not clock.is_frozen
