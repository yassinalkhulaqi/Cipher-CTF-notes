"""Snippet libraries, search, and safe command composition."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from redscribe.content.snippets import BUILTIN_SNIPPETS
from redscribe.v2.playbooks.errors import DuplicateKeyError, UnknownSnippetError
from redscribe.v2.playbooks.interpolate import (
    RenderResult,
    render,
    variables_in,
)
from redscribe.v2.playbooks.types import Issue, SnippetRecord, Values
from redscribe.v2.playbooks.validation import ensure_valid, validate_snippet

_SNIPPET_REF = re.compile(r"\{\{\s*snippet:([a-z0-9_-]+)\s*\}\}", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SnippetComposeResult:
    """The result of composing and interpolating one or more snippets."""

    command: str
    order: tuple[str, ...]
    cycles: tuple[tuple[str, ...], ...]
    missing: tuple[str, ...]
    result: RenderResult | None = None

    @property
    def ok(self) -> bool:
        return not self.cycles and not self.missing and (self.result is None or self.result.ok)

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "order": list(self.order),
            "cycles": [list(cycle) for cycle in self.cycles],
            "missing": list(self.missing),
            "warnings": [issue.as_dict() for issue in (self.result.issues if self.result else ())],
            "ok": self.ok,
        }


def snippet_variables(command: str) -> tuple[str, ...]:
    """Return variable names used by a snippet command."""
    return variables_in(_SNIPPET_REF.sub(" ", command))


def snippet_refs(command: str) -> tuple[str, ...]:
    """Return keys referenced through ``{{snippet:key}}``."""
    return tuple(dict.fromkeys(match.group(1).lower() for match in _SNIPPET_REF.finditer(command)))


def builtin_snippets() -> tuple[SnippetRecord, ...]:
    """Convert the established v1 snippet catalog into v2 records."""
    records: list[SnippetRecord] = []
    for index, snippet in enumerate(BUILTIN_SNIPPETS, start=1):
        records.append(
            SnippetRecord(
                id=index,
                key=snippet.builtin_key,
                title=snippet.title,
                command=snippet.command,
                description=snippet.description,
                tags=tuple(tag.strip() for tag in snippet.tags.split(",") if tag.strip()),
                library="builtin",
                variables=snippet_variables(snippet.command),
                version="1.0.0",
            )
        )
    return tuple(records)


class SnippetLibrary:
    """An in-memory library with deterministic CRUD and search."""

    def __init__(self, name: str = "personal") -> None:
        self.name = name
        self._records: dict[str, SnippetRecord] = {}

    @property
    def records(self) -> tuple[SnippetRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def __len__(self) -> int:
        return len(self._records)

    def get(self, key: str) -> SnippetRecord:
        """Return one snippet or raise."""
        record = self._records.get(key.strip().casefold())
        if record is None:
            raise UnknownSnippetError(f"Snippet not found: {key}", details={"key": key})
        return record

    def find(self, key: str) -> SnippetRecord | None:
        """Return one snippet or ``None``."""
        return self._records.get(key.strip().casefold())

    def add(self, record: SnippetRecord, *, validate: bool = True) -> SnippetRecord:
        """Insert a snippet into the library."""
        key = record.key.strip().casefold()
        if key in self._records:
            raise DuplicateKeyError(f"Snippet already exists: {key}", details={"key": key})
        stored = record.with_changes(
            key=key,
            variables=record.variables or snippet_variables(record.command),
            library=record.library or self.name,
        )
        if validate:
            ensure_valid(validate_snippet(stored), "Snippet validation failed")
        self._records[key] = stored
        return stored

    def update(self, key: str, **changes: Any) -> SnippetRecord:
        """Update selected fields of one snippet."""
        current = self.get(key)
        updated = current.with_changes(**changes)
        if "key" in changes:
            updated = updated.with_changes(key=str(changes["key"]).strip().casefold())
            if updated.key != current.key and updated.key in self._records:
                raise DuplicateKeyError(f"Snippet already exists: {updated.key}")
            self._records.pop(current.key, None)
        updated = updated.with_changes(variables=snippet_variables(updated.command))
        ensure_valid(validate_snippet(updated), "Snippet validation failed")
        self._records[updated.key] = updated
        return updated

    def remove(self, key: str) -> SnippetRecord:
        """Remove a snippet from the library."""
        record = self.get(key)
        del self._records[record.key]
        return record

    def record_usage(self, key: str) -> SnippetRecord:
        """Increment the usage counter for a snippet."""
        record = self.get(key)
        updated = record.with_changes(usage_count=record.usage_count + 1)
        self._records[record.key] = updated
        return updated

    def replace_all(self, records: list[SnippetRecord], *, validate: bool = True) -> None:
        """Replace the library contents atomically."""
        staged: dict[str, SnippetRecord] = {}
        for record in records:
            key = record.key.strip().casefold()
            if key in staged:
                raise DuplicateKeyError(f"Duplicate snippet key: {key}")
            normalized = record.with_changes(
                key=key, variables=record.variables or snippet_variables(record.command)
            )
            if validate:
                ensure_valid(validate_snippet(normalized), "Snippet validation failed")
            staged[key] = normalized
        self._records = staged

    def search(
        self,
        query: str = "",
        *,
        tags: tuple[str, ...] = (),
        library: str = "",
        limit: int = 50,
    ) -> list[SnippetRecord]:
        """Rank snippets by text and tag overlap."""
        needle = query.strip().casefold()
        wanted = {tag.strip().casefold() for tag in tags if tag.strip()}
        results: list[tuple[int, SnippetRecord]] = []
        for record in self.records:
            if library and record.library.casefold() != library.casefold():
                continue
            record_tags = {tag.casefold() for tag in record.tags}
            if wanted and not wanted.intersection(record_tags):
                continue
            haystack = (
                f"{record.title} {record.description} {record.command} {' '.join(record.tags)}"
            )
            score = 0
            if needle:
                if record.title.casefold().startswith(needle):
                    score += 6
                if needle in record.title.casefold():
                    score += 4
                if needle in haystack.casefold():
                    score += 2
            if wanted:
                score += 2 * len(wanted.intersection(record_tags))
            score += min(record.usage_count, 10) // 5
            if (needle or wanted or library) and score == 0:
                continue
            results.append((score, record))
        results.sort(key=lambda item: (-item[0], item[1].key))
        return [record for _, record in results[:limit]]

    def variables(self, key: str) -> tuple[str, ...]:
        """Return variables used by one snippet."""
        return self.get(key).variables

    def stats(self) -> dict[str, Any]:
        """Return library statistics."""
        libraries: dict[str, int] = {}
        usages = 0
        for record in self.records:
            libraries[record.library] = libraries.get(record.library, 0) + 1
            usages += record.usage_count
        return {
            "total": len(self.records),
            "libraries": dict(sorted(libraries.items())),
            "usage_count": usages,
            "variables": sorted({name for record in self.records for name in record.variables}),
        }

    def as_dict(self, *, include_commands: bool = True) -> list[dict[str, Any]]:
        """Serialize all snippets."""
        return [
            record.as_dict() if include_commands else _without_command(record)
            for record in self.records
        ]

    def to_records(self) -> tuple[SnippetRecord, ...]:
        """Return all snippets for persistence."""
        return self.records

    @classmethod
    def from_records(
        cls, records: list[SnippetRecord], *, name: str = "personal"
    ) -> SnippetLibrary:
        """Build a library from persisted records."""
        library = cls(name)
        library.replace_all(records, validate=False)
        return library


def _without_command(record: SnippetRecord) -> dict[str, Any]:
    data = record.as_dict()
    data.pop("command", None)
    return data


def compose_snippets(
    records: list[SnippetRecord] | tuple[SnippetRecord, ...],
    values: Values | None = None,
    *,
    max_depth: int = 8,
) -> SnippetComposeResult:
    """Expand snippet references and interpolate variables without executing."""
    catalog = {record.key: record for record in records}
    order: list[str] = []
    cycles: list[tuple[str, ...]] = []
    missing: list[str] = []
    memo: dict[str, str] = {}

    def expand(key: str, active: tuple[str, ...]) -> str:
        if key in memo:
            return memo[key]
        record = catalog.get(key)
        if record is None:
            if key not in missing:
                missing.append(key)
            return ""
        if key in active:
            cycle = (*active[active.index(key) :], key)
            if cycle not in cycles:
                cycles.append(cycle)
            return ""
        if len(active) >= max_depth:
            return ""
        order.append(key)

        def replace(match: re.Match[str]) -> str:
            reference = match.group(1).casefold()
            return expand(reference, (*active, key))

        text = _SNIPPET_REF.sub(replace, record.command)
        memo[key] = text
        return text

    roots = [
        record.key
        for record in records
        if not any(record.key in snippet_refs(item.command) for item in records)
    ]
    expanded = "\n".join(expand(key, ()) for key in (roots or list(catalog)))
    rendered = render(expanded, values)
    issues: list[Issue] = []
    if cycles:
        issues.append(Issue("cyclic-snippet", "Snippet references contain a cycle"))
    return SnippetComposeResult(
        command=rendered.text,
        order=tuple(dict.fromkeys(order)),
        cycles=tuple(cycles),
        missing=tuple(missing),
        result=rendered,
    )
