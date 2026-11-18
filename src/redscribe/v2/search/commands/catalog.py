"""Built-in command catalog and registry operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from redscribe.v2.search.commands.grammar import parse_command, validate_arguments
from redscribe.v2.search.commands.models import (
    ArgumentSpec,
    CommandKind,
    CommandNode,
    CommandPlan,
    CommandSpec,
    ParsedCommand,
    ParseIssue,
)

_STATUS_CHOICES = ("todo", "active", "done", "blocked")
_SORT_CHOICES = ("relevance", "updated", "title", "id")


def _spec(
    name: str,
    kind: CommandKind,
    description: str,
    usage: str,
    *,
    aliases: Sequence[str] = (),
    arguments: Sequence[ArgumentSpec] = (),
    examples: Sequence[str] = (),
    min_args: int = 0,
    max_args: int | None = None,
) -> CommandSpec:
    return CommandSpec(
        name=name,
        kind=kind,
        description=description,
        usage=usage,
        aliases=tuple(aliases),
        arguments=tuple(arguments),
        examples=tuple(examples),
        min_args=min_args,
        max_args=max_args,
    )


DEFAULT_COMMANDS: tuple[CommandSpec, ...] = (
    _spec(
        "search",
        CommandKind.SEARCH,
        "Search note titles, content, tags, and targets.",
        "/search <terms> [--limit=20] [--sort=relevance]",
        aliases=("find", "query", "?"),
        min_args=1,
        examples=("/search flag --limit=20", "/find 'sql injection'"),
    ),
    _spec(
        "tag",
        CommandKind.FILTER,
        "Restrict results to one or more tags.",
        "/tag <name> [name...]",
        aliases=("tags",),
        min_args=1,
        examples=("/tag web recon", "/tag:web"),
    ),
    _spec(
        "status",
        CommandKind.FILTER,
        "Restrict results to notes in a given status.",
        "/status <todo|active|done|blocked>",
        arguments=(ArgumentSpec("status", True, choices=_STATUS_CHOICES),),
        min_args=1,
        max_args=1,
        examples=("/status active",),
    ),
    _spec(
        "saved",
        CommandKind.SAVED,
        "List, run, or manage saved queries.",
        "/saved <list|run|show|save> [name]",
        aliases=("queries",),
        arguments=(ArgumentSpec("action", choices=("list", "run", "show", "save")),),
        examples=("/saved list", "/saved run weekly"),
    ),
    _spec(
        "sort",
        CommandKind.FILTER,
        "Change the ordering of the current result set.",
        "/sort <relevance|updated|title|id>",
        arguments=(ArgumentSpec("sort", True, choices=_SORT_CHOICES),),
        min_args=1,
        max_args=1,
    ),
    _spec(
        "group",
        CommandKind.FILTER,
        "Group results by a metadata field.",
        "/group <status|kind|tag|path|target>",
        min_args=1,
        max_args=1,
    ),
    _spec(
        "goto",
        CommandKind.NAVIGATION,
        "Open a note by id or fuzzy title.",
        "/goto <id|title>",
        aliases=("open",),
        min_args=1,
        max_args=2,
    ),
    _spec(
        "recent",
        CommandKind.NAVIGATION,
        "Show the most recently updated notes.",
        "/recent [--limit=10]",
        max_args=1,
    ),
    _spec(
        "snippet",
        CommandKind.SEARCH,
        "Find command snippets by name or tag.",
        "/snippet <terms>",
        aliases=("cmd",),
        min_args=1,
    ),
    _spec(
        "reindex",
        CommandKind.ACTION,
        "Rebuild the incremental search index from the vault.",
        "/reindex [--force]",
        max_args=0,
    ),
    _spec(
        "clear",
        CommandKind.ACTION,
        "Clear the active query, filters, and grouping.",
        "/clear",
        max_args=0,
    ),
    _spec(
        "help",
        CommandKind.HELP,
        "Show available commands or help for one command.",
        "/help [command]",
        aliases=("?",),
        max_args=1,
    ),
)


class CommandCatalog:
    """Registry that resolves command names and aliases."""

    def __init__(self, specs: Iterable[CommandSpec] = DEFAULT_COMMANDS) -> None:
        self._specs: dict[str, CommandSpec] = {}
        self._aliases: dict[str, str] = {}
        for spec in specs:
            self.register(spec)

    @classmethod
    def default(cls) -> CommandCatalog:
        return cls(DEFAULT_COMMANDS)

    def register(self, spec: CommandSpec) -> None:
        self._specs[spec.name.casefold()] = spec
        for alias in spec.aliases:
            self._aliases[alias.casefold()] = spec.name.casefold()

    def unregister(self, name: str) -> bool:
        key = name.casefold()
        spec = self._specs.pop(key, None)
        if spec is None:
            return False
        for alias in spec.aliases:
            self._aliases.pop(alias.casefold(), None)
        return True

    def all(self) -> tuple[CommandSpec, ...]:
        return tuple(self._specs[name] for name in sorted(self._specs))

    def get(self, name: str) -> CommandSpec | None:
        key = name.casefold()
        resolved = self._aliases.get(key, key)
        return self._specs.get(resolved)

    def names(self) -> tuple[str, ...]:
        result: list[str] = []
        for name, spec in self._specs.items():
            result.extend([name, *spec.aliases])
        return tuple(sorted(set(result)))

    def by_kind(self, kind: CommandKind) -> tuple[CommandSpec, ...]:
        return tuple(spec for spec in self.all() if spec.kind == kind)

    def parse(self, text: str) -> ParsedCommand:
        """Parse input and attach validation issues from the matching spec."""
        preliminary = parse_command(text, known_names=self.names())
        node = preliminary.node
        if node is None:
            return preliminary
        spec = self.get(node.name)
        if spec is None:
            return preliminary
        issues = [*preliminary.issues, *validate_arguments(node, spec)]
        return ParsedCommand(
            raw=preliminary.raw,
            node=node,
            issues=tuple(dict.fromkeys(issues)),
            tokens=preliminary.tokens,
        )

    def plan(self, node: CommandNode) -> CommandPlan:
        """Turn a parsed command into a side-effect-free plan."""
        spec = self.get(node.name)
        name = spec.name if spec is not None else node.name
        text = node.text
        options = dict(node.options)
        if name in {"search", "snippet"}:
            return CommandPlan(
                name=name,
                action="search",
                query=text,
                target=options.get("target", ""),
                message=f"Search for {text}" if text else "Enter search terms",
                metadata={
                    "limit": options.get("limit", "20"),
                    "sort": options.get("sort", "relevance"),
                },
            )
        if name in {"tag", "status", "sort", "group"}:
            return CommandPlan(
                name=name,
                action="filter",
                filters=(f"{name}:{text}",) if text else (),
                message=f"Apply {name} filter {text}".strip(),
            )
        if name == "saved":
            action = node.positional[0].value.casefold() if node.positional else "list"
            return CommandPlan(
                name=name,
                action=f"saved_{action}",
                query=node.positional[1].value if len(node.positional) > 1 else "",
                message=f"Saved queries: {action}",
            )
        if name == "goto":
            return CommandPlan(
                name=name,
                action="open",
                target=text,
                message=f"Open {text}" if text else "Choose a note",
            )
        if name == "recent":
            return CommandPlan(
                name=name,
                action="search",
                query="",
                message="Show recent notes",
                metadata={"sort": "updated", "limit": options.get("limit", "10")},
            )
        if name == "reindex":
            return CommandPlan(name=name, action="reindex", message="Rebuild the search index")
        if name == "clear":
            return CommandPlan(name=name, action="clear", message="Clear the search")
        return CommandPlan(
            name=name, action="help", target=text, message=f"Help for {text or name}"
        )

    def as_dict(self) -> list[dict[str, object]]:
        return [spec.as_dict() for spec in self.all()]


def command_issues_summary(issues: Sequence[ParseIssue]) -> str:
    """Join parse issues into a readable message."""
    return "; ".join(issue.message for issue in issues) if issues else "OK"


def commands_by_prefix(catalog: CommandCatalog, prefix: str) -> tuple[CommandSpec, ...]:
    """Return commands whose names or aliases begin with ``prefix``."""
    needle = prefix.strip().casefold().lstrip("/:")
    if not needle:
        return catalog.all()
    result: list[CommandSpec] = []
    for spec in catalog.all():
        candidates = [spec.name, *spec.aliases]
        if any(value.casefold().startswith(needle) for value in candidates):
            result.append(spec)
    return tuple(result)


def command_metadata(catalog: CommandCatalog) -> dict[str, object]:
    """Return introspection metadata for the whole catalog."""
    specs = catalog.all()
    aliases: dict[str, str] = {}
    for name in catalog.names():
        spec = catalog.get(name)
        if spec is not None:
            aliases[name] = spec.name
    return {
        "commands": [spec.as_dict() for spec in specs],
        "count": len(specs),
        "aliases": aliases,
        "kinds": sorted({spec.kind.value for spec in specs}),
    }


def merge_issue_lists(*groups: Iterable[ParseIssue]) -> tuple[ParseIssue, ...]:
    """Merge and deduplicate parse issue collections."""
    result: list[ParseIssue] = []
    for group in groups:
        for issue in group:
            if issue not in result:
                result.append(issue)
    return tuple(result)


def spec_from_mapping(payload: Mapping[str, object]) -> CommandSpec:
    """Build a command spec from an API-provided mapping."""
    name = str(payload.get("name", "")).strip().casefold()
    if not name:
        raise ValueError("Command name is required")
    raw_aliases = payload.get("aliases", ())
    if not isinstance(raw_aliases, (list, tuple)):
        raise ValueError("Command aliases must be a list")
    aliases = tuple(str(value) for value in raw_aliases)
    description = str(payload.get("description", ""))
    usage = str(payload.get("usage", ""))
    return _spec(name, CommandKind.ACTION, description, usage, aliases=aliases)
