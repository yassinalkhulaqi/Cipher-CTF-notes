"""Fuzzy command completion and suggestion ranking."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from redscribe.domain.fuzzy import fold_key, fuzzy_score, token_aware_score
from redscribe.v2.search.commands.catalog import CommandCatalog, commands_by_prefix
from redscribe.v2.search.commands.grammar import command_context
from redscribe.v2.search.commands.models import (
    CommandSpec,
    CommandSuggestion,
    ParsedCommand,
    SuggestionResult,
)
from redscribe.v2.search.models import SavedQuery


def _score(prefix: str, candidate: str) -> float:
    value = fold_key(candidate)
    needle = fold_key(prefix)
    if not needle:
        return 1.0
    score = 0.0
    if value.startswith(needle):
        score += 100.0 + max(0, 12 - len(needle))
    elif needle in value:
        score += 70.0
    exact = fuzzy_score(needle, value)
    if exact is not None:
        score += min(exact, 60) / 3.0
    token_score = token_aware_score(needle, value)
    if token_score is not None:
        score += min(token_score, 90) / 4.0
    if len(value) < len(needle) - 3:
        score -= 10.0
    return score


def _completion_span(text: str, cursor: int) -> tuple[int, int]:
    bounded = max(0, min(cursor, len(text)))
    start = bounded
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    return start, bounded


def suggest_commands(
    text: str,
    catalog: CommandCatalog,
    *,
    saved: Iterable[SavedQuery] = (),
    limit: int = 8,
) -> tuple[CommandSuggestion, ...]:
    """Rank command and saved-query suggestions for a command prefix."""
    span_start, span_end = _completion_span(text, len(text))
    prefix = text[span_start:span_end].lstrip("/:")
    if span_start <= 1 and text.lstrip().startswith(("/", ":")):
        prefix = text.strip().lstrip("/:").split(" ", 1)[0]

    scored: list[CommandSuggestion] = []
    seen: set[str] = set()
    for spec in catalog.all():
        for candidate in (spec.name, *spec.aliases):
            score = _score(prefix, candidate)
            if score <= 0 or candidate in seen:
                continue
            seen.add(candidate)
            scored.append(
                CommandSuggestion(
                    label=f"/{candidate}",
                    value=candidate,
                    kind="command",
                    description=spec.description,
                    score=score,
                    insert_text=f"/{candidate} ",
                    start=span_start,
                    end=span_end,
                    metadata={"spec": spec.name, "kind": spec.kind.value},
                )
            )

    if prefix:
        for item in saved:
            score = _score(prefix, item.name)
            if score <= 0:
                continue
            scored.append(
                CommandSuggestion(
                    label=item.name,
                    value=item.query,
                    kind="saved",
                    description=item.description or item.query,
                    score=score + (8.0 if item.pinned else 0.0),
                    insert_text=item.query,
                    start=span_start,
                    end=span_end,
                    metadata={"id": item.id, "query": item.query, "tags": list(item.tags)},
                )
            )

    scored.sort(key=lambda item: (-item.score, item.label.casefold()))
    return tuple(scored[: max(0, limit)])


def suggest_arguments(
    spec: CommandSpec,
    prefix: str,
    *,
    start: int = 0,
    end: int = 0,
) -> tuple[CommandSuggestion, ...]:
    """Rank choices declared by a command's argument grammar."""
    results: list[CommandSuggestion] = []
    for argument in spec.arguments:
        for choice in argument.choices:
            score = _score(prefix, choice)
            if score <= 0:
                continue
            results.append(
                CommandSuggestion(
                    label=choice,
                    value=choice,
                    kind="argument",
                    description=argument.description,
                    score=score,
                    insert_text=choice,
                    start=start,
                    end=end,
                    metadata={"argument": argument.name},
                )
            )
    results.sort(key=lambda item: (-item.score, item.label.casefold()))
    return tuple(results)


def complete_command(
    text: str,
    catalog: CommandCatalog,
    *,
    cursor: int | None = None,
    saved: Iterable[SavedQuery] = (),
    vocabulary: Iterable[str] = (),
    limit: int = 8,
) -> SuggestionResult:
    """Complete a command, argument, option, or search term at the cursor."""
    position = len(text) if cursor is None else max(0, min(cursor, len(text)))
    context = command_context(text, position)
    start, end = _completion_span(text, position)
    prefix = text[start:end]

    if context == "command":
        suggestions = suggest_commands(text[:end], catalog, saved=saved, limit=limit)
        return SuggestionResult(text, position, prefix, suggestions, context)

    parsed: ParsedCommand = catalog.parse(text[:position])
    node = parsed.node
    spec = catalog.get(node.name) if node is not None else None
    if context == "option":
        options = ("limit", "sort", "group", "target", "force")
        suggestions = tuple(
            CommandSuggestion(
                label=f"--{option}",
                value=option,
                kind="option",
                score=_score(prefix.lstrip("-"), option),
                insert_text=f"--{option}=",
                start=start,
                end=end,
            )
            for option in options
            if _score(prefix.lstrip("-"), option) > 0
        )
        suggestions = tuple(sorted(suggestions, key=lambda item: (-item.score, item.label)))
        return SuggestionResult(text, position, prefix, suggestions[:limit], context)

    if spec is not None and spec.arguments:
        suggestions = suggest_arguments(spec, prefix, start=start, end=end)
        if suggestions:
            return SuggestionResult(text, position, prefix, suggestions[:limit], context)

    if vocabulary:
        candidates = sorted(
            (
                CommandSuggestion(
                    label=term,
                    value=term,
                    kind="term",
                    score=_score(prefix, term),
                    insert_text=term,
                    start=start,
                    end=end,
                )
                for term in vocabulary
                if _score(prefix, term) > 0
            ),
            key=lambda item: (-item.score, item.label),
        )
        return SuggestionResult(text, position, prefix, tuple(candidates[:limit]), context)

    if spec is not None and context == "argument":
        suggestions = tuple(
            CommandSuggestion(
                label=example,
                value=example,
                kind="example",
                description=spec.description,
                score=_score(prefix, example),
                insert_text=example,
                start=start,
                end=end,
            )
            for example in spec.examples
            if _score(prefix, example) > 0
        )
        return SuggestionResult(text, position, prefix, suggestions[:limit], context)

    return SuggestionResult(text, position, prefix, (), context)


def rank_suggestions(
    suggestions: Sequence[CommandSuggestion],
    *,
    preferred_kinds: Sequence[str] = (),
) -> tuple[CommandSuggestion, ...]:
    """Re-rank suggestions, preferring selected kinds on score ties."""
    preferences = {kind: index for index, kind in enumerate(preferred_kinds)}
    return tuple(
        sorted(
            suggestions,
            key=lambda item: (
                -item.score,
                preferences.get(item.kind, len(preferences)),
                item.label.casefold(),
            ),
        )
    )


def suggestion_labels(suggestions: Iterable[CommandSuggestion]) -> tuple[str, ...]:
    """Return display labels for a suggestion list."""
    return tuple(item.label for item in suggestions)


def apply_suggestion(text: str, suggestion: CommandSuggestion) -> str:
    """Replace the suggestion's completion span in a command line."""
    if suggestion.start < 0 or suggestion.end < suggestion.start:
        return text
    return f"{text[: suggestion.start]}{suggestion.insert_text}{text[suggestion.end :]}"


def prefix_matches(catalog: CommandCatalog, prefix: str) -> tuple[str, ...]:
    """Return command names and aliases matching a prefix."""
    return tuple(
        name for spec in commands_by_prefix(catalog, prefix) for name in (spec.name, *spec.aliases)
    )
