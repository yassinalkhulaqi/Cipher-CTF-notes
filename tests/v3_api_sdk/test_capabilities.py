"""Capability negotiation and explicit write opt-in."""

from __future__ import annotations

import pytest

from redscribe.v3.api_sdk.capabilities import CapabilityDecision, CapabilityNegotiator
from redscribe.v3.api_sdk.errors import (
    CapabilityDeniedError,
    ReadOnlyViolationError,
)
from redscribe.v3.capabilities import (
    ALL_CAPABILITIES,
    CAP_EXTENSIONS,
    CAP_FINDINGS,
    Capabilities,
)
from redscribe.v3.config import V3Config


def _negotiator(enabled: frozenset[str]) -> CapabilityNegotiator:
    return CapabilityNegotiator(capabilities=Capabilities(enabled=enabled))


def test_advertise_and_decide() -> None:
    negotiator = _negotiator(frozenset({CAP_EXTENSIONS}))
    advertised = negotiator.advertise()
    assert set(advertised) == set(ALL_CAPABILITIES)
    assert advertised[CAP_EXTENSIONS] is True
    assert advertised[CAP_FINDINGS] is False
    allowed = negotiator.decide(CAP_EXTENSIONS, required_for="manifest")
    assert allowed.granted
    assert allowed.required_for == "manifest"
    assert allowed.as_dict()["source"] == "negotiation"
    denied = negotiator.decide(CAP_FINDINGS)
    assert not denied.granted
    assert isinstance(denied, CapabilityDecision)


def test_unknown_capability_is_denied() -> None:
    negotiator = _negotiator(frozenset(ALL_CAPABILITIES))
    decision = negotiator.decide("telepathy")
    assert not decision.granted
    assert decision.reason == "unknown capability"
    assert decision.source == "catalog"


def test_negotiate_sorts_and_deduplicates() -> None:
    negotiator = _negotiator(frozenset({CAP_EXTENSIONS, CAP_FINDINGS}))
    decisions = negotiator.negotiate(
        [CAP_FINDINGS, CAP_EXTENSIONS, CAP_FINDINGS], required_for="script"
    )
    assert [item.name for item in decisions] == sorted({CAP_EXTENSIONS, CAP_FINDINGS})
    assert all(item.required_for == "script" for item in decisions)


def test_require_raises_on_disabled_capability() -> None:
    negotiator = _negotiator(frozenset())
    with pytest.raises(CapabilityDeniedError) as excinfo:
        negotiator.require(CAP_EXTENSIONS)
    assert excinfo.value.status == 403
    assert excinfo.value.context["capability"] == CAP_EXTENSIONS


def test_missing_returns_disabled_capabilities() -> None:
    negotiator = _negotiator(frozenset({CAP_EXTENSIONS}))
    assert CAP_EXTENSIONS not in negotiator.missing()
    assert CAP_FINDINGS in negotiator.missing()
    assert tuple(sorted(negotiator.missing())) == negotiator.missing()


def test_allow_write_requires_opt_in_first() -> None:
    config = V3Config(allow_extensions=True, enabled_capabilities=(CAP_EXTENSIONS,))
    negotiator = CapabilityNegotiator(config=config)
    with pytest.raises(ReadOnlyViolationError):
        negotiator.allow_write(opt_in=False)
    granted = negotiator.allow_write(opt_in=True)
    assert granted.granted
    assert granted.name == CAP_EXTENSIONS


def test_allow_write_denied_by_configuration() -> None:
    negotiator = CapabilityNegotiator(config=V3Config())
    with pytest.raises(CapabilityDeniedError) as excinfo:
        negotiator.allow_write(opt_in=True)
    assert excinfo.value.field == "allow_extensions"


def test_allow_write_denied_by_capability() -> None:
    config = V3Config(allow_extensions=True, enabled_capabilities=(CAP_FINDINGS,))
    negotiator = CapabilityNegotiator(config=config)
    with pytest.raises(CapabilityDeniedError) as excinfo:
        negotiator.allow_write(opt_in=True)
    assert excinfo.value.field == "capability"


def test_negotiator_summary() -> None:
    negotiator = _negotiator(frozenset({CAP_EXTENSIONS}))
    summary = negotiator.as_dict()
    assert summary["allow_extensions"] is False
    assert summary["offline_only"] is True
    assert CAP_EXTENSIONS in summary["granted"]
    assert CAP_FINDINGS in summary["denied"]
