"""Tests for V3 foundation configuration, capabilities, and clock helpers."""

from __future__ import annotations

import pytest

from redscribe.v3 import VERSION
from redscribe.v3.capabilities import (
    ALL_CAPABILITIES,
    Capabilities,
    CapabilityError,
)
from redscribe.v3.clock import (
    FixedClock,
    SystemClock,
    epoch_start,
    iso_from_timestamp,
    timestamp_from_iso,
)
from redscribe.v3.config import V3Config, default_config
from redscribe.v3.entities.validation import (
    check_metadata,
    clean_text,
    normalize_tags,
    optional_string,
    require_number,
    require_string,
)


def test_version_and_config() -> None:
    assert VERSION.startswith("3.")
    assert default_config.api_version == "3.0"
    assert default_config.schema_version == 5
    assert default_config.offline_only is True
    assert default_config.as_dict()["page_size"] == 50
    with pytest.raises(ValueError):
        V3Config(page_size=0)
    with pytest.raises(ValueError):
        V3Config(enabled_capabilities=("bogus",))


def test_capabilities() -> None:
    capabilities = Capabilities()
    assert capabilities.has("findings")
    assert capabilities.missing() == ()
    reduced = capabilities.remove("findings")
    assert reduced.has("findings") is False
    assert reduced.missing() == ("findings",)
    with pytest.raises(CapabilityError):
        reduced.require("findings")
    assert len(ALL_CAPABILITIES) == 14
    assert capabilities.as_dict()["encryption"] is True


def test_clocks() -> None:
    fixed = FixedClock(start=100.0, step=2.0)
    assert fixed.now_timestamp() == 100.0
    assert fixed.now_timestamp() == 102.0
    fixed.advance(10.0)
    assert fixed.now_timestamp() == 114.0
    assert fixed.now_iso().endswith("Z")
    assert SystemClock().now_timestamp() > 0
    assert SystemClock().now_iso().endswith("Z")


def test_timestamp_helpers() -> None:
    assert epoch_start() > 0
    iso = iso_from_timestamp(0.0)
    assert iso.startswith("1970-01-01")
    assert timestamp_from_iso(iso) == 0.0
    with pytest.raises(ValueError):
        timestamp_from_iso("2020-01-01T00:00:00")


def test_entity_validation_helpers() -> None:
    assert clean_text("  a   b ") == "a b"
    with pytest.raises(ValueError):
        clean_text("x" * 241)
    assert normalize_tags([" Web ", "#RECON", "web"]) == ("recon", "web")
    with pytest.raises(ValueError):
        normalize_tags(["bad tag"])
    assert require_string({"title": "ok"}, "title") == "ok"
    with pytest.raises(ValueError):
        require_string({}, "title")
    assert optional_string({}, "summary", default="none") == "none"
    assert require_number({"score": 5}, "score") == 5.0
    with pytest.raises(ValueError):
        require_number({"score": -1}, "score")
    assert check_metadata({"a": 1, "b": [1, 2]}) == {"a": 1, "b": [1, 2]}
    with pytest.raises(ValueError):
        check_metadata({"bad": object()})
