"""Deterministic builders shared by the v4 block editor tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from itertools import cycle

from redscribe.v4.blocks_pro.types import (
    Block,
    BlockDocument,
    BlockKind,
    InlineMark,
    new_block,
    new_document,
)


def id_factory(*values: str) -> Callable[[], str]:
    """Return a factory that yields the supplied identifiers in order."""
    iterator: Iterator[str] = cycle(values)

    def factory() -> str:
        return next(iterator)

    return factory


def clock_factory(*values: str) -> Callable[[], str]:
    """Return a clock that yields the supplied ISO timestamps in order."""
    iterator: Iterator[str] = cycle(values)

    def clock() -> str:
        return next(iterator)

    return clock


def make_block(
    identifier: str,
    kind: BlockKind = BlockKind.PARAGRAPH,
    text: str = "",
    *,
    level: int = 1,
    language: str = "",
    items: Sequence[str] = (),
    attrs: dict[str, str] | None = None,
) -> Block:
    return Block(
        id=identifier,
        kind=kind,
        text=text,
        level=level,
        language=language,
        items=tuple(items),
        attrs=tuple(sorted((attrs or {}).items())),
    )


def make_document(
    identifier: str = "doc1",
    title: str = "Test document",
    blocks: Sequence[Block] = (),
) -> BlockDocument:
    return BlockDocument(identifier, title, tuple(blocks))


def sample_blocks() -> tuple[Block, ...]:
    """One well-formed block of every supported kind."""
    return (
        make_block("b1", BlockKind.PARAGRAPH, "A plain paragraph with detail."),
        make_block("b2", BlockKind.HEADING, "Section heading", level=2),
        make_block("b3", BlockKind.CODE, "print('hello')", language="python"),
        make_block(
            "b4",
            BlockKind.LIST,
            items=("first", "second"),
            attrs={"style": "bullet"},
        ),
        make_block("b5", BlockKind.QUOTE, "Quoted line one\nQuoted line two"),
        make_block(
            "b6",
            BlockKind.TABLE,
            items=("alpha|1", "beta|2"),
            attrs={"header": "Name|Value"},
        ),
        make_block("b7", BlockKind.DIVIDER),
    )


def sample_document() -> BlockDocument:
    return make_document("doc1", "All block kinds", sample_blocks())


def simple_document() -> BlockDocument:
    return make_document(
        "doc1",
        "Notes",
        (
            make_block("a", text="alpha"),
            make_block("b", text="bravo"),
            make_block("c", text="charlie"),
        ),
    )


def mark_block(
    identifier: str,
    mark: InlineMark,
    target: str,
    href: str = "",
) -> Block:
    text = f"Before {target} after"
    return make_block(identifier, BlockKind.PARAGRAPH, mark.apply(text, target, href))


def generated_document(seed: int = 3) -> BlockDocument:
    factory = id_factory(*(f"gen{i}" for i in range(seed)))
    blocks = tuple(
        new_block(BlockKind.PARAGRAPH, f"line {index}", id_factory=factory) for index in range(seed)
    )
    return new_document("generated", blocks, id_factory=id_factory("generated"))
