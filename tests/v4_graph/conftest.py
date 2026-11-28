"""Shared, deterministic fixtures for the v4 graph workbench tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from redscribe.v4.contracts import EntityKind, EntityLink, EntityRef
from redscribe.v4.graph_v4.service import GraphBuilder
from redscribe.v4.graph_v4.types import GraphData

NODE_A = "11111111-1111-4111-8111-111111111111"
NODE_B = "22222222-2222-4222-8222-222222222222"
NODE_C = "33333333-3333-4333-8333-333333333333"
NODE_D = "44444444-4444-4444-8444-444444444444"
NODE_E = "55555555-5555-4555-8555-555555555555"
NODE_F = "66666666-6666-4666-8666-666666666666"
NODE_G = "77777777-7777-4777-8777-777777777777"


def make_refs() -> tuple[EntityRef, ...]:
    return (
        EntityRef(kind=EntityKind.NOTE, id=NODE_A, label="Alpha note"),
        EntityRef(kind=EntityKind.TARGET, id=NODE_B, label="Beta target"),
        EntityRef(kind=EntityKind.FINDING, id=NODE_C, label="Gamma finding"),
        EntityRef(kind=EntityKind.EVIDENCE, id=NODE_D, label="Delta evidence"),
        EntityRef(kind=EntityKind.NOTE, id=NODE_E, label="Epsilon note"),
        EntityRef(kind=EntityKind.TARGET, id=NODE_F, label="Zed host"),
        EntityRef(kind=EntityKind.NOTE, id=NODE_G, label="Eta note"),
    )


def make_links() -> tuple[EntityLink, ...]:
    refs = make_refs()
    return (
        EntityLink(source=refs[0], target=refs[1], relation="linked_to", weight=0.9),
        EntityLink(source=refs[1], target=refs[2], relation="derived_from", weight=0.7),
        EntityLink(source=refs[2], target=refs[3], relation="supports", weight=0.6),
        EntityLink(source=refs[0], target=refs[2], relation="mentions", weight=0.4),
        EntityLink(source=refs[0], target=refs[1], relation="linked_to", weight=0.5),
        EntityLink(source=refs[5], target=refs[6], relation="related_to", weight=0.8),
    )


@pytest.fixture
def sample_builder() -> GraphBuilder:
    builder = GraphBuilder()
    builder.add_refs(make_refs())
    builder.add_links(make_links())
    return builder


@pytest.fixture
def sample_data(sample_builder: GraphBuilder) -> GraphData:
    return sample_builder.build()


@pytest.fixture
def fixed_clock() -> Callable[[], str]:
    counter = iter(range(1, 1000))

    def clock() -> str:
        return f"2026-01-01T00:00:{next(counter):02d}Z"

    return clock


@pytest.fixture
def fixed_id() -> Callable[[], str]:
    counter = iter(range(1, 1000))

    def identifier() -> str:
        return f"fixed-id-{next(counter)}"

    return identifier
