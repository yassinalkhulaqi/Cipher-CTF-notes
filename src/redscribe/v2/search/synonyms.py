"""Synonym groups and query expansion for the v2 search engine."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from redscribe.v2.search.tokenizer import normalize_token, stem

DEFAULT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("ctf", "capturetheflag", "challenge", "challenges"),
    ("flag", "flags", "answer", "answers"),
    ("port", "ports", "openport", "openports"),
    ("scan", "scanner", "scanning", "nmap", "rustscan"),
    ("recon", "reconnaissance", "discovery", "enumeration"),
    ("host", "hosts", "target", "targets", "machine", "ip"),
    ("domain", "domains", "dns", "hostname", "hostnames"),
    ("web", "website", "http", "https"),
    ("vulnerability", "vulnerabilities", "vuln", "vulns"),
    ("exploit", "exploits", "payload", "poc"),
    ("password", "passwords", "credential", "credentials", "creds"),
    ("user", "users", "username", "usernames"),
    ("note", "notes", "notebook", "entry", "entries"),
    ("tag", "tags", "label", "labels"),
    ("filter", "filters", "query", "search"),
    ("subdomain", "subdomains", "subs"),
    ("directory", "directories", "folder", "folders", "dir"),
    ("evidence", "proof", "screenshot", "screenshots"),
    ("login", "signin", "authentication", "auth"),
    ("token", "tokens", "jwt", "session"),
)


class SynonymSet:
    """A transitive, case-insensitive set of synonym groups."""

    def __init__(self, groups: Iterable[Sequence[str]] = DEFAULT_GROUPS) -> None:
        cleaned: list[tuple[str, ...]] = []
        for group in groups:
            values = tuple(value for value in (self._clean(item) for item in group) if value)
            if len(values) > 1:
                cleaned.append(values)
        parent: dict[str, str] = {member: member for group in cleaned for member in group}

        def find(value: str) -> str:
            root = value
            while parent[root] != root:
                root = parent[root]
            while parent[value] != root:
                parent[value], value = root, parent[value]
            return root

        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[max(left_root, right_root)] = min(left_root, right_root)

        for group in cleaned:
            for member in group[1:]:
                union(group[0], member)
        components: dict[str, list[str]] = {}
        for member in parent:
            components.setdefault(find(member), []).append(member)
        self._groups = tuple(
            tuple(sorted(values)) for values in components.values() if len(values) > 1
        )
        self._canonical = {member: group[0] for group in self._groups for member in group}
        self._components = {member: group for group in self._groups for member in group}

    @staticmethod
    def _clean(value: str) -> str:
        return stem(normalize_token(str(value)))

    @classmethod
    def empty(cls) -> SynonymSet:
        """Return a synonym set with no expansion rules."""
        return cls(())

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Sequence[str]]) -> SynonymSet:
        """Build a set from canonical term to synonym list mappings."""
        groups = [
            [str(canonical), *(str(value) for value in values)]
            for canonical, values in mapping.items()
        ]
        return cls(groups)

    @property
    def groups(self) -> tuple[tuple[str, ...], ...]:
        return self._groups

    @property
    def size(self) -> int:
        return len(self._canonical)

    def canonical(self, term: str) -> str:
        """Return the canonical spelling for a term."""
        key = self._clean(term)
        return self._canonical.get(key, key)

    def expand(self, term: str, *, include_self: bool = True) -> tuple[str, ...]:
        """Return all synonyms in the same connected component as ``term``."""
        key = self._clean(term)
        if not key:
            return ()
        component = self._components.get(key, (key,))
        if include_self:
            return component
        return tuple(value for value in component if value != key)

    def expand_terms(
        self,
        terms: Iterable[str],
        *,
        include_self: bool = False,
    ) -> tuple[str, ...]:
        """Expand many terms while preserving first-seen order."""
        results: list[str] = []
        seen: set[str] = set()
        for term in terms:
            for value in self.expand(term, include_self=include_self):
                if value not in seen:
                    seen.add(value)
                    results.append(value)
        return tuple(results)

    def related(self, left: str, right: str) -> bool:
        """Return whether two terms share a synonym component."""
        first = self._clean(left)
        second = self._clean(right)
        return bool(first and first == second) or second in self.expand(first)

    def as_dict(self) -> dict[str, object]:
        return {"groups": [list(group) for group in self._groups], "terms": self.size}


def merge_synonyms(*sets: SynonymSet) -> SynonymSet:
    """Combine multiple synonym sets into one transitive set."""
    groups: list[tuple[str, ...]] = []
    for item in sets:
        groups.extend(item.groups)
    return SynonymSet(groups)
