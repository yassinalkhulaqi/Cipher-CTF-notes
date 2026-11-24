"""Deterministic scoring and grouping for command-bar results."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from redscribe.v3.commands.context import ContextResolver
from redscribe.v3.commands.types import (
    CommandContext,
    CommandGroup,
    CommandGroupResult,
    CommandHit,
    CommandSpec,
)
from redscribe.v3.commands.usage import UsageModel

_WEIGHTS: dict[str, float] = {
    "exact": 6.0,
    "prefix": 3.0,
    "word": 2.0,
    "contains": 1.2,
    "subsequence": 0.8,
    "keyword": 1.6,
    "alias": 2.4,
    "group": 0.5,
    "context": 2.0,
    "usage": 2.2,
}


def normalize(text: str) -> str:
    """Normalize text for case-insensitive matching."""
    return " ".join(text.strip().casefold().split())


def tokenize_query(query: str) -> tuple[str, ...]:
    """Split a normalized query into word tokens."""
    return tuple(re.findall(r"[a-z0-9]+", normalize(query)))


def subsequence_ratio(query: str, text: str) -> float:
    """Return how much of ``query`` appears as an ordered subsequence."""
    needle = normalize(query).replace(" ", "")
    haystack = normalize(text).replace(" ", "")
    if not needle:
        return 0.0
    if not haystack:
        return 0.0
    cursor = 0
    matched = 0
    for char in haystack:
        if cursor < len(needle) and char == needle[cursor]:
            matched += 1
            cursor += 1
    return matched / len(needle)


@dataclass(frozen=True, slots=True)
class CommandScore:
    """Breakdown of why a command matched a query."""

    command_id: str
    exact: float = 0.0
    prefix: float = 0.0
    word: float = 0.0
    contains: float = 0.0
    subsequence: float = 0.0
    keyword: float = 0.0
    alias: float = 0.0
    group: float = 0.0
    context: float = 0.0
    usage: float = 0.0
    signals: tuple[str, ...] = ()
    matched_text: str = ""

    @property
    def total(self) -> float:
        """Weighted sum of all signals."""
        return round(
            self.exact * _WEIGHTS["exact"]
            + self.prefix * _WEIGHTS["prefix"]
            + self.word * _WEIGHTS["word"]
            + self.contains * _WEIGHTS["contains"]
            + self.subsequence * _WEIGHTS["subsequence"]
            + self.keyword * _WEIGHTS["keyword"]
            + self.alias * _WEIGHTS["alias"]
            + self.group * _WEIGHTS["group"]
            + self.context * _WEIGHTS["context"]
            + self.usage * _WEIGHTS["usage"],
            4,
        )

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation."""
        return {
            "command_id": self.command_id,
            "total": self.total,
            "signals": list(self.signals),
            "matched_text": self.matched_text,
        }


@dataclass(slots=True)
class CommandScorer:
    """Score commands against a query, context, and usage history."""

    resolver: ContextResolver = field(default_factory=ContextResolver)
    usage: UsageModel | None = None
    now: float = 0.0

    def score(
        self,
        query: str,
        spec: CommandSpec,
        context: CommandContext,
        *,
        now: float | None = None,
    ) -> CommandScore:
        """Score one command; zero means the query did not match."""
        needle = normalize(query)
        title = normalize(spec.title)
        command_id = normalize(spec.id)
        group = normalize(spec.group.value)
        signals: list[str] = []
        exact = prefix = word = contains = subseq = keyword = alias = group_score = 0.0
        matched = ""
        if needle:
            for candidate, label in (
                (title, "title"),
                (command_id, "id"),
                (spec.id.split(".")[-1], "action"),
            ):
                if candidate == needle:
                    exact = 1.0
                    matched = candidate
                    signals.append(f"exact:{label}")
                    break
                if candidate.startswith(needle):
                    prefix = max(prefix, 1.0)
                    matched = matched or candidate
                    signals.append(f"prefix:{label}")
                elif needle in candidate:
                    contains = max(contains, 1.0)
                    matched = matched or candidate
                    signals.append(f"contains:{label}")
                if label in ("title", "action"):
                    subseq = max(subseq, subsequence_ratio(needle, candidate))
            tokens = tokenize_query(query)
            for token in tokens:
                if token in title.split() or token in command_id.replace(".", " ").split():
                    word += 1.0
                    signals.append(f"word:{token}")
            for term in spec.keywords:
                if needle and (term.startswith(needle) or needle in term):
                    keyword = max(keyword, 1.0)
                    signals.append(f"keyword:{term}")
            for candidate in spec.aliases:
                if needle and (
                    normalize(candidate) == needle or normalize(candidate).startswith(needle)
                ):
                    alias = 1.0
                    matched = matched or normalize(candidate)
                    signals.append(f"alias:{candidate}")
            if any(needle in token or token.startswith(needle) for token in group.split("_")):
                group_score = 1.0
                signals.append("group")
        else:
            subseq = 0.0
        if not signals and needle and subseq < 0.7:
            return CommandScore(command_id=spec.id, matched_text=matched)
        if subseq >= 0.7:
            signals.append("subsequence")
        context_score = self.resolver.weight(spec, context)
        if context_score:
            signals.append("context")
        usage_score = self.usage.score(spec.id, now or self.now) if self.usage is not None else 0.0
        if usage_score > 0.15:
            signals.append("frequent")
        return CommandScore(
            command_id=spec.id,
            exact=exact,
            prefix=prefix,
            word=min(word, 2.0),
            contains=contains,
            subsequence=subseq if subseq >= 0.7 else 0.0,
            keyword=keyword,
            alias=alias,
            group=group_score,
            context=context_score,
            usage=usage_score,
            signals=tuple(dict.fromkeys(signals)),
            matched_text=matched,
        )


def _hit(spec: CommandSpec, score: CommandScore) -> CommandHit:
    """Convert a score breakdown into a ranked hit."""
    return CommandHit(
        command=spec, score=score.total, signals=score.signals, matched_text=score.matched_text
    )


def rank_commands(
    query: str,
    specs: Iterable[CommandSpec],
    context: CommandContext,
    *,
    resolver: ContextResolver | None = None,
    usage: UsageModel | None = None,
    limit: int = 12,
    now: float = 0.0,
) -> tuple[CommandHit, ...]:
    """Rank available commands for the current query and context."""
    if limit < 1:
        raise ValueError("limit must be positive")
    active_resolver = resolver or ContextResolver()
    scorer = CommandScorer(resolver=active_resolver, usage=usage, now=now)
    scored: list[CommandHit] = []
    for spec in specs:
        if not active_resolver.is_available(spec, context):
            continue
        result = scorer.score(query, spec, context, now=now)
        if result.total > 0 or not query.strip():
            scored.append(_hit(spec, result))
    scored.sort(
        key=lambda hit: (
            -hit.score,
            hit.command.group.order,
            hit.command.order,
            hit.command.id,
        )
    )
    return tuple(scored[:limit])


def group_hits(
    hits: Iterable[CommandHit], *, limit_per_group: int = 6
) -> tuple[CommandGroupResult, ...]:
    """Group ranked hits into sections for the palette UI."""
    if limit_per_group < 1:
        raise ValueError("limit_per_group must be positive")
    buckets: dict[CommandGroup, list[CommandHit]] = {}
    for hit in hits:
        buckets.setdefault(hit.command.group, []).append(hit)
    results: list[CommandGroupResult] = []
    for group in sorted(buckets, key=lambda item: item.order):
        section = tuple(buckets[group][:limit_per_group])
        results.append(CommandGroupResult(group=group, hits=section))
    return tuple(results)
