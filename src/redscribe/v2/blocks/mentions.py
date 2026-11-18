"""Mention parsing, rendering, and block-level reference indices."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v2.blocks.constants import (
    MAX_MENTION_LABEL_LENGTH,
    MAX_MENTION_TARGET_LENGTH,
    MAX_SEARCH_RESULTS,
)
from redscribe.v2.blocks.model import Block, BlockDocument, Mention
from redscribe.v2.blocks.types import MentionKind

_MENTION_RE = re.compile(
    r"@\[(?P<label>[^\]\n]{1," + str(MAX_MENTION_LABEL_LENGTH) + r"})\]"
    r"\((?P<kind>[a-z][a-z0-9_-]{0,31}):(?P<target>[^\s)]{1,"
    + str(MAX_MENTION_TARGET_LENGTH)
    + r"})\)",
    re.UNICODE,
)


def mention_pattern() -> re.Pattern[str]:
    """Return the compiled mention token pattern."""
    return _MENTION_RE


def extract_mentions(text: str, *, block_id: str = "") -> tuple[Mention, ...]:
    """Extract all valid mention tokens along with their source offsets."""
    mentions: list[Mention] = []
    for match in _MENTION_RE.finditer(text):
        try:
            kind = MentionKind(match.group("kind"))
        except ValueError:
            continue
        target = match.group("target").strip()
        label = match.group("label").strip()
        if not target or not label:
            continue
        mentions.append(
            Mention(
                kind=kind,
                target=target,
                label=label,
                start=match.start(),
                end=match.end(),
                block_id=block_id,
            )
        )
    return tuple(mentions)


def refresh_block_mentions(block: Block) -> Block:
    """Return a block whose mention offsets match its current text."""
    return block.with_changes(mentions=extract_mentions(block.text, block_id=block.id))


def render_mention(kind: MentionKind | str, target: str, label: str) -> str:
    """Render one mention token from its components."""
    name = kind.value if isinstance(kind, MentionKind) else str(kind)
    return f"@[{label}]({name}:{target})"


def replace_mention_targets(
    text: str,
    replacements: Mapping[tuple[str, str], str],
) -> str:
    """Replace mention targets using ``(kind, target)`` lookup keys."""
    pieces: list[str] = []
    cursor = 0
    for match in _MENTION_RE.finditer(text):
        pieces.append(text[cursor : match.start()])
        key = (match.group("kind"), match.group("target"))
        replacement = replacements.get(key)
        if replacement is None:
            pieces.append(match.group(0))
        else:
            pieces.append(render_mention(key[0], replacement, match.group("label")))
        cursor = match.end()
    pieces.append(text[cursor:])
    return "".join(pieces)


def mention_targets(mentions: Iterable[Mention], *, kind: MentionKind | None = None) -> list[str]:
    """Return deduplicated mention targets in first-seen order."""
    result: list[str] = []
    seen: set[tuple[str, str]] = set()
    for mention in mentions:
        if kind is not None and mention.kind is not kind:
            continue
        key = (mention.kind.value, mention.target)
        if key in seen:
            continue
        seen.add(key)
        result.append(mention.target)
    return result


def document_mentions(document: BlockDocument) -> tuple[Mention, ...]:
    """Return all mentions stored on a document's blocks."""
    return tuple(mention for block in document.blocks for mention in block.mentions)


@dataclass(frozen=True, slots=True)
class MentionHit:
    """One indexed mention with its owning document and block."""

    document_id: str
    block_id: str
    mention: Mention

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            **self.mention.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class MentionSuggestion:
    """A candidate mention target returned by autocomplete."""

    kind: str
    target: str
    label: str
    score: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target": self.target,
            "label": self.label,
            "score": self.score,
        }


def _rank(candidate: str, query: str) -> int:
    haystack = candidate.casefold()
    needle = query.strip().casefold()
    if not needle:
        return 1
    if haystack == needle:
        return 100
    if haystack.startswith(needle):
        return 80 - min(20, len(haystack) - len(needle))
    if needle in haystack:
        return 50 - min(20, haystack.index(needle))
    return 0


class MentionIndex:
    """In-memory inverted index over block mentions."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
        self._by_document: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self._labels: dict[tuple[str, str], str] = {}

    def clear(self) -> None:
        """Drop all indexed mentions."""
        self._by_key.clear()
        self._by_document.clear()
        self._labels.clear()

    def add(self, document: BlockDocument) -> int:
        """Index a document and return the number of mentions added."""
        self.remove(document.id)
        count = 0
        for block in document.blocks:
            for mention in block.mentions:
                key = (mention.kind.value, mention.target)
                owner = (document.id, block.id)
                self._by_key[key].add(owner)
                self._by_document[document.id].add(owner)
                self._labels.setdefault(key, mention.label)
                count += 1
        return count

    def remove(self, document_id: str) -> bool:
        """Remove a document from the index."""
        owners = self._by_document.pop(document_id, None)
        if owners is None:
            return False
        for owner in owners:
            for key, values in list(self._by_key.items()):
                values.discard(owner)
                if not values:
                    del self._by_key[key]
                    self._labels.pop(key, None)
        return True

    def replace(self, document: BlockDocument) -> int:
        """Atomically replace a document's indexed mentions."""
        return self.add(document)

    def for_target(
        self,
        target: str,
        *,
        kind: MentionKind | str | None = None,
    ) -> list[MentionHit]:
        """Return mentions pointing at ``target``."""
        kind_value = kind.value if isinstance(kind, MentionKind) else kind
        hits: list[MentionHit] = []
        for (stored_kind, stored_target), owners in self._by_key.items():
            if stored_target.casefold() != target.casefold():
                continue
            if kind_value is not None and stored_kind != kind_value:
                continue
            for document_id, block_id in sorted(owners):
                mention = self._mention_for(stored_kind, stored_target, document_id, block_id)
                if mention is not None:
                    hits.append(MentionHit(document_id, block_id, mention))
        hits.sort(key=lambda hit: (hit.document_id, hit.block_id, hit.mention.start))
        return hits

    def for_kind(self, kind: MentionKind | str) -> list[MentionHit]:
        """Return all mentions of one namespace."""
        kind_value = kind.value if isinstance(kind, MentionKind) else kind
        hits: list[MentionHit] = []
        for (stored_kind, stored_target), owners in self._by_key.items():
            if stored_kind != kind_value:
                continue
            for document_id, block_id in sorted(owners):
                mention = self._mention_for(stored_kind, stored_target, document_id, block_id)
                if mention is not None:
                    hits.append(MentionHit(document_id, block_id, mention))
        return hits

    def all(self) -> list[MentionHit]:
        """Return every indexed mention in deterministic order."""
        hits: list[MentionHit] = []
        for (kind, target), owners in sorted(self._by_key.items()):
            for document_id, block_id in sorted(owners):
                mention = self._mention_for(kind, target, document_id, block_id)
                if mention is not None:
                    hits.append(MentionHit(document_id, block_id, mention))
        return hits

    def suggestions(
        self,
        query: str,
        *,
        kind: MentionKind | str | None = None,
        limit: int = 12,
    ) -> list[MentionSuggestion]:
        """Rank indexed targets for mention autocomplete."""
        kind_value = kind.value if isinstance(kind, MentionKind) else kind
        candidates: list[MentionSuggestion] = []
        for (stored_kind, target), label in self._labels.items():
            if kind_value is not None and stored_kind != kind_value:
                continue
            score = max(_rank(target, query), _rank(label, query))
            if score > 0:
                candidates.append(MentionSuggestion(stored_kind, target, label, score))
        candidates.sort(key=lambda item: (-item.score, item.kind, item.target, item.label))
        return candidates[: max(0, min(limit, MAX_SEARCH_RESULTS))]

    def size(self) -> int:
        """Return the number of unique indexed mention targets."""
        return len(self._by_key)

    def _mention_for(
        self,
        kind: str,
        target: str,
        document_id: str,
        block_id: str,
    ) -> Mention | None:
        try:
            mention_kind = MentionKind(kind)
        except ValueError:
            return None
        return Mention(
            kind=mention_kind,
            target=target,
            label=self._labels.get((kind, target), target),
            start=0,
            end=0,
            block_id=block_id,
        )


def build_mention_index(documents: Sequence[BlockDocument]) -> MentionIndex:
    """Build an index from a sequence of documents."""
    index = MentionIndex()
    for document in documents:
        index.add(document)
    return index
